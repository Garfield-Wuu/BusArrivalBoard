/**
 * @file ota_update.c
 * @brief OTA 固件升级实现
 */

#include "ota_update.h"

#include "esp_app_desc.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include <stdlib.h>
#include <string.h>

static const char *TAG = "ota";

/// manifest JSON 响应缓冲区上限（够放版本号和大小）
#define OTA_MANIFEST_BUF_SIZE 512

/// OTA 写入块大小。1KB 是吞吐与内存的折中
#define OTA_WRITE_CHUNK_SIZE 1024

// ---------------------------------------------------------------------------
// 极简 JSON 字段提取
// ---------------------------------------------------------------------------

/**
 * @brief 从 JSON 文本里抠出字符串字段的值
 *
 * 只处理 "key": "value" 这一种形态，够读 manifest 就行。
 * 不引入 cJSON 是为了少一个依赖——manifest 格式由我们自己的服务端决定，
 * 不需要通用解析器。
 *
 * @param json JSON 文本
 * @param key 字段名（不含引号）
 * @param[out] out 输出缓冲区
 * @param out_size 缓冲区容量
 * @return true 找到并成功提取
 */
static bool json_get_string(const char *json, const char *key, char *out, size_t out_size)
{
    char pattern[64];
    snprintf(pattern, sizeof(pattern), "\"%s\"", key);

    const char *p = strstr(json, pattern);
    if (!p) {
        return false;
    }
    p += strlen(pattern);

    // 跳过冒号与空白
    while (*p && (*p == ':' || *p == ' ' || *p == '\t')) {
        p++;
    }
    if (*p != '"') {
        return false;
    }
    p++;

    const char *end = strchr(p, '"');
    if (!end) {
        return false;
    }

    size_t len = (size_t)(end - p);
    if (len >= out_size) {
        len = out_size - 1;
    }
    memcpy(out, p, len);
    out[len] = '\0';
    return true;
}

/**
 * @brief 从 JSON 文本里抠出整数字段的值
 *
 * @return 找到则返回该值，否则返回 0
 */
static size_t json_get_number(const char *json, const char *key)
{
    char pattern[64];
    snprintf(pattern, sizeof(pattern), "\"%s\"", key);

    const char *p = strstr(json, pattern);
    if (!p) {
        return 0;
    }
    p += strlen(pattern);

    while (*p && (*p == ':' || *p == ' ' || *p == '\t')) {
        p++;
    }
    return (size_t)strtoul(p, NULL, 10);
}

// ---------------------------------------------------------------------------
// 版本查询
// ---------------------------------------------------------------------------

const char *ota_get_running_version(void)
{
    const esp_app_desc_t *desc = esp_app_get_description();
    return desc ? desc->version : "unknown";
}

esp_err_t ota_check_update(const char *base_url, const char *auth_token,
                           ota_check_result_t *result)
{
    if (!base_url || !result) {
        return ESP_ERR_INVALID_ARG;
    }
    memset(result, 0, sizeof(*result));

    strncpy(result->local_version, ota_get_running_version(),
            sizeof(result->local_version) - 1);

    char url[256];
    snprintf(url, sizeof(url), "%s/api/ota/manifest", base_url);

    char *buf = calloc(1, OTA_MANIFEST_BUF_SIZE);
    if (!buf) {
        return ESP_ERR_NO_MEM;
    }

    esp_http_client_config_t cfg = {
        .url = url,
        .timeout_ms = 10000,
    };
    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (!client) {
        free(buf);
        return ESP_FAIL;
    }

    if (auth_token && auth_token[0]) {
        esp_http_client_set_header(client, "X-Device-Token", auth_token);
    }

    esp_err_t ret = esp_http_client_open(client, 0);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "manifest 请求失败: %s", esp_err_to_name(ret));
        goto cleanup;
    }

    esp_http_client_fetch_headers(client);
    int status = esp_http_client_get_status_code(client);
    if (status != 200) {
        // 服务端没提供 OTA 接口是正常情况，降级为 warning
        ESP_LOGW(TAG, "manifest HTTP %d，跳过 OTA 检查", status);
        ret = ESP_FAIL;
        goto cleanup;
    }

    int read_len = esp_http_client_read(client, buf, OTA_MANIFEST_BUF_SIZE - 1);
    if (read_len <= 0) {
        ESP_LOGW(TAG, "manifest 响应为空");
        ret = ESP_FAIL;
        goto cleanup;
    }
    buf[read_len] = '\0';

    if (!json_get_string(buf, "version", result->remote_version,
                         sizeof(result->remote_version))) {
        ESP_LOGW(TAG, "manifest 缺少 version 字段");
        ret = ESP_FAIL;
        goto cleanup;
    }
    result->firmware_size = json_get_number(buf, "size");

    // 版本字符串不同就认为有更新，不做语义化比较
    result->update_available =
        (strcmp(result->remote_version, result->local_version) != 0);

    ESP_LOGI(TAG, "本地 %s / 远端 %s → %s", result->local_version,
             result->remote_version,
             result->update_available ? "有更新" : "已是最新");
    ret = ESP_OK;

cleanup:
    esp_http_client_close(client);
    esp_http_client_cleanup(client);
    free(buf);
    return ret;
}

