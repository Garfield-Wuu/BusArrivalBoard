# OTA Update 组件

双分区空中升级，带自动回滚保护。

## 核心设计

**回滚保护**是这个组件存在的唯一理由——墙上设备刷了个连不上 WiFi 的固件，自己会退回上一版，不用拆下来接 USB。

流程：
1. `ota_check_update()` 查服务端有没有新版本
2. `ota_perform_update()` 下载写入非活动分区（ota_0/ota_1 交替）
3. 重启后新固件运行
4. **新固件必须调用 `ota_mark_valid()` 确认自己能跑**
5. 未确认就又重启 → bootloader 自动回滚旧版本

## API 用例

```c
#include "ota_update.h"

// 1. 查更新
ota_check_result_t check;
if (ota_check_update("http://192.168.1.100:8000", NULL, &check) == ESP_OK) {
    if (check.update_available) {
        ESP_LOGI(TAG, "发现新版本: %s", check.remote_version);
        
        // 2. 下载并写入
        char url[256];
        snprintf(url, sizeof(url), "http://192.168.1.100:8000/api/ota/firmware.bin");
        if (ota_perform_update(url, NULL) == ESP_OK) {
            ESP_LOGI(TAG, "OTA 完成，5 秒后重启");
            vTaskDelay(pdMS_TO_TICKS(5000));
            esp_restart();
        }
    }
}

// 3. 新固件启动后，确认核心功能可用再标记有效
void app_main(void) {
    if (ota_is_pending_verify()) {
        ESP_LOGW(TAG, "新固件待验证");
        
        // 先跑核心流程：WiFi 连接 + 成功拉一帧
        if (wifi_connect(15000) == ESP_OK && test_pull_frame() == ESP_OK) {
            ota_mark_valid();  // 确认有效，取消回滚
            ESP_LOGI(TAG, "新固件验证通过");
        } else {
            ESP_LOGE(TAG, "核心功能失败，触发回滚");
            ota_rollback_and_reboot();
        }
    }
    
    // 正常业务逻辑...
}
```

## 服务端要求

需要两个接口：

**1. GET /api/ota/manifest** — 版本清单
```json
{
  "version": "0.2.0",
  "size": 912345,
  "url": "/api/ota/firmware.bin"
}
```

**2. GET /api/ota/firmware.bin** — 固件二进制

可以用 X-Device-Token 头做认证（与帧接口一致）。

## 回滚时序图

```
时刻 | 分区状态      | 说明
-----|--------------|-----
T0   | ota_0 (有效) | 旧固件运行中
T1   | ota_1 (写入) | 下载新固件
T2   | 重启         | bootloader 尝试 ota_1
T3   | ota_1 运行   | 状态 = PENDING_VERIFY
T4   | 调用 mark_valid() | 确认 → 状态变 VALID
-----|--------------|-----
如果 T3 → T5 之间再次重启且未确认：
T5   | 重启         | bootloader 检测到 PENDING_VERIFY 超时
T6   | ota_0 恢复   | 自动回退旧固件
```

## 注意事项

1. **分区必须是双 OTA**（partitions.csv 有 ota_0 和 ota_1）
2. **新固件不要在 app_main 开头立即 mark_valid**，那样回滚保护就失效了
3. **固件必须 < 1.4MB**（当前分区大小限制）
4. 首次刷机用 idf.py flash，之后才能用 OTA
