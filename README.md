# 闲鱼NS卡带价格爬虫

基于 Playwright（浏览器模式）或 HTTP API（无浏览器模式）的闲鱼（goofish.com）NS卡带价格抓取工具，支持图片下载、Excel输出、MySQL存储和每日定时更新。

## 功能

- 按游戏清单搜索闲鱼二手NS卡带
- **双引擎**：Playwright 浏览器模式（默认）或 HTTP API 模式（`--api`，无需浏览器）
- 抓取商品标题、价格、卖家、地区、商品链接
- 下载宣传图和卡带信息图到本地
- 输出Excel（含"最新价格"、"价格历史"、"价格统计"、"游戏价格汇总"四个Sheet）
- 价格统计Sheet使用Excel公式自动计算最低/最高/平均价
- 支持每日定时运行，历史数据自动追加
- **价格算法**：IQR去异常值 + 10元分桶 + 主簇中位数 + 历史平滑稳定器

## 快速开始

### 1. 环境安装

双击运行 `setup.bat`，或手动执行：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

需要 Python 3.9+，下载地址：https://www.python.org/downloads/

### 2. 首次登录（扫码）

**Playwright 模式（默认）**：
```bash
python main.py --login
```
会弹出浏览器窗口，用手机淘宝/支付宝扫码登录闲鱼。登录成功后Cookie自动保存，后续运行无需重复登录。

**API 模式（无浏览器，推荐 Linux）**：
```bash
python main.py --api --login
```
在终端显示二维码，用闲鱼 APP 扫码（左上角扫一扫）。需要 Node.js 18+ 支持。

### 3. 执行爬取

```bash
# Playwright 模式（默认）
python main.py

# API 模式（无浏览器，适合 Linux 服务器）
python main.py --api
```

无头模式运行，爬取配置文件中所有游戏。结果保存在 `data/output/` 目录。

### 4. 查看结果

- **Excel文件**: `data/output/NS卡带价格追踪.xlsx`
  - Sheet "最新价格" — 当前快照，每次运行覆盖
  - Sheet "价格历史" — 所有历史记录，每次运行追加
  - Sheet "价格统计" — 公式自动计算各游戏最低/最高/平均价
  - Sheet "游戏价格汇总" — 各游戏最新参考价汇总
- **图片目录**: `data/images/<游戏名>/<商品ID>/`
- **JSON备份**: `data/output/NS卡带价格_YYYY-MM-DD.json`

## 命令行参数

```
python main.py [选项]

选项:
  --api            使用 HTTP API 模式（无需浏览器，终端扫码，适合 Linux）
  --login          首次登录（Playwright 模式弹出浏览器，API 模式终端扫码）
  --config PATH    游戏配置文件路径 (默认: config/games.yaml)
  --headful        显示浏览器窗口（调试用，仅 Playwright 模式）
  --no-detail      不抓详情页（快速模式，只抓搜索结果）
  --max-items N    每个游戏最大商品数 (默认: 200)
  --max-detail N   每个游戏最大详情页数 (默认: 0，不抓详情)
  --download-images 下载商品图片（默认不下载，仅抓价格）
  --output NAME    输出Excel文件名
  --no-excel       不输出Excel文件（定时任务用）
  --games KEYWORD  只爬名称包含关键词的游戏
  --days N         只搜最近N天内发布的商品 (默认: 0，不限时间)
  --from-db        从 product_spu 表加载游戏列表（替代 YAML 配置）
  --verbose        详细日志
```

常用组合：

```bash
# 快速模式（仅搜索结果，不进详情页，速度快）
python main.py --no-detail --max-items 10

# 调试模式（可见浏览器，详细日志）
python main.py --headful --verbose

# 只爬塞尔达相关
python main.py --games 塞尔达

# API 模式（无浏览器，适合 Linux 服务器）
python main.py --api --from-db --no-excel

# API 模式首次登录（终端扫码）
python main.py --api --login
```

## 配置游戏清单

编辑 `config/games.yaml`，按以下格式添加游戏：

```yaml
games:
  - name: "游戏名称"
    search_keyword: "闲鱼搜索关键词 NS卡带"
    version: "卡带"
```

`search_keyword` 建议包含"NS卡带"或"switch卡带"以精确匹配，避免搜到周边配件。

