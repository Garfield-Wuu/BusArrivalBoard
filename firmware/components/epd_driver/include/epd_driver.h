/**
 * @file epd_driver.h
 * @brief E-Paper Display (EPD) 驱动接口
 *
 * 支持通过 SPI 控制的墨水屏，当前实现：
 *   - UC8176 (4.2" 黑白 400×300)
 *
 * 设计要点：
 *   - 阻塞 API：刷新需 4-20 秒，期间芯片进深度睡眠，无需异步
 *   - 分层：spi_send_command/data 封装细节，型号驱动只管命令序列
 *   - 可扩展：新增型号只需实现 epd_model_ops_t 四个函数
 */

#pragma once

#include "driver/spi_master.h"
#include "esp_err.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief 墨水屏型号枚举
 *
 * 编号与 Python 侧 EPDDriver 枚举保持一致（供 menuconfig 和服务端协商）。
 */
typedef enum {
    EPD_MODEL_UC8176_BW_42 = 0,  ///< 4.2" 黑白 UC8176 (400×300)
    EPD_MODEL_UC8176_3C_42 = 1,  ///< 4.2" 三色 UC8176 (400×300)
    EPD_MODEL_SSD1619_BW_42 = 2, ///< 4.2" 黑白 SSD1619 (400×300)
    EPD_MODEL_SSD1619_3C_42 = 3, ///< 4.2" 三色 SSD1619 (400×300)
    // 后续型号保留位
    EPD_MODEL_MAX
} epd_model_t;

/**
 * @brief 墨水屏配置结构
 */
typedef struct {
    spi_host_device_t spi_host; ///< SPI 主机（HSPI_HOST 或 VSPI_HOST）
    int pin_cs;                  ///< 片选引脚
    int pin_dc;                  ///< 数据/命令控制引脚（0=命令，1=数据）
    int pin_rst;                 ///< 复位引脚（低电平有效）
    int pin_busy;                ///< 忙碌状态引脚（高电平=忙，低电平=空闲）
    epd_model_t model;           ///< 屏幕型号
    uint16_t width;              ///< 屏幕宽度（像素）
    uint16_t height;             ///< 屏幕高度（像素）
} epd_config_t;

/**
 * @brief 墨水屏驱动句柄（不透明）
 */
typedef struct epd_handle_s *epd_handle_t;

/**
 * @brief 初始化墨水屏驱动
 *
 * 会完成以下操作：
 *   1. 初始化 GPIO（CS/DC/RST 输出，BUSY 输入）
 *   2. 初始化 SPI 总线与设备（10MHz 时钟，模式 0）
 *   3. 硬件复位屏幕
 *   4. 发送型号对应的初始化命令序列
 *   5. 等待 BUSY 引脚拉低（屏幕就绪）
 *
 * @param config 配置结构指针
 * @param[out] out_handle 成功时返回句柄，失败时为 NULL
 * @return
 *   - ESP_OK 成功
 *   - ESP_ERR_INVALID_ARG 参数无效（NULL 指针、不支持的型号）
 *   - ESP_ERR_NO_MEM 内存不足
 *   - 其他 GPIO/SPI 错误码
 */
esp_err_t epd_init(const epd_config_t *config, epd_handle_t *out_handle);

/**
 * @brief 释放墨水屏驱动资源
 *
 * 会进入深度睡眠模式（功耗 < 1µA），然后释放 SPI 总线与 GPIO。
 *
 * @param handle 驱动句柄
 * @return
 *   - ESP_OK 成功
 *   - ESP_ERR_INVALID_ARG handle 为 NULL
 */
esp_err_t epd_deinit(epd_handle_t handle);

/**
 * @brief 刷新屏幕内容（阻塞，耗时 4-20 秒）
 *
 * 将内存中的画面缓冲区传输到屏幕并触发刷新。刷新完成前函数会阻塞
 * （轮询 BUSY 引脚）。黑白屏耗时约 4 秒，三色/四色屏约 15-20 秒。
 *
 * @param handle 驱动句柄
 * @param framebuffer 画面缓冲区（单色位图，width×height/8 字节）
 *                    - 1 bit = 1 像素，MSB first
 *                    - 黑白屏：0=白，1=黑
 *                    - 三色屏需两次调用（黑色通道 + 红色通道）
 * @param len 缓冲区长度（字节），必须等于 width×height/8
 * @return
 *   - ESP_OK 成功
 *   - ESP_ERR_INVALID_ARG handle 或 framebuffer 为 NULL，或 len 不匹配
 *   - ESP_ERR_TIMEOUT BUSY 引脚超时（屏幕可能损坏）
 */
esp_err_t epd_display_frame(epd_handle_t handle, const uint8_t *framebuffer, size_t len);

/**
 * @brief 清屏（全白）
 *
 * 快速清除屏幕内容，比发送全白帧更快（使用控制器内置的清屏命令）。
 *
 * @param handle 驱动句柄
 * @return ESP_OK 或错误码
 */
esp_err_t epd_clear(epd_handle_t handle);

/**
 * @brief 进入深度睡眠模式
 *
 * 关闭屏幕电源，功耗降至 < 1µA。唤醒需重新调用 epd_init。
 * **推荐在每次刷新后调用**，避免长期通电损伤屏幕或产生残影。
 *
 * @param handle 驱动句柄
 * @return ESP_OK 或错误码
 */
esp_err_t epd_sleep(epd_handle_t handle);

#ifdef __cplusplus
}
#endif
