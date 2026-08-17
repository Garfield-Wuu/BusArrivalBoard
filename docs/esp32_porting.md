# ESP32 移植指南

## 概述

本文档指导将 BusArrivalBoard Python 项目移植到 ESP32 平台，配合墨水屏实现实时公交到站显示。

**核心挑战：**
- HTTPS 请求与证书验证
- MD5 签名生成
- AES-256-ECB 解密
- 大响应体内存管理（10-50 KB JSON）
- 墨水屏局部刷新与低功耗设计

---

## 架构对照表

| Python 模块 | ESP32 实现方案 | 说明 |
|------------|---------------|------|
| `requests` | `esp_http_client` (ESP-IDF) / `HTTPClient` (Arduino) | HTTPS GET 请求，支持 TLS |
| `cryptography` (MD5) | `mbedtls_md5_*` (mbedTLS) | ESP-IDF 内置，Arduino 可用 `<mbedtls/md5.h>` |
| `cryptography` (AES) | `mbedtls_aes_*` (mbedTLS) | AES-256-ECB 模式解密 + PKCS7 去填充 |
| `pydantic` 模型 | `ArduinoJson` / `cJSON` | JSON 解析与数据提取 |
| `rich` 终端输出 | `GxEPD2` / `U8g2` | 墨水屏渲染库 |
| Python 字符串处理 | `String` / `std::string` | 大括号配对、Base64 解码 |

---

## 关键代码骨架

### 1. MD5 签名生成

车来了 API 签名算法：
1. 将参数按**插入顺序**拼接为 `"key1"="value1"&"key2"="value2"&...`
2. 末尾追加固定盐 `qwihrnbtmj`
3. 计算 MD5，输出十六进制小写

```cpp
#include <mbedtls/md5.h>

// 固定盐值
#define SIGN_SALT "qwihrnbtmj"

/**
 * 生成车来了 API 签名
 * @param params 参数键值对（需保持插入顺序，建议用 std::vector<std::pair<String, String>>）
 * @return 32 位小写 MD5 签名
 */
String generateSignature(const std::vector<std::pair<String, String>>& params) {
    String signString = "";
    
    // 拼接参数：\"key\"=\"value\"&...
    for (size_t i = 0; i < params.size(); i++) {
        signString += "\"" + params[i].first + "\"=\"" + params[i].second + "\"";
        if (i < params.size() - 1) {
            signString += "&";
        }
    }
    
    // 追加盐值（不加 &）
    signString += SIGN_SALT;
    
    // 计算 MD5
    unsigned char digest[16];
    mbedtls_md5_context ctx;
    mbedtls_md5_init(&ctx);
    mbedtls_md5_starts(&ctx);
    mbedtls_md5_update(&ctx, (const unsigned char*)signString.c_str(), signString.length());
    mbedtls_md5_finish(&ctx, digest);
    mbedtls_md5_free(&ctx);
    
    // 转十六进制小写
    char hexOutput[33];
    for (int i = 0; i < 16; i++) {
        sprintf(&hexOutput[i * 2], "%02x", digest[i]);
    }
    hexOutput[32] = '\0';
    
    return String(hexOutput);
}
```

**使用示例：**
```cpp
std::vector<std::pair<String, String>> params = {
    {"s", "h5"},
    {"wxs", "wx_app"},
    {"cityId", "014"},
    {"key", "M592"}
};
String cryptoSign = generateSignature(params);
// 将 cryptoSign 作为额外参数附加到 URL
```

---

### 2. AES-256-ECB 解密

车来了加密数据格式：
- 密钥：**32 字节 ASCII 字面量** `FF32AE65FBFD19414EAAFF6291A54B42`（注意：不是 hex 解码！）
- 模式：AES-256-ECB
- 填充：PKCS7
- 传输：Base64 编码

