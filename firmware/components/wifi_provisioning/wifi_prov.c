/**
 * @file wifi_prov.c
 * @brief WiFi 连接与 SmartConfig 配网实现
 *
 * 连接策略（三级回退）：
 *   1. NVS 中已保存的凭据（上次 SmartConfig 配网成功后自动保存）
 *   2. menuconfig 中硬编码的 SSID/Password
 *   3. SmartConfig（ESP-Touch v2）等待手机下发
 *
 * 之所以优先用 NVS：深度睡眠唤醒后不必重新配网，
 * 而 esp_wifi 本身就会把凭据存进 NVS（storage=WIFI_STORAGE_FLASH）。
 */

#include "wifi_prov.h"

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_smartconfig.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "sdkconfig.h"
#include <string.h>

static const char *TAG = "wifi_prov";

#define WIFI_CONNECTED_BIT BIT0
#define SMARTCONFIG_DONE_BIT BIT1

/// 单次连接尝试的最大重试次数，超过则判定该凭据无效
#define WIFI_MAX_RETRY 5

static EventGroupHandle_t s_event_group = NULL;
static bool s_stack_initialized = false;
static int s_retry_count = 0;
static bool s_smartconfig_running = false;

// ---------------------------------------------------------------------------
// 事件处理
// ---------------------------------------------------------------------------

static void on_wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
        return;
    }

    if (id == WIFI_EVENT_STA_DISCONNECTED) {
        // SmartConfig 期间的断连是正常现象，不计入重试
        if (s_smartconfig_running) {
            return;
        }
        if (s_retry_count < WIFI_MAX_RETRY) {
            s_retry_count++;
            ESP_LOGI(TAG, "连接失败，重试 %d/%d", s_retry_count, WIFI_MAX_RETRY);
            esp_wifi_connect();
        } else {
            ESP_LOGW(TAG, "重试 %d 次仍失败，放弃当前凭据", WIFI_MAX_RETRY);
        }
    }
}

static void on_ip_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)data;
        ESP_LOGI(TAG, "已获得 IP: " IPSTR, IP2STR(&event->ip_info.ip));
        s_retry_count = 0;
        xEventGroupSetBits(s_event_group, WIFI_CONNECTED_BIT);
    }
}

static void on_smartconfig_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    switch (id) {
    case SC_EVENT_SCAN_DONE:
        ESP_LOGI(TAG, "SmartConfig: 扫描完成");
        break;

    case SC_EVENT_FOUND_CHANNEL:
        ESP_LOGI(TAG, "SmartConfig: 已找到信道，等待凭据");
        break;

    case SC_EVENT_GOT_SSID_PSWD: {
        smartconfig_event_got_ssid_pswd_t *evt = (smartconfig_event_got_ssid_pswd_t *)data;
        wifi_config_t cfg = {0};
        memcpy(cfg.sta.ssid, evt->ssid, sizeof(cfg.sta.ssid));
        memcpy(cfg.sta.password, evt->password, sizeof(cfg.sta.password));

        ESP_LOGI(TAG, "SmartConfig: 收到凭据 SSID=%s", (const char *)cfg.sta.ssid);

        // 用新凭据重连。凭据会随 WIFI_STORAGE_FLASH 自动落盘，
        // 下次唤醒无需重新配网。
        ESP_ERROR_CHECK(esp_wifi_disconnect());
        ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &cfg));
        ESP_ERROR_CHECK(esp_wifi_connect());
        break;
    }

    case SC_EVENT_SEND_ACK_DONE:
        ESP_LOGI(TAG, "SmartConfig: 已向手机回执，配网结束");
        xEventGroupSetBits(s_event_group, SMARTCONFIG_DONE_BIT);
        break;

    default:
        break;
    }
}

// ---------------------------------------------------------------------------
// 内部辅助
// ---------------------------------------------------------------------------

/**
 * @brief 初始化 TCP/IP 栈、事件循环与 WiFi 驱动（仅执行一次）
 */
static esp_err_t ensure_stack_initialized(void)
{
    if (s_stack_initialized) {
        return ESP_OK;
    }

    s_event_group = xEventGroupCreate();
    if (!s_event_group) {
        return ESP_ERR_NO_MEM;
    }

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t init_cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init_cfg));

    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &on_wifi_event, NULL));
    ESP_ERROR_CHECK(
        esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &on_ip_event, NULL));
    ESP_ERROR_CHECK(
        esp_event_handler_register(SC_EVENT, ESP_EVENT_ANY_ID, &on_smartconfig_event, NULL));

    // 凭据落 Flash，深度睡眠唤醒后可直接复用
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_FLASH));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));

    s_stack_initialized = true;
    return ESP_OK;
}

/**
 * @brief 判断当前是否已有可用凭据（NVS 或 menuconfig）
 */
static bool has_stored_credentials(void)
{
    wifi_config_t cfg = {0};
    if (esp_wifi_get_config(WIFI_IF_STA, &cfg) != ESP_OK) {
        return false;
    }
    return cfg.sta.ssid[0] != '\0';
}

// ---------------------------------------------------------------------------
// 公开 API
// ---------------------------------------------------------------------------

