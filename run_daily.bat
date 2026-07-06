@echo off
chcp 65001 >nul 2>&1
REM ============================================================
REM  闲鱼NS卡带价格爬虫 - 每日定时运行脚本
REM
REM  使用方法:
REM    1. 双击运行一次测试
REM    2. 通过Windows任务计划程序设置每日自动运行
REM       （详见 README.md "定时任务"章节）
REM ============================================================

REM 切换到脚本所在目录
cd /d "%~dp0"

REM 记录开始时间
set START_TIME=%date% %time%
echo [%START_TIME%] 开始运行闲鱼爬虫... >> data\cron.log

REM 激活虚拟环境（如果存在）
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo [警告] 未找到虚拟环境，使用系统Python >> data\cron.log
)

REM 执行爬虫（无头模式，不抓详情以加快速度）
REM 如需详情页图片，去掉 --no-detail 参数
python main.py --no-detail --max-items 15 >> data\cron.log 2>&1

REM 检查退出码
if %errorlevel% equ 0 (
    echo [%date% %time%] 爬取完成，成功 >> data\cron.log
) else (
    echo [%date% %time%] 爬取失败，退出码: %errorlevel% >> data\cron.log
)

echo. >> data\cron.log
