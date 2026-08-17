"""
EPD-nRF5 蓝牙墨水屏客户端

本模块是一个**独立的 Python 实现**，用于通过 BLE 驱动运行 EPD-nRF5 固件的
电子墨水屏设备（二手电子价签等）。

协议来源说明:
    GATT 服务/特征 UUID、命令码表与图片分包策略均来自 EPD-nRF5 开源项目的
    Web 上位机源码 ``html/js/main.js``（Web Bluetooth API 调用逻辑）。
    上游项目: https://github.com/tsl0922/EPD-nRF5 (开源公开代码)

    本文件不包含任何上游 JavaScript 代码，仅为对同一 BLE 协议的独立
    Python 语言实现。

依赖说明:
    需要可选依赖 ``bleak``。安装方式::

        pip install bus-arrival-board[epd]
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, List, Optional, Union

if TYPE_CHECKING:  # pragma: no cover - 仅供类型检查器使用
    from bleak.backends.device import BLEDevice

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GATT 定义（来源: EPD-nRF5 html/js/main.js）
# ---------------------------------------------------------------------------

SERVICE_UUID = "62750001-d828-918d-fb46-b6c11c675aec"
"""EPD 主服务 UUID"""

CHAR_CMD_UUID = "62750002-d828-918d-fb46-b6c11c675aec"
"""命令特征 UUID（write + notify）"""

CHAR_VERSION_UUID = "62750003-d828-918d-fb46-b6c11c675aec"
"""固件版本特征 UUID（read）"""

DEVICE_NAME_PREFIX = "NRF_EPD"
"""EPD 设备广播名称前缀"""


class EPDCommand:
    """EPD-nRF5 固件命令码

    报文格式: 首字节为命令码，其后为数据载荷。
    """

    SET_PINS = 0x00  # 设置引脚映射，数据为引脚 hex 串
    INIT = 0x01  # 初始化驱动，数据为驱动型号
    CLEAR = 0x02  # 清屏
    SEND_CMD = 0x03  # 向驱动 IC 发送命令
    SEND_DATA = 0x04  # 向驱动 IC 发送数据
    REFRESH = 0x05  # 刷新显示
    SLEEP = 0x06  # 驱动进入睡眠
    SET_TIME = 0x20  # 设置时间（日历模式）
    WRITE_IMG = 0x30  # 写入图像数据（固件 v1.6+，分包传输）
    SET_CONFIG = 0x90  # 写入配置
    SYS_RESET = 0x91  # 系统复位
    SYS_SLEEP = 0x92  # 系统睡眠
    CFG_ERASE = 0x99  # 擦除配置


DEFAULT_INTERLEAVED_COUNT = 20
"""交错 ACK 间隔：每 N 个不带响应的写入插入 1 次带响应的写入"""

DEFAULT_MTU_SIZE = 23
"""BLE 默认 MTU，协商失败时的保守回退值"""


# ---------------------------------------------------------------------------
# 异常定义
# ---------------------------------------------------------------------------


class EPDError(Exception):
    """EPD 客户端基础异常"""

    pass


class EPDConnectionError(EPDError):
    """蓝牙连接相关错误（扫描失败、未连接、连接中断等）"""

    pass


class EPDCommandError(EPDError):
    """命令写入或执行失败"""

    pass


# ---------------------------------------------------------------------------
# bleak 延迟导入
# ---------------------------------------------------------------------------

_BLEAK_HINT = (
    "缺少可选依赖 bleak，无法使用蓝牙功能。请安装：\n"
    "    pip install bus-arrival-board[epd]\n"
    "或单独安装：pip install bleak"
)


def _import_bleak() -> Any:
    """延迟导入 bleak 模块

    bleak 属于可选依赖（extras: epd），因此仅在真正需要蓝牙功能时导入，
    保证在未安装 bleak 的环境下本模块仍可正常导入。

    Returns:
        Any: 已导入的 ``bleak`` 模块对象。

    Raises:
        EPDError: bleak 未安装时抛出，并附带安装提示。
    """
    try:
        import bleak
    except ImportError as exc:  # pragma: no cover - 依赖缺失路径
        raise EPDError(_BLEAK_HINT) from exc
    return bleak


def _bleak_error_type() -> type[Exception]:
    """获取 ``BleakError`` 类型用于异常捕获

    Returns:
        type[Exception]: ``bleak.exc.BleakError`` 类；导入失败时回退为 ``Exception``。
    """
    try:
        from bleak.exc import BleakError

        return BleakError
    except ImportError:  # pragma: no cover - 依赖缺失路径
        return Exception


# ---------------------------------------------------------------------------
# EPD 蓝牙客户端
# ---------------------------------------------------------------------------


class EPDClient:
    """EPD-nRF5 蓝牙墨水屏客户端

    使用示例::

        async with EPDClient() as client:
            # 扫描并连接到第一个发现的 EPD 设备
            devices = await client.scan(timeout=10)
            if not devices:
                raise Exception("未找到 EPD 设备")

            await client.connect(devices[0].address)

            # 初始化 4.2寸黑白屏（UC8176）
            await client.set_pins("0508090A0B0C0D")
            await client.init(driver=0)

            # 发送图像数据（黑白位图，宽*高/8 字节）
            await client.write_image(image_bytes)
            await client.refresh()

            # 进入睡眠模式
            await client.sleep()

    Args:
        interleaved_count: 交错 ACK 间隔，每 N 个不带响应的写入插入 1 次带响应写入。
            默认值 20 来自上游 Web 实现。
    """

    def __init__(self, interleaved_count: int = DEFAULT_INTERLEAVED_COUNT) -> None:
        self._bleak_module = _import_bleak()
        self._client: Optional[Any] = None  # BleakClient 实例
        self._firmware_version: Optional[str] = None
        self._interleaved_count = interleaved_count
        logger.debug("EPDClient 已初始化，交错 ACK 间隔=%d", interleaved_count)

    # -----------------------------------------------------------------------
    # 上下文管理器
    # -----------------------------------------------------------------------

    async def __aenter__(self) -> EPDClient:
        """进入异步上下文管理器"""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """退出异步上下文管理器，自动断开连接"""
        if self._client is not None:
            await self.disconnect()

    # -----------------------------------------------------------------------
    # 连接管理
    # -----------------------------------------------------------------------

    @classmethod
    async def scan(cls, timeout: float = 10.0) -> List[BLEDevice]:
        """扫描附近的 EPD 设备

        Args:
            timeout: 扫描超时时间（秒）。

        Returns:
            List[BLEDevice]: 发现的 EPD 设备列表（名称以 ``NRF_EPD`` 开头）。

        Raises:
            EPDError: bleak 未安装。
            EPDConnectionError: 扫描失败。
        """
        bleak = _import_bleak()
        logger.info("开始扫描 EPD 设备，超时 %.1f 秒", timeout)
        try:
            devices = await bleak.BleakScanner.discover(timeout=timeout)
            epd_devices = [d for d in devices if d.name and d.name.startswith(DEVICE_NAME_PREFIX)]
            logger.info("扫描完成，发现 %d 个 EPD 设备", len(epd_devices))
            for dev in epd_devices:
                logger.debug("  - %s (%s)", dev.name, dev.address)
            return epd_devices
        except _bleak_error_type() as exc:
            raise EPDConnectionError(f"BLE 扫描失败: {exc}") from exc

    async def connect(self, device_name_or_address: Union[str, BLEDevice]) -> None:
        """连接到 EPD 设备

        Args:
            device_name_or_address: 设备地址（如 ``AA:BB:CC:DD:EE:FF``）、设备名称
                （如 ``NRF_EPD_ABCD``）或 ``BLEDevice`` 对象。

        Raises:
            EPDConnectionError: 连接失败或服务发现失败。
        """
        if self._client is not None:
            logger.warning("已有活跃连接，先断开现有连接")
            await self.disconnect()

        logger.info("正在连接到 EPD 设备: %s", device_name_or_address)
        try:
            self._client = self._bleak_module.BleakClient(device_name_or_address)
            await self._client.connect()
            logger.info("已连接，协商 MTU: %d", self._client.mtu_size)

            # 验证 GATT 服务是否可用
            services = self._client.services
            if SERVICE_UUID not in [str(s.uuid).lower() for s in services]:
                raise EPDConnectionError(
                    f"设备不支持 EPD 服务 (UUID: {SERVICE_UUID})，可能不是 EPD-nRF5 固件设备"
                )

            # 读取固件版本
            try:
                version_bytes = await self._client.read_gatt_char(CHAR_VERSION_UUID)
                self._firmware_version = version_bytes.decode("utf-8", errors="ignore").strip()
                logger.info("固件版本: %s", self._firmware_version)
            except Exception as exc:  # pragma: no cover - 旧固件可能不支持版本特征
                logger.warning("无法读取固件版本: %s", exc)
                self._firmware_version = None

        except _bleak_error_type() as exc:
            self._client = None
            self._firmware_version = None
            raise EPDConnectionError(f"连接失败: {exc}") from exc

    async def disconnect(self) -> None:
        """断开与 EPD 设备的连接"""
        if self._client is None:
            logger.debug("未连接，无需断开")
            return

        logger.info("正在断开连接")
        try:
            await self._client.disconnect()
        except _bleak_error_type() as exc:  # pragma: no cover - 断开失败通常不致命
            logger.warning("断开连接时出现异常: %s", exc)
        finally:
            self._client = None
            self._firmware_version = None
            logger.debug("已断开连接")

    @property
    def firmware_version(self) -> Optional[str]:
        """固件版本字符串

        Returns:
            Optional[str]: 已连接时返回固件版本（如 ``v1.6.0``），未连接时返回 ``None``。
        """
        return self._firmware_version

    @property
    def is_connected(self) -> bool:
        """是否已连接到设备

        Returns:
            bool: ``True`` 表示当前已连接。
        """
        return self._client is not None and self._client.is_connected

    # -----------------------------------------------------------------------
    # 底层命令发送
    # -----------------------------------------------------------------------

    async def _send_command(self, command_code: int, payload: bytes = b"") -> None:
        """向设备发送单个命令报文

        Args:
            command_code: 命令码（见 ``EPDCommand``）。
            payload: 命令数据载荷。

        Raises:
            EPDConnectionError: 未连接到设备。
            EPDCommandError: 命令写入失败。
        """
        if self._client is None or not self._client.is_connected:
            raise EPDConnectionError("未连接到 EPD 设备")

        packet = bytes([command_code]) + payload
        logger.debug("发送命令: 0x%02X, 载荷长度=%d", command_code, len(payload))

        try:
            await self._client.write_gatt_char(CHAR_CMD_UUID, packet, response=True)
        except _bleak_error_type() as exc:
            raise EPDCommandError(f"命令 0x{command_code:02X} 写入失败: {exc}") from exc

    # -----------------------------------------------------------------------
    # 高级 API
    # -----------------------------------------------------------------------

    async def set_pins(self, pins: str) -> None:
        """设置引脚映射（设备首次初始化时必须调用）

        Args:
            pins: 引脚配置 hex 字符串，如 ``"0508090A0B0C0D"``。
                格式参考 EPD-nRF5 文档或 Web 上位机 UI。

        Raises:
            EPDCommandError: 引脚配置格式错误或写入失败。
        """
        try:
            pin_bytes = bytes.fromhex(pins)
        except ValueError as exc:
            raise EPDCommandError(f"引脚配置格式错误，需要有效 hex 字符串: {exc}") from exc

        logger.info("设置引脚映射: %s", pins)
        await self._send_command(EPDCommand.SET_PINS, pin_bytes)

    async def init(self, driver: int) -> None:
        """初始化墨水屏驱动

        Args:
            driver: 驱动型号索引（见 ``bus_arrival_board.epd.drivers.EPDDriver``）。

        Raises:
            EPDCommandError: 驱动初始化失败。
        """
        logger.info("初始化驱动: %d", driver)
        await self._send_command(EPDCommand.INIT, bytes([driver]))

    async def clear(self) -> None:
        """清屏（全屏填充白色）"""
        logger.info("执行清屏")
        await self._send_command(EPDCommand.CLEAR)

    async def refresh(self) -> None:
        """刷新显示（将帧缓冲区内容输出到屏幕）"""
        logger.info("刷新显示")
        await self._send_command(EPDCommand.REFRESH)

    async def sleep(self) -> None:
        """使驱动进入睡眠模式（低功耗）"""
        logger.info("进入睡眠模式")
        await self._send_command(EPDCommand.SLEEP)

    async def write_image(self, pixels: bytes) -> None:
        """写入图像数据到帧缓冲区（固件 v1.6+ 的高效分包传输）

        图像数据格式:
            - **黑白屏**: 1 位/像素，宽*高/8 字节，MSB 在前。
            - **三色/四色屏**: 参考具体驱动 IC 文档，通常为双平面或多位编码。

        分包策略（来源: EPD-nRF5 html/js/main.js 第 145-148 行）:
            - 每包最大 ``mtu_size - 2`` 字节（首字节 0x30 占用 1 字节）。
            - 每 ``interleaved_count`` 个包中，1 个用带响应写入（ACK），其余用不带响应写入。

        Args:
            pixels: 图像像素数据字节串。

        Raises:
            EPDCommandError: 写入失败。
        """
        if self._client is None or not self._client.is_connected:
            raise EPDConnectionError("未连接到 EPD 设备")

        mtu_size = getattr(self._client, "mtu_size", DEFAULT_MTU_SIZE)
        chunk_size = mtu_size - 2  # 减去 ATT 协议头占用（1 字节命令码 + 至少 1 字节开销）
        total_chunks = (len(pixels) + chunk_size - 1) // chunk_size

        logger.info(
            "开始写入图像: %d 字节, MTU=%d, 块大小=%d, 分 %d 包",
            len(pixels),
            mtu_size,
            chunk_size,
            total_chunks,
        )

        i = 0
        try:
            for i in range(total_chunks):
                start = i * chunk_size
                end = min(start + chunk_size, len(pixels))
                chunk = pixels[start:end]
                packet = bytes([EPDCommand.WRITE_IMG]) + chunk

                # 交错 ACK: 每 interleaved_count 个包用带响应写入
                use_response = (i % self._interleaved_count) == 0
                await self._client.write_gatt_char(CHAR_CMD_UUID, packet, response=use_response)

                if (i + 1) % 50 == 0 or (i + 1) == total_chunks:
                    logger.debug("进度: %d / %d 包", i + 1, total_chunks)

            logger.info("图像写入完成")

        except _bleak_error_type() as exc:
            raise EPDCommandError(f"图像写入失败（第 {i+1}/{total_chunks} 包）: {exc}") from exc
