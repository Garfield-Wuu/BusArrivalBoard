#!/bin/bash
# ESP-IDF 环境激活脚本
# 使用: source scripts/activate_idf.sh && cd firmware && idf.py build

export IDF_PATH=~/esp/esp-idf

# 激活 Python 虚拟环境
if [[ -f ~/.espressif/python_env/idf5.3_py3.10_env/bin/activate ]]; then
    source ~/.espressif/python_env/idf5.3_py3.10_env/bin/activate
elif [[ -f ~/.espressif/python_env/idf5.3_py3.11_env/bin/activate ]]; then
    source ~/.espressif/python_env/idf5.3_py3.11_env/bin/activate
else
    echo "错误: 找不到 ESP-IDF Python 环境，请先运行 ~/esp/esp-idf/install.sh"
    return 1
fi

# 加载工具链路径
if [[ -f $IDF_PATH/export.sh ]]; then
    source $IDF_PATH/export.sh
else
    echo "错误: $IDF_PATH/export.sh 不存在"
    return 1
fi

echo "ESP-IDF 环境已激活，当前版本:"
idf.py --version 2>/dev/null || python $IDF_PATH/tools/idf.py --version
