"""
公交信息墨水屏渲染引擎

使用 Pillow 将实时公交数据渲染为单色或多色墨水屏图像。
支持自动字体发现、多种布局模式、BLE 传输字节流生成。

Example:
    >>> from bus_arrival_board.epd.renderer import BusDisplayRenderer
    >>> renderer = BusDisplayRenderer(width=400, height=300)
    >>> image = renderer.render(result, target, layout='compact')
    >>> renderer.render_to_file('/tmp/preview.png', result, target)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

logger = logging.getLogger(__name__)

# 延迟导入 Pillow，给出友好提示（可选依赖 [epd]）
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:
    raise ImportError(
        "Pillow 未安装，墨水屏渲染功能不可用。\n"
        "请安装 [epd] 可选依赖：\n"
        "  pip install 'bus-arrival-board[epd]'\n"
        "或单独安装：\n"
        "  pip install pillow>=10.0.0"
    ) from exc

from bus_arrival_board.config import WatchTarget

# 类型导入
from chelaile_sdk.models import RealtimeResult

# 中文字体候选路径（按优先级排序）
DEFAULT_FONT_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/truetype/arphic/ukai.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


class BusDisplayRenderer:
    """公交信息墨水屏渲染器

    支持将 RealtimeResult 渲染为单色或多色墨水屏图像，提供多种布局模式。

    Attributes:
        width: 图像宽度（像素）
        height: 图像高度（像素）
        mode: PIL 图像模式，'1'=单色，'L'=灰度，'RGB'=彩色
        font_title: 标题字体
        font_body: 正文字体
        font_small: 小字体
    """

    def __init__(
        self,
        width: int = 400,
        height: int = 300,
        mode: Literal["1", "L", "RGB"] = "1",
        font_paths: Optional[list[str]] = None,
    ) -> None:
        """初始化渲染器

        Args:
            width: 图像宽度，默认 400px
            height: 图像高度，默认 300px
            mode: PIL 图像模式，'1'=单色位图，'L'=8位灰度，'RGB'=24位彩色，默认 '1'
            font_paths: 自定义字体路径列表，None=自动搜索系统字体

        Raises:
            ValueError: width 或 height <= 0
        """
        if width <= 0 or height <= 0:
            raise ValueError(f"图像尺寸必须 > 0，当前 {width}x{height}")

        self.width = width
        self.height = height
        self.mode = mode

        # 自动发现字体
        self._font_path = self._find_font(font_paths or DEFAULT_FONT_PATHS)
        logger.info(f"墨水屏渲染器初始化: {width}x{height} 模式={mode} 字体={self._font_path}")

        # 加载不同尺寸字体
        self.font_title = self._load_font(20)
        self.font_body = self._load_font(16)
        self.font_small = self._load_font(12)

    def _find_font(self, candidates: list[str]) -> Optional[str]:
        """从候选列表中查找第一个存在的字体文件

        Args:
            candidates: 字体文件路径列表

        Returns:
            找到的字体路径，或 None（将使用 PIL 默认位图字体）
        """
        for path in candidates:
            if os.path.exists(path):
                logger.debug(f"找到字体: {path}")
                return path

        logger.warning(
            f"未找到中文字体，将 fallback 到 PIL 默认位图字体。\n" f"搜索路径: {candidates}"
        )
        return None

    def _load_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """加载指定大小的字体

        Args:
            size: 字体大小（磅）

        Returns:
            PIL 字体对象（TrueType 或默认位图字体）
        """
        if self._font_path:
            try:
                return ImageFont.truetype(self._font_path, size)
            except Exception as exc:
                logger.warning(f"加载字体 {self._font_path} 失败: {exc}，使用默认字体")

        # Fallback 到 PIL 默认位图字体
        return ImageFont.load_default()

    def render(
        self,
        result: RealtimeResult,
        target: WatchTarget,
        layout: Literal["compact"] = "compact",
    ) -> Image.Image:
        """渲染公交信息为墨水屏图像

        Args:
            result: 实时查询结果（包含线路、车辆列表）
            target: 监控目标配置（包含站点名、别名）
            layout: 布局模式，当前仅支持 'compact'

        Returns:
            PIL.Image.Image 对象（模式由初始化时指定）

        Example:
            >>> renderer = BusDisplayRenderer()
            >>> img = renderer.render(result, target, layout='compact')
            >>> img.save('/tmp/preview.png')
        """
        if layout != "compact":
            raise ValueError(f"不支持的布局模式: {layout}，当前仅支持 'compact'")

        # 创建白色背景图像（单色模式下 1=白色，0=黑色）
        bg_color = 1 if self.mode == "1" else 255
        image = Image.new(self.mode, (self.width, self.height), bg_color)
        draw = ImageDraw.Draw(image)

        # 文字颜色（单色模式下 0=黑色）
        text_color = 0 if self.mode == "1" else 0

        # 当前绘制 Y 坐标
        y = 10

        # === 1. 顶部标题：线路名 + 站点名 ===
        title = self._format_title(result, target)
        draw.text((10, y), title, fill=text_color, font=self.font_title)
        y += 30

        # 分隔线
        draw.line([(10, y), (self.width - 10, y)], fill=text_color, width=2)
        y += 15

        # === 2. 中部：车辆信息（最多3辆） ===
        max_display = min(3, len(result.buses))
        if max_display == 0:
            # 无车辆数据
            no_bus_text = "暂无车辆信息"
            draw.text((10, y), no_bus_text, fill=text_color, font=self.font_body)
            y += 80
        else:
            for i in range(max_display):
                bus = result.buses[i]
                bus_text = self._format_bus_info(bus, result.target_order)
                draw.text((10, y), bus_text, fill=text_color, font=self.font_body)
                y += 60

        # === 3. 底部：更新时间 + 数据源标记 ===
        y = self.height - 40
        draw.line([(10, y), (self.width - 10, y)], fill=text_color, width=2)
        y += 10

        footer = self._format_footer(result)
        draw.text((10, y), footer, fill=text_color, font=self.font_small)

        return image

    def _format_title(self, result: RealtimeResult, target: WatchTarget) -> str:
        """格式化标题（线路 + 站点）

        Args:
            result: 实时查询结果
            target: 监控目标配置

        Returns:
            标题文本，如 "M592 → 安翼嘉寓"
        """
        # 优先使用 target.alias，否则用 target.station
        station_name = target.alias if target.alias else target.station
        line_name = result.line.name

        return f"{line_name} → {station_name}"

    def _format_bus_info(self, bus, target_order: int) -> str:
        """格式化单辆车信息

        Args:
            bus: BusInfo 对象
            target_order: 目标站点序号

        Returns:
            车辆信息文本，如 "1. 粤B12345 | 第5站 | 3分钟 | 宽松"

        Note:
            不使用 emoji（如 🚌）作为前缀，因为中文字体（NotoSansCJK/文泉驿）
            通常不含 emoji 字形，墨水屏上会渲染成豆腐块（⊠）。
        """
        # 车牌号（截取后5位避免过长）
        bus_id_short = bus.bus_id[-6:] if len(bus.bus_id) > 6 else bus.bus_id

        # 当前所在站序号
        current_station = f"第{bus.order}站"

        # ETA 分钟数或暂无预测
        if bus.eta_minutes is not None:
            eta_text = f"{bus.eta_minutes}分钟"
        else:
            eta_text = "暂无预测"

        # 拥挤度
        crowd = bus.crowd_level

        return f"{bus_id_short} | {current_station} | {eta_text} | {crowd}"

    def _format_footer(self, result: RealtimeResult) -> str:
        """格式化页脚（更新时间 + 数据源）

        Args:
            result: 实时查询结果

        Returns:
            页脚文本，如 "更新: 14:35 | GPS实时"
        """
        now = datetime.now().strftime("%H:%M")
        source = "GPS实时" if result.real_data else "时刻表"
        return f"更新: {now} | {source}"

    def to_bytes(self, image: Optional[Image.Image] = None) -> bytes:
        """将图像转换为原始字节流（用于 BLE 传输）

        将图像转换为单色位图（mode='1'）后，提取原始字节数据。
        适用于墨水屏 BLE 传输协议。

        Args:
            image: PIL.Image 对象，None=使用上次 render() 的结果

        Returns:
            单色位图原始字节流

        Raises:
            ValueError: image 为 None 且未调用过 render()

        Example:
            >>> img = renderer.render(result, target)
            >>> raw_bytes = renderer.to_bytes(img)
            >>> len(raw_bytes)  # 400*300/8 = 15000
            15000
        """
        if image is None:
            raise ValueError("to_bytes() 需要传入 image 参数")

        # 确保转换为单色模式
        if image.mode != "1":
            image = image.convert("1")

        return image.tobytes()

    def render_to_file(
        self,
        path: str | Path,
        result: RealtimeResult,
        target: WatchTarget,
        layout: Literal["compact"] = "compact",
    ) -> Path:
        """渲染并保存为文件（便捷方法，用于调试预览）

        Args:
            path: 保存路径（支持 .png, .bmp, .jpg 等 PIL 支持的格式）
            result: 实时查询结果
            target: 监控目标配置
            layout: 布局模式，默认 'compact'

        Returns:
            保存后的文件路径（Path 对象）

        Example:
            >>> renderer.render_to_file('/tmp/preview.png', result, target)
            PosixPath('/tmp/preview.png')
        """
        image = self.render(result, target, layout)

        # 转换路径
        output_path = Path(path).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 保存（PNG 格式支持单色模式，其他格式可能需要转换）
        if output_path.suffix.lower() in [".png", ".bmp"]:
            image.save(output_path)
        else:
            # JPEG 等格式不支持单色，转换为 RGB
            image.convert("RGB").save(output_path)

        logger.info(f"渲染完成，已保存到: {output_path}")
        return output_path
