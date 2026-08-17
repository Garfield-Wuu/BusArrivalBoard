# BusArrivalBoard 下一步开发计划

## 🎯 目标

将项目从"纯 SDK + CLI 工具"升级为**完整的公交信息展示解决方案**，支持：
- ✅ 已完成：Python SDK、CLI 工具、配置管理、多站点监控
- 🚧 进行中：蓝牙墨水屏显示模块
- 📋 规划中：Web 服务、MQTT 推送、HomeAssistant 集成

---

## 📦 阶段 1：蓝牙墨水屏模块（优先级 P0）

### 1.1 核心 BLE 客户端

**文件**: `bus_arrival_board/epd/ble_client.py`

**功能**:
- 扫描/连接 nRF51/nRF52 墨水屏设备（前缀 `NRF_EPD_`）
- GATT 服务发现（UUID `62750001-...`）
- 命令发送（`0x00-0x06`, `0x20`, `0x30` 等）
- MTU 协商与自适应分包
- 交错 ACK 策略（`writeValueWithResponse` / `withoutResponse`）
- 固件版本检测

**依赖**: `bleak>=0.21.0`

**接口设计**:
```python
class EPDClient:
    async def connect(device_name_or_address: str) -> None
    async def disconnect() -> None
    async def set_pins(pins: str) -> None  # "0508090A0B0C0D"
    async def init(driver: int) -> None    # 驱动型号
    async def write_image(pixels: bytes, width: int, height: int) -> None
    async def refresh() -> None
    async def clear() -> None
    async def sleep() -> None
    @property
    async def firmware_version() -> str
```

**测试策略**:
- 单元测试：Mock `BleakClient`，验证命令格式
- 集成测试：真实设备（手动，CI 跳过）

---

### 1.2 图像渲染引擎

**文件**: `bus_arrival_board/epd/renderer.py`

**功能**:
- 公交数据 → PIL Image（黑白/三色）
- 多种布局模板（紧凑型、详细型、日历型）
- 中文字体处理（自动查找系统字体）
- 抖动算法（Floyd-Steinberg, Ordered, Atkinson）
- 分辨率适配（4.2寸 400×300、7.5寸 640×384）

**接口设计**:
```python
class BusDisplayRenderer:
    def __init__(width: int, height: int, mode: str = "1")
    def render(result: RealtimeResult, target: WatchTarget, 
               layout: str = "compact") -> Image.Image
    def add_header(text: str) -> None
    def add_bus_line(bus: BusInfo, index: int) -> None
    def add_footer(timestamp: datetime) -> None
    def to_bytes() -> bytes  # 单色位图字节流
```

**布局模板**:
- `compact`: 3 行公交信息 + 标题 + 更新时间
- `detailed`: 含距离、拥挤度、GPS 坐标
- `calendar`: 左侧日历 + 右侧公交（混合模式）

**测试策略**:
- 快照测试：生成图片与基准 PNG diff
- 参数化测试：不同分辨率 / 公交数量

---

### 1.3 高层封装

**文件**: `bus_arrival_board/epd/updater.py`

**功能**:
- 查询 + 渲染 + 发送 **一步到位**
- 错误重试与降级策略
- 日志与指标（刷新耗时、失败计数）

**接口设计**:
```python
class EPDUpdater:
    def __init__(config: AppConfig, epd_client: EPDClient, 
                 renderer: BusDisplayRenderer)
    async def update_once() -> None
    async def run_loop(interval_seconds: int = 300) -> None
```

**使用示例**:
```python
from bus_arrival_board.config import load_config
from bus_arrival_board.monitor import BusMonitor
from bus_arrival_board.epd import EPDClient, BusDisplayRenderer, EPDUpdater

cfg = load_config("config.yaml")
monitor = BusMonitor(cfg)
monitor.resolve_targets()

epd = EPDClient()
await epd.connect("NRF_EPD_A1B2")
await epd.set_pins("0508090A0B0C0D")
await epd.init(driver=0)  # UC8176 黑白

renderer = BusDisplayRenderer(400, 300, mode="1")
updater = EPDUpdater(cfg, epd, renderer)
await updater.run_loop(interval_seconds=300)
```

