# BusArrivalBoard

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

**实时公交到站显示系统** — 通用、可配置的公交到站信息解决方案

[English](./README_EN.md) | 简体中文

---

## 📖 项目简介

BusArrivalBoard 是一个开源的实时公交到站信息显示系统，支持：

- ✅ **Python SDK** — 快速集成到任何 Python 项目
- ✅ **命令行工具** — 终端实时监控公交到站
- ✅ **多城市支持** — 覆盖全国 480+ 城市
- ✅ **配置化管理** — YAML 配置文件，支持多站点监控
- 🚧 **ESP32/墨水屏** — 嵌入式硬件显示方案（开发中）

### 核心特性

| 特性 | 说明 |
|------|------|
| **实时数据** | 基于车来了 API，GPS 实时定位，秒级更新 |
| **完整信息** | 车辆位置、剩余站数、预计到达时间、拥挤度 |
| **蓝牙墨水屏** | 实时推送到 nRF51/52 电子墨水屏（4.2/7.5寸） |
| **环线支持** | 正确处理环线公交的站点计算逻辑 |
| **零依赖认证** | 无需账号/API Key，开箱即用 |
| **嵌入式友好** | 核心算法可移植到 ESP32/Arduino |

---

## 🚀 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/Garfield-Wuu/BusArrivalBoard.git
cd BusArrivalBoard

# 安装依赖
pip install -r requirements.txt

# 或安装为库
pip install -e .
```

### 5分钟上手

```bash
# 查询深圳 M592 路公交实时状态
python -m bus_arrival_board.cli query \
  --city "深圳" \
  --line "M592" \
  --station "安翼嘉寓"
```

**输出示例：**
```
查询时间: 2026-08-17 15:01:16
线路: M592  站点: 安翼嘉寓 (第17/26站, 环线)
----------------------------------------------------------
🚌 1. 粤B03745D  在第2站 | 还差15站 | 距离12086m
      约 35分钟 到站 (预计 15:36) | 不拥挤
🚌 2. 粤B05981D  在第7站 | 还差10站 | 距离7549m
      约 21分钟 到站 (预计 15:21) | 不拥挤
🚌 3. 粤B06857D  在第14站 | 还差3站 | 距离2200m
      约 7分钟 到站 (预计 15:07) | 不拥挤
```

---

## 📦 项目结构

```
BusArrivalBoard/
├── chelaile_sdk/          # 核心 SDK
│   ├── client.py          # API 客户端
│   ├── crypto.py          # 加密/签名
│   ├── models.py          # 数据模型
│   └── exceptions.py      # 异常定义
├── bus_arrival_board/     # 应用层
│   ├── cli.py             # 命令行工具
│   ├── config.py          # 配置管理
│   └── monitor.py         # 实时监控
├── examples/              # 使用示例
├── tests/                 # 单元测试
├── config/                # 配置文件示例
└── docs/                  # 文档
```

---

## 🔧 使用方式

### 1. Python SDK

```python
from chelaile_sdk import ChelaiLeClient

# 创建客户端
client = ChelaiLeClient()

# 搜索线路
lines = client.search_line(city_id="014", keyword="M592")

# 获取实时到站信息
buses = client.get_realtime_buses(
    city_id="014",
    line_id=lines[0]["lineId"],
    station_id="0755-15924",
    target_order=17
)

for bus in buses:
    print(f"🚌 {bus['busId']}: {bus['eta']['travelTime']}秒后到站")
```

### 2. 命令行工具

```bash
# 实时监控（每60秒刷新）
python -m bus_arrival_board.cli monitor \
  --config config/shenzhen_m592.yaml

# 导出 JSON
python -m bus_arrival_board.cli query \
  --city "深圳" --line "M592" --station "安翼嘉寓" \
  --format json > output.json
```

### 3. 配置文件

`config/shenzhen_m592.yaml`:
```yaml
city: "深圳"
line: "M592"
station: "安翼嘉寓"

refresh_interval: 60  # 秒
display:
  max_buses: 3        # 显示前3辆车
  show_crowd: true    # 显示拥挤度
```

---

## 🎯 应用场景

- **个人桌面监控** — 出门前查看公交到站时间
- **墨水屏显示器** — ESP32 驱动的低功耗实时显示（硬件方案开发中）
- **智能家居集成** — Home Assistant / Node-RED
- **数据分析** — 公交准点率统计、客流分析

---

## 📡 硬件方案（计划中）

### ESP32 + 墨水屏

**推荐硬件：**
- **开发板**: LilyGo T5-4.7" Plus (ESP32-S3 + 4.7寸墨水屏)
- **成本**: ¥150-200
- **功耗**: 深度睡眠模式下 < 0.5mA

**特性：**
- 60秒自动刷新
- Wi-Fi 联网获取数据
- 电池供电，续航 7-14 天
- 3D 打印外壳（STL 文件即将开源）

详见 [硬件指南](docs/hardware_guide.md)（开发中）

---

## 🧪 开发

### 运行测试

```bash
pytest tests/ -v
```

### 代码格式化

```bash
black .
isort .
```

### 类型检查

```bash
mypy chelaile_sdk/ bus_arrival_board/
```

---

## 📚 文档

- [API 参考](docs/api_reference.md)
- [配置指南](docs/configuration.md)
- [ESP32 移植指南](docs/esp32_porting.md)
- [硬件 BOM](docs/hardware_bom.md)

---

## 🤝 贡献

欢迎贡献代码、文档、硬件设计！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交改动 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 提交 Pull Request

详见 [贡献指南](CONTRIBUTING.md)

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 🙏 致谢

- 数据源：车来了（[chelaile.net.cn](https://www.chelaile.net.cn/)）
- 逆向参考：[chelaile-mcp](https://github.com/PeanutSplash/chelaile-mcp) by PeanutSplash

---

## ⚠️ 免责声明

本项目**仅供个人学习和研究使用**，不得用于商业目的。使用本项目即表示您同意：

1. 数据来源于第三方服务，作者不对数据准确性负责
2. 请遵守车来了的服务条款，不要滥用 API
3. 建议刷新间隔 ≥ 60 秒，避免对服务器造成压力
4. 作者不对使用本项目造成的任何损失负责

---

## 📬 联系方式

- **Issues**: [GitHub Issues](https://github.com/Garfield-Wuu/BusArrivalBoard/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Garfield-Wuu/BusArrivalBoard/discussions)

---

**⭐ 如果这个项目对你有帮助，请给一个 Star！**
