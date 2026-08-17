# BusArrivalBoard

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

**Real-time Bus Arrival Display System** — Universal, configurable solution for public transit information

[简体中文](./README.md) | English

---

## 📖 Overview

BusArrivalBoard is an open-source real-time bus arrival information system that supports:

- ✅ **Python SDK** — Quick integration into any Python project
- ✅ **CLI Tools** — Real-time monitoring in terminal
- ✅ **Multi-City Support** — Covers 480+ cities nationwide (China)
- ✅ **Configuration Management** — YAML-based multi-station monitoring
- 🚧 **ESP32 + E-Ink** — Embedded hardware display (in development)

### Core Features

| Feature | Description |
|---------|-------------|
| **Real-time Data** | GPS-based positioning via Chelaile API, sub-minute updates |
| **Complete Info** | Vehicle position, remaining stops, ETA, crowd level |
| **Loop Line Support** | Correct handling of circular routes |
| **Zero Auth** | No account/API key required, works out of the box |
| **Embedded-Friendly** | Core algorithms portable to ESP32/Arduino |

---

## 🚀 Quick Start

### Installation

```bash
# Clone repository
git clone https://github.com/Garfield-Wuu/BusArrivalBoard.git
cd BusArrivalBoard

# Install dependencies
pip install -r requirements.txt

# Or install as library
pip install -e .
```

### 5-Minute Tutorial

```bash
# Query Shenzhen M592 bus real-time status
python -m bus_arrival_board.cli query \
  --city "深圳" \
  --line "M592" \
  --station "安翼嘉寓"
```

**Sample Output:**
```
Query Time: 2026-08-17 15:01:16
Line: M592  Station: 安翼嘉寓 (17/26 stops, loop line)
----------------------------------------------------------
🚌 1. 粤B03745D  At stop 2 | 15 stops left | 12086m away
      ~35 mins (ETA 15:36) | Not crowded
🚌 2. 粤B05981D  At stop 7 | 10 stops left | 7549m away
      ~21 mins (ETA 15:21) | Not crowded
🚌 3. 粤B06857D  At stop 14 | 3 stops left | 2200m away
      ~7 mins (ETA 15:07) | Not crowded
```

---

## 📦 Project Structure

```
BusArrivalBoard/
├── chelaile_sdk/          # Core SDK
│   ├── client.py          # API client
│   ├── crypto.py          # Encryption/signing
│   ├── models.py          # Data models
│   └── exceptions.py      # Exception definitions
├── bus_arrival_board/     # Application layer
│   ├── cli.py             # CLI tool
│   ├── config.py          # Configuration management
│   └── monitor.py         # Real-time monitoring
├── examples/              # Usage examples
├── tests/                 # Unit tests
├── config/                # Config file samples
└── docs/                  # Documentation
```

---

## 🔧 Usage

### 1. Python SDK

```python
from chelaile_sdk import ChelaiLeClient

# Create client
client = ChelaiLeClient()

# Search for lines
lines = client.search_line(city_id="014", keyword="M592")

# Get real-time arrival info
buses = client.get_realtime_buses(
    city_id="014",
    line_id=lines[0]["lineId"],
    station_id="0755-15924",
    target_order=17
)

for bus in buses:
    print(f"🚌 {bus['busId']}: {bus['eta']['travelTime']}s to arrival")
```

### 2. Command-Line Tool

```bash
# Real-time monitoring (refresh every 60s)
python -m bus_arrival_board.cli monitor \
  --city "深圳" --line "M592" --station "安翼嘉寓"

# Export JSON
python -m bus_arrival_board.cli query \
  --city "深圳" --line "M592" --station "安翼嘉寓" \
  --format json > output.json
```

### 3. Configuration File

`config/shenzhen_m592.yaml`:
```yaml
city: "深圳"
line: "M592"
station: "安翼嘉寓"

refresh_interval: 60  # seconds
display:
  max_buses: 3        # show top 3 buses
  show_crowd: true    # show crowd level
```

---

## 🎯 Use Cases

- **Desktop Monitoring** — Check bus arrival before leaving
- **E-Ink Display** — ESP32-driven low-power real-time display (hardware plan in development)
- **Smart Home Integration** — Home Assistant / Node-RED
- **Data Analysis** — Punctuality stats, passenger flow analysis

---

## 📡 Hardware Plan (Planned)

### ESP32 + E-Ink Display

**Recommended Hardware:**
- **Dev Board**: LilyGo T5-4.7" Plus (ESP32-S3 + 4.7" E-Ink)
- **Cost**: ¥150-200
- **Power**: Deep sleep mode < 0.5mA

**Features:**
- 60s auto-refresh
- Wi-Fi data fetching
- Battery powered, 7-14 days runtime
- 3D-printed enclosure (STL files coming soon)

See [Hardware Guide](docs/hardware_guide.md) (in development)

---

## 🧪 Development

### Run Tests

```bash
pytest tests/ -v
```

### Code Formatting

```bash
black .
isort .
```

### Type Checking

```bash
mypy chelaile_sdk/ bus_arrival_board/
```

---

## 📚 Documentation

- [API Reference](docs/api_reference.md)
- [Configuration Guide](docs/configuration.md)
- [ESP32 Porting Guide](docs/esp32_porting.md)
- [Hardware BOM](docs/hardware_bom.md)

---

## 🤝 Contributing

Contributions welcome — code, docs, hardware designs!

1. Fork this repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Submit Pull Request

See [Contributing Guide](CONTRIBUTING.md)

---

## 📄 License

This project is licensed under the MIT License - see [LICENSE](LICENSE)

---

## 🙏 Acknowledgments

- Data Source: Chelaile ([chelaile.net.cn](https://www.chelaile.net.cn/))
- Reverse Engineering Reference: [chelaile-mcp](https://github.com/PeanutSplash/chelaile-mcp) by PeanutSplash

---

## ⚠️ Disclaimer

This project is **for personal learning and research only**, not for commercial use. By using this project, you agree:

1. Data is from third-party services; author is not responsible for data accuracy
2. Please respect Chelaile's Terms of Service and do not abuse the API
3. Recommended refresh interval ≥ 60 seconds to avoid server pressure
4. Author is not liable for any losses caused by using this project

---

## 📬 Contact

- **Issues**: [GitHub Issues](https://github.com/Garfield-Wuu/BusArrivalBoard/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Garfield-Wuu/BusArrivalBoard/discussions)

---

**⭐ If this project helps you, please give it a Star!**
