# EPD-nRF5 蓝牙墨水屏接入指南

## 📋 项目概述

EPD-nRF5 是一个基于 nRF51/nRF52 的蓝牙墨水屏固件，**通过 Web Bluetooth API 在浏览器中发送图片**，无需单独的 PC 端软件或手机 App。

**关键特性：**
- ✅ **Web Bluetooth API** - 在 Chrome/Edge/Bluefy 浏览器直接连接
- ✅ **无需原生 App** - 不需要 Python BLE 库或独立程序
- ✅ **廉价硬件** - 二手电子价签（nRF51822/nRF52811）约 ¥1-5/个
- ✅ **图片传输** - 支持黑白/三色/四色墨水屏
- ✅ **日历模式** - 内置农历/节气/节假日显示

---

## 🛒 硬件采购

### 推荐方案：二手电子价签

**在哪买：**
- 闲鱼/淘宝搜：`nrf51822 价签` 或 `nrf52811 墨水屏`
- 合理价格：**¥1-5/个**（拆好屏的碎屏价签）

**推荐型号：**
| 型号 | MCU | Flash | 屏幕 | 价格 | 推荐度 |
|------|-----|-------|------|------|--------|
| 老五 4.2寸 黑白 | nRF51822 | 128K | UC8176 | ~¥3 | ⭐⭐⭐ |
| 老五 4.2寸 三色 | nRF51802 | 256K | UC8176 | ~¥5 | ⭐⭐⭐⭐ |
| 思飞 52810 | nRF52810 | 192K | 4.2寸 | ~¥4 | ⭐⭐⭐⭐⭐ 速度快 |
| 盒马/淘宝 52811 | nRF52811 | 192K | 4.2寸 | ~¥5 | ⭐⭐⭐⭐⭐ 速度快 |

**注意：**
- nRF52 系列蓝牙传输速度比 nRF51 快 3-5 倍
- 128K Flash 只支持固件 v1.4（已停止更新）
- 建议买 **256K Flash** 或 nRF52 系列

---

## 🔧 刷机准备（首次使用）

### 1. 烧录器

**需要：** J-Link 或 DAPLink（淘宝 ¥5-20）

