/**
 * @file http_frame_client.h
 * @brief HTTP 帧下载客户端
 *
 * 从 BusArrivalBoard 服务端拉取预渲染好的墨水屏画面。
 *
 * 关键设计：
 *   - **ETag 条件请求**：画面未变时服务端返回 304，跳过下载与刷屏，
 *     这是电池供电设备最重要的省电手段
 *   - **ETag 持久化**：调用方负责把 etag 存进 RTC 内存或 NVS，
 *     深度睡眠唤醒后仍能命中缓存
 *   - **流式接收**：15KB 帧数据直接写入调用方缓冲区，不做二次拷贝
 */

#pragma once

#include "esp_err.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/// ETag 字符串最大长度（含引号与结束符）
#define HTTP_FRAME_ETAG_MAX_LEN 64

/**
 * @brief 帧下载请求参数
 */
typedef struct {
    const char *url;        ///< 完整 URL，如 "http://192.168.1.100:8000/api/epd/frame.bin"
    const char *etag;       ///< 上次收到的 ETag，为 NULL 或空串时不发条件请求
    const char *auth_token; ///< 可选：X-Device-Token 头的值，NULL 表示不带认证
    uint8_t *buffer;        ///< 接收缓冲区，需由调用方分配
    size_t buffer_size;     ///< 缓冲区容量（字节）
    int timeout_ms;         ///< 超时（毫秒），建议 15000
} http_frame_request_t;

/**
 * @brief 帧下载结果
 */
typedef struct {
    bool not_modified;                        ///< true 表示服务端返回 304，buffer 未被写入
    size_t bytes_received;                    ///< 实际写入 buffer 的字节数
    char etag[HTTP_FRAME_ETAG_MAX_LEN];       ///< 服务端返回的 ETag（原样保留引号）
    int http_status;                          ///< HTTP 状态码，便于诊断
    bool frame_stale;                         ///< 服务端标记数据已降级（X-Frame-Stale: 1）
    uint16_t frame_width;                     ///< 来自 X-Frame-Width，0 表示服务端未提供
    uint16_t frame_height;                    ///< 来自 X-Frame-Height
} http_frame_result_t;

/**
 * @brief 下载一帧画面
 *
 * 若 request->etag 非空，会发送 If-None-Match 条件请求。服务端画面未变
 * 时返回 304，此时 result->not_modified 为 true，调用方应跳过刷屏。
 *
 * @param request 请求参数
 * @param[out] result 下载结果
 * @return
 *   - ESP_OK 请求成功（含 304，需检查 result->not_modified）
 *   - ESP_ERR_INVALID_ARG 参数无效
 *   - ESP_ERR_INVALID_SIZE 响应体超出 buffer_size
 *   - ESP_ERR_TIMEOUT 请求超时
 *   - ESP_FAIL 其他 HTTP 错误（状态码见 result->http_status）
 */
esp_err_t http_frame_download(const http_frame_request_t *request, http_frame_result_t *result);

#ifdef __cplusplus
}
#endif
