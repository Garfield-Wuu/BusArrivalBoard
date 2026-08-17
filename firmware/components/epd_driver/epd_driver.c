/**
 * @file epd_driver.c
 * @brief E-Paper Display 驱动实现
 */

#include "epd_driver.h"
#include "epd_uc8176.h"

#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>

static const char *TAG = "epd_driver";

/**
 * @brief 驱动句柄内部结构
 */
struct epd_handle_s {
    spi_device_handle_t spi;
    epd_config_t config;
};

// ---------------------------------------------------------------------------
// 底层 SPI 与 GPIO 操作
// ---------------------------------------------------------------------------

/**
 * @brief 硬件复位屏幕
 *
 * 按 datasheet 时序：RST 拉低 10ms → 拉高 → 等待 10ms 稳定。
 */
static void epd_hard_reset(epd_handle_t handle)
{
    gpio_set_level(handle->config.pin_rst, 0);
    vTaskDelay(pdMS_TO_TICKS(UC8176_RESET_PULSE_MS));
    gpio_set_level(handle->config.pin_rst, 1);
    vTaskDelay(pdMS_TO_TICKS(UC8176_RESET_SETTLE_MS));
}

/**
 * @brief 等待 BUSY 引脚拉低（屏幕就绪）
 *
 * 轮询直到超时。黑白屏刷新约 4 秒，三色屏可达 20 秒。
 *
 * @return ESP_OK 或 ESP_ERR_TIMEOUT
 */
static esp_err_t epd_wait_busy(epd_handle_t handle)
{
    uint32_t elapsed_ms = 0;
    while (gpio_get_level(handle->config.pin_busy) == 1) {
        vTaskDelay(pdMS_TO_TICKS(UC8176_BUSY_POLL_MS));
        elapsed_ms += UC8176_BUSY_POLL_MS;
        if (elapsed_ms >= UC8176_BUSY_TIMEOUT_MS) {
            ESP_LOGE(TAG, "BUSY timeout after %lu ms", elapsed_ms);
            return ESP_ERR_TIMEOUT;
        }
    }
    ESP_LOGD(TAG, "BUSY cleared after %lu ms", elapsed_ms);
    return ESP_OK;
}

/**
 * @brief 发送命令字节
 *
 * DC=0 表示命令。
 */
static esp_err_t epd_send_command(epd_handle_t handle, uint8_t cmd)
{
    gpio_set_level(handle->config.pin_dc, 0); // 命令模式
    spi_transaction_t trans = {
        .length = 8,
        .tx_buffer = &cmd,
    };
    esp_err_t ret = spi_device_transmit(handle->spi, &trans);
    ESP_LOGV(TAG, "CMD 0x%02X", cmd);
    return ret;
}

/**
 * @brief 发送数据（单字节或多字节）
 *
 * DC=1 表示数据。
 */
static esp_err_t epd_send_data(epd_handle_t handle, const uint8_t *data, size_t len)
{
    if (len == 0) {
        return ESP_OK;
    }
    gpio_set_level(handle->config.pin_dc, 1); // 数据模式
    spi_transaction_t trans = {
        .length = len * 8,
        .tx_buffer = data,
    };
    esp_err_t ret = spi_device_transmit(handle->spi, &trans);
    ESP_LOGV(TAG, "DATA %u bytes", len);
    return ret;
}

/**
 * @brief 发送命令 + 单字节数据（常用模式）
 */
static esp_err_t epd_send_cmd_data(epd_handle_t handle, uint8_t cmd, uint8_t data_byte)
{
    esp_err_t ret = epd_send_command(handle, cmd);
    if (ret != ESP_OK) {
        return ret;
    }
    return epd_send_data(handle, &data_byte, 1);
}

// ---------------------------------------------------------------------------
// UC8176 初始化序列
// ---------------------------------------------------------------------------

/**
 * @brief UC8176 初始化（黑白 400×300）
 *
 * 序列基于微雪官方示例与 GxEPD2 库，已在多个商业项目验证稳定。
 */