```cpp
#include <mbedtls/aes.h>
#include <mbedtls/base64.h>

// AES 密钥（32 字节 ASCII 字符串）
const unsigned char AES_KEY[32] = "FF32AE65FBFD19414EAAFF6291A54B42";

/**
 * AES-256-ECB 解密车来了响应数据
 * @param base64Ciphertext Base64 编码的密文
 * @return 解密后的明文 JSON 字符串（空字符串表示失败）
 */
String decryptAesEcb(const String& base64Ciphertext) {
    // 1. Base64 解码
    size_t outLen;
    unsigned char* encrypted = nullptr;
    
    // 计算解码后长度
    int ret = mbedtls_base64_decode(nullptr, 0, &outLen, 
                                      (const unsigned char*)base64Ciphertext.c_str(), 
                                      base64Ciphertext.length());
    if (ret != MBEDTLS_ERR_BASE64_BUFFER_TOO_SMALL) {
        return "";
    }
    
    encrypted = (unsigned char*)malloc(outLen);
    if (!encrypted) return "";
    
    ret = mbedtls_base64_decode(encrypted, outLen, &outLen, 
                                  (const unsigned char*)base64Ciphertext.c_str(), 
                                  base64Ciphertext.length());
    if (ret != 0) {
        free(encrypted);
        return "";
    }
    
    // 2. AES-256-ECB 解密
    mbedtls_aes_context aes;
    mbedtls_aes_init(&aes);
    mbedtls_aes_setkey_dec(&aes, AES_KEY, 256);
    
    size_t blockCount = outLen / 16;
    unsigned char* decrypted = (unsigned char*)malloc(outLen);
    if (!decrypted) {
        free(encrypted);
        mbedtls_aes_free(&aes);
        return "";
    }
    
    for (size_t i = 0; i < blockCount; i++) {
        mbedtls_aes_crypt_ecb(&aes, MBEDTLS_AES_DECRYPT, 
                               encrypted + i * 16, 
                               decrypted + i * 16);
    }
    mbedtls_aes_free(&aes);
    free(encrypted);
    
    // 3. PKCS7 去填充
    unsigned char paddingLen = decrypted[outLen - 1];
    if (paddingLen < 1 || paddingLen > 16) {
        free(decrypted);
        return "";
    }
    
    size_t plaintextLen = outLen - paddingLen;
    decrypted[plaintextLen] = '\0';
    
    String result = String((char*)decrypted);
    free(decrypted);
    return result;
}
```

---

### 3. YGKJ 信封剥离

车来了响应格式：`**YGKJ{...JSON...}YGKJ##`

**关键：** JSON 内部包含嵌套大括号，必须用栈式配对扫描，不能简单取 `find('{')` 到 `rfind('}')`。

```cpp
/**
 * 从车来了响应包装体中提取 JSON
 * @param response 原始响应文本
 * @return JSON 字符串（不含前后缀）
 */
String extractJson(const String& response) {
    int start = response.indexOf('{');
    if (start == -1) {
        Serial.println("ERROR: 未找到 JSON 起始符");
        return "";
    }
    
    int depth = 0;
    bool inString = false;
    bool escaped = false;
    
    for (size_t i = start; i < response.length(); i++) {
        char ch = response.charAt(i);
        
        if (inString) {
            if (escaped) {
                escaped = false;
            } else if (ch == '\\') {
                escaped = true;
            } else if (ch == '"') {
                inString = false;
            }
            continue;
        }
        
        if (ch == '"') {
            inString = true;
        } else if (ch == '{') {
            depth++;
        } else if (ch == '}') {
            depth--;
            if (depth == 0) {
                // 找到完整 JSON
                return response.substring(start, i + 1);
            }
        }
    }
    
    Serial.println("ERROR: JSON 大括号未闭合");
    return "";
}
```

---

### 4. ArduinoJson 解析实时车辆

