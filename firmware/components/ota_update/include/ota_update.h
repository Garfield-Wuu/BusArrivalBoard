/**
 * @file ota_update.h
 * @brief OTA 固件升级
 *
 * 双分区交替升级，带自动回滚保护：
 *   - 新固件写入非活动分区（ota_0/ota_1 交替）
 *   - 重启后新固件必须调用 ota_mark_valid() 确认自己能跑
 *   - 未确认就重启 → bootloader 自动回滚到旧版本
 *
 * 这个回滚机制是墙上设备的救命绳：刷了个连不上 WiFi 的固件，
 * 设备会自己退回上一版，不用把它拆下来接 USB。
 */

#pragma once

#include "esp_err.h"
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/// 版本字符串最大长度
#define OTA_VERSION_MAX_LEN 32

/**
 * @brief OTA 检查结果
 */
typedef struct {
    bool update_available;                  ///< 服务端有新版本
    char remote_version[OTA_VERSION_MAX_LEN]; ///< 服务端版本号
    char local_version[OTA_VERSION_MAX_LEN];  ///< 当前运行版本
    size_t firmware_size;                   ///< 新固件字节数（0 表示服务端未提供）
} ota_check_result_t;

/**
 * @brief 查询服务端是否有新固件
 *
 * 向 <base_url>/api/ota/manifest 发 GET，期望返回 JSON:
 *   {"version": "0.2.0", "size": 912345, "url": "/api/ota/firmware.bin"}
 *
 * 只比较版本字符串是否相同，不做语义化版本大小比较——
 * 服务端说什么版本就是什么版本，避免设备端自作聪明。
 *
 * @param base_url 服务端基地址，如 "http://192.168.1.100:8000"
 * @param auth_token 可选认证 token，NULL 表示不带
 * @param[out] result 检查结果
 * @return
 *   - ESP_OK 查询成功（是否有更新看 result->update_available）
 *   - ESP_ERR_INVALID_ARG 参数无效
 *   - ESP_FAIL HTTP 或 JSON 解析失败
 */
esp_err_t ota_check_update(const char *base_url, const char *auth_token,
                           ota_check_result_t *result);

/**
 * @brief 下载并写入新固件（阻塞，耗时取决于固件大小与网速）
 *
 * 流式写入非活动分区，不需要把整个固件读进内存。
 * 写完会校验镜像有效性，然后把该分区标记为下次启动分区。
 *
 * **本函数返回 ESP_OK 后需要手动重启才生效。**
 *
 * @param firmware_url 固件完整 URL
 * @param auth_token 可选认证 token
 * @return
 *   - ESP_OK 写入成功，重启后运行新固件
 *   - ESP_ERR_INVALID_SIZE 固件超出分区容量
 *   - ESP_ERR_OTA_VALIDATE_FAILED 镜像校验失败（下载损坏）
 *   - ESP_FAIL HTTP 或写入错误
 */
esp_err_t ota_perform_update(const char *firmware_url, const char *auth_token);

/**
 * @brief 确认当前固件工作正常，取消回滚
 *
 * **新固件启动后必须调用**，否则下次重启会被 bootloader 回滚。
 * 应该在确认核心功能可用之后调用——比如 WiFi 连上、成功拉到一帧之后，
 * 而不是 app_main 一进来就调，那样等于放弃了回滚保护。
 *
 * @return
 *   - ESP_OK 已确认（或当前不处于待确认状态，无需操作）
 *   - 其他 esp_ota_mark_app_valid_cancel_rollback 的错误码
 */
esp_err_t ota_mark_valid(void);

/**
 * @brief 主动回滚到上一个固件并重启
 *
 * 用于新固件自检发现自己有问题时主动退回。
 *
 * @return 不返回（成功则重启）；失败时返回错误码
 */
esp_err_t ota_rollback_and_reboot(void);

/**
 * @brief 判断当前固件是否处于"待确认"状态
 *
 * @return true 表示这是新刷入的固件，还没调用 ota_mark_valid()
 */
bool ota_is_pending_verify(void);

/**
 * @brief 获取当前运行固件的版本号
 *
 * 版本来自 CMake 的 PROJECT_VER，通过 esp_app_desc 读取。
 *
 * @return 版本字符串（静态存储，不需释放）
 */
const char *ota_get_running_version(void);

#ifdef __cplusplus
}
#endif
