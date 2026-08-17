# EPD Driver 组件

墨水屏 SPI 驱动，当前支持：
- **UC8176** (4.2" 黑白 400×300) — 微雪 / GDEW042T2

## API

```c
#include "epd_driver.h"

epd_config_t config = {
    .spi_host = SPI2_HOST,
    .pin_cs = 10,
    .pin_dc = 8,
    .pin_rst = 7,
    .pin_busy = 9,
    .model = EPD_MODEL_UC8176_BW_42,
    .width = 400,
    .height = 300,
};

epd_handle_t epd;
ESP_ERROR_CHECK(epd_init(&config, &epd));

// 刷新画面（framebuffer: 15000 字节 = 400×300/8）
ESP_ERROR_CHECK(epd_display_frame(epd, framebuffer, 15000));

// 进深度睡眠（< 1µA）
ESP_ERROR_CHECK(epd_sleep(epd));

// 释放资源
epd_deinit(epd);
```

## 位图格式

单色位图，MSB first，1 bit = 1 像素：
- `0` = 白色
- `1` = 黑色

顺序：从左上角按行扫描，每 8 个像素一个字节。

例：400×300 屏幕
- 总字节数：`400 × 300 / 8 = 15000`
- 第 1 行前 8 像素：`framebuffer[0]`（bit 7 = 左上角）
- 第 2 行前 8 像素：`framebuffer[50]`（400/8 = 50 字节/行）

## 时序

| 操作 | 耗时 |
|------|------|
| 初始化 | ~200ms |
| 刷新（黑白） | ~4 秒 |
| 刷新（三色） | ~15-20 秒 |
| 进深度睡眠 | <100ms |

## 引脚定义（ESP32-S3 推荐）

| 功能 | GPIO | 说明 |
|------|------|------|
| SCK | 12 | SPI 时钟 |
| MOSI | 11 | SPI 数据 |
| CS | 10 | 片选（低有效） |
| DC | 8 | 0=命令，1=数据 |
| RST | 7 | 复位（低有效） |
| BUSY | 9 | 1=忙，0=空闲 |

## 扩展新型号

新增屏幕只需：
1. 在 `epd_driver.h` 枚举中加型号
2. 写初始化函数（参考 `epd_uc8176_init_bw`）
3. 在 `epd_init` 中分发

三色屏需调用 `DTM1` + `DTM2` 两次发送黑/红通道。

## 调试

设置日志级别：
```c
esp_log_level_set("epd_driver", ESP_LOG_DEBUG);
```

常见问题：
- **BUSY 超时**：检查接线、屏幕供电（3.3V 稳定）
- **刷新无变化**：确认位图极性（0=白 vs 1=白因型号而异）
- **残影严重**：每次刷新后调用 `epd_sleep()`，避免长时间通电
