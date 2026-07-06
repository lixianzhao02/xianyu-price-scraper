# 闲鱼NS卡带价格爬虫 — AI Agent 指南

## 项目概述

基于 Playwright（浏览器模式）或 HTTP API（无浏览器模式）的闲鱼（goofish.com）NS 卡带价格抓取工具，支持图片下载、Excel 输出、MySQL 存储和每日定时更新。

## 快速命令

```bash
# 环境安装
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium

# 运行（Playwright 浏览器模式）
python main.py                          # 无头模式执行爬取
python main.py --login                  # 首次扫码登录
python main.py --headful --verbose      # 调试模式（可见浏览器+详细日志）
python main.py --no-detail --max-items 10  # 快速模式
python main.py --games 塞尔达           # 只爬指定游戏
python main.py --config path/to.yaml    # 自定义配置

# 运行（API 无浏览器模式，推荐 Linux）
python main.py --api                    # API 模式执行爬取
python main.py --api --login            # API 模式首次登录（终端扫码）
python main.py --api --from-db --no-excel  # API 模式 + 数据库 + 无 Excel

# 诊断
python diagnose.py                      # 截图并 dump DOM 结构
python generate_demo.py                 # 生成示例 Excel
python test_login_fix.py                # 测试登录检测逻辑
```

## 项目结构

```
xianyu-ns-scraper/
├── main.py                  # 入口：CLI 参数解析 + 主流程编排
├── config/
│   ├── games.yaml           # 游戏清单（可编辑 YAML）
│   └── config.yaml          # 数据库/爬虫/价格算法配置
├── core/
│   ├── scraper.py           # Playwright 爬虫核心（登录/搜索/详情/反检测）
│   ├── api_scraper.py       # HTTP API 爬虫核心（无浏览器模式）
│   ├── xianyu/              # XianYuApis HTTP API 库
│   │   ├── apis.py          # API 封装（登录/搜索/详情/发布）
│   │   ├── utils/           # 工具函数（签名生成、Cookie构建）
│   │   ├── static/          # JS 签名算法文件
│   │   └── message/         # 消息类型定义
│   ├── excel_writer.py      # Excel 输出（最新价格/价格历史/价格统计）
│   ├── image_downloader.py  # 图片下载（防盗链处理）
│   ├── db_writer.py         # MySQL 数据库写入 + 价格算法
│   └── config_loader.py     # 配置加载模块
├── data/
│   ├── cookies/             # Cookie 持久化
│   ├── images/              # 下载图片
│   ├── output/              # Excel + JSON 输出
│   └── screenshots/         # 调试截图
├── setup.bat                # Windows 环境安装脚本
├── setup_linux.sh           # Linux 环境安装脚本
├── run_daily.bat            # Windows 定时任务脚本
├── run_linux.sh             # Linux 运行脚本
├── cron_setup.sh            # Linux 定时任务安装脚本
├── diagnose.py              # DOM 诊断工具
├── generate_demo.py         # 示例数据生成
└── test_login_fix.py        # 登录检测测试
```

## 架构要点

### 双引擎架构

#### 引擎一：Playwright 浏览器模式 (`core/scraper.py`)
- **`XianyuScraper`** — 上下文管理器，管理 Playwright 浏览器生命周期
- **登录流程**：`login()` → 弹出浏览器扫码 → 轮询检测登录 → 保存 Cookie
- **搜索流程**：`search()` → 访问搜索页 → 模拟人类滚动 → `_extract_search_items()` 用 JS 提取 DOM
- **详情流程**：`get_detail()` → 进入商品详情 → `_extract_detail()` 提取图片/描述/成色
- **反检测**：`add_init_script()` 注入 `webdriver` 隐藏、`_human_scroll()` 模拟滚动、随机延迟
- **过滤**：`_filter_cartridge_items()` 排除数字版/MOD/攻略等非实体卡带