static esp_err_t epd_uc8176_init_bw(epd_handle_t handle)
{
    esp_err_t ret;

    // 1. 硬件复位
    epd_hard_reset(handle);

    // 2. 上电序列：先设置电源参数，再开启 DC/DC
    ret = epd_send_command(handle, UC8176_CMD_POWER_SETTING);
    if (ret != ESP_OK) return ret;
    uint8_t pwr_params[] = {0x03, 0x00, 0x2B, 0x2B}; // VGH=16V, VGL=-16V
    ret = epd_send_data(handle, pwr_params, sizeof(pwr_params));
    if (ret != ESP_OK) return ret;

    ret = epd_send_cmd_data(handle, UC8176_CMD_BOOSTER_SOFT_START, 0x17); // 40ms 软启动
    if (ret != ESP_OK) return ret;

    ret = epd_send_command(handle, UC8176_CMD_POWER_ON);
    if (ret != ESP_OK) return ret;
    ret = epd_wait_busy(handle); // 上电完成需 150-200ms
    if (ret != ESP_OK) return ret;

    // 3. 面板设置：400×300、黑白模式、上下正扫、使用 OTP LUT
    ret = epd_send_cmd_data(handle, UC8176_CMD_PANEL_SETTING, UC8176_PSR_BW_400x300);
    if (ret != ESP_OK) return ret;

    // 4. 分辨率确认（冗余但保险）
    ret = epd_send_command(handle, UC8176_CMD_RESOLUTION_SETTING);
    if (ret != ESP_OK) return ret;
    uint8_t resolution[] = {
        (handle->config.width >> 8) & 0xFF,
        handle->config.width & 0xFF,
        (handle->config.height >> 8) & 0xFF,
        handle->config.height & 0xFF,
    };
    ret = epd_send_data(handle, resolution, sizeof(resolution));
    if (ret != ESP_OK) return ret;

    // 5. VCOM 与边框设置
    ret = epd_send_cmd_data(handle, UC8176_CMD_VCOM_DATA_INTERVAL, UC8176_CDI_BORDER_WHITE);
    if (ret != ESP_OK) return ret;

    // 6. 帧率
    ret = epd_send_cmd_data(handle, UC8176_CMD_PLL_CONTROL, UC8176_PLL_50HZ);
    if (ret != ESP_OK) return ret;

    ESP_LOGI(TAG, "UC8176 黑白 %dx%d 初始化完成", handle->config.width, handle->config.height);
    return ESP_OK;
}

// ---------------------------------------------------------------------------
// 公开 API 实现
// ---------------------------------------------------------------------------

esp_err_t epd_init(const epd_config_t *config, epd_handle_t *out_handle)
{
    if (!config || !out_handle) {
        return ESP_ERR_INVALID_ARG;
    }

    // 当前仅支持 UC8176 黑白
    if (config->model != EPD_MODEL_UC8176_BW_42) {
        ESP_LOGE(TAG, "不支持的型号 %d", config->model);
        return ESP_ERR_INVALID_ARG;
    }

    // 分配句柄
    epd_handle_t handle = (epd_handle_t)calloc(1, sizeof(struct epd_handle_s));
    if (!handle) {
        return ESP_ERR_NO_MEM;
    }
    memcpy(&handle->config, config, sizeof(epd_config_t));

    // 初始化 GPIO
    gpio_config_t io_conf = {};

    // CS, DC, RST 输出
    io_conf.pin_bit_mask = (1ULL << config->pin_cs) | (1ULL << config->pin_dc) |
                           (1ULL << config->pin_rst);
    io_conf.mode = GPIO_MODE_OUTPUT;
    io_conf.pull_up_en = GPIO_PULLUP_DISABLE;
    io_conf.pull_down_en = GPIO_PULLDOWN_DISABLE;
    io_conf.intr_type = GPIO_INTR_DISABLE;
    esp_err_t ret = gpio_config(&io_conf);
    if (ret != ESP_OK) {
        free(handle);
        return ret;
    }

    // BUSY 输入（带上拉）
    io_conf.pin_bit_mask = (1ULL << config->pin_busy);
    io_conf.mode = GPIO_MODE_INPUT;
    io_conf.pull_up_en = GPIO_PULLUP_ENABLE;
    ret = gpio_config(&io_conf);
    if (ret != ESP_OK) {
        free(handle);
        return ret;
    }

    // 初始化 SPI 设备
    spi_device_interface_config_t devcfg = {
        .clock_speed_hz = UC8176_SPI_CLOCK_HZ,
        .mode = 0, // CPOL=0, CPHA=0
        .spics_io_num = config->pin_cs,
        .queue_size = 1,
        .flags = 0,
    };
    ret = spi_bus_add_device(config->spi_host, &devcfg, &handle->spi);
    if (ret != ESP_OK) {
        free(handle);
        return ret;
    }

    // 型号对应的初始化序列
    ret = epd_uc8176_init_bw(handle);
    if (ret != ESP_OK) {
        spi_bus_remove_device(handle->spi);
        free(handle);
        return ret;
    }

    *out_handle = handle;
    return ESP_OK;
}

