"""
EPD-nRF5 蓝牙墨水屏支持模块

提供通过 BLE 驱动 EPD-nRF5 固件墨水屏设备的客户端实现。

协议来源: https://github.com/tsl0922/EPD-nRF5 (html/js/main.js)
本模块为独立的 Python 实现。

注意:
    蓝牙功能需要可选依赖 ``bleak``::

        pip install bus-arrival-board[epd]

    未安装 bleak 时本模块仍可正常导入，仅在实例化 ``EPDClient``
    或调用扫描方法时抛出带安装提示的 ``EPDError``。
"""

from __future__ import annotations

from bus_arrival_board.epd.ble_client import (
    CHAR_CMD_UUID,
    CHAR_VERSION_UUID,
    DEVICE_NAME_PREFIX,
    SERVICE_UUID,
    EPDClient,
    EPDCommand,
    EPDCommandError,
    EPDConnectionError,
    EPDError,
)
from bus_arrival_board.epd.drivers import DRIVER_NAMES, EPDDriver
from bus_arrival_board.epd.renderer import BusDisplayRenderer

__all__ = [
    # 客户端
    "EPDClient",
    # 渲染器
    "BusDisplayRenderer",
    # 异常
    "EPDError",
    "EPDConnectionError",
    "EPDCommandError",
    # 协议常量
    "EPDCommand",
    "SERVICE_UUID",
    "CHAR_CMD_UUID",
    "CHAR_VERSION_UUID",
    "DEVICE_NAME_PREFIX",
    # 驱动型号
    "EPDDriver",
    "DRIVER_NAMES",
]