**刷机软件：** [JFlash](https://www.segger.com/downloads/jlink/) 或 [nRF Connect](https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-Desktop)

**刷机教程视频：** https://b23.tv/AaphIZp

### 2. 固件下载

https://github.com/tsl0922/EPD-nRF5/releases

- nRF51 128K: `EPD_128K_full.hex`
- nRF51 256K: `EPD_256K_full.hex`
- nRF52: `EPD_nRF52_full.hex`

### 3. 刷机步骤（JFlash）

1. 连接 J-Link 到价签的 SWD 接口（CLK/DIO/GND/VCC）
2. 打开 JFlash，选择对应芯片型号（如 nRF51822_xxAB）
3. Target → Connect
4. Target → Erase Chip (F4)
5. 拖入 `.hex` 文件
6. Target → Production Programming (F7)
7. 完成后断电重启

### 4. OTA 升级（v1.6+ 固件）

首次刷机后，后续可**通过蓝牙 OTA 升级**，无需拆机：
- Android: nRF Connect / nRF Toolbox
- iOS: nRF Connect / nRF Toolbox

---

## 🌐 Web 上位机使用

### 1. 浏览器要求

**支持的浏览器（必须支持 Web Bluetooth API）：**
- ✅ **电脑**: Chrome / Edge（需要蓝牙适配器）
- ✅ **Android**: Edge / Chrome
- ✅ **iOS**: [Bluefy](https://apps.apple.com/app/bluefy/id1492822055) 浏览器

**不支持：**
- ❌ Safari（苹果不支持 Web Bluetooth）
- ❌ Firefox（默认禁用）
- ❌ 大部分国产手机自带浏览器

### 2. 访问上位机

**官方地址：** https://tsl0922.github.io/EPD-nRF5/

或下载 `index.html` 本地打开。

### 3. 连接墨水屏

1. **唤醒设备**（如果支持 NFC）：
   - Android: NFC 扫描界面刷一下价签
   - iOS: 快捷指令 App 扫描 NFC

2. **浏览器中连接：**
   - 点击"蓝牙连接"按钮
   - 搜索设备名：`NRF_EPD_XXXX`（后 4 位是 MAC 地址）
   - 选择并配对

3. **配置驱动**（首次连接）：
   - 选择屏幕尺寸（如 4.2寸）
   - 选择驱动 IC（如 UC8176 黑白）
   - 如果屏幕无反应，切换到"开发模式"逐个尝试驱动
   - 引脚配置通常是自动的，不行则参考 [设备文档](https://github.com/tsl0922/EPD-nRF5/blob/main/docs/devices.md)

---

## 🚌 集成 BusArrivalBoard

### 方案 A：Python 生成图片 + 手动上传（临时方案）

**流程：**
1. Python 脚本查询公交数据
2. 用 PIL/Pillow 生成墨水屏图片（400x300 或 640x384）
3. 浏览器打开 https://tsl0922.github.io/EPD-nRF5/
4. 手动上传图片并发送到墨水屏

**优点：** 简单，无需写蓝牙代码  
**缺点：** 需要手动操作，无法自动化

---

### 方案 B：Python + Web Bluetooth（自动化）

EPD-nRF5 的 Web Bluetooth 协议是**开放的**，可以用 Python 直接调用。

#### 1. 安装依赖

```bash
pip install bleak pillow
```

#### 2. 关键 BLE 服务

根据 EPD-nRF5 固件，蓝牙服务 UUID（需要从网页 JS 逆向获取）：

- **图片传输服务**: `UUID_IMAGE_SERVICE`
- **控制服务**: `UUID_CONTROL_SERVICE`

**⚠️ 协议逆向：**  
由于 EPD-nRF5 没有公开 BLE 协议文档，需要：
1. 查看 `web/js/*.js` 源码（Web Bluetooth API 调用）
2. 或用 nRF Connect 抓包分析 GATT 特征值

#### 3. Python BLE 客户端框架（伪代码）

```python
from bleak import BleakClient, BleakScanner
from PIL import Image, ImageDraw, ImageFont
import asyncio

# 1. 扫描设备
async def scan_epd():
    devices = await BleakScanner.discover(timeout=10)
    for d in devices:
        if d.name and d.name.startswith("NRF_EPD"):
            return d.address
    raise Exception("未找到墨水屏设备")

# 2. 连接并发送图片
async def send_image(address, image_path):
    async with BleakClient(address) as client:
        # 读取图片并转换为单色/三色格式
        img = Image.open(image_path).convert("1")  # 黑白
        pixels = img.tobytes()
        
        # 发送图片数据（需要根据逆向的协议分包发送）
        # await client.write_gatt_char(UUID_IMAGE_CHAR, packet)
        ...

# 3. 生成公交到站图片
def generate_bus_display(buses):
    img = Image.new("1", (400, 300), 255)  # 4.2寸黑白
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 24)
    
    # 绘制标题
    draw.text((10, 10), "M592路 安翼嘉寓站", font=font, fill=0)
    
    # 绘制公交信息
    y = 60
    for i, bus in enumerate(buses[:3], 1):
        text = f"{i}. {bus['busId']}  剩余{bus['remaining']}站"
        if bus['eta']:
            text += f"  约{bus['eta']}分钟"
        draw.text((10, y), text, font=font, fill=0)
        y += 50
    
    return img

# 4. 主流程
async def main():
    # 查询公交数据
    from chelaile_sdk import ChelaiLeClient
    client = ChelaiLeClient()
    result = client.get_realtime_buses(...)
    
    # 生成图片
    img = generate_bus_display(result.buses)
    img.save("/tmp/bus.png")
    
    # 发送到墨水屏
    address = await scan_epd()
    await send_image(address, "/tmp/bus.png")

asyncio.run(main())
```

---

### 方案 C：本地 Web 服务 + 浏览器自动化（推荐）

**思路：**
1. Python Flask/FastAPI 提供实时公交图片接口
2. 修改 EPD-nRF5 的 `index.html`，增加"自动刷新"按钮
3. 浏览器定时（如每 5 分钟）拉取图片并自动发送到墨水屏

**优点：**
- 利用现成的 Web Bluetooth 代码
- 无需逆向蓝牙协议
- 跨平台（手机/电脑都能用）

**实现步骤：**

#### 1. 创建图片生成服务

```python
# bus_arrival_board/epd_server.py
from flask import Flask, send_file
from PIL import Image, ImageDraw, ImageFont
from chelaile_sdk import ChelaiLeClient
from bus_arrival_board.config import load_config
from bus_arrival_board.monitor import BusMonitor
import io

app = Flask(__name__)

@app.route("/bus-display.png")
def bus_display():
    # 查询实时数据
    cfg = load_config("config/shenzhen_m592.yaml")
    monitor = BusMonitor(cfg)
    monitor.resolve_targets()
    results = list(monitor.poll_once())
    
    # 生成图片
    img = Image.new("1", (400, 300), 255)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 20)
    
    if results:
        target, result = results[0]
        draw.text((10, 10), f"{target.line} {target.station}", font=font, fill=0)
        
        y = 50
        for i, bus in enumerate(result.buses[:3], 1):
            eta_text = f"{bus.eta_minutes}分钟" if bus.eta_minutes else "暂无"
            text = f"{i}. {bus.bus_id}  {bus.order}站  {eta_text}"
            draw.text((10, y), text, font=font, fill=0)
            y += 60
    
    # 返回图片
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

#### 2. 启动服务

```bash
python bus_arrival_board/epd_server.py
```

#### 3. 浏览器中使用

打开 https://tsl0922.github.io/EPD-nRF5/，连接墨水屏后：
1. 点击"图片"标签
2. 输入图片 URL：`http://你的电脑IP:5000/bus-display.png`
3. 点击"刷新图片"并发送

**自动化：**
- 修改 `index.html`，增加定时器每 5 分钟自动刷新并发送
- 或用浏览器扩展（如 Tampermonkey）写脚本自动化

---

## 📐 图片尺寸参考

| 屏幕尺寸 | 分辨率 | 宽x高(px) | PIL `Image.new()` |
|----------|--------|-----------|-------------------|
| 4.2寸 | 黑白 | 400x300 | `("1", (400, 300), 255)` |
| 4.2寸 | 三色 | 400x300 | `("P", (400, 300))` + 调色板 |
| 7.5寸 | 黑白 | 640x384 | `("1", (640, 384), 255)` |

**颜色模式：**
- 黑白：`"1"` (1-bit)
- 三色（黑/白/红）：`"P"` (palette) + 3色调色板
- 四色：需要特殊格式（参考固件文档）

---

## 🔄 自动化刷新方案总结

| 方案 | 复杂度 | 自动化 | 推荐度 |
|------|--------|--------|--------|
| **方案 A：手动上传** | ⭐ | ❌ | 适合测试 |
| **方案 B：Python BLE** | ⭐⭐⭐⭐ | ✅ | 需要逆向协议 |
| **方案 C：Web服务+浏览器** | ⭐⭐ | ✅ | **推荐**，利用现成代码 |

---

## ⚠️ 注意事项

1. **唤醒机制**：部分价签支持 NFC 唤醒，没有则需要按复位键或无线充电唤醒
2. **传输速度**：nRF51 传输一张图约 30-60 秒，nRF52 约 10-20 秒
3. **刷新频率**：墨水屏建议 ≥5 分钟刷新一次，避免残影
4. **电池续航**：价签内置电池，纽扣电池约 1-3 个月（取决于刷新频率）
5. **蓝牙距离**：有效距离约 5-10 米，受墙壁/障碍物影响

---

## 📚 参考资料

- **项目主页**: https://github.com/tsl0922/EPD-nRF5
- **Web 上位机**: https://tsl0922.github.io/EPD-nRF5/
- **教程视频**: https://www.bilibili.com/video/BV1KWAVe1EKs
- **刷机教程**: https://b23.tv/AaphIZp
- **QQ 交流群**: 1033086563

---

## ✅ 你的蓝牙硬件状态

```
蓝牙硬件: Intel AX200 Bluetooth ✅
蓝牙服务: active (running) ✅
适配器状态: Powered: yes ✅
bluetoothctl: 5.64 ✅
```

**结论：你的电脑完全支持蓝牙墨水屏，买到设备后即可开始！**

---

## 🎯 下一步行动

1. **立即可做**：
   - 在闲鱼搜索 `nrf52811 价签` 或 `老五 4.2寸 价签`
   - 预算 ¥5-10 买 1-2 个碎屏价签（确认型号）

2. **收货后**：
   - 用 J-Link 刷 EPD-nRF5 固件（首次需要烧录器）
   - Chrome 浏览器打开 https://tsl0922.github.io/EPD-nRF5/ 测试连接

3. **集成公交**：
   - 我帮你写方案 C 的完整代码（Flask 图片服务 + 浏览器自动化脚本）
   - 或者等你熟悉后，逆向协议写 Python BLE 直连

**需要我现在先写好方案 C 的完整代码吗？**
