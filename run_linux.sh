#!/bin/bash
# 闲鱼NS卡带价格爬虫 - Linux 执行脚本
# 用法: bash run_linux.sh [--login]

set -e

cd "$(dirname "$0")"
PYTHON=".venv/bin/python"
MAIN="main.py"

if [ ! -d ".venv" ]; then
    echo "[错误] 虚拟环境不存在，请先运行 bash setup_linux.sh"
    exit 1
fi

if [ "$1" = "--login" ]; then
    echo "首次登录模式（Playwright 浏览器）..."
    $PYTHON $MAIN --login
elif [ "$1" = "--api-login" ]; then
    echo "首次登录模式（API 终端扫码）..."
    $PYTHON $MAIN --api --login
elif [ "$1" = "--api" ]; then
    echo "执行爬取（API 模式，无浏览器）..."
    $PYTHON $MAIN --api --from-db --no-excel
else
    echo "执行爬取（Playwright 模式）..."
    $PYTHON $MAIN --from-db --no-excel
fi
