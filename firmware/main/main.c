/**
 * @file main.c
 * @brief BusArrivalBoard ESP32 固件主程序
 *
 * 完整流程：
 *   1. 连接 WiFi（SmartConfig 或已保存凭据）
 *   2. 下载帧数据（ETag 条件请求，304 时跳过刷屏）
 *   3. 刷新墨水屏（4 秒）
 *   4. 深度睡眠（5-10 分钟）
 *   5. RTC 定时器唤醒后回到步骤 1
 */

#include "epd_driver.h"
#include "http_frame_client.h"
#include "ota_update.h"
#include "power_mgmt.h"
#include "wifi_prov.h"

#include "driver/spi_master.h"
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "sdkconfig.h"
#include <stdlib.h>
#include <string.h>
#include <time.h>

static const char *TAG = "main";

/// RTC 内存中保存的 ETag（深度睡眠期间不丢失）
RTC_DATA_ATTR static char s_last_etag[64] = {0};

void app_main(void)
{
    ESP_LOGI(TAG, "========== BusArrivalBoard ESP32 固件 ==========");
    ESP_LOGI(TAG, "版本: %s", ota_get_running_version());
    ESP_LOGI(TAG, "IDF: %s", esp_get_idf_version());

    // 新固件刚刷入时处于待确认状态。这里只提示，不急着确认——
    // 要等 WiFi 和拉帧都成功了才 mark_valid，否则回滚保护形同虚设。
    bool pending_verify = ota_is_pending_verify();
    if (pending_verify) {
        ESP_LOGW(TAG, "本固件为新刷入版本，待核心流程验证后确认");
    }

    // 唤醒原因
    esp_sleep_wakeup_cause_t wakeup_reason = power_get_wakeup_cause();
    if (wakeup_reason == ESP_SLEEP_WAKEUP_TIMER) {
        ESP_LOGI(TAG, "RTC 定时器唤醒");
    } else {
        ESP_LOGI(TAG, "首次上电或硬复位");
    }

    // 电池状态。读 ADC 不需要联网，所以放在最前面：
    // 电量已经很低时，联网+刷屏（瞬时 200mA+）可能直接把电池拉到保护关断，
    // 不如拉长睡眠间隔，撑到用户来换电池。
    float battery_v = power_get_battery_voltage();
    int battery_pct = power_get_battery_percent();
    bool battery_low = power_is_battery_low();
    if (battery_v > 0) {
        ESP_LOGI(TAG, "电池: %.2fV (~%d%%)%s", battery_v, battery_pct,
                 battery_low ? " [低电量]" : "");
    }
    if (battery_low) {
        ESP_LOGW(TAG, "低电量，延长睡眠间隔至 %d 秒", CONFIG_BUS_SLEEP_INTERVAL_SEC * 4);
        power_enter_deep_sleep(CONFIG_BUS_SLEEP_INTERVAL_SEC * 4);
    }

    // 夜间模式：跳过刷新直接睡眠（省电）
    if (power_is_night_mode()) {
        ESP_LOGI(TAG, "夜间模式，跳过刷新");
        power_enter_deep_sleep(CONFIG_BUS_SLEEP_INTERVAL_SEC);
    }

    // 初始化 NVS（存储 WiFi 凭据）
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    // ---------------------------------------------------------------------------
    // 1. 连接 WiFi
    // ---------------------------------------------------------------------------
    ESP_LOGI(TAG, "连接 WiFi...");
    ret = wifi_connect(CONFIG_BUS_WIFI_CONNECT_TIMEOUT_MS);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "WiFi 连接失败: %s", esp_err_to_name(ret));
        ESP_LOGI(TAG, "30 秒后重试");
        power_enter_deep_sleep(30);
    }

    // ---------------------------------------------------------------------------
    // 2. 下载帧数据（带 ETag 条件请求）
    // ---------------------------------------------------------------------------
    size_t frame_size = (CONFIG_BUS_EPD_WIDTH * CONFIG_BUS_EPD_HEIGHT) / 8;
    uint8_t *framebuffer = (uint8_t *)malloc(frame_size);
    if (!framebuffer) {
        ESP_LOGE(TAG, "内存不足（需 %u 字节）", frame_size);
        power_enter_deep_sleep(CONFIG_BUS_SLEEP_INTERVAL_SEC);
    }

    http_frame_request_t req = {
        .url = CONFIG_BUS_SERVER_URL,
        .etag = s_last_etag[0] != '\0' ? s_last_etag : NULL,
        .auth_token = CONFIG_BUS_SERVER_TOKEN[0] != '\0' ? CONFIG_BUS_SERVER_TOKEN : NULL,
        .buffer = framebuffer,
        .buffer_size = frame_size,
        .timeout_ms = CONFIG_BUS_HTTP_TIMEOUT_MS,
    };

    http_frame_result_t result = {0};
    ret = http_frame_download(&req, &result);

    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "下载失败: %s", esp_err_to_name(ret));
        free(framebuffer);
        wifi_disconnect();
        ESP_LOGI(TAG, "60 秒后重试");
        power_enter_deep_sleep(60);
    }

    // 304 Not Modified: 画面未变，跳过刷屏省电
    if (result.not_modified) {
        ESP_LOGI(TAG, "服务端返回 304，画面未变化，跳过刷新");
        free(framebuffer);
        wifi_disconnect();
        power_enter_deep_sleep(CONFIG_BUS_SLEEP_INTERVAL_SEC);
    }

    ESP_LOGI(TAG, "HTTP %d, 已下载 %u 字节", result.http_status, result.bytes_received);
    if (result.frame_stale) {
        ESP_LOGW(TAG, "服务端数据已降级（上游故障回退旧帧）");
    }

    // 走到这里说明 WiFi 和拉帧都成功了——新固件的核心能力得到验证，
    // 现在才确认有效、取消回滚。刷屏失败不算致命（可能只是接线问题），
    // 但连不上网或拉不到帧的固件必须被回滚掉。
    if (pending_verify) {
        ota_mark_valid();
    }

    // 保存 ETag 到 RTC 内存
    if (result.etag[0] != '\0') {
        strncpy(s_last_etag, result.etag, sizeof(s_last_etag) - 1);
        s_last_etag[sizeof(s_last_etag) - 1] = '\0';
        ESP_LOGI(TAG, "ETag 已保存: %s", s_last_etag);
    }

    // 尺寸校验
    if (result.bytes_received != frame_size) {
        ESP_LOGE(TAG, "帧大小不匹配: 期望 %u, 实际 %u", frame_size, result.bytes_received);
        free(framebuffer);
        wifi_disconnect();
        power_enter_deep_sleep(CONFIG_BUS_SLEEP_INTERVAL_SEC);
    }

    // ---------------------------------------------------------------------------
    // 3. 刷新墨水屏
    // ---------------------------------------------------------------------------

    // WiFi 用完立即关闭，避免影响 SPI 时序
    wifi_disconnect();

    ESP_LOGI(TAG, "初始化墨水屏...");

    // 先初始化 SPI 总线（主机）
    spi_bus_config_t buscfg = {
        .mosi_io_num = CONFIG_BUS_EPD_PIN_MOSI,
        .miso_io_num = -1, // 墨水屏只写不读
        .sclk_io_num = CONFIG_BUS_EPD_PIN_SCK,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = frame_size,
    };
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &buscfg, SPI_DMA_CH_AUTO));

    epd_config_t epd_cfg = {
        .spi_host = SPI2_HOST,
        .pin_cs = CONFIG_BUS_EPD_PIN_CS,
        .pin_dc = CONFIG_BUS_EPD_PIN_DC,
        .pin_rst = CONFIG_BUS_EPD_PIN_RST,
        .pin_busy = CONFIG_BUS_EPD_PIN_BUSY,
        .model = EPD_MODEL_UC8176_BW_42,
        .width = CONFIG_BUS_EPD_WIDTH,
        .height = CONFIG_BUS_EPD_HEIGHT,
    };

    epd_handle_t epd;
    ret = epd_init(&epd_cfg, &epd);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "墨水屏初始化失败: %s", esp_err_to_name(ret));
        free(framebuffer);
        power_enter_deep_sleep(CONFIG_BUS_SLEEP_INTERVAL_SEC);
    }

    ESP_LOGI(TAG, "刷新屏幕（约 4 秒）...");
    ret = epd_display_frame(epd, framebuffer, frame_size);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "刷屏失败: %s", esp_err_to_name(ret));
    }

    free(framebuffer);

    // 进深度睡眠（< 1µA）
    epd_sleep(epd);
    epd_deinit(epd);

    // ---------------------------------------------------------------------------
    // 4. 深度睡眠前：检查 OTA 更新（低频轮询，每 24 小时查一次）
    // ---------------------------------------------------------------------------
    
    // 用 RTC 内存记录上次检查时间，避免每次唤醒都查
    static RTC_DATA_ATTR time_t s_last_ota_check = 0;
    time_t now = time(NULL);
    if ((now - s_last_ota_check) > 86400) {  // 24 小时
        s_last_ota_check = now;
        
        // 重新联网（刚才 WiFi 已断）
        if (wifi_connect(CONFIG_BUS_WIFI_CONNECT_TIMEOUT_MS) == ESP_OK) {
            ota_check_result_t ota_check;
            // 从服务端 URL 构造 base_url（去掉路径部分）
            char base_url[128];
            strncpy(base_url, CONFIG_BUS_SERVER_URL, sizeof(base_url) - 1);
            char *path_start = strstr(base_url, "/api/");
            if (path_start) {
                *path_start = '\0';  // 截断到域名部分
            }
            
            if (ota_check_update(base_url, 
                                CONFIG_BUS_SERVER_TOKEN[0] ? CONFIG_BUS_SERVER_TOKEN : NULL,
                                &ota_check) == ESP_OK && ota_check.update_available) {
                ESP_LOGI(TAG, "发现新版本 %s（当前 %s），开始升级",
                         ota_check.remote_version, ota_check.local_version);
                
                char fw_url[256];
                snprintf(fw_url, sizeof(fw_url), "%s/api/ota/firmware.bin", base_url);
                
                if (ota_perform_update(fw_url, 
                                      CONFIG_BUS_SERVER_TOKEN[0] ? CONFIG_BUS_SERVER_TOKEN : NULL)
                    == ESP_OK) {
                    ESP_LOGI(TAG, "OTA 成功，5 秒后重启");
                    vTaskDelay(pdMS_TO_TICKS(5000));
                    esp_restart();
                } else {
                    ESP_LOGE(TAG, "OTA 失败，继续运行旧版本");
                }
            }
            wifi_disconnect();
        }
    }

    ESP_LOGI(TAG, "刷新完成，进入深度睡眠 %d 秒", CONFIG_BUS_SLEEP_INTERVAL_SEC);
    power_enter_deep_sleep(CONFIG_BUS_SLEEP_INTERVAL_SEC);
}
