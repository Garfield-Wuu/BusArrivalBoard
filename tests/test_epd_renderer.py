"""墨水屏渲染引擎测试

覆盖：字体发现与 fallback、布局渲染、to_bytes 字节流、render_to_file。
"""

from __future__ import annotations

import pytest

from bus_arrival_board.config import WatchTarget
from chelaile_sdk.models import BusETA, BusInfo, LineInfo, RealtimeResult

# Pillow 是可选依赖 [epd]，缺失时跳过整个模块
pytest.importorskip("PIL")

from bus_arrival_board.epd.renderer import BusDisplayRenderer  # noqa: E402


@pytest.fixture
def line() -> LineInfo:
    return LineInfo(
        line_id="012000052",
        name="M592",
        direction=0,
        start_station="平安居场站",
        end_station="平安居场站",
    )


@pytest.fixture
def target() -> WatchTarget:
    return WatchTarget(city="深圳", line="M592", station="安翼嘉寓", alias="回家")


@pytest.fixture
def result(line: LineInfo) -> RealtimeResult:
    buses = [
        BusInfo(
            bus_id="粤B02621D",
            order=14,
            lat=22.5430,
            lng=113.9502,
            capacity=1,
            distance_to_station=2500,
            eta=BusETA(travel_time=420, arrival_time=1640000000000, display_time="16:38"),
        ),
        BusInfo(
            bus_id="粤B05309D",
            order=9,
            lat=22.5380,
            lng=113.9450,
            capacity=0,
            distance_to_station=5000,
            eta=None,  # 无预测
        ),
    ]
    return RealtimeResult(
        line=line, target_order=17, real_data=True, buses=buses, refresh_interval=60
    )


class TestFontDiscovery:
    """字体发现与 fallback"""

    def test_finds_system_font(self) -> None:
        r = BusDisplayRenderer()
        # 本机装有 NotoSansCJK；即使没有也不应崩溃
        assert r.font_title is not None
        assert r.font_body is not None
        assert r.font_small is not None

    def test_fallback_when_no_font_exists(self) -> None:
        """所有候选路径都不存在时，fallback 到 PIL 默认位图字体，不得崩溃"""
        r = BusDisplayRenderer(font_paths=["/nonexistent/a.ttc", "/nonexistent/b.ttf"])
        assert r._font_path is None
        assert r.font_body is not None

    def test_render_survives_missing_fonts(
        self, result: RealtimeResult, target: WatchTarget
    ) -> None:
        r = BusDisplayRenderer(font_paths=["/nonexistent/x.ttf"])
        img = r.render(result, target)
        assert img.size == (400, 300)


class TestRender:
    """渲染主流程"""

    def test_default_size_and_mode(self, result: RealtimeResult, target: WatchTarget) -> None:
        r = BusDisplayRenderer()
        img = r.render(result, target)
        assert img.size == (400, 300)
        assert img.mode == "1"

    def test_custom_size(self, result: RealtimeResult, target: WatchTarget) -> None:
        r = BusDisplayRenderer(width=250, height=122)
        img = r.render(result, target)
        assert img.size == (250, 122)

    def test_draws_content(self, result: RealtimeResult, target: WatchTarget) -> None:
        """渲染结果应含黑色像素（不是纯白空图）"""
        r = BusDisplayRenderer()
        img = r.render(result, target)
        black = sum(1 for p in img.convert("L").tobytes() if p == 0)
        assert black > 500

    def test_empty_buses(self, line: LineInfo, target: WatchTarget) -> None:
        empty = RealtimeResult(
            line=line, target_order=17, real_data=False, buses=[], refresh_interval=60
        )
        r = BusDisplayRenderer()
        img = r.render(empty, target)
        assert img.size == (400, 300)

    def test_caps_at_three_buses(self, line: LineInfo, target: WatchTarget) -> None:
        buses = [
            BusInfo(bus_id=f"粤B{i:05d}", order=i, lat=22.5, lng=113.9, capacity=0)
            for i in range(1, 8)
        ]
        many = RealtimeResult(
            line=line, target_order=17, real_data=True, buses=buses, refresh_interval=60
        )
        r = BusDisplayRenderer()
        assert r.render(many, target).size == (400, 300)

    def test_invalid_layout_raises(self, result: RealtimeResult, target: WatchTarget) -> None:
        r = BusDisplayRenderer()
        with pytest.raises(ValueError, match="不支持的布局模式"):
            r.render(result, target, layout="fancy")  # type: ignore[arg-type]

    def test_invalid_size_raises(self) -> None:
        with pytest.raises(ValueError, match="图像尺寸必须"):
            BusDisplayRenderer(width=0, height=300)


