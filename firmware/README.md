# BusArrivalBoard ESP32 固件

ESP32 WiFi 自联网墨水屏固件，定时从 Python 服务端拉取预渲染好的公交到站画面。

---

## 硬件需求

| 组件 | 推荐型号 | 备注 |
|------|---------|------|
| **主控** | ESP32-S3 N16R8 | 16MB Flash + 8MB PSRAM，双核 240MHz |
| **墨水屏** | 微雪 4.2寸黑白 UC8176 | 400×300，官方驱动完善 |
| **转接板** | 微雪 ESP32 Driver Board | 或自己杜邦线连接（见下方引脚定义） |
| **电源** | 18650 锂电 + TP4056 | 深度睡眠功耗 < 10µA，可撑数月 |

**引脚连接**（ESP32-S3 标准 SPI）：
```
墨水屏   → ESP32-S3 GPIO
GND    → GND
3.3V   → 3V3
SCK    → 12
MOSI   → 11
RST    → 7
DC     → 8
CS     → 10
BUSY   → 9
```

---

## 软件环境

**必需**：
- [ESP-IDF](https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32s3/get-started/) v5.1 或更高
- CMake ≥ 3.16
- Python 3.8+

**推荐**：
- VSCode + [ESP-IDF 插件](https://marketplace.visualstudio.com/items?itemName=espressif.esp-idf-extension)

---

## 快速开始

### 1. 安装 ESP-IDF

参考[官方文档](https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32s3/get-started/linux-macos-setup.html)安装：

```bash
# 以 Linux 为例
mkdir -p ~/esp
cd ~/esp
git clone --recursive https://github.com/espressif/esp-idf.git
cd esp-idf
./install.sh esp32s3
. ./export.sh
```

**验证安装**：
```bash
idf.py --version  # 应输出 ESP-IDF v5.x
```

### 2. 配置固件

```bash
cd firmware/
idf.py set-target esp32s3
idf.py menuconfig
```

进入 `BusArrivalBoard Configuration` 菜单，配置：
- WiFi SSID / Password
- 服务器 URL（如 `http://192.168.1.100:8000`）
- 墨水屏尺寸与型号
- 深度睡眠间隔（秒）

配置会保存在 `sdkconfig` 文件（已加入 `.gitignore`，因为含 WiFi 密码）。

### 3. 编译

```bash
idf.py build
```

首次编译约 5-10 分钟（下载组件 + 编译 SDK）。

### 4. 烧录

连接 ESP32-S3 开发板到 USB，确认串口设备名（Linux 通常是 `/dev/ttyUSB0`）：

```bash
idf.py -p /dev/ttyUSB0 flash
```

### 5. 监控串口日志

```bash
idf.py -p /dev/ttyUSB0 monitor
```

按 `Ctrl+]` 退出监控。

---

## 开发工作流

### 增量构建与烧录

修改代码后只需：
```bash
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
```

增量编译通常 < 10 秒。

### 清除配置与构建产物

```bash
idf.py fullclean
rm sdkconfig
idf.py menuconfig  # 重新配置
```

### 查看编译产物大小

```bash
idf.py size
idf.py size-components  # 各组件体积
```

### OTA 固件升级（后续支持）

首次烧录需 USB，后续可通过 HTTP OTA 无线升级：
```bash
# 主机上：
python -m http.server 8070 --directory build/
# ESP32 上：
# 在串口输入 OTA 命令触发升级（待实现）
```

---

## VSCode 开发

### 安装插件

1. 打开 VSCode
2. 安装 **ESP-IDF** 插件（Espressif）
3. 按 `F1` 运行 `ESP-IDF: Configure ESP-IDF Extension`
4. 选择已安装的 ESP-IDF 路径（如 `~/esp/esp-idf`）

### 常用快捷键

| 功能 | 快捷键 |
|------|--------|
| 构建 | `Ctrl+E` `B` |
| 烧录 | `Ctrl+E` `F` |
| 监控 | `Ctrl+E` `M` |
| 全流程 | `Ctrl+E` `D`（构建+烧录+监控） |
| menuconfig | `Ctrl+E` `G` |

### IntelliSense 配置

首次编译后会生成 `build/compile_commands.json`，VSCode 自动识别：
- 自动补全 ESP-IDF API
- 跳转到 SDK 头文件
- 实时错误检查

---

## 项目结构

```
firmware/
├── CMakeLists.txt              # 顶层构建配置
├── sdkconfig.defaults          # SDK 默认配置
├── partitions.csv              # Flash 分区表（支持 OTA）
├── main/                       # 主程序
│   ├── main.c                  # 入口
│   ├── CMakeLists.txt
│   └── Kconfig.projbuild       # menuconfig 配置项
├── components/                 # 自定义组件
│   ├── epd_driver/             # 墨水屏 SPI 驱动
│   ├── http_frame_client/      # HTTP 帧下载
│   ├── wifi_provisioning/      # WiFi 配网
│   └── power_management/       # 深度睡眠与电源管理
├── .vscode/                    # VSCode 配置
└── README.md                   # 本文件
```

---

## 故障排查

### 编译错误

**问题**：`CMake Error: Could not find IDF_PATH`
**解决**：每次打开新终端需运行 `. ~/esp/esp-idf/export.sh`

**问题**：`fatal error: esp_log.h: No such file or directory`
**解决**：运行 `idf.py fullclean && idf.py build`

### 烧录失败

**问题**：`A fatal error occurred: Failed to connect`
**解决**：
1. 检查 USB 线是否支持数据传输（非纯充电线）
2. 按住 BOOT 键不放，点一下 RST 键，松开 BOOT，再烧录
3. 确认串口设备名：`ls /dev/ttyUSB*` 或 `ls /dev/ttyACM*`

**问题**：`Permission denied: '/dev/ttyUSB0'`
**解决**：
```bash
sudo usermod -a -G dialout $USER  # 把用户加进 dialout 组
# 注销重新登录生效
```

### 运行时问题

**问题**：WiFi 连不上
**解决**：
1. 检查 `menuconfig` 里 SSID / Password 是否正确
2. 串口看日志：`idf.py monitor`，查找 `wifi:` 开头的行
3. 尝试手机热点测试（排除路由器兼容性问题）

**问题**：墨水屏不刷新
**解决**：
1. 检查引脚连接（对照上方引脚表）
2. 确认屏幕型号与 `menuconfig` 配置一致
3. 用万用表测量屏幕供电是否正常（3.3V）

**问题**：服务器连不上
**解决**：
1. 确认 ESP32 与服务器在同一局域网
2. `ping <服务器IP>` 测试连通性
3. 浏览器访问 `http://<服务器IP>:8000/health` 验证服务端正常
4. 检查防火墙是否拦截 8000 端口

---

## 功耗优化

当前实现的深度睡眠电流 < 20µA，18650 锂电（2500mAh）理论续航：

| 刷新间隔 | 续航 |
|---------|------|
| 5 分钟  | ~3 个月 |
| 10 分钟 | ~6 个月 |
| 30 分钟 | ~1 年 |

**进一步优化**：
- 关闭 WiFi 休眠前断开连接（省 1-2mA）
- 使用 RTC GPIO 外部唤醒（按钮 / 传感器）
- ULP 协处理器定时查询（主核完全关闭）

---

## 后续计划

- [ ] SmartConfig / WPS / SoftAP 三种配网方式
- [ ] HTTPS 支持（服务端证书验证）
- [ ] OTA 固件升级（HTTP / HTTPS）
- [ ] 支持多种屏幕型号（SSD1619 / IL0398 / 7.5寸）
- [ ] 触摸唤醒（带触摸 IC 的型号）
- [ ] 电池电压监测与低电报警

---

## 许可证

与主项目一致：MIT License
