#!/bin/bash
# 闲鱼NS卡带价格爬虫 - Linux 环境安装脚本
# 用法: bash setup_linux.sh

set -e

echo "============================================"
echo "  闲鱼NS卡带价格爬虫 - Linux 环境安装"
echo "============================================"
echo ""

cd "$(dirname "$0")"

# 检测 Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未检测到 Python3，请先安装 Python 3.9+"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "  CentOS/RHEL:   sudo yum install python3 python3-pip"
    exit 1
fi
echo "[1/4] Python: $(python3 --version)"

# 创建虚拟环境
if [ ! -d ".venv" ]; then
    echo "[2/4] 创建虚拟环境..."
    python3 -m venv .venv
    echo "  虚拟环境已创建: .venv"
else
    echo "[2/4] 虚拟环境已存在，跳过创建"
fi

# 安装依赖
echo "[3/4] 安装 Python 依赖..."
.venv/bin/pip install -r requirements.txt -q

# 安装 Playwright 浏览器（API 模式不需要，但保留兼容）
echo "[4/4] 安装 Playwright Chromium 浏览器（可选，API 模式不需要）..."
.venv/bin/python -m playwright install chromium 2>/dev/null || echo "  (跳过，API 模式不需要 Playwright)"

# 检测 Node.js（API 模式需要）
echo ""
echo "--- 可选依赖检查 ---"
if command -v node &> /dev/null; then
    echo "  Node.js: $(node --version) ✓ (API 模式需要)"
else
    echo "  Node.js: 未安装"
    echo "  API 模式需要 Node.js 18+ 来执行 JS 签名算法"
    echo "  安装: curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash - && sudo apt install -y nodejs"
    echo "  或: sudo apt install nodejs npm"
fi

echo ""
echo "============================================"
echo "  安装完成！"
echo "============================================"
echo ""
echo "首次登录（Playwright 浏览器模式）:"
echo "  .venv/bin/python main.py --login"
echo ""
echo "首次登录（API 模式，终端扫码）:"
echo "  .venv/bin/python main.py --api --login"
echo ""
echo "执行爬取（Playwright 模式）:"
echo "  .venv/bin/python main.py --from-db --no-excel"
echo ""
echo "执行爬取（API 模式，推荐 Linux）:"
echo "  .venv/bin/python main.py --api --from-db --no-excel"
echo ""
echo "设置定时任务:"
echo "  bash cron_setup.sh"
echo ""
