#!/usr/bin/env bash
#
# 质量门禁 — 每个开发阶段结束后必须通过
#
# 用法:
#   ./scripts/review.sh            # 全量检查
#   ./scripts/review.sh --quick    # 跳过 3.9 兼容性检查（较慢）
#
# 退出码: 0=全部通过, 1=有阻塞项
#
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

QUICK=0
[[ "${1:-}" == "--quick" ]] && QUICK=1

FAILED=0
PASSED=0
SKIPPED=0

pass() { echo "  ✅ $1"; PASSED=$((PASSED + 1)); }
fail() { echo "  ❌ $1"; FAILED=$((FAILED + 1)); }
skip() { echo "  ⏭️  $1"; SKIPPED=$((SKIPPED + 1)); }
section() { echo; echo "── $1 ──"; }

# ---------------------------------------------------------------------------
section "1. 代码格式"
# ---------------------------------------------------------------------------
if command -v black >/dev/null 2>&1; then
    if black --check . >/dev/null 2>&1; then
        pass "black 格式规范"
    else
        fail "black 未格式化（运行: black .）"
    fi
else
    skip "black 未安装"
fi

if command -v isort >/dev/null 2>&1; then
    if isort --check-only . >/dev/null 2>&1; then
        pass "isort import 顺序"
    else
        fail "isort 顺序错误（运行: isort .）"
    fi
else
    skip "isort 未安装"
fi

# ---------------------------------------------------------------------------
section "2. 单元测试"
# ---------------------------------------------------------------------------
if command -v pytest >/dev/null 2>&1; then
    TEST_OUT=$(PYTHONPATH=. pytest -m "not network and not hardware" -q 2>&1)
    if echo "$TEST_OUT" | grep -qE "^(FAILED|ERROR)|failed"; then
        fail "测试失败"
        echo "$TEST_OUT" | tail -8 | sed 's/^/      /'
    else
        COUNT=$(echo "$TEST_OUT" | grep -oE "[0-9]+ passed" | head -1 || echo "? passed")
        pass "离线测试通过（$COUNT）"
    fi
else
    skip "pytest 未安装"
fi

# ---------------------------------------------------------------------------
section "3. 导入健全性"
# ---------------------------------------------------------------------------
# 核心 SDK 不得依赖可选依赖
if PYTHONPATH=. python3 -c "import chelaile_sdk, bus_arrival_board.cli" 2>/dev/null; then
    pass "核心模块可导入"
else
    fail "核心模块导入失败"
fi

# 可选依赖模块：装了就该能导入
if python3 -c "import bleak, PIL" 2>/dev/null; then
    if PYTHONPATH=. python3 -c "import bus_arrival_board.epd" 2>/dev/null; then
        pass "epd 模块可导入"
    else
        fail "epd 模块导入失败"
    fi
else
    skip "epd 依赖未安装"
fi

# ---------------------------------------------------------------------------
section "4. Python 3.9 兼容性"
# ---------------------------------------------------------------------------
# 项目声明支持 3.9；本机通常是更高版本，用 uv 拉真实 3.9 验证
if [[ $QUICK -eq 1 ]]; then
    skip "跳过（--quick）"
elif [[ -x /tmp/py39/bin/python ]]; then
    if /tmp/py39/bin/python -c "import chelaile_sdk, bus_arrival_board.cli" 2>/dev/null; then
        pass "3.9 导入正常"
    else
        fail "3.9 导入失败（检查 int|None 语法需 __future__ 导入）"
    fi
elif command -v uv >/dev/null 2>&1; then
    skip "3.9 环境未就绪（uv venv --python 3.9 /tmp/py39）"
else
    skip "无 3.9 环境且无 uv"
fi

# ---------------------------------------------------------------------------
section "5. 安全扫描（暂存区新增行）"
# ---------------------------------------------------------------------------
# 只扫代码文件，且排除门禁脚本自身——否则本脚本里的检测模式
# 会被当成真实的危险调用，造成自我误报。
SCAN_PATHS=('*.py' '*.c' '*.h' '*.yaml' '*.yml' '*.toml')
DIFF=$(git diff --cached -- "${SCAN_PATHS[@]}" 2>/dev/null || true)
[[ -z "$DIFF" ]] && DIFF=$(git diff -- "${SCAN_PATHS[@]}" 2>/dev/null || true)

if [[ -z "$DIFF" ]]; then
    skip "无改动"
