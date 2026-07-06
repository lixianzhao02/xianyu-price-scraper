---
name: scraper-debug
description: 'Diagnose and fix issues with the Xianyu (goofish.com) NS cartridge scraper. Use when: scraper returns empty results, login fails, DOM changed, anti-detection triggered, images not downloading, Excel errors, or any scraper malfunction.'
argument-hint: 'Describe the scraper issue (e.g., "empty search results", "login not working", "no images downloaded")'
---

# 闲鱼爬虫诊断技能

诊断和修复闲鱼 NS 卡带价格爬虫的常见问题。

## 何时使用

- 搜索结果为空或数量异常
- 登录失败或 Cookie 过期
- 闲鱼页面结构变化导致提取失败
- 反爬检测触发（被识别为机器人）
- 图片下载失败
- Excel 输出异常（公式错误、数据缺失）
- 任何爬虫运行时错误

## 诊断流程

### 1. 收集现场信息

```bash
# 查看最近日志
type data\scraper.log | Select-Object -Last 50

# 查看截图目录（出错时自动保存）
dir data\screenshots\

# 运行诊断脚本（截图 + DOM dump）
python diagnose.py
```

### 2. 检查登录状态

查看 `data/screenshots/home.png` 截图，确认是否处于登录态。

**判断依据：**
- 页面顶部显示用户昵称 / "我的闲鱼" → 已登录
- 页面显示"登录"按钮或"请登录"提示 → Cookie 过期

**修复：**
```bash
python main.py --login
```

### 3. 分析 DOM 结构

运行 `diagnose.py` 后查看输出和截图：

- 检查 `data/screenshots/search.png` — 搜索结果是否正常渲染
- 检查 `data/screenshots/home.png` — 首页是否正常
- 查看 `diagnose.py` 输出的 DOM 结构信息（容器 class、链接格式等）

**如果 DOM 结构变化：**
1. 运行 `python main.py --headful --verbose` 观察浏览器实际行为
2. 对比 `diagnose.py` 输出的容器 class 与 `core/scraper.py` 中 `_extract_search_items()` 和 `_extract_detail()` 的 CSS 选择器
3. 更新选择器以匹配新结构

### 4. 检查反检测机制

查看 `core/scraper.py` 中的反检测配置：

- `add_init_script()` 注入的脚本（`webdriver` 隐藏、`navigator` 伪造）
- `_human_scroll()` 的滚动参数
- 随机延迟范围（搜索间 5-10s）

**如果被检测：**
- 增加 `_human_scroll` 的滚动次数和延迟
- 更新 User-Agent 为最新 Chrome 版本
- 添加更多浏览器指纹伪造（WebGL、Canvas、AudioContext 等）
- 减少 `--max-items` 和 `--max-detail` 降低请求频率

### 5. 检查图片下载

查看日志中的图片下载错误：

- 检查 `data/images/<游戏名>/<商品ID>/` 目录是否存在
- 确认 `core/image_downloader.py` 中的 `Referer` 头是否正确
- 测试单个图片 URL 是否可访问

### 6. 检查 Excel 输出

- 打开生成的 `.xlsx` 文件检查三个 Sheet
- 如果公式显示 `#NAME?` — 需 Excel 2019+ 或 Microsoft 365
- 如果数据缺失 — 检查 `all_items` 是否包含所需字段

## 常见修复

| 问题 | 修复 |
|------|------|
| Cookie 过期 | `python main.py --login` 重新扫码 |
| 搜索结果为空 | 检查 `diagnose.py` 截图，更新 CSS 选择器 |
| 反爬检测 | 更新 User-Agent，增加延迟，减少并发 |
| 图片下载失败 | 检查 `Referer` 头，测试图片 URL 可达性 |
| Excel 公式错误 | 确认 Excel 版本支持 `MINIFS`/`MAXIFS` |
| 页面结构变化 | 更新 `_extract_search_items()` 和 `_extract_detail()` 中的 JS 选择器 |

## 参考文件

- [爬虫核心模块](../../core/scraper.py) — 登录、搜索、详情提取逻辑
- [图片下载模块](../../core/image_downloader.py) — 防盗链处理
- [诊断脚本](../../diagnose.py) — DOM 分析工具
- [登录检测测试](../../test_login_fix.py) — 登录状态检测逻辑