## 定时任务（每日自动运行）

### 方法一：双击运行

每天双击 `run_daily.bat` 即可执行。

### 方法二：Windows任务计划程序（自动）

1. 打开"开始菜单" → 搜索"任务计划程序"
2. 点击"创建基本任务"
3. 名称填"闲鱼NS卡带价格爬虫"
4. 触发器选"每天"，设置时间（如每天上午10点）
5. 操作选"启动程序"
6. 程序路径选 `run_daily.bat` 的完整路径
7. 起始位置选项目根目录
8. 完成

也可以用命令行创建（管理员权限）：

```cmd
schtasks /create /tn "XianyuNSScraper" /tr "C:\完整路径\run_daily.bat" /sc daily /st 10:00
```

查看已创建的任务：

```cmd
schtasks /query /tn "XianyuNSScraper"
```

删除任务：

```cmd
schtasks /delete /tn "XianyuNSScraper" /f
```

定时运行日志保存在 `data/cron.log`。

## 目录结构

```
xianyu-ns-scraper/
├── config/
│   ├── games.yaml          # 游戏清单配置（可编辑）
│   └── config.yaml         # 数据库/爬虫/价格算法配置
├── core/
│   ├── scraper.py           # Playwright爬虫核心（浏览器模式）
│   ├── api_scraper.py       # HTTP API爬虫核心（无浏览器模式）
│   ├── xianyu/              # XianYuApis HTTP API 库
│   │   ├── apis.py          # API 封装（登录/搜索/详情/发布）
│   │   ├── utils/           # 工具函数（签名生成、Cookie构建）
│   │   ├── static/          # JS 签名算法文件
│   │   └── message/         # 消息类型定义
│   ├── image_downloader.py  # 图片下载模块
│   ├── excel_writer.py      # Excel输出模块
│   ├── db_writer.py         # MySQL数据库写入模块
│   └── config_loader.py     # 配置加载模块
├── data/
│   ├── cookies/             # 登录Cookie存储
│   ├── images/              # 下载的图片
│   ├── output/              # Excel和JSON输出
│   ├── screenshots/         # 调试截图
│   ├── scraper.log          # 运行日志
│   └── cron.log             # 定时任务日志
├── setup.bat                # Windows 环境安装
├── setup_linux.sh           # Linux 环境安装
├── run_daily.bat            # Windows 每日运行
├── run_linux.sh             # Linux 运行脚本
├── cron_setup.sh            # Linux 定时任务安装
├── diagnose.py              # DOM 诊断工具
├── generate_demo.py         # 示例数据生成
└── test_login_fix.py        # 登录检测测试
```
├── main.py                  # 主程序入口
├── setup.bat                # 环境安装脚本
├── run_daily.bat            # 每日运行脚本
├── requirements.txt         # Python依赖
└── README.md
```

## 注意事项

- **Cookie有效期**：闲鱼Cookie大约7-30天过期，过期后需重新运行 `python main.py --login`
- **反爬限制**：程序已内置随机延迟和反检测脚本，但仍不建议过于频繁地运行
- **DOM变化**：闲鱼页面结构可能更新，导致提取失败。可查看 `data/screenshots/` 中的截图调试
- **图片防盗链**：图片下载已设置Referer头处理防盗链
- **无头模式**：定时任务使用无头模式（无浏览器窗口），首次登录必须用 `--login` 且不能用无头模式

## 常见问题

**Q: 搜索结果为空？**
A: 可能是Cookie过期或闲鱼页面结构变化。运行 `python main.py --login` 重新登录，或 `python main.py --headful --verbose` 查看浏览器实际情况。查看 `data/screenshots/` 中的截图。

**Q: 图片下载失败？**
A: 部分图片可能有防盗链限制。程序已设置Referer，如仍失败可检查网络或手动下载。

**Q: Excel公式显示#NAME?或#REF!?**
A: 统计Sheet使用了MINIFS/MAXIFS函数，需Excel 2019+或Microsoft 365。旧版Excel可手动修改公式。

**Q: 如何加快爬取速度？**
A: 使用 `--no-detail` 跳过详情页，减少 `--max-items` 数量。

**Q: 如何添加新游戏？**
A: 编辑 `config/games.yaml`，在 `games` 列表中添加新条目即可。