else
    ADDED=$(echo "$DIFF" | grep "^+" || true)

    # 硬编码密钥（排除已知的上游协议常量）
    if echo "$ADDED" | grep -iE "(api_key|secret|password|passwd|token)\s*=\s*['\"][^'\"]{8,}['\"]" \
        | grep -viE "(AES_KEY|SALT|placeholder|example|your_|xxx|test)" | grep -q .; then
        fail "可能的硬编码凭据"
        echo "$ADDED" | grep -inE "(api_key|secret|password|token)\s*=\s*['\"][^'\"]{8,}['\"]" \
            | grep -viE "(AES_KEY|SALT|placeholder|example|your_)" | head -3 | sed 's/^/      /'
    else
        pass "无硬编码凭据"
    fi

    # 危险调用
    if echo "$ADDED" | grep -E "os\.system\(|shell=True|\beval\(|\bexec\(|pickle\.loads?\(" | grep -q .; then
        fail "存在危险调用（os.system/shell=True/eval/exec/pickle）"
        echo "$ADDED" | grep -nE "os\.system\(|shell=True|\beval\(|\bexec\(" | head -3 | sed 's/^/      /'
    else
        pass "无危险调用"
    fi
fi

# ---------------------------------------------------------------------------
section "6. 文档与配置一致性"
# ---------------------------------------------------------------------------
# 版本号三处必须一致
V_INIT=$(grep -oE '__version__ = "[^"]+"' chelaile_sdk/__init__.py 2>/dev/null | grep -oE '[0-9.]+' || echo "")
V_TOML=$(grep -oE '^version = "[^"]+"' pyproject.toml 2>/dev/null | grep -oE '[0-9.]+' || echo "")
V_SETUP=$(grep -oE 'version="[^"]+"' setup.py 2>/dev/null | grep -oE '[0-9.]+' || echo "")

if [[ -n "$V_INIT" && "$V_INIT" == "$V_TOML" && "$V_TOML" == "$V_SETUP" ]]; then
    pass "版本号一致（$V_INIT）"
else
    fail "版本号不一致: __init__=$V_INIT pyproject=$V_TOML setup=$V_SETUP"
fi

# 依赖三处必须一致（requirements.txt 是 pyproject 的子集）
if [[ -f requirements.txt ]]; then
    MISSING=""
    while read -r dep; do
        [[ -z "$dep" || "$dep" == \#* ]] && continue
        name=$(echo "$dep" | sed -E 's/[><=!~].*//' | tr -d ' ')
        [[ -z "$name" ]] && continue
        grep -q "\"$name" pyproject.toml || MISSING="$MISSING $name"
    done < requirements.txt

    if [[ -z "$MISSING" ]]; then
        pass "requirements.txt 与 pyproject 一致"
    else
        fail "pyproject 缺少依赖:$MISSING"
    fi
else
    skip "无 requirements.txt"
fi

# ---------------------------------------------------------------------------
section "7. ESP-IDF 固件（若存在）"
# ---------------------------------------------------------------------------
if [[ -d firmware ]]; then
    # 顶层与 main 组件必须有 CMakeLists.txt
    if [[ -f firmware/CMakeLists.txt && -f firmware/main/CMakeLists.txt ]]; then
        pass "CMakeLists.txt 结构完整"
    else
        fail "缺少 CMakeLists.txt（顶层或 main/）"
    fi

    # 每个组件目录都要有自己的 CMakeLists.txt
    BAD_COMP=""
    for d in firmware/components/*/; do
        [[ -d "$d" ]] || continue
        [[ -f "$d/CMakeLists.txt" ]] || BAD_COMP="$BAD_COMP $(basename "$d")"
    done
    if [[ -z "$BAD_COMP" ]]; then
        pass "组件 CMakeLists.txt 齐全"
    else
        fail "组件缺少 CMakeLists.txt:$BAD_COMP"
    fi

    # 固件不得硬编码 WiFi 凭据
    if grep -rEn '(WIFI_SSID|WIFI_PASS\w*)\s+"[^"]{3,}"' firmware --include='*.c' --include='*.h' 2>/dev/null \
        | grep -viE '(CONFIG_|your_|example|placeholder|""|MY_SSID)' | grep -q .; then
        fail "固件疑似硬编码 WiFi 凭据"
    else
        pass "固件无硬编码凭据"
    fi

    # idf.py 可用时做真实构建
    if command -v idf.py >/dev/null 2>&1; then
        skip "idf.py 存在，建议手动运行 idf.py build 验证"
    else
        skip "idf.py 未安装（无法验证真实编译）"
    fi
else
    skip "firmware/ 目录不存在"
fi

# ---------------------------------------------------------------------------
echo
echo "════════════════════════════════════════"
echo "  通过 $PASSED  失败 $FAILED  跳过 $SKIPPED"
echo "════════════════════════════════════════"

if [[ $FAILED -gt 0 ]]; then
    echo "❌ 门禁未通过，修复后重跑"
    exit 1
fi
echo "✅ 门禁通过"
exit 0