class TestFormatting:
    """文本格式化"""

    def test_title_prefers_alias(self, result: RealtimeResult, target: WatchTarget) -> None:
        r = BusDisplayRenderer()
        assert r._format_title(result, target) == "M592 → 回家"

    def test_title_falls_back_to_station(self, result: RealtimeResult) -> None:
        t = WatchTarget(city="深圳", line="M592", station="安翼嘉寓")
        r = BusDisplayRenderer()
        assert r._format_title(result, t) == "M592 → 安翼嘉寓"

    def test_bus_info_with_eta(self, result: RealtimeResult) -> None:
        r = BusDisplayRenderer()
        text = r._format_bus_info(result.buses[0], 17)
        assert "第14站" in text
        assert "7分钟" in text
        assert "适中" in text

    def test_bus_info_without_eta(self, result: RealtimeResult) -> None:
        r = BusDisplayRenderer()
        assert "暂无预测" in r._format_bus_info(result.buses[1], 17)

    def test_no_emoji_in_bus_line(self, result: RealtimeResult) -> None:
        """中文字体无 emoji 字形，会渲染成豆腐块，故不得含 emoji"""
        r = BusDisplayRenderer()
        assert "🚌" not in r._format_bus_info(result.buses[0], 17)

    def test_footer_gps(self, result: RealtimeResult) -> None:
        r = BusDisplayRenderer()
        footer = r._format_footer(result)
        assert "GPS实时" in footer
        assert "更新:" in footer

    def test_footer_schedule(self, line: LineInfo) -> None:
        res = RealtimeResult(
            line=line, target_order=17, real_data=False, buses=[], refresh_interval=60
        )
        r = BusDisplayRenderer()
        assert "时刻表" in r._format_footer(res)


class TestToBytes:
    """BLE 字节流"""

    def test_length_matches_resolution(self, result: RealtimeResult, target: WatchTarget) -> None:
        r = BusDisplayRenderer(width=400, height=300)
        raw = r.to_bytes(r.render(result, target))
        assert len(raw) == 400 * 300 // 8
        assert isinstance(raw, bytes)

    def test_converts_non_mono_image(self, result: RealtimeResult, target: WatchTarget) -> None:
        r = BusDisplayRenderer(mode="L")
        img = r.render(result, target)
        assert img.mode == "L"
        raw = r.to_bytes(img)
        assert len(raw) == 400 * 300 // 8

    def test_requires_image(self) -> None:
        r = BusDisplayRenderer()
        with pytest.raises(ValueError):
            r.to_bytes(None)


class TestRenderToFile:
    """文件输出"""

    def test_writes_png(self, tmp_path, result: RealtimeResult, target: WatchTarget) -> None:
        r = BusDisplayRenderer()
        out = r.render_to_file(tmp_path / "preview.png", result, target)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_creates_parent_dirs(
        self, tmp_path, result: RealtimeResult, target: WatchTarget
    ) -> None:
        r = BusDisplayRenderer()
        out = r.render_to_file(tmp_path / "nested" / "deep" / "p.png", result, target)
        assert out.exists()

    def test_jpeg_converts_to_rgb(
        self, tmp_path, result: RealtimeResult, target: WatchTarget
    ) -> None:
        """JPEG 不支持 mode='1'，应自动转 RGB 而非抛错"""
        r = BusDisplayRenderer()
        out = r.render_to_file(tmp_path / "preview.jpg", result, target)
        assert out.exists()
