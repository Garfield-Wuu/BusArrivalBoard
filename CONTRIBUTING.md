# 贡献指南

感谢你考虑为 BusArrivalBoard 做出贡献！

## 🎯 贡献方式

我们欢迎以下类型的贡献：

- **代码改进** — Bug 修复、新功能、性能优化
- **文档完善** — README、API 文档、教程
- **硬件设计** — ESP32 适配、外壳 STL、BOM 优化
- **测试用例** — 单元测试、集成测试
- **问题反馈** — Bug 报告、功能建议

---

## 🔧 开发环境搭建

### 1. Fork 并克隆仓库

```bash
git clone https://github.com/YOUR_USERNAME/BusArrivalBoard.git
cd BusArrivalBoard
```

### 2. 安装开发依赖

```bash
pip install -e ".[dev]"
```

这会安装：
- pytest（测试框架）
- black/isort（代码格式化）
- mypy（类型检查）
- pytest-cov（覆盖率）

### 3. 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 跳过需要联网的测试
pytest -m "not network"

# 查看覆盖率
pytest --cov=chelaile_sdk --cov-report=html
```

---

## 📝 提交代码

### 分支命名规范

- `feature/xxx` — 新功能
- `fix/xxx` — Bug 修复
- `docs/xxx` — 文档更新
- `refactor/xxx` — 代码重构
- `test/xxx` — 测试相关

### Commit 消息格式

遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
<type>(<scope>): <subject>

<body>
```

**类型（type）：**
- `feat` — 新功能
- `fix` — Bug 修复
- `docs` — 文档
- `style` — 格式（不影响代码运行）
- `refactor` — 重构
- `test` — 测试
- `chore` — 构建/工具链

**示例：**
```bash
git commit -m "feat(sdk): 支持多线路并行查询"
git commit -m "fix(cli): 修复环线站点计算错误"
git commit -m "docs: 更新 ESP32 移植指南"
```

### 代码风格

运行格式化工具：

```bash
# 自动格式化
black .
isort .

# 检查但不修改
black --check .
isort --check-only .
```

### 类型检查

```bash
mypy chelaile_sdk/ bus_arrival_board/
```

---

## ✅ 提交 Pull Request 前检查

- [ ] 代码通过所有测试
- [ ] 新功能有对应的测试用例
- [ ] 代码符合 black/isort 规范
- [ ] 类型注解完整
- [ ] 添加了必要的文档/注释
- [ ] 更新了 README（如果适用）

---

## 🚨 报告 Bug

提交 Issue 时请包含：

1. **环境信息**
   - Python 版本
   - 操作系统
   - 依赖版本（`pip list | grep -E "requests|pydantic|click"`）

2. **复现步骤**
   - 具体命令或代码
   - 配置文件（去除敏感信息）

3. **预期行为 vs 实际行为**

4. **错误日志**
   ```
   完整的错误堆栈
   ```

---

## 💡 功能建议

提交功能请求时请说明：

- **使用场景** — 为什么需要这个功能？
- **预期行为** — 功能应该如何工作？
- **替代方案** — 目前有没有变通方法？

---

## 🧪 测试指南

### 编写测试

所有新功能都应该有测试覆盖。测试文件位于 `tests/` 目录：

```python
# tests/test_my_feature.py
import pytest
from chelaile_sdk import ChelaiLeClient

def test_my_feature():
    client = ChelaiLeClient()
    result = client.my_new_method()
    assert result is not None
```

### 标记测试

使用 `@pytest.mark.network` 标记需要联网的测试：

```python
@pytest.mark.network
def test_real_api():
    """这个测试会真实调用车来了 API"""
    client = ChelaiLeClient()
    cities = client.get_city_list()
    assert len(cities) > 0
```

CI 中会跳过 `network` 标记的测试。

---

## 📚 文档规范

### Docstring 风格

使用 Google 风格：

```python
def get_realtime_buses(
    self,
    city_id: str,
    line_id: str,
    station_id: str,
    target_order: int,
    lat: float,
    lng: float
) -> RealtimeResult:
    """获取实时到站信息
    
    Args:
        city_id: 城市ID（如 "014" 为深圳）
        line_id: 线路ID
        station_id: 站点ID
        target_order: 目标站点序号
        lat: 纬度（WGS-84）
        lng: 经度（WGS-84）
    
    Returns:
        实时查询结果，包含线路信息和车辆列表
    
    Raises:
        NetworkError: 网络请求失败
        APIError: API 返回错误
    
    Example:
        >>> client = ChelaiLeClient()
        >>> result = client.get_realtime_buses(
        ...     city_id="014",
        ...     line_id="0755182470300",
        ...     station_id="0755-15924",
        ...     target_order=17,
        ...     lat=22.6295,
        ...     lng=113.8127
        ... )
        >>> print(result.buses[0].bus_id)
        粤B05981D
    """
```

---

## 🔐 安全问题

如果发现安全漏洞，请**不要**公开提交 Issue，而是通过以下方式私下报告：

- 邮件：wu_garfield@163.com
- GitHub Security Advisory

---

## ❓ 问题咨询

- **GitHub Issues** — Bug 报告、功能请求
- **GitHub Discussions** — 一般性讨论、使用问题

---

## 📜 行为准则

我们致力于维护一个友好、包容的社区。请遵守以下原则：

- ✅ 尊重他人
- ✅ 建设性反馈
- ✅ 保持专业
- ❌ 人身攻击
- ❌ 骚扰行为
- ❌ 歧视性言论

---

再次感谢你的贡献！🎉