// ---------------------------------------------------------------------------
// OTA 下载与写入
// ---------------------------------------------------------------------------

esp_err_t ota_perform_update(const char *firmware_url, const char *auth_token)
{
    if (!firmware_url) {
        return ESP_ERR_INVALID_ARG;
    }

    ESP_LOGI(TAG, "开始 OTA: %s", firmware_url);

    esp_http_client_config_t cfg = {
        .url = firmware_url,
        .timeout_ms = 30000,
        .buffer_size = OTA_WRITE_CHUNK_SIZE,
    };
    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (!client) {
        return ESP_FAIL;
    }

    if (auth_token && auth_token[0]) {
        esp_http_client_set_header(client, "X-Device-Token", auth_token);
    }

    esp_err_t ret = esp_http_client_open(client, 0);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "HTTP open 失败: %s", esp_err_to_name(ret));
        esp_http_client_cleanup(client);
        return ret;
    }

    esp_http_client_fetch_headers(client);
    int status = esp_http_client_get_status_code(client);
    if (status != 200) {
        ESP_LOGE(TAG, "HTTP %d", status);
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return ESP_FAIL;
    }

    // 取下一个可写 OTA 分区（当前运行 ota_0 则返回 ota_1，反之亦然）
    const esp_partition_t *update_partition = esp_ota_get_next_update_partition(NULL);
    if (!update_partition) {
        ESP_LOGE(TAG, "未找到可用 OTA 分区");
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return ESP_FAIL;
    }
    ESP_LOGI(TAG, "写入分区: %s @ 0x%lx (%lu bytes)", update_partition->label,
             update_partition->address, update_partition->size);

    esp_ota_handle_t ota_handle = 0;
    ret = esp_ota_begin(update_partition, OTA_SIZE_UNKNOWN, &ota_handle);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "esp_ota_begin 失败: %s", esp_err_to_name(ret));
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return ret;
    }

    uint8_t *buf = malloc(OTA_WRITE_CHUNK_SIZE);
    if (!buf) {
        esp_ota_abort(ota_handle);
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return ESP_ERR_NO_MEM;
    }

    size_t total_written = 0;
    int last_progress = -1;

    while (1) {
        int read_len = esp_http_client_read(client, (char *)buf, OTA_WRITE_CHUNK_SIZE);
        if (read_len < 0) {
            ESP_LOGE(TAG, "HTTP 读取失败");
            ret = ESP_FAIL;
            break;
        }
        if (read_len == 0) {
            // EOF
            break;
        }

        ret = esp_ota_write(ota_handle, buf, read_len);
        if (ret != ESP_OK) {
            ESP_LOGE(TAG, "OTA 写入失败: %s", esp_err_to_name(ret));
            break;
        }
        total_written += read_len;

        // 每 10KB 打一次进度
        int progress = (int)(total_written / 10240);
        if (progress != last_progress) {
            ESP_LOGI(TAG, "已下载 %u KB", (unsigned)(total_written / 1024));
            last_progress = progress;
        }
    }

    free(buf);
    esp_http_client_close(client);
    esp_http_client_cleanup(client);

    if (ret != ESP_OK) {
        esp_ota_abort(ota_handle);
        return ret;
    }

    ESP_LOGI(TAG, "下载完成，总计 %u 字节", (unsigned)total_written);

    ret = esp_ota_end(ota_handle);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "OTA 结束失败（可能镜像损坏）: %s", esp_err_to_name(ret));
        return ret;
    }

    // 标记为启动分区
    ret = esp_ota_set_boot_partition(update_partition);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "设置启动分区失败: %s", esp_err_to_name(ret));
        return ret;
    }

    ESP_LOGI(TAG, "OTA 完成，重启后运行新固件");
    return ESP_OK;
}

// ---------------------------------------------------------------------------
// 状态确认与回滚
// ---------------------------------------------------------------------------

bool ota_is_pending_verify(void)
{
    const esp_partition_t *running = esp_ota_get_running_partition();
    esp_ota_img_states_t state;
    if (esp_ota_get_state_partition(running, &state) != ESP_OK) {
        return false;
    }
    return (state == ESP_OTA_IMG_PENDING_VERIFY);
}

esp_err_t ota_mark_valid(void)
{
    if (!ota_is_pending_verify()) {
        // 不处于待确认状态，无需操作
        return ESP_OK;
    }

    esp_err_t ret = esp_ota_mark_app_valid_cancel_rollback();
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "固件已确认有效，取消回滚");
    } else {
        ESP_LOGW(TAG, "确认失败: %s", esp_err_to_name(ret));
    }
    return ret;
}

esp_err_t ota_rollback_and_reboot(void)
{
    ESP_LOGW(TAG, "触发回滚并重启");
    const esp_partition_t *last_valid = esp_ota_get_last_invalid_partition();
    if (!last_valid) {
        ESP_LOGE(TAG, "未找到上一个有效分区");
        return ESP_FAIL;
    }

    esp_err_t ret = esp_ota_set_boot_partition(last_valid);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "回滚设置失败: %s", esp_err_to_name(ret));
        return ret;
    }

    esp_restart();
    return ESP_OK; // 不会执行到这里
}
