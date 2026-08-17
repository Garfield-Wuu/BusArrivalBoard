/**
 * @file power_mgmt.c
 * @brief 电源管理实现
 */

#include "power_mgmt.h"
#include "esp_log.h"
#include "esp_sleep.h"
#include "sdkconfig.h"
#include <sys/time.h>
#include <time.h>

static const char *TAG = "power_mgmt";

void power_enter_deep_sleep(uint32_t seconds)
{
    ESP_LOGI(TAG, "进入深度睡眠 %lu 秒", (unsigned long)seconds);

    // 配置 RTC 定时器唤醒源
    ESP_ERROR_CHECK(esp_sleep_enable_timer_wakeup(seconds * 1000000ULL));

    // 进入深度睡眠（不返回）
    esp_deep_sleep_start();
}

bool power_is_night_mode(void)
{
#if !CONFIG_BUS_NIGHT_MODE_ENABLE
    return false;
#else
    time_t now;
    struct tm timeinfo;

    time(&now);
    localtime_r(&now, &timeinfo);

    int hour = timeinfo.tm_hour;
    int start = CONFIG_BUS_NIGHT_START_HOUR;
    int end = CONFIG_BUS_NIGHT_END_HOUR;

    // 夜间时段可能跨午夜：例如 23:00-06:00
    if (start < end) {
        // 正常区间：如 08:00-18:00
        return hour >= start && hour < end;
    } else {
        // 跨午夜：如 23:00-06:00
        return hour >= start || hour < end;
    }
#endif
}