---

### 1.4 CLI 集成

**文件**: `bus_arrival_board/cli.py` 新增命令

```bash
# 扫描设备
bus-arrival epd scan

# 单次刷新（调试）
bus-arrival epd update \
  --device NRF_EPD_A1B2 \
  --config config.yaml \
  --pins "0508090A0B0C0D" \
  --driver 0

# 守护进程模式
bus-arrival epd daemon \
  --config config.yaml \
  --interval 300
```

---

## 📦 阶段 2：Web 服务（优先级 P1）

**目标**: 提供 HTTP API 和实时图片接口

**文件**: `bus_arrival_board/server.py`

**功能**:
- `GET /api/query?city=深圳&line=M592&station=安翼嘉寓` → JSON
- `GET /api/image.png?target=0&width=400&height=300` → PNG
- WebSocket 实时推送
- Prometheus metrics

**技术栈**: FastAPI + uvicorn

**部署**:
```bash
uvicorn bus_arrival_board.server:app --host 0.0.0.0 --port 8000
```

**HomeAssistant 集成**:
```yaml
sensor:
  - platform: rest
    resource: http://localhost:8000/api/query?city=深圳&line=M592&station=安翼嘉寓
    name: "M592 到站"
    json_attributes:
      - buses
```

---

## 📦 阶段 3：MQTT 推送（优先级 P2）

**文件**: `bus_arrival_board/mqtt.py`

**功能**:
- 定时发布公交状态到 MQTT broker
- 主题格式: `bus/{city}/{line}/{station}`
- 支持 HomeAssistant MQTT Discovery

**配置示例**:
```yaml
mqtt:
  broker: "mqtt://localhost:1883"
  username: user
  password: pass
  topic_prefix: "bus"
  homeassistant_discovery: true
```

---

## 📦 阶段 4：扩展功能（优先级 P3）

### 4.1 多数据源支持

当前只有车来了，未来可扩展：
- 高德地图公交 API
- 百度地图公交 API
- 交通部标准接口（一线城市开放数据）

**抽象接口**:
```python
class BusAPIClient(ABC):
    @abstractmethod
    def get_realtime_buses(...) -> RealtimeResult
```

### 4.2 历史数据与统计

- SQLite 存储每次查询结果
- 准点率分析（实际到站 vs 预测 ETA）
- 高峰期客流统计

### 4.3 智能提醒

- "下班时间前 10 分钟，下一班 5 分钟后到"
- Telegram/钉钉/企业微信推送
- 语音播报（TTS）

---

## 🛠️ 工程化改进

### 依赖管理

将依赖分类：
```toml
[project.optional-dependencies]
epd = ["bleak>=0.21.0", "pillow>=10.0.0"]
server = ["fastapi>=0.104.0", "uvicorn>=0.24.0"]
mqtt = ["paho-mqtt>=1.6.0"]
dev = ["pytest>=7.4", "pytest-cov>=4.1", "black>=23.0", ...]
```

安装示例：
```bash
pip install bus-arrival-board          # 核心 SDK + CLI
pip install bus-arrival-board[epd]     # 墨水屏功能
pip install bus-arrival-board[server]  # Web 服务
pip install bus-arrival-board[all]     # 全部功能
```

### 目录结构

