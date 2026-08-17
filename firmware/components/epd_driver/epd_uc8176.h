/**
 * @file epd_uc8176.h
 * @brief UC8176 控制器命令定义（内部头文件）
 *
 * 命令码来自官方 datasheet:
 *   https://files.waveshare.com/upload/8/88/UC8176.pdf
 *
 * 适用屏幕：4.2 寸 400×300（黑白 / 三色）
 */

#pragma once

// ---------------------------------------------------------------------------
// UC8176 命令码（datasheet 第 24-40 页）
// ---------------------------------------------------------------------------

#define UC8176_CMD_PANEL_SETTING          0x00 ///< PSR: 分辨率/扫描方向/是否用内置 LUT
#define UC8176_CMD_POWER_SETTING          0x01 ///< PWR: 电源电压设置
#define UC8176_CMD_POWER_OFF              0x02 ///< POF: 关闭 DC/DC，进省电态
#define UC8176_CMD_POWER_OFF_SEQUENCE     0x03 ///< PFS: 关电序列
#define UC8176_CMD_POWER_ON               0x04 ///< PON: 打开 DC/DC，之后须等 BUSY
#define UC8176_CMD_POWER_ON_MEASURE       0x05 ///< PMES: 上电测量
#define UC8176_CMD_BOOSTER_SOFT_START     0x06 ///< BTST: 升压软启动参数
#define UC8176_CMD_DEEP_SLEEP             0x07 ///< DSLP: 深度睡眠，需先发 0xA5 校验码
#define UC8176_CMD_DATA_START_TRANS_1     0x10 ///< DTM1: 黑白通道像素数据
#define UC8176_CMD_DATA_STOP              0x11 ///< DSP: 数据传输结束
#define UC8176_CMD_DISPLAY_REFRESH        0x12 ///< DRF: 触发刷新，之后 BUSY 拉低
#define UC8176_CMD_DATA_START_TRANS_2     0x13 ///< DTM2: 红色通道像素数据（三色屏）
#define UC8176_CMD_PLL_CONTROL            0x30 ///< PLL: 帧率设置
#define UC8176_CMD_TEMP_SENSOR_CALIB      0x40 ///< TSC: 温度传感器校准
#define UC8176_CMD_TEMP_SENSOR_SELECT     0x41 ///< TSE: 选择内/外部温度传感器
#define UC8176_CMD_VCOM_DATA_INTERVAL     0x50 ///< CDI: VCOM 与数据间隔，含边框颜色
#define UC8176_CMD_LOW_POWER_DETECT       0x51 ///< LPD: 低电压检测
#define UC8176_CMD_TCON_SETTING           0x60 ///< TCON: 源极/栅极非重叠周期
#define UC8176_CMD_RESOLUTION_SETTING     0x61 ///< TRES: 分辨率（宽 16bit + 高 16bit）
#define UC8176_CMD_GET_STATUS             0x71 ///< FLG: 读取状态标志
#define UC8176_CMD_AUTO_MEASURE_VCOM      0x80 ///< AMV: 自动测量 VCOM
#define UC8176_CMD_READ_VCOM_VALUE        0x81 ///< VV: 读 VCOM 值
#define UC8176_CMD_VCM_DC_SETTING         0x82 ///< VDCS: VCOM_DC 设置

// ---------------------------------------------------------------------------
// 初始化参数
// ---------------------------------------------------------------------------

/**
 * PSR (0x00) 面板设置位定义
 *
 * bit[7:6] RES[1:0]  分辨率: 00=400x300, 01=320x300, 10=320x240, 11=200x300
 * bit[5]   REG_EN    LUT 来源: 0=OTP 内置, 1=寄存器(自定义波形)
 * bit[4]   BWR       颜色模式: 0=黑白红三色, 1=纯黑白
 * bit[3]   UD        扫描方向: 0=从下往上, 1=从上往下
 * bit[2]   SHL       源极移位: 0=右往左, 1=左往右
 * bit[1]   SHD_N     DC/DC: 0=关, 1=开
 * bit[0]   RST_N     软复位: 0=复位中, 1=正常
 *
 * 黑白屏取值 0x1F: 400x300 + OTP LUT + 纯黑白 + 上下正扫 + 左右正扫 + DC/DC 开 + 不复位
 * 三色屏取值 0x0F: 同上但 BWR=0（启用红色通道）
 */
#define UC8176_PSR_BW_400x300  0x1F
#define UC8176_PSR_3C_400x300  0x0F

/**
 * CDI (0x50) VCOM 与数据间隔设置
 *
 * bit[7:6] 边框颜色: 00=浮空(黑), 01=白, 10=黑, 11=浮空
 * bit[5:4] 数据极性
 * bit[3:0] 间隔时长（帧数）
 *
 * 0x97: 边框白 + 间隔 7 帧，实测可减少边框残留
 * 0xD7: 边框黑 + 间隔 7 帧
 */
#define UC8176_CDI_BORDER_WHITE 0x97
#define UC8176_CDI_BORDER_BLACK 0xD7

/**
 * PLL (0x30) 帧率
 *
 * 0x3C = 50Hz（默认，稳定）
 * 0x3A = 100Hz（更快但可能不稳）
 */
#define UC8176_PLL_50HZ 0x3C

/**
 * DSLP (0x07) 深度睡眠校验码
 *
 * 必须紧跟命令发送，否则控制器忽略睡眠请求。
 */
#define UC8176_DEEP_SLEEP_CHECK_CODE 0xA5

// ---------------------------------------------------------------------------
// 时序参数（datasheet 电气特性章节）
// ---------------------------------------------------------------------------

#define UC8176_SPI_CLOCK_HZ       10000000 ///< SPI 时钟上限 10MHz
#define UC8176_RESET_PULSE_MS     10       ///< 复位低电平保持时长
#define UC8176_RESET_SETTLE_MS    10       ///< 复位后稳定等待
#define UC8176_BUSY_TIMEOUT_MS    30000    ///< BUSY 等待超时（三色屏刷新可达 20 秒）
#define UC8176_BUSY_POLL_MS       10       ///< BUSY 轮询间隔
