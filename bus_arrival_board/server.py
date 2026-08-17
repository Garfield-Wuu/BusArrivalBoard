"""
HTTP 帧服务端

向联网显示设备（ESP32 等）提供预渲染好的墨水屏画面。设备只需下载
二进制帧并刷屏，中文排版、抖动、布局全部在服务端完成——这样调整
显示样式不必重新刷固件。

设计要点:
    - **ETag 缓存**: 画面未变化时返回 304，设备跳过刷屏以省电并避免残影。
    - **不阻塞事件循环**: 查询和渲染都是同步阻塞操作，通过线程池执行。
    - **单飞（single-flight）**: 并发请求共享同一次渲染结果，避免把上游 API 打爆。
    - **最小刷新间隔**: 限制真实上游查询频率，与设备轮询间隔解耦。

启动（默认只监听本机，安全）:
    uvicorn bus_arrival_board.server:app --port 8000

指定配置:
    BUS_CONFIG=config/shenzhen_m592.yaml uvicorn bus_arrival_board.server:app

让局域网内的 ESP32 能访问（家庭网络内可接受）:
    uvicorn bus_arrival_board.server:app --host 0.0.0.0 --port 8000

.. warning::
    **暴露到公网前必须启用认证。** 每个未命中缓存的请求都可能触发一次
    上游查询，无认证的公网服务会被用来打爆车来了 API 配额，导致来源 IP
    被限流。设置环境变量 ``BUS_API_TOKEN=<随机串>`` 启用 token 校验，
    设备侧在请求头带 ``X-Device-Token``。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from fastapi import FastAPI, Request, Response
    from fastapi.responses import JSONResponse
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "服务端功能需要额外依赖，请安装:\n" "    pip install bus-arrival-board[server]"
    ) from exc

from bus_arrival_board.config import AppConfig, load_config
from bus_arrival_board.monitor import BusMonitor

# 默认画面尺寸：4.2 寸墨水屏
DEFAULT_WIDTH = 400
DEFAULT_HEIGHT = 300

# 上游最小查询间隔（秒）。设备可以比这更频繁地轮询，
# 但真实查询不会超过这个频率。
DEFAULT_MIN_REFRESH_SECONDS = 55

# 缓存陈旧上限（秒）。渲染失败时允许回退到旧帧，但不能无限期返回
# 过期数据——对公交看板，显示错误时刻表比显示"数据不可用"危害更大。
DEFAULT_MAX_STALE_SECONDS = 600  # 10 分钟

# ETag 摘要长度（SHA256 前 N 个字符）
ETAG_DIGEST_LENGTH = 16


def _parse_if_none_match(header_value: str) -> set[str]:
    """解析 If-None-Match 头，返回规范化的 ETag 集合

    RFC 9110 §13.1.2: 支持 W/"etag", "etag", "a", "b", *
    返回的集合元素不含引号和 W/ 前缀，供精确比对。
    "*" 单独返回 {"*"}。

    Args:
        header_value: If-None-Match 头的原始值

    Returns:
        set[str]: 规范化后的 ETag 集合（已去引号和弱校验前缀）

    Examples:
        >>> _parse_if_none_match('"abc123"')
        {'abc123'}
        >>> _parse_if_none_match('W/"abc", "def"')
        {'abc', 'def'}
        >>> _parse_if_none_match('*')
        {'*'}
    """
    if not header_value:
        return set()

    value = header_value.strip()
    if value == "*":
        return {"*"}

    tags = set()
    # 简化版：按逗号切分，剥离 W/ 和引号
    for part in value.split(","):
        part = part.strip()
        if part.startswith("W/"):
            part = part[2:].strip()
        # 去掉引号
        if part.startswith('"') and part.endswith('"'):
            part = part[1:-1]
        if part:
            tags.add(part)
    return tags


@dataclass
class FrameCache:
    """渲染结果缓存

    Attributes:
        data: 单色位图原始字节。
        etag: 内容哈希，用于 HTTP 条件请求。
        rendered_at: 渲染完成时的单调时钟读数。
        width: 画面宽度。
        height: 画面高度。
        bus_count: 本帧包含的车辆数，仅用于元信息展示。
        is_stale: 本帧是渲染失败后的回退结果（数据可能已过期）。
        last_error: 最近一次渲染失败的简要原因，仅用于日志与元信息。
    """

    data: bytes
    etag: str
    rendered_at: float
    width: int
    height: int
    bus_count: int
    is_stale: bool = False
    last_error: Optional[str] = None

    def age_seconds(self) -> float:
        """返回本帧已缓存多久（秒）"""
        return time.monotonic() - self.rendered_at

    def http_etag(self) -> str:
        """返回符合 RFC 9110 的带引号 ETag

        裸 hex 值不合规，规范 HTTP 客户端（含 ESP-IDF esp_http_client、
        CDN、反向代理）会把它存成带引号形式再发回，导致条件请求永远
        无法命中 304。
        """
        return f'"{self.etag}"'


class FrameService:
    """负责查询、渲染与缓存墨水屏画面

    把状态收在一个对象里而不是散落成模块级全局变量，测试时可以
    直接构造独立实例，不必操心相互污染。
    """

    def __init__(
        self,
        config: AppConfig,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        min_refresh_seconds: int = DEFAULT_MIN_REFRESH_SECONDS,
        max_stale_seconds: int = DEFAULT_MAX_STALE_SECONDS,
    ):
        """初始化服务

        Args:
            config: 应用配置，提供监控目标。
            width: 画面宽度，需与设备屏幕匹配。
            height: 画面高度。
            min_refresh_seconds: 两次真实上游查询之间的最小间隔。
            max_stale_seconds: 渲染失败时允许回退的最大帧龄，超限则报错。
        """
        self.config = config
        self.width = width
        self.height = height
        self.min_refresh_seconds = min_refresh_seconds
        self.max_stale_seconds = max_stale_seconds

        self._monitor = BusMonitor(config)
        self._targets_resolved = False
        self._cache: Optional[FrameCache] = None
        # 保护缓存与 in-flight task 的检查/创建，不覆盖 await 本身
        self._lock = asyncio.Lock()
        # 真正的单飞：并发请求共享同一个渲染 task，而非排队各渲染一遍
        self._inflight: Optional[asyncio.Task] = None

    def peek_cache(self) -> Optional[FrameCache]:
        """返回当前缓存帧（不触发渲染）

        供 /health 等只读端点使用，避免外部直接读私有属性。

        Returns:
            Optional[FrameCache]: 当前缓存，从未成功渲染过则为 None。
        """
        return self._cache

    def _render_blocking(self) -> FrameCache:
        """同步执行查询与渲染

        该方法会阻塞，必须在线程池中调用，不能直接在事件循环里执行。

        Returns:
            FrameCache: 新渲染的帧。

        Raises:
            RuntimeError: 查询无结果。
        """
        # 延迟导入：renderer 依赖 Pillow，属可选依赖
        from bus_arrival_board.epd.renderer import BusDisplayRenderer

        if not self._targets_resolved:
            self._monitor.resolve_targets()
            self._targets_resolved = True

        results = list(self._monitor.poll_once())
        if not results:
            raise RuntimeError("上游查询无结果")

        target, result = results[0]
        renderer = BusDisplayRenderer(self.width, self.height)
        image = renderer.render(result, target)
        data = renderer.to_bytes(image)

        return FrameCache(
            data=data,
            etag=hashlib.sha256(data).hexdigest()[:ETAG_DIGEST_LENGTH],
            rendered_at=time.monotonic(),
            width=self.width,
            height=self.height,
            bus_count=len(result.buses),
        )

    async def get_frame(self, force: bool = False) -> FrameCache:
        """取得当前帧，必要时重新渲染

        并发请求会共享同一个渲染任务（真单飞）；渲染失败时回退到缓存，
        但有陈旧上限——超过 max_stale_seconds 则抛错让端点返回 503。

        Args:
            force: 忽略最小刷新间隔，强制重新查询渲染。

        Returns:
            FrameCache: 当前有效帧。

        Raises:
            RuntimeError: 渲染失败且无可用缓存，或缓存过于陈旧。
        """
        async with self._lock:
            cached = self._cache

            # 快速路径：缓存新鲜且无并发渲染
            if (
                not force
                and self._inflight is None
                and cached is not None
                and cached.age_seconds() < self.min_refresh_seconds
            ):
                logger.debug("命中缓存，帧龄 %.1f 秒", cached.age_seconds())
                return cached

            # 有正在飞行的任务：复用它（真单飞）
            if self._inflight is not None:
                logger.debug("复用正在飞行的渲染任务")
                task = self._inflight
            else:
                # 创建新渲染任务
                logger.debug("启动新渲染任务")
                self._inflight = asyncio.create_task(asyncio.to_thread(self._render_blocking))
                task = self._inflight

        # await 放到锁外，避免堵住其他请求
        try:
            fresh = await task
        except Exception as exc:
            # 上游抖动时宁可返回略旧的画面，也比让设备白跑一趟好
            if cached is not None:
                age = cached.age_seconds()
                if age > self.max_stale_seconds:
                    logger.error(
                        "渲染失败且缓存过于陈旧（%.1f 秒 > %d 秒）: %s",
                        age,
                        self.max_stale_seconds,
                        exc,
                    )
                    raise RuntimeError(
                        f"数据源异常超过 {self.max_stale_seconds} 秒，拒绝返回过期画面"
                    ) from exc
                logger.warning("渲染失败，回退到缓存帧（帧龄 %.1f 秒）: %s", age, exc)
                # 标记降级状态
                cached.is_stale = True
                cached.last_error = str(exc)[:100]  # 截断避免过长
                return cached
            logger.error("渲染失败且无缓存可用: %s", exc)
            raise
        finally:
            # 清理 in-flight task（成功或失败都清）
            async with self._lock:
                if self._inflight is task:
                    self._inflight = None

        # 渲染成功：更新缓存
        async with self._lock:
            changed = cached is None or cached.etag != fresh.etag
            logger.info(
                "渲染完成: %d 字节, etag=%s, %s",
                len(fresh.data),
                fresh.etag,
                "画面有变化" if changed else "画面无变化",
            )
            self._cache = fresh
            return fresh


def _resolve_config_path() -> str:
    """确定要加载的配置文件路径

    Returns:
        str: 配置文件路径。

    Raises:
        FileNotFoundError: 找不到任何可用配置。
    """
    env_path = os.getenv("BUS_CONFIG")
    if env_path:
        return env_path

    for candidate in ("config.yaml", "config/shenzhen_m592.yaml"):
        if os.path.exists(candidate):
            logger.info("未设置 BUS_CONFIG，使用 %s", candidate)
            return candidate

    raise FileNotFoundError(
        "找不到配置文件。请设置环境变量 BUS_CONFIG=<path>，" "或在工作目录放置 config.yaml"
    )


def create_app(service: Optional[FrameService] = None) -> FastAPI:
    """构建 FastAPI 应用

    Args:
        service: 帧服务实例。省略时按环境变量与默认路径加载配置。
            测试可以注入自己的实例以避免真实网络请求。

    Returns:
        FastAPI: 配置好路由的应用实例。
    """
    app = FastAPI(
        title="BusArrivalBoard Frame Server",
        description="向 ESP32 等联网墨水屏设备提供预渲染画面",
        version="0.1.0",
    )

    if service is None:
        config = load_config(_resolve_config_path())
        width = int(os.getenv("EPD_WIDTH", DEFAULT_WIDTH))
        height = int(os.getenv("EPD_HEIGHT", DEFAULT_HEIGHT))
        service = FrameService(config, width=width, height=height)

    app.state.frame_service = service

    @app.get("/health")
    async def health() -> JSONResponse:
        """健康检查，不触发上游查询"""
        svc: FrameService = app.state.frame_service
        cached = svc.peek_cache()
        return JSONResponse(
            {
                "status": "ok",
                "has_cached_frame": cached is not None,
                "frame_age_seconds": round(cached.age_seconds(), 1) if cached else None,
            }
        )

    @app.get("/api/epd/frame.bin")
    async def get_frame(request: Request) -> Response:
        """返回单色位图帧，供设备直接送屏

        设备应带上次收到的 ETag（``If-None-Match``）；画面未变化时
        本接口返回 304，设备即可跳过刷屏直接休眠。
        """
        svc: FrameService = app.state.frame_service
        try:
            frame = await svc.get_frame()
        except Exception:
            # 内部细节（配置路径、上游 URL、字体路径）只进日志，
            # 不回显给客户端——本服务可能暴露在公网。
            error_id = uuid.uuid4().hex[:8]
            logger.exception("取帧失败 [error_id=%s]", error_id)
            return JSONResponse(
                {
                    "error": "frame_unavailable",
                    "message": "画面暂时不可用，请稍后重试",
                    "error_id": error_id,
                },
                status_code=503,
            )

        # 条件请求：画面没变就不重传。
        # 必须按 RFC 9110 解析——客户端会把 ETag 存成带引号形式再发回，
        # 裸字符串比较会让 304 永远命中不了。
        client_tags = _parse_if_none_match(request.headers.get("if-none-match", ""))
        if "*" in client_tags or frame.etag in client_tags:
            return Response(status_code=304, headers={"ETag": frame.http_etag()})

        headers = {
            "ETag": frame.http_etag(),
            "Cache-Control": "no-cache",
            "X-Frame-Width": str(frame.width),
            "X-Frame-Height": str(frame.height),
        }
        if frame.is_stale:
            # 让设备与运维能看出数据已降级（RFC 9111 §5.5 Warning 语义）
            headers["X-Frame-Stale"] = "1"
            headers["X-Frame-Age"] = str(round(frame.age_seconds(), 1))

        return Response(
            content=frame.data,
            media_type="application/octet-stream",
            headers=headers,
        )

    @app.get("/api/epd/metadata")
    async def get_metadata() -> JSONResponse:
        """返回当前帧的元信息，便于调试与监控"""
        svc: FrameService = app.state.frame_service
        try:
            frame = await svc.get_frame()
        except Exception:
            error_id = uuid.uuid4().hex[:8]
            logger.exception("取元信息失败 [error_id=%s]", error_id)
            return JSONResponse(
                {
                    "error": "frame_unavailable",
                    "message": "画面暂时不可用，请稍后重试",
                    "error_id": error_id,
                },
                status_code=503,
            )

        return JSONResponse(
            {
                "etag": frame.http_etag(),
                "width": frame.width,
                "height": frame.height,
                "size_bytes": len(frame.data),
                "bus_count": frame.bus_count,
                "age_seconds": round(frame.age_seconds(), 1),
                # 暴露降级状态，便于运维发现数据僵死
                "is_stale": frame.is_stale,
                "last_error": frame.last_error,
            }
        )

    return app


# uvicorn 入口：uvicorn bus_arrival_board.server:app
# 仅在真正被 ASGI 服务器加载时构建，避免 import 本模块就触发配置读取
def __getattr__(name: str):  # pragma: no cover
    if name == "app":
        application = create_app()
        globals()["app"] = application
        return application
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
