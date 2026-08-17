/**
 * @file power_mgmt.c
 * @brief 电源管理实现
 */

#include "power_mgmt.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_log.h"
#include "esp_sleep.h"
#include "sdkconfig.h"
#include <sys/time.h>
#include <time.h>

static const char *TAG = "power_mgmt";

// ADC 句柄（延迟初始化）
static adc_oneshot_unit_handle_t s_adc_handle = NULL;

/**
 * @brief 初始化 ADC（首次调用时执行）
 */
static esp_err_t ensure_adc_initialized(void)
{
    if (s_adc_handle) {
        return ESP_OK;
    }

#if CONFIG_BUS_BATTERY_MONITOR_ENABLE
    adc_oneshot_unit_init_cfg_t init_cfg = {
        .unit_id = ADC_UNIT_1,
    };
    esp_err_t ret = adc_oneshot_new_unit(&init_cfg, &s_adc_handle);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "ADC 初始化失败: %s", esp_err_to_name(ret));
        return ret;
    }

    adc_oneshot_chan_cfg_t chan_cfg = {
        .bitwidth = ADC_BITWIDTH_12,
        .atten = ADC_ATTEN_DB_12,  // 0-3.3V 量程
    };
    ret = adc_oneshot_config_channel(s_adc_handle, CONFIG_BUS_BATTERY_ADC_CHANNEL, &chan_cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "ADC 通道配置失败: %s", esp_err_to_name(ret));
        adc_oneshot_del_unit(s_adc_handle);
        s_adc_handle = NULL;
        return ret;
    }

    ESP_LOGI(TAG, "ADC 初始化完成（通道 %d）", CONFIG_BUS_BATTERY_ADC_CHANNEL);
#endif
    return ESP_OK;
}

float power_get_battery_voltage(void)
{
#if !CONFIG_BUS_BATTERY_MONITOR_ENABLE
    return -1.0f;
#else
    if (ensure_adc_initialized() != ESP_OK) {
        return -1.0f;
    }

    // 多次采样取平均，降低噪声
    const int samples = 8;
    int sum = 0;
    for (int i = 0; i < samples; i++) {
        int raw = 0;
        if (adc_oneshot_read(s_adc_handle, CONFIG_BUS_BATTERY_ADC_CHANNEL, &raw) == ESP_OK) {
            sum += raw;
        }
    }
    int avg_raw = sum / samples;

    // ADC 12bit: 0-4095 对应 0-3.3V（衰减 12dB 下）
    float adc_voltage = (avg_raw / 4095.0f) * 3.3f;

    // 还原电池实际电压。Kconfig 不支持浮点，分压比按放大 100 倍存整数
    float battery_voltage = adc_voltage * (CONFIG_BUS_BATTERY_DIVIDER_RATIO / 100.0f);

    ESP_LOGD(TAG, "ADC raw=%d, V_adc=%.3fV, V_bat=%.3fV", avg_raw, adc_voltage, battery_voltage);
    return battery_voltage;
#endif
}

bool power_is_battery_low(void)
{
#if !CONFIG_BUS_BATTERY_MONITOR_ENABLE
    return false;
#else
    float voltage = power_get_battery_voltage();
    if (voltage < 0) {
        return false;  // 读取失败，保守返回 false
    }
    return (voltage < (CONFIG_BUS_BATTERY_LOW_MV / 1000.0f));
#endif
}

int power_get_battery_percent(void)
{
#if !CONFIG_BUS_BATTERY_MONITOR_ENABLE
    return -1;
#else
    float v = power_get_battery_voltage();
    if (v < 0) {
        return -1;
    }

    // 单节锂电放电曲线分段线性近似（粗略估计）
    // 4.2V=100%, 3.9V=75%, 3.7V=50%, 3.5V=25%, 3.3V=0%
    if (v >= 4.2f) return 100;
    if (v >= 3.9f) return 75 + (int)((v - 3.9f) / (4.2f - 3.9f) * 25);
    if (v >= 3.7f) return 50 + (int)((v - 3.7f) / (3.9f - 3.7f) * 25);
    if (v >= 3.5f) return 25 + (int)((v - 3.5f) / (3.7f - 3.5f) * 25);
    if (v >= 3.3f) return (int)((v - 3.3f) / (3.5f - 3.3f) * 25);
    return 0;
#endif
}

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
