/**
 * @file power_mgmt.h
 * @brief 电源管理 — 深度睡眠与 RTC 定时唤醒
 *
 * 深度睡眠功耗 < 20µA（关闭 CPU/WiFi/外设，只保留 RTC 与 ULP）。
 * 18650 锂电（2500mAh）理论续航：
 *   - 5 分钟刷新：~3 个月
 *   - 10 分钟刷新：~6 个月
 *   - 30 分钟刷新：~1 年
 */

#pragma once

#include "esp_err.h"
#include "esp_sleep.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief 进入深度睡眠，指定时长后 RTC 定时器唤醒
 *
 * **调用前务必**：
 *   - 关闭 WiFi（wifi_disconnect）
 *   - 墨水屏进深度睡眠（epd_sleep）
 *   - 释放不必要的资源
 *
 * 唤醒后从 `app_main` 重新开始（cold boot），但可通过
 * `esp_sleep_get_wakeup_cause()` 判断是定时唤醒还是首次上电。
 *
 * @param seconds 睡眠时长（秒）
 * @return 不返回（进入深度睡眠后 CPU 停止运行）
 */
void power_enter_deep_sleep(uint32_t seconds) __attribute__((noreturn));

/**
 * @brief 获取本次唤醒原因
 *
 * @return esp_sleep_wakeup_cause_t，常见值：
 *   - ESP_SLEEP_WAKEUP_TIMER: RTC 定时器唤醒
 *   - ESP_SLEEP_WAKEUP_UNDEFINED: 首次上电或硬复位
 */
static inline esp_sleep_wakeup_cause_t power_get_wakeup_cause(void)
{
    return esp_sleep_get_wakeup_cause();
}

/**
 * @brief 检查是否为夜间（根据 RTC 时钟与 menuconfig 配置）
 *
 * 夜间模式：公交停运时跳过刷新，显著延长续航。
 * 注意：RTC 时钟需在联网后通过 SNTP 校准，否则时区不准。
 *
 * @return true 当前处于夜间时段，应跳过刷新
 */
bool power_is_night_mode(void);

#ifdef __cplusplus
}
#endif
