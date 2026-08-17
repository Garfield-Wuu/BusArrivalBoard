/**
 * @file main.c
 * @brief BusArrivalBoard ESP32 固件主程序
 *
 * 启动流程:
 *   1. 连接 WiFi（SmartConfig 或硬编码 SSID）
 *   2. 下载帧数据（HTTP GET /api/epd/frame.bin + ETag 缓存）
 *   3. 刷新墨水屏
 *   4. 深度睡眠（5-10 分钟）
 *   5. RTC 定时器唤醒后回到步骤 1
 *
 * 配置:
 *   idf.py menuconfig
 *     → BusArrivalBoard Configuration
 *       - WiFi SSID / Password
 *       - 服务器 URL
 *       - 墨水屏尺寸与型号
 *       - 深度睡眠间隔
 */

#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_log.h"
#include "nvs_flash.h"

static const char *TAG = "main";

void app_main(void)
{
    ESP_LOGI(TAG, "BusArrivalBoard ESP32 固件启动");
    ESP_LOGI(TAG, "固件版本: v0.1.0");
    ESP_LOGI(TAG, "IDF 版本: %s", esp_get_idf_version());

    // 初始化 NVS（存储 WiFi 凭据与配置）
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    ESP_LOGI(TAG, "========== 启动完成 ==========");
    ESP_LOGI(TAG, "组件尚未实现，固件将空转");
    ESP_LOGI(TAG, "下一步：实现 WiFi / HTTP / EPD 组件");

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(5000));
        ESP_LOGI(TAG, "心跳");
    }
}
