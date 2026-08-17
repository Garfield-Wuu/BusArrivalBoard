/**
 * @file wifi_prov.h
 * @brief WiFi 配网封装
 *
 * 目前实现：硬编码 SSID/Password（通过 menuconfig 配置）
 * 后续扩展：SmartConfig / WPS / SoftAP + Captive Portal
 */

#pragma once

#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief 连接 WiFi（阻塞，直到成功或超时）
 *
 * 三级回退策略：
 *   1. NVS 已保存凭据（上次 SmartConfig 成功后自动存储）
 *   2. menuconfig 硬编码 SSID/Password
 *   3. 启动 SmartConfig 配网（需 CONFIG_BUS_WIFI_ENABLE_SMARTCONFIG）
 *
 * @param timeout_ms 单次连接超时（毫秒），0 表示无限等待
 * @return
 *   - ESP_OK 成功连接并获得 IP
 *   - ESP_ERR_TIMEOUT 超时
 *   - ESP_FAIL 其他错误
 */
esp_err_t wifi_connect(uint32_t timeout_ms);

/**
 * @brief 启动 SmartConfig 配网（ESP-Touch v2）
 *
 * 用户需用微信小程序或 EspTouch App 在同一 2.4GHz 网络下发送凭据。
 * 成功后凭据自动存入 NVS，下次启动可直连。
 *
 * @param timeout_ms 配网超时（毫秒），0 表示无限等待
 * @return
 *   - ESP_OK 配网成功并已连接
 *   - ESP_ERR_TIMEOUT 超时
 */
esp_err_t wifi_start_smartconfig(uint32_t timeout_ms);

/**
 * @brief 断开 WiFi
 *
 * 进深度睡眠前调用以节省功耗。
 *
 * @return ESP_OK 或错误码
 */
esp_err_t wifi_disconnect(void);

/**
 * @brief 检查是否已连接
 *
 * @return true 已连接且有 IP，false 未连接
 */
bool wifi_is_connected(void);

#ifdef __cplusplus
}
#endif
