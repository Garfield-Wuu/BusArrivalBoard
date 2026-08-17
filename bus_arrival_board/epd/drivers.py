"""
EPD-nRF5 墨水屏驱动型号常量

驱动索引顺序对应 EPD-nRF5 Web 上位机下拉列表顺序。
协议来源: https://github.com/tsl0922/EPD-nRF5 html/js/main.js
"""

from __future__ import annotations

from enum import IntEnum


class EPDDriver(IntEnum):
    """墨水屏驱动型号枚举

    索引值对应固件命令中的驱动型号参数。
    """

    # 4.2寸系列
    UC8176_4_2_BW = 0  # 4.2寸黑白 UC8176
    UC8176_4_2_BWR = 1  # 4.2寸三色 UC8176
    SSD1619_4_2_BW = 2  # 4.2寸黑白 SSD1619
    SSD1619_4_2_BWR = 3  # 4.2寸三色 SSD1619
    JD79668_4_2_BWRY = 4  # 4.2寸四色 JD79668

    # 5.83寸系列
    UC8179_5_83 = 5  # 5.83寸 UC8179

    # 7.5寸系列
    UC8179_7_5 = 6  # 7.5寸 UC8179
    SSD1677_7_5_HD = 7  # 7.5寸高清 SSD1677


# 驱动型号描述映射
DRIVER_NAMES = {
    EPDDriver.UC8176_4_2_BW: "4.2寸黑白 UC8176",
    EPDDriver.UC8176_4_2_BWR: "4.2寸三色 UC8176",
    EPDDriver.SSD1619_4_2_BW: "4.2寸黑白 SSD1619",
    EPDDriver.SSD1619_4_2_BWR: "4.2寸三色 SSD1619",
    EPDDriver.JD79668_4_2_BWRY: "4.2寸四色 JD79668",
    EPDDriver.UC8179_5_83: "5.83寸 UC8179",
    EPDDriver.UC8179_7_5: "7.5寸 UC8179",
    EPDDriver.SSD1677_7_5_HD: "7.5寸高清 SSD1677",
}