```cpp
#include <ArduinoJson.h>

/**
 * 解析实时公交数据
 * @param jsonString 解密后的 JSON 字符串
 */
void parseRealtimeBuses(const String& jsonString) {
    // 估算 JSON 文档容量（根据实际响应大小调整）
    // 使用 https://arduinojson.org/v6/assistant/ 计算
    DynamicJsonDocument doc(16384);  // 16 KB，适配中等规模响应
    
    DeserializationError error = deserializeJson(doc, jsonString);
    if (error) {
        Serial.print("JSON 解析失败: ");
        Serial.println(error.c_str());
        return;
    }
    
    // 提取线路信息
    JsonObject line = doc["line"];
    String lineName = line["name"].as<String>();
    int totalStations = line["stationsNum"] | 0;
    
    // 提取车辆数组
    JsonArray buses = doc["buses"];
    int targetOrder = doc["targetOrder"] | 0;
    
    Serial.printf("线路: %s, 目标站序: %d\n", lineName.c_str(), targetOrder);
    
    for (JsonObject bus : buses) {
        String busId = bus["busId"].as<String>();
        int order = bus["order"] | 0;
        
        // 计算剩余站数（环线支持）
        int remaining;
        if (order <= targetOrder) {
            remaining = targetOrder - order;
        } else if (totalStations > 0) {
            remaining = (targetOrder - order + totalStations) % totalStations;
        } else {
            remaining = 0;
        }
        
        // 提取 ETA（仅前 1-2 辆有 travels 数组）
        JsonArray travels = bus["travels"];
        if (!travels.isNull() && travels.size() > 0) {
            JsonObject travel = travels[0];
            int travelTime = travel["travelTime"] | 0;
            String recommTip = travel["recommTip"].as<String>();
            
            Serial.printf("  🚌 %s | 剩余 %d 站 | 预计 %d 秒 (%s)\n", 
                          busId.c_str(), remaining, travelTime, recommTip.c_str());
        } else {
            Serial.printf("  🚌 %s | 剩余 %d 站 | 无 ETA\n", busId.c_str(), remaining);
        }
    }
}
```