#### 引擎二：HTTP API 模式 (`core/api_scraper.py`)
- **`ApiXianyuScraper`** — 基于 XianYuApis HTTP API，无需浏览器
- **登录流程**：`login()` → 终端显示二维码 → 闲鱼 APP 扫码 → 保存 Cookie
- **搜索流程**：`search()` → 调用 mtop API → 翻页采集 → 解析 JSON 响应
- **无详情页**：API 模式暂不支持详情页（搜索结果已含价格/标题/图片）
- **过滤**：与 Playwright 模式一致的 `_filter_cartridge_items()` 逻辑
- **依赖**：需要 Node.js 18+（用于执行 JS 签名算法）

### XianYuApis 库 (`core/xianyu/`)
- **`XianyuApis`** — HTTP API 封装类，提供 `search()`、`get_item_info()`、`get_token()` 等方法
- **`qrcode_login()`** — 终端二维码登录，返回已登录的 XianyuApis 实例
- **`build_initial_cookies()`** — 纯 HTTP 获取基础 Cookie（无登录态）
- **签名算法**：`utils/goofish_utils.py` 通过 `execjs` 调用 `static/goofish_js_version_2.js`
- **tfstk 生成**：`utils/gen_tfstk.js` 通过 Node.js 子进程生成

### Excel 输出 (`core/excel_writer.py`)
- **4 个 Sheet**："最新价格"（覆盖）、"价格历史"（追加）、"价格统计"（Excel 公式）、"游戏价格汇总"
- 使用 `MINIFS`/`MAXIFS`/`AVERAGEIF` 公式，需 Excel 2019+ 或 Microsoft 365
- 图片列存储本地路径，点击可打开

### 数据库写入 (`core/db_writer.py`)
- **价格算法**：IQR 去异常值 → 10元分桶 → 主簇中位数×0.7 + 整体中位数×0.3 → 30%稳定性约束 → math.ceil
- **价格稳定器**：指数平滑（alpha=0.3）+ 每日最大波动限制（5元）
- **表结构**：`scraper_records`（汇总）+ `scraper_raw_data`（原始 JSON）

### 图片下载 (`core/image_downloader.py`)
- 设置 `Referer` 头处理防盗链
- 自动去重（已存在且非空则跳过）
- 目录结构：`data/images/<游戏名>/<商品ID>/`

## 重要约定

- **编码**：所有 Python 文件使用 `# -*- coding: utf-8 -*-`，UTF-8 编码
- **虚拟环境**：`.venv\` 目录，通过 `setup.bat` 创建
- **Cookie**：存储在 `data/cookies/xianyu_state.json`，有效期约 7-30 天
- **日志**：同时输出到 `data/scraper.log` 和 stdout
- **截图**：出错时自动保存到 `data/screenshots/`，用于调试 DOM 变化
- **反爬**：内置随机延迟（搜索间 5-10s）和反检测脚本，不建议过于频繁运行

## 常见陷阱

1. **Cookie 过期**：运行 `python main.py --login` 或 `python main.py --api --login` 重新扫码
2. **闲鱼页面结构变化**：查看 `data/screenshots/` 截图，运行 `diagnose.py` 分析 DOM
3. **搜索结果为空**：检查 Cookie 有效性，用 `--headful --verbose` 观察浏览器行为
4. **Excel 公式错误**：`MINIFS`/`MAXIFS` 需要 Excel 2019+，旧版需手动修改公式
5. **图片下载失败**：防盗链限制，程序已设 Referer，可检查网络
6. **API 模式 Node.js 错误**：确保 Node.js 18+ 已安装，`core/xianyu/static/goofish_js_version_2.js` 存在
7. **API 模式 execjs 错误**：确保已安装 `execjs` 和 `blackboxprotobuf` 依赖

## 配置格式 (`config/games.yaml`)

```yaml
games:
  - name: "游戏名称"
    search_keyword: "闲鱼搜索关键词 NS卡带"
    version: "卡带"
```

`search_keyword` 建议包含 "NS卡带" 或 "switch卡带" 以精确匹配。
