/**
 * @file http_frame_client.c
 * @brief HTTP 帧下载客户端实现
 */

#include "http_frame_client.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include <stdlib.h>
#include <string.h>

static const char *TAG = "http_frame";

/**
 * @brief HTTP 事件处理器上下文
 */
typedef struct {
    uint8_t *buffer;
    size_t buffer_size;
    size_t bytes_written;
    bool overflow;
} http_event_ctx_t;

/**
 * @brief HTTP 事件处理回调
 *
 * 拦截响应体，流式写入调用方缓冲区。
 */
static esp_err_t http_event_handler(esp_http_client_event_t *evt)
{
    http_event_ctx_t *ctx = (http_event_ctx_t *)evt->user_data;

    switch (evt->event_id) {
    case HTTP_EVENT_ON_DATA:
        if (ctx->overflow) {
            // 已溢出，丢弃后续数据
            return ESP_OK;
        }
        if (ctx->bytes_written + evt->data_len > ctx->buffer_size) {
            ESP_LOGE(TAG, "响应体超出缓冲区: %d + %d > %d",
                     ctx->bytes_written, evt->data_len, ctx->buffer_size);
            ctx->overflow = true;
            return ESP_FAIL;
        }
        memcpy(ctx->buffer + ctx->bytes_written, evt->data, evt->data_len);
        ctx->bytes_written += evt->data_len;
        break;

    case HTTP_EVENT_ERROR:
        ESP_LOGE(TAG, "HTTP 错误");
        break;

    default:
        break;
    }
    return ESP_OK;
}

esp_err_t http_frame_download(const http_frame_request_t *request, http_frame_result_t *result)
{
    if (!request || !request->url || !request->buffer || request->buffer_size == 0 || !result) {
        return ESP_ERR_INVALID_ARG;
    }

    // 清空结果
    memset(result, 0, sizeof(http_frame_result_t));

    // 事件处理上下文
    http_event_ctx_t event_ctx = {
        .buffer = request->buffer,
        .buffer_size = request->buffer_size,
        .bytes_written = 0,
        .overflow = false,
    };

    esp_http_client_config_t config = {
        .url = request->url,
        .event_handler = http_event_handler,
        .user_data = &event_ctx,
        .timeout_ms = request->timeout_ms,
        .buffer_size = 4096,           // HTTP 内部缓冲区
        .buffer_size_tx = 1024,
    };

    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) {
        ESP_LOGE(TAG, "HTTP 客户端初始化失败");
        return ESP_FAIL;
    }

    // 设置请求头
    esp_http_client_set_method(client, HTTP_METHOD_GET);

    // ETag 条件请求
    if (request->etag && request->etag[0] != '\0') {
        esp_http_client_set_header(client, "If-None-Match", request->etag);
        ESP_LOGI(TAG, "条件请求 ETag: %s", request->etag);
    }

    // 认证 token（可选）
    if (request->auth_token && request->auth_token[0] != '\0') {
        esp_http_client_set_header(client, "X-Device-Token", request->auth_token);
    }

    // 发起请求
    esp_err_t err = esp_http_client_perform(client);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "HTTP 请求失败: %s", esp_err_to_name(err));
        esp_http_client_cleanup(client);
        return err;
    }

    // 读取响应
    result->http_status = esp_http_client_get_status_code(client);
    ESP_LOGI(TAG, "HTTP %d, 已接收 %d 字节", result->http_status, event_ctx.bytes_written);

    // 304 Not Modified
    if (result->http_status == 304) {
        result->not_modified = true;
        ESP_LOGI(TAG, "服务端返回 304，画面未变化");
        esp_http_client_cleanup(client);
        return ESP_OK;
    }

    // 200 OK
    if (result->http_status == 200) {
        if (event_ctx.overflow) {
            esp_http_client_cleanup(client);
            return ESP_ERR_INVALID_SIZE;
        }

        result->bytes_received = event_ctx.bytes_written;

        // 提取 ETag（带引号）
        int etag_len = 0;
        char *etag_header = NULL;
        err = esp_http_client_get_header(client, "ETag", &etag_header);
        if (err == ESP_OK && etag_header) {
            etag_len = strlen(etag_header);
            if (etag_len < HTTP_FRAME_ETAG_MAX_LEN) {
                strncpy(result->etag, etag_header, HTTP_FRAME_ETAG_MAX_LEN - 1);
                result->etag[HTTP_FRAME_ETAG_MAX_LEN - 1] = '\0';
            } else {
                ESP_LOGW(TAG, "ETag 过长，截断");
                strncpy(result->etag, etag_header, HTTP_FRAME_ETAG_MAX_LEN - 1);
                result->etag[HTTP_FRAME_ETAG_MAX_LEN - 1] = '\0';
            }
        }

        // 降级标记（X-Frame-Stale: 1）
        char *stale_header = NULL;
        err = esp_http_client_get_header(client, "X-Frame-Stale", &stale_header);
        if (err == ESP_OK && stale_header && strcmp(stale_header, "1") == 0) {
            result->frame_stale = true;
            ESP_LOGW(TAG, "服务端数据已降级（上游故障回退旧帧）");
        }

        // 帧尺寸（X-Frame-Width / X-Frame-Height）
        char *width_header = NULL;
        err = esp_http_client_get_header(client, "X-Frame-Width", &width_header);
        if (err == ESP_OK && width_header) {
            result->frame_width = (uint16_t)atoi(width_header);
        }

        char *height_header = NULL;
        err = esp_http_client_get_header(client, "X-Frame-Height", &height_header);
        if (err == ESP_OK && height_header) {
            result->frame_height = (uint16_t)atoi(height_header);
        }

        esp_http_client_cleanup(client);
        return ESP_OK;
    }

    // 其他状态码（4xx / 5xx）
    ESP_LOGE(TAG, "HTTP %d 错误", result->http_status);
    esp_http_client_cleanup(client);
    return ESP_FAIL;
}