**注意事项：**
- `DynamicJsonDocument` 容量不足会导致解析失败，实测深圳 M592 响应约 12 KB
- 使用 [ArduinoJson Assistant](https://arduinojson.org/v6/assistant/) 根据实际 JSON 估算所需容量
- 考虑使用 `StaticJsonDocument` 在栈上分配以避免堆碎片（需 ESP32-S3 等大内存芯片）

---

## 内存与性能优化

### 内存需求估算

| 组件 | 内存需求 | 说明 |
|------|---------|------|
| HTTPS 响应缓冲 | 20-50 KB | 完整响应体，考虑流式处理 |
| ArduinoJson 文档 | 12-20 KB | 根据 JSON 深度和数组长度 |
| TLS 握手栈 | 16-32 KB | mbedTLS 需要较大栈空间 |
| 墨水屏帧缓冲 | 15-30 KB | 4.2 寸 400×300 ≈ 15 KB (1-bit) |
| **总计** | **60-130 KB** | ESP32 基本款 (320 KB SRAM) 紧张 |

### 优化策略

#### 1. PSRAM 扩展（强烈建议）
- 选用 ESP32-S3 或带 PSRAM 的开发板（额外 2-8 MB）
- 在 `sdkconfig` 中启用 `CONFIG_SPIRAM_SUPPORT`
- 大缓冲区分配到 PSRAM：
  ```cpp
  char* buffer = (char*)heap_caps_malloc(50000, MALLOC_CAP_SPIRAM);
  ```

#### 2. 流式 HTTP 处理
避免一次性读取完整响应体：
```cpp
esp_http_client_config_t config = {
    .url = "https://web.chelaile.net.cn/api/...",
    .event_handler = http_event_handler,  // 回调处理分块数据
};
```

#### 3. JSON 过滤解析
仅提取必要字段，忽略冗余数据：
```cpp
// 使用 ArduinoJson 过滤器减少内存占用
StaticJsonDocument<200> filter;
filter["buses"][0]["busId"] = true;
filter["buses"][0]["order"] = true;
filter["buses"][0]["travels"][0]["travelTime"] = true;

DynamicJsonDocument doc(8192);
deserializeJson(doc, jsonString, DeserializationOption::Filter(filter));
```

#### 4. HTTPS 证书验证权衡
```cpp
// 方案 A：跳过证书验证（不推荐，存在中间人攻击风险）
client.setInsecure();

// 方案 B：证书固定（推荐）
const char* root_ca = \
"-----BEGIN CERTIFICATE-----\n" \
"MIIEdTCCA12g..."; // 车来了服务器根证书
client.setCACert(root_ca);
```
**安全性说明：** `setInsecure()` 会降低安全性，仅适用于测试环境或低风险场景。生产环境建议固定证书或使用系统根证书。

---

## 低功耗设计

### Deep Sleep 唤醒周期

```cpp
#include <esp_sleep.h>

#define REFRESH_INTERVAL_SEC 60  // 刷新间隔（秒）

void enterDeepSleep() {
    Serial.println("进入深度睡眠...");
    esp_sleep_enable_timer_wakeup(REFRESH_INTERVAL_SEC * 1000000ULL);
    esp_deep_sleep_start();
}

void loop() {
    // 1. 连接 Wi-Fi
    connectWiFi();
    
    // 2. 获取实时数据
    String data = fetchBusData();
    
    // 3. 更新墨水屏
    updateDisplay(data);
    
    // 4. 断开 Wi-Fi，进入睡眠
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    enterDeepSleep();
}
```

**功耗估算：**
- Deep Sleep: 10-150 μA（ESP32 型号差异）
- Wi-Fi 活动: 80-160 mA（持续 5-15 秒）
- 墨水屏刷新: 30-50 mA（持续 2-5 秒）

### 墨水屏刷新策略

| 刷新类型 | 速度 | 功耗 | 残影 | 适用场景 |
|---------|------|------|------|----------|
| 全刷 (Full) | 2-5 秒 | 高 | 无 | 首次显示、每 10 次循环 |
| 局刷 (Partial) | 0.5-1 秒 | 低 | 轻微累积 | ETA 数字更新 |
| 快刷 (Fast) | < 1 秒 | 低 | 明显 | 部分型号支持 |

```cpp
GxEPD2_BW<GxEPD2_420, GxEPD2_420::HEIGHT> display(/*pins*/);

int refreshCount = 0;

void updateDisplay(const String& data) {
    if (refreshCount % 10 == 0) {
        // 每 10 次循环全刷一次，清除残影
        display.setFullWindow();
        display.firstPage();
        do {
            renderContent(data);
        } while (display.nextPage());
    } else {
        // 局部刷新 ETA 区域
        display.setPartialWindow(10, 80, 200, 50);  // x, y, w, h
        display.firstPage();
        do {
            renderETAOnly(data);
        } while (display.nextPage());
    }
    refreshCount++;
}
```

### 按运营时段调整轮询

```cpp
void loop() {
    struct tm timeinfo;
    if (!getLocalTime(&timeinfo)) {
        Serial.println("时间同步失败");
        return;
    }
    
    int hour = timeinfo.tm_hour;
    
    if (hour >= 6 && hour < 23) {
        // 运营时段：60 秒刷新
        fetchAndUpdate();
        esp_sleep_enable_timer_wakeup(60 * 1000000ULL);
    } else {
        // 夜间停运：跳过更新，睡眠到 5:55
        int sleepMinutes = (6 * 60 - 5) - (hour * 60 + timeinfo.tm_min);
        if (sleepMinutes < 0) sleepMinutes += 24 * 60;
        esp_sleep_enable_timer_wakeup(sleepMinutes * 60 * 1000000ULL);
    }
    
    esp_deep_sleep_start();
}
```

---

## 分阶段移植清单

### 阶段 1：网络连通性验证
**目标：** 建立 HTTPS 连接，获取原始响应

```cpp
// 验证代码
HTTPClient http;
http.begin("https://web.chelaile.net.cn/wwd/ncitylist");
int httpCode = http.GET();
if (httpCode == 200) {
    String payload = http.getString();
    Serial.println(payload);  // 应看到城市列表 JSON
}
http.end();
```

**验证点：**
- [ ] Wi-Fi 连接成功
- [ ] HTTPS 请求返回 200
- [ ] 响应包含 `"cityList"` 字段

---

### 阶段 2：签名算法验证
**目标：** 生成正确的 `cryptoSign`，获取搜索结果

```cpp
std::vector<std::pair<String, String>> params = {
    {"s", "h5"}, {"wxs", "wx_app"}, {"sign", "1"},
    {"cityId", "014"}, {"key", "M592"}  // 深圳是 014，不是 034（034 是上海）
    // ...（参考 constants.py 添加所有 DEFAULT_PARAMS）
};
String sign = generateSignature(params);
Serial.println("签名: " + sign);

// 构造 URL
String url = "https://web.chelaile.net.cn/api/bus/query!nSearch.action?";
for (auto& p : params) {
    url += p.first + "=" + p.second + "&";
}
url += "cryptoSign=" + sign;

// 发送请求
HTTPClient http;
http.begin(url);
// 设置所有必需请求头（参考 constants.py REQUEST_HEADERS）
http.addHeader("User-Agent", "Mozilla/5.0 ...");  // 完整 UA
http.addHeader("Host", "web.chelaile.net.cn");
// ...
```

**验证点：**
- [ ] 签名生成与 Python 版本一致（可用相同参数对比）
- [ ] API 返回 `"status":"00"`（非 400 错误）
- [ ] 响应包含 `**YGKJ{` 前缀

**常见错误：**
- 缺少必需请求头 → HTTP 400
- 参数顺序错误 → 签名校验失败
- 签名字符串格式错误（引号缺失、分隔符错误）

---

### 阶段 3：解密逻辑验证
**目标：** 正确解密 `encryptResult` 字段

```cpp
String jsonStr = extractJson(response);
DynamicJsonDocument doc(8192);
deserializeJson(doc, jsonStr);

String encrypted = doc["jsonr"]["data"]["encryptResult"];
String decrypted = decryptAesEcb(encrypted);
Serial.println("解密结果: " + decrypted);

// 验证解密后的 JSON 可解析
DynamicJsonDocument innerDoc(16384);
deserializeJson(innerDoc, decrypted);
Serial.println(innerDoc["line"]["name"].as<String>());
```

**验证点：**
- [ ] Base64 解码成功
- [ ] AES 解密输出有效 UTF-8 字符串
- [ ] PKCS7 去填充正确（无乱码尾部）
- [ ] 二次 JSON 解析成功

---

### 阶段 4：完整业务流程
**目标：** 实现城市搜索 → 线路搜索 → 站点列表 → 实时数据

```cpp
void setup() {
    Serial.begin(115200);
    connectWiFi();
    
    // 1. 搜索城市
    String cityId = searchCity("深圳");
    
    // 2. 搜索线路
    String lineId = searchLine(cityId, "M592");
    
    // 3. 获取站点列表
    Station targetStation = getStationByName(cityId, lineId, "安翼嘉寓");
    
    // 4. 获取实时数据
    String realtimeData = getRealtimeBuses(cityId, lineId, 
                                            targetStation.id, 
                                            targetStation.order,
                                            targetStation.lat, 
                                            targetStation.lng);
    
    // 5. 解析并打印
    parseRealtimeBuses(realtimeData);
}
```

**验证点：**
- [ ] 所有 API 调用返回有效数据
- [ ] 环线线路（如 M592）剩余站数计算正确
- [ ] 最近 1-2 辆车有 `travels` 预测

---

### 阶段 5：墨水屏渲染
**目标：** 将数据显示到墨水屏

```cpp
#include <GxEPD2_BW.h>
#include <Fonts/FreeSansBold18pt7b.h>

void renderContent(const JsonDocument& doc) {
    display.fillScreen(GxEPD_WHITE);
    display.setTextColor(GxEPD_BLACK);
    
    // 线路名（大字体）
    display.setFont(&FreeSansBold18pt7b);
    display.setCursor(10, 40);
    display.print(doc["line"]["name"].as<String>());
    
    // 站点名
    display.setFont(/* 中等字体 */);
    display.setCursor(10, 70);
    display.print("前往：" + doc["line"]["endSn"].as<String>());
    
    // 前两班车 ETA
    JsonArray buses = doc["buses"];
    int y = 110;
    for (int i = 0; i < 2 && i < buses.size(); i++) {
        JsonObject bus = buses[i];
        JsonArray travels = bus["travels"];
        
        if (!travels.isNull() && travels.size() > 0) {
            int minutes = travels[0]["travelTime"].as<int>() / 60;
            String tip = travels[0]["recommTip"].as<String>();
            
            display.setCursor(10, y);
            display.printf("🚌 %d 分钟后 (%s)", minutes, tip.c_str());
        } else {
            display.setCursor(10, y);
            display.print("🚌 暂无预测");
        }
        y += 40;
    }
    
    // 更新时间
    display.setFont(/* 小字体 */);
    display.setCursor(10, 280);
    display.print("更新: " + getFormattedTime());
}
```

**验证点：**
- [ ] 中文字体正确显示（需使用支持中文的字体文件）
- [ ] 局部刷新无残影累积
- [ ] 刷新时间在可接受范围（< 5 秒全刷）

---

### 阶段 6：低功耗集成
**目标：** 实现 Deep Sleep 循环

**验证点：**
- [ ] Deep Sleep 电流 < 200 μA
- [ ] 定时唤醒准确（误差 < 1 秒）
- [ ] 唤醒后 Wi-Fi 重连成功
- [ ] 墨水屏内容保持（断电后仍显示）

**测试方法：**
- 使用万用表测量电流（串联在电源正极）
- 记录 10 个唤醒周期的实际间隔
- 计算预期续航时间（见硬件文档）

---

## 故障排查

### 常见问题

| 症状 | 可能原因 | 解决方案 |
|------|---------|---------|
| HTTP 400 错误 | 缺少必需请求头 | 完整复制 `constants.py` 中的 `REQUEST_HEADERS` |
| 签名校验失败 | 参数顺序错误或盐值错误 | 对比 Python 版本生成的签名，确认参数拼接格式 |
| AES 解密乱码 | 密钥使用错误（hex 解码） | 密钥是 ASCII 字面量，不要做 hex 转换 |
| JSON 解析失败 | 大括号配对错误 | 使用栈式扫描算法，不要用 `indexOf/lastIndexOf` |
| 内存不足崩溃 | 堆碎片或缓冲区过小 | 启用 PSRAM，使用流式处理 |
| Wi-Fi 重连慢 | Deep Sleep 后 DHCP 超时 | 静态 IP 或减少 DHCP 超时时间 |
| 墨水屏无响应 | SPI 引脚冲突或供电不足 | 检查接线，确保 3.3V 稳定供电 |

### 调试工具

```cpp
// 启用 ESP-IDF 日志
esp_log_level_set("*", ESP_LOG_DEBUG);

// 打印堆内存状态
Serial.printf("Free heap: %d bytes\n", ESP.getFreeHeap());
Serial.printf("Max alloc: %d bytes\n", ESP.getMaxAllocHeap());

// 监控 HTTPS 事件
esp_http_client_set_event_handler(client, [](esp_http_client_event_t *evt) {
    Serial.printf("HTTP Event: %d\n", evt->event_id);
});
```

---

## 参考资源

- **ESP-IDF 官方文档：** https://docs.espressif.com/projects/esp-idf/
- **mbedTLS 示例：** `esp-idf/examples/protocols/https_mbedtls/`
- **ArduinoJson 容量计算器：** https://arduinojson.org/v6/assistant/
- **GxEPD2 墨水屏库：** https://github.com/ZinggJM/GxEPD2
- **车来了 API 协议分析：** 见项目 `chelaile_sdk/` 源码注释

---

## 附录：完整端点列表

| 端点 | 用途 | 需签名 | 需解密 |
|------|------|-------|--------|
| `/wwd/ncitylist` | 城市列表 | 否 | 否 |
| `/bus/query!nSearch.action` | 搜索线路 | 是 | 是 |
| `/bus/line!encryptedLineDetail.action` | 站点列表 | 是 | 是 |
| `/bus/line!encryptedBusDetail.action` | 实时车辆 | 是 | 是 |

**BASE URL：** `https://web.chelaile.net.cn/api`（城市列表端点除外，使用 `https://web.chelaile.net.cn`）
