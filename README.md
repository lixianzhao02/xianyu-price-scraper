# 闲鱼NS卡带价格爬虫

🎮 闲鱼 NS 卡带价格爬虫 — 双引擎（Playwright + HTTP API），自动计算参考价，支持 MySQL 存储、Excel 输出、Linux 定时任务

## 功能

- **双引擎**：Playwright 浏览器模式（默认）或 HTTP API 模式（`--api`，无需浏览器，适合 Linux）
- **智能定价**：IQR 去异常值 + 10元分桶 + 主簇中位数 + 历史平滑稳定器
- **自动续期**：Cookie 自动刷新，无需频繁扫码
- **多端输出**：Excel（4个Sheet）、MySQL 数据库、JSON 备份
- **定时任务**：支持 Linux cron 每日自动运行
- **反爬策略**：随机延迟、关键词过滤、翻页采集

## 快速开始

### 环境安装

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium

# Linux
bash setup_linux.sh
```

需要 Python 3.9+，API 模式需要 Node.js 18+。

### 首次登录

```bash
# Playwright 模式（弹出浏览器扫码）
python main.py --login

# API 模式（终端显示二维码，用闲鱼 APP 扫码）
python main.py --api --login
```

### 执行爬取

```bash
# Playwright 模式
python main.py

# API 模式（推荐 Linux 服务器）
python main.py --api --from-db --no-excel
```

## 命令行参数

| 参数 | 说明 |
|------|------|
| `--api` | HTTP API 模式（无需浏览器） |
| `--login` | 首次扫码登录 |
| `--from-db` | 从数据库加载游戏列表 |
| `--no-excel` | 不输出 Excel（定时任务用） |
| `--max-items N` | 每游戏最大采集数（默认 200） |
| `--games KEYWORD` | 只爬指定游戏 |
| `--headful` | 显示浏览器窗口（调试用） |
| `--verbose` | 详细日志 |

## 价格算法

```
原始价格 → IQR去异常值 → 10元分桶 → 主簇中位数×0.7 + 整体中位数×0.3
→ 30%稳定性约束 → math.ceil → 指数平滑(α=0.3) + 日波动≤5元 → 参考价
```

## 目录结构

```
xianyu-ns-scraper/
├── main.py                  # 主程序入口
├── config/
│   ├── games.yaml           # 游戏清单
│   └── config.yaml          # 数据库/爬虫配置（已 gitignore）
├── core/
│   ├── scraper.py           # Playwright 爬虫引擎
│   ├── api_scraper.py       # HTTP API 爬虫引擎
│   ├── xianyu/              # XianYuApis HTTP API 库
│   │   ├── apis.py          # API 封装（登录/搜索/签名）
│   │   ├── utils/           # 签名生成、Cookie 构建
│   │   └── static/          # JS 签名算法
│   ├── db_writer.py         # MySQL 写入 + 价格算法
│   ├── excel_writer.py      # Excel 输出
│   ├── image_downloader.py  # 图片下载
│   └── config_loader.py     # 配置加载
├── data/                    # 运行时数据（已 gitignore）
├── setup.bat                # Windows 安装
├── setup_linux.sh           # Linux 安装
├── run_daily.bat            # Windows 每日运行
├── run_linux.sh             # Linux 运行脚本
├── cron_setup.sh            # Linux 定时任务安装
└── requirements.txt         # Python 依赖
```

## 定时任务（Linux）

```bash
# 安装定时任务（每天凌晨4点自动执行）
bash cron_setup.sh

# 查看已安装的任务
crontab -l
```

## 技术栈

- **Python 3.9+** — 核心语言
- **Playwright** — 浏览器自动化引擎
- **XianYuApis** — 闲鱼 HTTP API 封装（签名算法逆向）
- **Node.js 18+** — 执行 JS 签名算法
- **MySQL** — 价格数据持久化
- **openpyxl** — Excel 输出
- **NumPy** — 价格算法计算

## 许可证

MIT

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