```
bus_arrival_board/
├── __init__.py
├── cli.py              # CLI 入口
├── config.py           # 配置加载
├── monitor.py          # 多站点监控
├── epd/                # 墨水屏模块
│   ├── __init__.py
│   ├── ble_client.py   # BLE 通信
│   ├── renderer.py     # 图像渲染
│   ├── updater.py      # 高层封装
│   └── drivers.py      # 驱动型号定义
├── server.py           # Web 服务（可选）
├── mqtt.py             # MQTT 推送（可选）
└── utils/              # 工具函数
    ├── fonts.py        # 字体查找
    └── image.py        # 图像处理

tests/
├── test_epd_ble.py     # BLE 客户端测试
├── test_epd_renderer.py # 渲染器测试
└── fixtures/           # 测试数据

examples/
├── epd_basic.py        # 墨水屏基础用法
├── epd_daemon.py       # 守护进程
└── homeassistant.yaml  # HA 配置示例
```

### CI/CD 增强

```yaml
jobs:
  test:
    # ... 现有测试
  
  test-epd:
    # 墨水屏模块测试（需要 bleak）
    if: contains(github.event.head_commit.message, '[epd]')
    steps:
      - run: pip install -e ".[epd,dev]"
      - run: pytest tests/test_epd*.py -m "not hardware"
  
  build-docs:
    # 自动生成 API 文档
    steps:
      - run: pip install pdoc3
      - run: pdoc --html --output-dir docs/api bus_arrival_board
```

---

## 📚 文档更新计划

### 新增文档

1. **`docs/epd_api.md`** - BLE 协议完整文档
   - GATT 服务结构
   - 命令参考（含字节格式）
   - 分包策略
   - 故障排查

2. **`docs/rendering_guide.md`** - 渲染引擎使用指南
   - 布局模板对比
   - 自定义渲染
   - 字体配置
   - 抖动算法选择

3. **`docs/deployment.md`** - 部署指南
   - 树莓派部署（systemd service）
   - Docker 镜像
   - 开机自启动
   - 日志轮转

4. **`examples/`** - 完整示例
   - 基础用法
   - 自定义渲染
   - HomeAssistant 集成
   - MQTT 推送

### 更新现有文档

- **`README.md`** - 增加墨水屏功能介绍
- **`docs/epd_bluetooth_integration.md`** - 标注"已集成，无需手动实现"
- **`CONTRIBUTING.md`** - 增加墨水屏模块开发规范

---

## 🚀 执行计划（本次开发）

### 第一步：基础 BLE 客户端（今天）

1. 创建 `bus_arrival_board/epd/` 模块
2. 实现 `ble_client.py`（核心协议）
3. 单元测试（Mock 设备）
4. CLI 命令 `epd scan` / `epd connect`

### 第二步：渲染引擎（今天）

1. 实现 `renderer.py`（紧凑布局）
2. 字体自动查找（中文支持）
3. 快照测试（生成示例图片）
4. CLI 命令 `epd render --output test.png`

### 第三步：高层封装与集成（今天）

1. 实现 `updater.py`（查询→渲染→发送）
2. CLI 命令 `epd update` / `epd daemon`
3. 完整端到端示例脚本
4. 更新所有文档

### 第四步：测试与打磨（明天或等硬件到）

1. 真实设备测试（需要你的硬件）
2. MTU 协商与分包优化
3. 错误处理与重试
4. 性能测试（刷新耗时）

---

## ⚠️ 风险与应对

| 风险 | 应对 |
|------|------|
| 硬件未到，无法真实测试 | 先完成 Mock 测试，标注 `@pytest.mark.hardware` |
| MTU 实际值未知 | 代码支持自适应，默认保守值（20 字节） |
| 固件版本差异 | 版本检测 + 降级兼容 |
| 字体缺失导致渲染失败 | 自动 fallback（英文 → 无字体模式） |

---

## 📊 成功标准

- ✅ 无硬件可 Mock 测试通过（CI 绿）
- ✅ 代码覆盖率 ≥80%（墨水屏模块）
- ✅ 文档完整（API 文档 + 3 个示例）
- ✅ 有硬件可端到端刷新成功（等你的屏到）
- ✅ 刷新耗时 < 30 秒（nRF52）

---

**准备好了吗？我现在开始实施第一步：创建 `bus_arrival_board/epd/` 模块并实现 BLE 客户端。**
