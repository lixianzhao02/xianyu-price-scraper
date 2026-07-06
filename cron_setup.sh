#!/bin/bash
# 闲鱼NS卡带价格爬虫 - Linux 定时任务安装脚本
# 用法: bash cron_setup.sh
# 功能: 添加每日凌晨4点执行的 crontab 任务

set -e

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"
CRON_LOG="$PROJECT_DIR/data/cron.log"
PYTHON="$PROJECT_DIR/.venv/bin/python"
MAIN="$PROJECT_DIR/main.py"

# 确保 data 目录存在
mkdir -p "$PROJECT_DIR/data"

# 从配置文件读取定时时间
if [ -f "$PROJECT_DIR/config.yaml" ]; then
    CRON_TIME=$(python3 -c "
import yaml
with open('$PROJECT_DIR/config.yaml') as f:
    cfg = yaml.safe_load(f)
t = cfg.get('schedule', {}).get('daily_time', '04:00')
print(t)
" 2>/dev/null || echo "04:00")
else
    CRON_TIME="04:00"
fi

HOUR=$(echo $CRON_TIME | cut -d: -f1)
MINUTE=$(echo $CRON_TIME | cut -d: -f2)

# 构建 crontab 行（API 模式，无需浏览器）
CRON_LINE="$MINUTE $HOUR * * * cd $PROJECT_DIR && $PYTHON $MAIN --api --from-db --no-excel >> $CRON_LOG 2>&1"

# 检查是否已存在
if crontab -l 2>/dev/null | grep -q "$MAIN"; then
    echo "定时任务已存在，正在更新..."
    (crontab -l 2>/dev/null | grep -v "$MAIN"; echo "$CRON_LINE") | crontab -
else
    echo "添加定时任务..."
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
fi

echo ""
echo "============================================"
echo "  定时任务已设置！"
echo "============================================"
echo ""
echo "  执行时间: 每天 $CRON_TIME"
echo "  执行命令: $PYTHON $MAIN --from-db --no-excel"
echo "  日志文件: $CRON_LOG"
echo ""
echo "查看定时任务:"
echo "  crontab -l"
echo ""
echo "删除定时任务:"
echo "  crontab -e  # 手动删除包含 xianyu 的行"
echo ""