esp_err_t wifi_connect(uint32_t timeout_ms)
{
    esp_err_t ret = ensure_stack_initialized();
    if (ret != ESP_OK) {
        return ret;
    }

    s_retry_count = 0;
    xEventGroupClearBits(s_event_group, WIFI_CONNECTED_BIT | SMARTCONFIG_DONE_BIT);

    // menuconfig 里填了 SSID 就覆盖 NVS（便于开发期固定网络）
    if (strlen(CONFIG_BUS_WIFI_SSID) > 0) {
        wifi_config_t cfg = {0};
        strncpy((char *)cfg.sta.ssid, CONFIG_BUS_WIFI_SSID, sizeof(cfg.sta.ssid) - 1);
        strncpy((char *)cfg.sta.password, CONFIG_BUS_WIFI_PASSWORD,
                sizeof(cfg.sta.password) - 1);
        ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &cfg));
        ESP_LOGI(TAG, "使用 menuconfig 凭据: %s", CONFIG_BUS_WIFI_SSID);
    } else if (has_stored_credentials()) {
        ESP_LOGI(TAG, "使用 NVS 中已保存的凭据");
    } else {
        ESP_LOGW(TAG, "无可用凭据，需要 SmartConfig 配网");
    }

    ESP_ERROR_CHECK(esp_wifi_start());

    // 无凭据时直接进配网，不白等超时
    if (!has_stored_credentials() && strlen(CONFIG_BUS_WIFI_SSID) == 0) {
#if CONFIG_BUS_WIFI_ENABLE_SMARTCONFIG
        return wifi_start_smartconfig(CONFIG_BUS_WIFI_SMARTCONFIG_TIMEOUT_MS);
#else
        ESP_LOGE(TAG, "无凭据且 SmartConfig 未启用");
        return ESP_ERR_INVALID_STATE;
#endif
    }

    EventBits_t bits = xEventGroupWaitBits(
        s_event_group, WIFI_CONNECTED_BIT, pdFALSE, pdFALSE,
        timeout_ms == 0 ? portMAX_DELAY : pdMS_TO_TICKS(timeout_ms));

    if (bits & WIFI_CONNECTED_BIT) {
        return ESP_OK;
    }

    ESP_LOGW(TAG, "连接超时（%lu ms）", (unsigned long)timeout_ms);

#if CONFIG_BUS_WIFI_ENABLE_SMARTCONFIG
    ESP_LOGI(TAG, "转入 SmartConfig 配网");
    return wifi_start_smartconfig(CONFIG_BUS_WIFI_SMARTCONFIG_TIMEOUT_MS);
#else
    return ESP_ERR_TIMEOUT;
#endif
}

esp_err_t wifi_start_smartconfig(uint32_t timeout_ms)
{
    esp_err_t ret = ensure_stack_initialized();
    if (ret != ESP_OK) {
        return ret;
    }

    ESP_LOGI(TAG, "SmartConfig 启动，请用微信或 EspTouch App 配网");
    ESP_LOGI(TAG, "手机需连接目标 2.4GHz WiFi（ESP32 不支持 5GHz）");

    s_smartconfig_running = true;
    xEventGroupClearBits(s_event_group, SMARTCONFIG_DONE_BIT);

    // ESP-Touch v2 同时兼容微信小程序与 EspTouch
    smartconfig_start_config_t sc_cfg = SMARTCONFIG_START_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_smartconfig_set_type(SC_TYPE_ESPTOUCH_V2));
    ESP_ERROR_CHECK(esp_smartconfig_start(&sc_cfg));

    // 等到"拿到 IP"且"已回执手机"两件事都完成
    EventBits_t bits = xEventGroupWaitBits(
        s_event_group, WIFI_CONNECTED_BIT | SMARTCONFIG_DONE_BIT, pdFALSE, pdTRUE,
        timeout_ms == 0 ? portMAX_DELAY : pdMS_TO_TICKS(timeout_ms));

    esp_smartconfig_stop();
    s_smartconfig_running = false;

    if ((bits & WIFI_CONNECTED_BIT) && (bits & SMARTCONFIG_DONE_BIT)) {
        ESP_LOGI(TAG, "SmartConfig 配网成功，凭据已保存");
        return ESP_OK;
    }

    // 拿到 IP 但没等到 ACK 也算成功——ACK 丢包不影响联网
    if (bits & WIFI_CONNECTED_BIT) {
        ESP_LOGW(TAG, "已联网但未收到手机回执（ACK 可能丢包），继续");
        return ESP_OK;
    }

    ESP_LOGE(TAG, "SmartConfig 超时（%lu ms）", (unsigned long)timeout_ms);
    return ESP_ERR_TIMEOUT;
}

esp_err_t wifi_disconnect(void)
{
    if (!s_stack_initialized) {
        return ESP_OK;
    }
    // 进深度睡眠前彻底关掉射频，否则会多耗 1-2 mA
    esp_wifi_disconnect();
    return esp_wifi_stop();
}

bool wifi_is_connected(void)
{
    if (!s_stack_initialized || !s_event_group) {
        return false;
    }
    return (xEventGroupGetBits(s_event_group) & WIFI_CONNECTED_BIT) != 0;
}