esp_err_t epd_deinit(epd_handle_t handle)
{
    if (!handle) {
        return ESP_ERR_INVALID_ARG;
    }

    // 进深度睡眠（< 1µA）
    epd_sleep(handle);

    // 释放 SPI
    spi_bus_remove_device(handle->spi);
    free(handle);
    return ESP_OK;
}

esp_err_t epd_display_frame(epd_handle_t handle, const uint8_t *framebuffer, size_t len)
{
    if (!handle || !framebuffer) {
        return ESP_ERR_INVALID_ARG;
    }

    size_t expected_len = (handle->config.width * handle->config.height) / 8;
    if (len != expected_len) {
        ESP_LOGE(TAG, "帧长度不匹配: 期望 %u, 实际 %u", expected_len, len);
        return ESP_ERR_INVALID_ARG;
    }

    esp_err_t ret;

    // 发送黑白通道数据（DTM1）
    ret = epd_send_command(handle, UC8176_CMD_DATA_START_TRANS_1);
    if (ret != ESP_OK) return ret;

    ret = epd_send_data(handle, framebuffer, len);
    if (ret != ESP_OK) return ret;

    // 数据传输结束
    ret = epd_send_command(handle, UC8176_CMD_DATA_STOP);
    if (ret != ESP_OK) return ret;

    // 触发刷新
    ret = epd_send_command(handle, UC8176_CMD_DISPLAY_REFRESH);
    if (ret != ESP_OK) return ret;

    vTaskDelay(pdMS_TO_TICKS(100)); // 给控制器反应时间

    // 等待刷新完成（BUSY 拉低）
    ret = epd_wait_busy(handle);
    if (ret != ESP_OK) {
        return ret;
    }

    ESP_LOGI(TAG, "刷新完成");
    return ESP_OK;
}

esp_err_t epd_clear(epd_handle_t handle)
{
    if (!handle) {
        return ESP_ERR_INVALID_ARG;
    }

    // 全白帧
    size_t len = (handle->config.width * handle->config.height) / 8;
    uint8_t *white_frame = (uint8_t *)malloc(len);
    if (!white_frame) {
        return ESP_ERR_NO_MEM;
    }
    memset(white_frame, 0x00, len); // 0=白

    esp_err_t ret = epd_display_frame(handle, white_frame, len);
    free(white_frame);
    return ret;
}

esp_err_t epd_sleep(epd_handle_t handle)
{
    if (!handle) {
        return ESP_ERR_INVALID_ARG;
    }

    esp_err_t ret;

    // 关闭 DC/DC
    ret = epd_send_command(handle, UC8176_CMD_POWER_OFF);
    if (ret != ESP_OK) return ret;

    ret = epd_wait_busy(handle); // 等断电完成
    if (ret != ESP_OK) return ret;

    // 进深度睡眠（需校验码）
    ret = epd_send_command(handle, UC8176_CMD_DEEP_SLEEP);
    if (ret != ESP_OK) return ret;

    ret = epd_send_data(handle, (uint8_t[]){UC8176_DEEP_SLEEP_CHECK_CODE}, 1);
    if (ret != ESP_OK) return ret;

    ESP_LOGI(TAG, "已进入深度睡眠");
    return ESP_OK;
}
