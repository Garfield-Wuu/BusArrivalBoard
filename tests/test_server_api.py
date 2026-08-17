"""
服务端 API 单元测试

测试策略:
    - 不依赖真实网络：用 mock 的 FrameService 注入预设结果
    - 用 httpx.AsyncClient 直接测 ASGI app，不启动 uvicorn 服务器
    - 覆盖正常路径与异常分支（查询失败、ETag 缓存命中）
    - 评审发现：FakeFrameService 需加真实延迟才能测出单飞缺陷
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from typing import Optional

import pytest
from httpx import ASGITransport, AsyncClient

from bus_arrival_board.config import AppConfig, WatchTarget
from bus_arrival_board.server import ETAG_DIGEST_LENGTH, FrameCache, FrameService, create_app


@dataclass
class FakeFrameService:
    """测试用的假服务，返回固定画面

    加了可配置延迟以测试单飞逻辑——原版无延迟时并发测试只是验证了
    mock 自己的行为，真实的竞态条件被掩盖。
    """

    frame_data: bytes
    raise_on_render: Optional[Exception] = None
    call_count: int = 0
    render_delay_seconds: float = 0.0  # 模拟渲染耗时

    def _make_cache(self) -> FrameCache:
        return FrameCache(
            data=self.frame_data,
            etag=hashlib.sha256(self.frame_data).hexdigest()[:ETAG_DIGEST_LENGTH],
            rendered_at=time.monotonic(),
            width=400,
            height=300,
            bus_count=3,
        )

    async def get_frame(self, force: bool = False) -> FrameCache:
        self.call_count += 1
        if self.render_delay_seconds > 0:
            await asyncio.sleep(self.render_delay_seconds)
        if self.raise_on_render:
            raise self.raise_on_render
        return self._make_cache()

    def peek_cache(self) -> Optional[FrameCache]:
        """对齐 FrameService 接口"""
        if self.raise_on_render:
            return None
        return self._make_cache()


@pytest.fixture
def fake_service():
    """生成一个包含 15000 字节伪画面的假服务"""
    return FakeFrameService(frame_data=b"\x00" * 15000)


@pytest.fixture
async def client(fake_service):
    """测试客户端，使用假服务"""
    app = create_app(service=fake_service)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """健康检查端点应返回 200 及缓存状态"""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["has_cached_frame"] is True


@pytest.mark.asyncio
async def test_get_frame_success(client: AsyncClient):
    """正常获取帧：返回 15000 字节 + ETag"""
    resp = await client.get("/api/epd/frame.bin")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/octet-stream"
    assert len(resp.content) == 15000
    assert "ETag" in resp.headers
    assert "X-Frame-Width" in resp.headers
    assert resp.headers["X-Frame-Width"] == "400"


@pytest.mark.asyncio
async def test_etag_cache_hit(client: AsyncClient, fake_service: FakeFrameService):
    """第一次拿到带引号 ETag，第二次按规范带回应返回 304

    RFC 9110 §8.8.3: ETag 必须是 quoted-string，客户端存储后也会按
    带引号形式发回，裸值比对会让 304 永远无法命中。
    """
    # 首次请求拿 ETag
    resp1 = await client.get("/api/epd/frame.bin")
    assert resp1.status_code == 200
    etag_header = resp1.headers["ETag"]
    # 服务端必须发带引号形式
    assert etag_header.startswith('"') and etag_header.endswith('"')
    etag_bare = etag_header.strip('"')

    # 再次请求，按规范带引号发回（客户端实际行为）
    resp2 = await client.get("/api/epd/frame.bin", headers={"if-none-match": f'"{etag_bare}"'})
    assert resp2.status_code == 304
    assert resp2.headers["ETag"] == etag_header
    assert len(resp2.content) == 0  # 304 不带 body

    # 弱校验也应支持
    resp3 = await client.get("/api/epd/frame.bin", headers={"if-none-match": f'W/"{etag_bare}"'})
    assert resp3.status_code == 304

    # 多值场景
    resp4 = await client.get(
        "/api/epd/frame.bin", headers={"if-none-match": f'"other", "{etag_bare}"'}
    )
    assert resp4.status_code == 304

    # 通配 * 也应命中
    resp5 = await client.get("/api/epd/frame.bin", headers={"if-none-match": "*"})
    assert resp5.status_code == 304


@pytest.mark.asyncio
async def test_metadata_endpoint(client: AsyncClient):
    """元信息端点应返回帧的详细信息，含降级状态"""
    resp = await client.get("/api/epd/metadata")
    assert resp.status_code == 200
    data = resp.json()
    assert data["width"] == 400
    assert data["height"] == 300
    assert data["size_bytes"] == 15000
    assert data["bus_count"] == 3
    assert "etag" in data
    assert data["etag"].startswith('"') and data["etag"].endswith('"')  # 带引号
    assert "age_seconds" in data
    # 降级状态字段
    assert "is_stale" in data
    assert data["is_stale"] is False  # FakeFrameService 不降级
    assert data["last_error"] is None


@pytest.mark.asyncio
async def test_frame_unavailable():
    """查询失败时应返回 503 并带错误信息"""
    failing_service = FakeFrameService(
        frame_data=b"",
        raise_on_render=RuntimeError("上游 API 超时"),
    )
    app = create_app(service=failing_service)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/epd/frame.bin")
        assert resp.status_code == 503
        data = resp.json()
        assert data["error"] == "frame_unavailable"
        # 内部细节不得外泄，只给固定文案 + 关联 ID
        assert "detail" not in data
        assert data["message"] == "画面暂时不可用，请稍后重试"
        assert len(data["error_id"]) == 8


@pytest.mark.asyncio
async def test_error_does_not_leak_internal_paths():
    """503 响应不得泄漏文件路径、上游 URL 等内部信息

    原实现直接回显 str(exc)，而异常来自 load_config（含绝对路径）、
    resolve_targets（含上游 URL 与线路 ID）、Pillow（含字体路径）。
    """
    leaky = FakeFrameService(
        frame_data=b"",
        raise_on_render=RuntimeError(
            "/home/garfieldwu/secret/config.yaml 打开失败 http://api.internal"
        ),
    )
    app = create_app(service=leaky)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/epd/frame.bin")
        body = resp.text
        assert resp.status_code == 503
        assert "/home/garfieldwu" not in body
        assert "secret" not in body
        assert "api.internal" not in body


@pytest.mark.asyncio
async def test_metadata_unavailable():
    """元信息查询失败时也应返回 503"""
    failing_service = FakeFrameService(
        frame_data=b"",
        raise_on_render=RuntimeError("无数据"),
    )
    app = create_app(service=failing_service)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/epd/metadata")
        assert resp.status_code == 503


@pytest.mark.asyncio
async def test_single_flight_true_concurrency():
    """并发请求应共享同一次渲染（真单飞），而非串行化成 N 次

    用真实 FrameService + mock 渲染器才能测出单飞逻辑。
    并发 5 个请求，渲染耗时 0.3s：
    - 真单飞：耗时 ~0.3s，渲染 1 次
    - 假单飞（互斥锁排队）：耗时 ~1.5s，渲染 5 次

    原实现是假单飞，min_refresh_seconds=0 时并发会放大成 N 倍上游查询。
    """
    config = AppConfig(
        targets=[WatchTarget(city="深圳", line="M592", station="安翼嘉寓")],
    )
    svc = FrameService(config, min_refresh_seconds=0)

    # Mock 渲染逻辑：加延迟 + 计数
    original_render = svc._render_blocking
    render_count = {"n": 0}

    def mock_render_with_delay() -> FrameCache:
        render_count["n"] += 1
        time.sleep(0.3)  # 同步阻塞 0.3 秒
        return FrameCache(
            data=b"\x00" * 15000,
            etag="mock12345678abcd",
            rendered_at=time.monotonic(),
            width=400,
            height=300,
            bus_count=3,
        )

    svc._render_blocking = mock_render_with_delay  # type: ignore[method-assign]

    app = create_app(service=svc)
    transport = ASGITransport(app=app)

    start = time.monotonic()
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        tasks = [c.get("/api/epd/frame.bin") for _ in range(5)]
        responses = await asyncio.gather(*tasks)
    elapsed = time.monotonic() - start

    # 都应成功
    assert all(r.status_code == 200 for r in responses)
    # ETag 应该一致（同一帧）
    etags = [r.headers["ETag"] for r in responses]
    assert len(set(etags)) == 1

    # 真单飞：只渲染 1 次，耗时接近单次延迟
    assert render_count["n"] == 1, f"期望 1 次渲染，实际 {render_count['n']}"
    assert elapsed < 0.6, f"期望 ~0.3s，实际 {elapsed:.2f}s（可能是假单飞排队）"


class TestParseIfNoneMatch:
    """ETag 头解析的单元测试（RFC 9110 §13.1.2）"""

    def test_quoted_single(self):
        from bus_arrival_board.server import _parse_if_none_match

        assert _parse_if_none_match('"abc123"') == {"abc123"}

    def test_weak_validator(self):
        from bus_arrival_board.server import _parse_if_none_match

        assert _parse_if_none_match('W/"abc123"') == {"abc123"}

    def test_multiple_values(self):
        from bus_arrival_board.server import _parse_if_none_match

        assert _parse_if_none_match('"abc", "def"') == {"abc", "def"}

    def test_mixed_weak_and_strong(self):
        from bus_arrival_board.server import _parse_if_none_match

        assert _parse_if_none_match('W/"abc", "def"') == {"abc", "def"}

    def test_wildcard(self):
        from bus_arrival_board.server import _parse_if_none_match

        assert _parse_if_none_match("*") == {"*"}

    def test_empty(self):
        from bus_arrival_board.server import _parse_if_none_match

        assert _parse_if_none_match("") == set()

    def test_bare_value_still_accepted(self):
        """非规范的裸值也接受，兼容简陋客户端"""
        from bus_arrival_board.server import _parse_if_none_match

        assert _parse_if_none_match("abc123") == {"abc123"}


class TestStaleFallback:
    """陈旧回退上限测试（问题 3 回归防护）"""

    @pytest.mark.asyncio
    async def test_stale_cache_rejected_after_limit(self):
        """缓存超过 max_stale_seconds 后应拒绝返回，而非无限期给旧画面

        对公交看板，显示错误时刻表比显示"数据不可用"危害更大——
        乘客会照着错的时间出门。
        """
        from bus_arrival_board.server import FrameCache

        config = AppConfig(
            targets=[WatchTarget(city="深圳", line="M592", station="安翼嘉寓")],
        )
        svc = FrameService(config, min_refresh_seconds=0, max_stale_seconds=1)

        # 手工塞一个"很久以前"的缓存
        svc._cache = FrameCache(
            data=b"\x00" * 15000,
            etag="oldframe12345678",
            rendered_at=time.monotonic() - 100,  # 100 秒前
            width=400,
            height=300,
            bus_count=2,
        )
        svc._targets_resolved = True

        # 让渲染永久失败
        def always_fail():
            raise RuntimeError("上游持续 500")

        svc._render_blocking = always_fail  # type: ignore[method-assign]

        # 缓存已过期 100 秒 > max_stale_seconds=1，应抛错
        with pytest.raises(RuntimeError, match="拒绝返回过期画面"):
            await svc.get_frame()

    @pytest.mark.asyncio
    async def test_fresh_stale_cache_still_served_with_flag(self):
        """未超陈旧上限时仍回退旧帧，但要标记 is_stale"""
        from bus_arrival_board.server import FrameCache

        config = AppConfig(
            targets=[WatchTarget(city="深圳", line="M592", station="安翼嘉寓")],
        )
        svc = FrameService(config, min_refresh_seconds=0, max_stale_seconds=600)

        svc._cache = FrameCache(
            data=b"\x00" * 15000,
            etag="recentframe12345",
            rendered_at=time.monotonic() - 10,  # 仅 10 秒前
            width=400,
            height=300,
            bus_count=2,
        )
        svc._targets_resolved = True

        def always_fail():
            raise RuntimeError("上游偶发超时")

        svc._render_blocking = always_fail  # type: ignore[method-assign]

        frame = await svc.get_frame()
        assert frame.is_stale is True
        assert frame.last_error is not None
        assert "上游偶发超时" in frame.last_error


@pytest.mark.asyncio
@pytest.mark.network
async def test_real_rendering_integration():
    """集成测试：用真实配置渲染一次画面

    标记为 network，CI 默认跳过，本地开发可手动验证。
    """
    from bus_arrival_board.config import load_config

    try:
        config = load_config("config/shenzhen_m592.yaml")
    except FileNotFoundError:
        pytest.skip("无可用配置文件")

    svc = FrameService(config, width=400, height=300, min_refresh_seconds=0)
    frame = await svc.get_frame(force=True)

    assert len(frame.data) == 15000  # 400×300/8
    assert len(frame.etag) == 16
    assert frame.width == 400
    assert frame.height == 300
    assert frame.bus_count > 0
