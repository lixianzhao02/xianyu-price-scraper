@echo off
chcp 65001 >nul 2>&1
REM ============================================================
REM  闲鱼NS卡带价格爬虫 - 环境安装脚本
REM  双击运行即可自动安装所有依赖
REM ============================================================

echo.
echo  ============================================
echo    闲鱼NS卡带价格爬虫 - 环境安装
echo  ============================================
echo.

REM 切换到脚本所在目录
cd /d "%~dp0"

REM 检测Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo  [错误] 未检测到Python，请先安装 Python 3.9+
    echo  下载地址: https://www.python.org/downloads/
    echo  安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)

echo  [1/4] 检测到Python:
python --version
echo.

REM 创建虚拟环境（如果不存在）
if not exist ".venv" (
    echo  [2/4] 创建虚拟环境...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo  [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo  虚拟环境已创建: .venv
) else (
    echo  [2/4] 虚拟环境已存在，跳过创建
)
echo.

REM 激活虚拟环境
call ".venv\Scripts\activate.bat"

REM 安装Python依赖
echo  [3/4] 安装Python依赖...
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo  [错误] 依赖安装失败，请检查网络连接
    pause
    exit /b 1
)
echo  依赖安装完成
echo.

REM 安装Playwright浏览器
echo  [4/4] 安装Playwright浏览器引擎（首次较慢）...
python -m playwright install chromium
if %errorlevel% neq 0 (
    echo  [错误] Playwright浏览器安装失败
    echo  请尝试手动运行: python -m playwright install chromium
    pause
    exit /b 1
)
echo  Playwright浏览器安装完成
echo.

echo  ============================================
echo    环境安装完成！
echo  ============================================
echo.
echo  下一步:
echo    1. 首次登录: python main.py --login
echo    2. 执行爬取: python main.py
echo    3. 定时运行: 见 run_daily.bat
echo.
pause
