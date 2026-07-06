# -*- coding: utf-8 -*-
"""
闲鱼NS卡带价格爬虫 - Playwright核心爬虫模块

功能：
  1. Cookie持久化登录（首次扫码，后续自动复用）
  2. 按关键词搜索闲鱼商品
  3. 提取搜索结果列表（标题、价格、图片、链接、卖家、地区）
  4. 进入详情页提取更多图片和描述
  5. 反自动化检测（随机延迟、模拟人类行为）

使用：
  with XianyuScraper(cookie_path, headless=True) as scraper:
      scraper.login()              # 首次登录
      items = scraper.scrape_game("塞尔达", "塞尔达 NS卡带")
"""

import re
import time
import random
import logging
from pathlib import Path
from datetime import datetime
from urllib.parse import quote_plus

from playwright.sync_api import (
    sync_playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeout,
)

logger = logging.getLogger(__name__)


class XianyuScraper:
    """闲鱼爬虫，支持Cookie持久化和自动搜索"""

    BASE_URL = "https://www.goofish.com"
    SEARCH_URL = "https://www.goofish.com/search"

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        cookie_path: str,
        headless: bool = True,
        max_items_per_game: int = 200,
        max_detail_pages: int = 0,
        days: int = 0,
    ):
        self.cookie_path = Path(cookie_path)
        self.headless = headless
        self.max_items_per_game = max_items_per_game
        self.max_detail_pages = max_detail_pages
        self.days = days
        self._playwright = None
        self._browser = None
        self._context = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self):
        """启动浏览器和上下文"""
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        ctx_kwargs = dict(
            user_agent=self.USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )

        if self.cookie_path.exists():
            ctx_kwargs["storage_state"] = str(self.cookie_path)
            logger.info("加载已保存的Cookie: %s", self.cookie_path)
        else:
            logger.info("未找到Cookie文件，需要首次登录")

        self._context = self._browser.new_context(**ctx_kwargs)

        # 注入反检测脚本
        self._context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            window.chrome = {runtime: {}};
            """
        )

    def close(self):
        """关闭浏览器"""
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.close()

    # ------------------------------------------------------------------
    # 登录
    # ------------------------------------------------------------------

    def login(self, timeout: int = 300) -> bool:
        """
        首次登录：打开浏览器让用户扫码
        timeout: 等待扫码的超时时间（秒），默认5分钟
        """
        page = self._context.new_page()
        try:
            page.goto(self.BASE_URL, wait_until="domcontentloaded")
            time.sleep(3)

            # 检查是否已经登录
            if self._check_logged_in(page):
                logger.info("已经处于登录状态")
                self._save_cookie()
                return True

            # 未登录，尝试打开登录弹窗
            logger.info("未检测到登录状态，准备扫码登录")
            try:
                login_link = page.locator("text=登录").first
                login_link.click(timeout=5000)
                time.sleep(2)
                logger.info("已点击登录按钮，等待弹窗")
            except Exception:
                logger.info("未找到登录按钮，尝试直接访问登录页")
                page.goto(f"{self.BASE_URL}/login", wait_until="domcontentloaded")
                time.sleep(2)

            print("\n" + "=" * 60)
            print("  请在弹出的浏览器窗口中扫码登录闲鱼")
            print("  登录成功后程序会自动继续（最多等待%d分钟）" % (timeout // 60))
            print("=" * 60 + "\n")

            # 轮询等待登录成功
            deadline = time.time() + timeout
            while time.time() < deadline:
                time.sleep(5)
                try:
                    if self._check_logged_in(page):
                        logger.info("检测到登录成功！")
                        self._save_cookie()
                        return True
                except Exception:
                    pass

            logger.error("登录超时（%d秒），请重新运行 --login", timeout)
            return False

        except Exception as e:
            logger.error("登录过程出错: %s", e)
            self._screenshot(page, "login_error")
            return False
        finally:
            page.close()

    def _check_logged_in(self, page: Page) -> bool:
        """
        检查是否已登录
        核心逻辑：未登录时页面会显示"立即登录""请登录"文本或登录弹窗
        """
        try:
            result = page.evaluate(
                """
                () => {
                    const text = document.body.innerText || '';
                    // "立即登录"只在未登录时的弹窗/banner中出现
                    if (text.includes('立即登录')) return false;
                    // "请登录"也表示未登录
                    if (text.includes('请登录')) return false;
                    // 检查是否有登录弹窗
                    const modal = document.querySelector(
                        '[class*="login-modal"], [class*="login-dialog"], '
                        + '[class*="LoginDialog"], [class*="login-box"]'
                    );
                    if (modal) return false;
                    // 检查header区域是否有独立的"登录"链接
                    // 未登录时header有"登录"，登录后变成用户昵称/"我的"
                    const navLinks = document.querySelectorAll(
                        'header a, header span, [class*="header"] a, [class*="header"] span'
                    );
                    for (const el of navLinks) {
                        const t = (el.textContent || '').trim();
                        if (t === '登录') return false;
                    }
                    return true;
                }
                """
            )
            return bool(result)
        except Exception:
            return False

    def _save_cookie(self):
        """保存Storage State（含Cookie和localStorage）"""
        self.cookie_path.parent.mkdir(parents=True, exist_ok=True)
        self._context.storage_state(path=str(self.cookie_path))
        logger.info("Cookie保存到: %s", self.cookie_path)

    def check_login_valid(self) -> bool:
        """
        检查已保存的Cookie是否仍然有效
        通过访问首页检查是否被重定向到登录页
        """
        page = self._context.new_page()
        try:
            page.goto(self.BASE_URL, wait_until="domcontentloaded")
            time.sleep(2)

            current_url = page.url
            if "login" in current_url:
                logger.warning("Cookie已失效，需要重新登录")
                return False

            if self._check_logged_in(page):
                logger.info("Cookie有效，已登录")
                return True

            logger.warning("Cookie已失效，需要重新登录")
            return False

        except Exception as e:
            logger.error("检查登录状态出错: %s", e)
            return False
        finally:
            page.close()

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------

    def search(self, keyword: str, game_name: str = "") -> list:
        """
        搜索闲鱼商品，返回搜索结果列表
        """
        page = self._context.new_page()
        items = []

        try:
            # 构建搜索URL
            url = f"{self.SEARCH_URL}?q={quote_plus(keyword)}"
            logger.info("搜索: %s -> %s", keyword, url)
            page.goto(url, wait_until="domcontentloaded")

            # 等待页面渲染
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeout:
                pass
            time.sleep(random.uniform(2, 4))

            # 检查是否需要登录
            if not self._check_logged_in(page):
                logger.error("需要登录才能搜索，请先运行 --login")
                self._screenshot(page, f"search_need_login_{game_name or keyword}")
                return []

            # 等待"加载中"消失
            for _ in range(10):
                is_loading = page.evaluate(
                    "() => (document.body.innerText || '').includes('加载中')"
                )
                if not is_loading:
                    break
                time.sleep(2)

            # 模拟人类滚动
            self._human_scroll(page, scrolls=3)

            # 提取搜索结果
            items = self._extract_search_items(page)

            # 翻页采集更多（滚动+翻页直到达到 max_items）
            if len(items) < self.max_items_per_game:
                items = self._scroll_and_collect(page, items)
            if len(items) < self.max_items_per_game:
                items = self._page_and_collect(page, items)

            items = items[: self.max_items_per_game]

            if not items:
                logger.warning("搜索 '%s' 未提取到商品", keyword)
                self._screenshot(page, f"search_empty_{game_name or keyword}")

            logger.info("搜索 '%s' 获取到 %d 个商品", keyword, len(items))

        except Exception as e:
            logger.error("搜索 '%s' 失败: %s", keyword, e)
            self._screenshot(page, f"search_error_{game_name or keyword}")
        finally:
            page.close()

        return items

    def _wait_page_ready(self, page: Page, timeout: int = 15):
        """等待页面就绪"""
        try:
            page.wait_for_load_state("networkidle", timeout=timeout * 1000)
        except PlaywrightTimeout:
            pass
        # 额外等待渲染
        time.sleep(random.uniform(1, 2))

    def _click_time_filter(self, page: Page):
        """点击搜索页的"7天内"时间筛选按钮"""
        try:
            time.sleep(1)
            # 先检查当前是否已经是"7天内"
            current = page.evaluate(
                """
                () => {
                    const title = document.querySelector('[class*="search-select-title"]');
                    return title ? title.textContent.trim() : '';
                }
                """
            )
            if current == '7天内':
                logger.info("已经是7天内筛选，无需切换")
                return

            # 点击标题展开下拉
            expanded = page.evaluate(
                """
                () => {
                    const container = document.querySelector('[class*="search-select-container"]');
                    if (!container) return false;
                    const title = container.querySelector('[class*="search-select-title"]');
                    if (title) { title.click(); return true; }
                    return false;
                }
                """
            )
            if not expanded:
                logger.info("未找到时间筛选容器")
                return

            time.sleep(0.8)
            # 展开后点击"7天内"
            clicked = page.evaluate(
                """
                () => {
                    const items = document.querySelectorAll('[class*="search-select-item"]');
                    for (const el of items) {
                        if (el.textContent.trim() === '7天内') {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }
                """
            )
            if clicked:
                logger.info("已选择时间筛选: 7天内")
                time.sleep(random.uniform(1, 2))
            else:
                logger.info("未找到7天内选项")
        except Exception as e:
            logger.debug("点击时间筛选失败: %s", e)

    def _human_scroll(self, page: Page, scrolls: int = 3):
        """模拟人类滚动行为"""
        for _ in range(scrolls):
            page.evaluate("window.scrollBy(0, 500)")
            time.sleep(random.uniform(0.5, 1.5))

    def _scroll_and_collect(self, page: Page, existing: list) -> list:
        """滚动加载更多并持续提取，翻页直到达到 max_items"""
        items = list(existing)
        seen = {i.get("url") for i in items if i.get("url")}
        no_new_count = 0

        for _ in range(30):  # 最多滚动30次
            if len(items) >= self.max_items_per_game:
                break

            page.evaluate("window.scrollBy(0, 1000)")
            time.sleep(random.uniform(1.5, 3))

            new_items = self._extract_search_items(page)
            added = 0
            for item in new_items:
                url = item.get("url")
                if url and url not in seen:
                    items.append(item)
                    seen.add(url)
                    added += 1

            # 连续3次没有新商品则停止
            if added == 0:
                no_new_count += 1
                if no_new_count >= 3:
                    break
            else:
                no_new_count = 0

            logger.info("  滚动加载: 已收集 %d/%d 个商品", len(items), self.max_items_per_game)

        return items

    def _page_and_collect(self, page: Page, existing: list) -> list:
        """翻页采集：点击下一页按钮，收集多页商品"""
        items = list(existing)
        seen = {i.get("url") for i in items if i.get("url")}
        max_pages = 20

        for page_num in range(2, max_pages + 2):
            if len(items) >= self.max_items_per_game:
                break

            # 点击下一页
            clicked = page.evaluate(
                """
                () => {
                    // 找下一页按钮（右箭头）
                    // 用户提供的 class: search-pagination-arrow-container--lt2kCP6J
                    const containers = document.querySelectorAll('[class*="search-pagination-arrow-container"]');
                    for (const c of containers) {
                        const cls = c.className || '';
                        // 右箭头（下一页）或最后一个箭头
                        if (cls.includes('right') || cls.includes('Right')) {
                            c.click();
                            return true;
                        }
                    }
                    // 如果没找到带方向的，点最后一个箭头容器
                    if (containers.length > 0) {
                        containers[containers.length - 1].click();
                        return true;
                    }
                    // 备选：找 tiny-arrow-right
                    const tinyRight = document.querySelector('[class*="arrow-right"], [class*="ArrowRight"]');
                    if (tinyRight) { tinyRight.click(); return true; }
                    return false;
                }
                """
            )
            if not clicked:
                logger.info("  翻页: 没有下一页按钮，停止翻页")
                break

            # 等待新页面加载
            time.sleep(random.uniform(2, 4))
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            time.sleep(random.uniform(1, 2))

            # 滚动一下触发懒加载
            self._human_scroll(page, scrolls=2)

            # 提取新页商品
            new_items = self._extract_search_items(page)
            added = 0
            for item in new_items:
                url = item.get("url")
                if url and url not in seen:
                    items.append(item)
                    seen.add(url)
                    added += 1

            logger.info("  翻页: 第%d页, 新增%d个, 已收集 %d/%d 个商品",
                        page_num, added, len(items), self.max_items_per_game)

            if added == 0:
                logger.info("  翻页: 第%d页无新商品，停止翻页", page_num)
                break

        return items

    def _extract_search_items(self, page: Page) -> list:
        """从搜索页DOM提取商品列表（JavaScript灵活提取）"""
        items = page.evaluate(
            """
            () => {
                const items = [];

                // 策略1: 查找所有商品链接（goofish用 /item?id= 格式）
                const linkSel = 'a[href*="/item/"], a[href*="item?id="], a[href*="item.htm"]';
                let cards = Array.from(document.querySelectorAll(linkSel));

                // 策略2: 查找商品卡片容器
                if (cards.length === 0) {
                    const selectors = [
                        '[class*="feeds-item"]',
                        '[class*="item-card"]',
                        '[class*="search-item"]',
                        '[class*="product-card"]',
                        '[class*="goods-item"]',
                        '[class*="card-item"]',
                    ];
                    for (const sel of selectors) {
                        cards = Array.from(document.querySelectorAll(sel));
                        if (cards.length > 0) break;
                    }
                }

                // 策略3: 找所有含价格文本的容器
                if (cards.length === 0) {
                    const allDivs = document.querySelectorAll('div, li');
                    allDivs.forEach(div => {
                        if (cards.length > 50) return;
                        const text = div.textContent || '';
                        if (text.includes('¥') && div.querySelector('img')) {
                            cards.push(div);
                        }
                    });
                }

                cards.forEach(card => {
                    try {
                        // 标题
                        const titleEl = card.querySelector(
                            '[class*="title"], [class*="name"], h3, h4, [class*="item-name"]'
                        );
                        let title = titleEl ? titleEl.textContent.trim() : '';
                        if (!title && card.textContent) {
                            // 取卡片内前50个非价格字符作为标题
                            const text = card.textContent.replace(/¥[\\d,.]+/g, '').trim();
                            title = text.substring(0, 80);
                        }

                        // 价格 — 从纯价格容器提取（不含"累计降价""想要"等杂音）
                        let price = null;
                        let priceText = '';
                        // 优先找纯价格元素（class 以 price-wrap 开头，不含 row3）
                        const allPriceWraps = card.querySelectorAll('[class*="price-wrap"]');
                        for (const el of allPriceWraps) {
                            if (el.className && el.className.startsWith('price-wrap')) {
                                priceText = el.textContent.trim();
                                const m = priceText.match(/¥\\s*([\\d,]+(?:\\.\\d+)?)/);
                                if (m) { price = parseFloat(m[1].replace(/,/g, '')); break; }
                            }
                        }
                        // 如果没找到，从卡片全文找第一个 ¥
                        if (price === null && card.textContent) {
                            const m = card.textContent.match(/¥\\s*([\\d,]+(?:\\.\\d+)?)/);
                            if (m) price = parseFloat(m[1].replace(/,/g, ''));
                        }
                        // 合理性校验
                        if (price !== null && (price < 50 || price > 1500)) {
                            price = null;
                        }

                        // 图片
                        const img = card.querySelector('img');
                        let image = '';
                        if (img) {
                            image = img.src || img.getAttribute('data-src') || '';
                            // 处理懒加载src
                            if (!image || image.includes('data:image')) {
                                image = img.getAttribute('data-src')
                                     || img.getAttribute('data-lazy-src')
                                     || '';
                            }
                        }

                        // 链接
                        let link = '';
                        if (card.tagName === 'A') {
                            link = card.href;
                        } else {
                            const a = card.querySelector(
                                'a[href*="/item"], a[href*="item.htm"]'
                            );
                            if (a) link = a.href;
                        }
                        if (!link && card.dataset && card.dataset.href) {
                            link = card.dataset.href;
                        }

                        // 卖家
                        const sellerEl = card.querySelector(
                            '[class*="user"], [class*="seller"], [class*="nick"], [class*="author"]'
                        );
                        const seller = sellerEl ? sellerEl.textContent.trim() : '';

                        // 地区
                        const areaEl = card.querySelector(
                            '[class*="area"], [class*="location"], [class*="city"], [class*="region"]'
                        );
                        const area = areaEl ? areaEl.textContent.trim() : '';

                        // 商品ID
                        let itemId = '';
                        const idMatch = link.match(/item\\/(\\d+)/) || link.match(/id=(\\d+)/);
                        if (idMatch) itemId = idMatch[1];

                        if (title && (price !== null || priceText) && link) {
                            items.push({
                                itemId: itemId,
                                title: title.substring(0, 200),
                                price: price,
                                priceText: priceText || (price ? '¥' + price : ''),
                                image: image,
                                url: link,
                                seller: seller.substring(0, 50),
                                area: area.substring(0, 50),
                            });
                        }
                    } catch (e) {}
                });

                // 去重（按URL）
                const seen = new Set();
                return items.filter(item => {
                    if (!item.url || seen.has(item.url)) return false;
                    seen.add(item.url);
                    return true;
                });
            }
            """
        )
        return items if items else []

    # ------------------------------------------------------------------
    # 详情页
    # ------------------------------------------------------------------

    def get_detail(self, item_url: str) -> dict:
        """获取商品详情页数据（更多图片、描述、成色等）"""
        page = self._context.new_page()
        detail = {}

        try:
            page.goto(item_url, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeout:
                pass

            time.sleep(random.uniform(1, 2.5))

            # 滚动以触发懒加载图片
            self._human_scroll(page, scrolls=4)

            detail = self._extract_detail(page)
            detail["url"] = item_url

        except Exception as e:
            logger.error("获取详情失败 %s: %s", item_url, e)
            self._screenshot(page, "detail_error")
        finally:
            page.close()

        return detail

    def _extract_detail(self, page: Page) -> dict:
        """提取详情页数据"""
        data = page.evaluate(
            """
            () => {
                const result = {
                    title: '', price: null, priceText: '',
                    description: '', images: [],
                    seller: '', area: '', condition: '',
                };

                // 标题
                const titleEl = document.querySelector(
                    'h1, [class*="title"], [class*="item-name"], [class*="item-title"]'
                );
                result.title = titleEl ? titleEl.textContent.trim() : '';

                // 价格 — 从 price-wrap 元素提取
                const priceEl = document.querySelector(
                    '[class*="price-wrap"], [class*="price"], [class*="Price"], [class*="amount"]'
                );
                result.priceText = priceEl ? priceEl.textContent.trim() : '';
                const pm = result.priceText.match(/¥\\s*([\\d,]+(?:\\.\\d+)?)/);
                result.price = pm ? parseFloat(pm[1].replace(/,/g, '')) : null;
                if (result.price !== null && (result.price < 50 || result.price > 1500)) {
                    result.price = null;
                }

                // 描述
                const descEl = document.querySelector('[class*="desc"], [class*="content"], [class*="detail-content"], [class*="item-desc"], [class*="description"]');
                result.description = descEl ? descEl.textContent.trim() : '';

                // 卖家
                const sellerEl = document.querySelector('[class*="seller"], [class*="user-name"], [class*="nick"], [class*="author-name"], [class*="shop-name"]');
                result.seller = sellerEl ? sellerEl.textContent.trim() : '';

                // 地区
                const areaEl = document.querySelector(
                    '[class*="area"], [class*="location"], [class*="region"]'
                );
                result.area = areaEl ? areaEl.textContent.trim() : '';

                // 成色/新旧
                const condEl = document.querySelector(
                    '[class*="condition"], [class*="quality"], [class*="new-old"], [class*="level"]'
                );
                result.condition = condEl ? condEl.textContent.trim() : '';

                // 所有图片
                const imgs = document.querySelectorAll('img[src*="alicdn"], img[src*="cdn"], img[src*="taobao"], img[data-src*="alicdn"], img[data-src*="cdn"]');
                imgs.forEach(img => {
                    let src = img.src || img.getAttribute('data-src') || '';
                    if (!src || src.includes('data:image')) {
                        src = img.getAttribute('data-src') || '';
                    }
                    // 过滤头像、logo等小图
                    if (src && !src.includes('avatar') && !src.includes('logo')
                        && !src.includes('icon') && !src.includes('sprite')) {
                        const w = img.naturalWidth || parseInt(img.getAttribute('width') || '0');
                        if (w === 0 || w > 80) {
                            result.images.push(src);
                        }
                    }
                });

                // 去重
                result.images = [...new Set(result.images)];

                return result;
            }
            """
        )
        return data if data else {}

    # ------------------------------------------------------------------
    # 商品过滤
    # ------------------------------------------------------------------

    # 非实体卡带关键词（标题含这些词的直接排除）
    # 注意：闲鱼搜索页标题可能被截断（如"修改器"显示为"修改..."），
    # 所以使用短关键词（如"修改"而非"修改器"）以匹配截断后的标题
    EXCLUDE_KEYWORDS = [
        # 数字/下载版
        "数字版", "数字下载", "数字", "下载版", "下载",
        # MOD/修改
        "MOD", "mod", "Mod", "修改", "存档",
        # 汉化/补丁
        "汉化", "补丁",
        # 升级/通行证/NS2
        "升级", "通行", "NS2", "switch2", "Switch2",
        # 账号/共享
        "主号", "租号", "共享", "账号",
        # 破解/虚拟
        "破解", "虚拟", "网盘", "百度网盘",
        # 电子版/攻略/设定
        "PDF", "pdf", "电子版", "电子", "设定集", "攻略本", "攻略", "艺术设定", "完全攻略",
        # 兑换码
        "兑换码", "激活码", "序列号",
        # 其他非卡带
        "eshop", "eShop", "ESHOP", "专用", "任选",
        # 周边/配件/非卡带商品
        "明信片", "收纳架", "收纳盒", "保护壳", "包邮送",
        # 广告/推荐块
        "为你推荐",
    ]

    # 实体卡带关键词（标题含这些词的优先保留）
    INCLUDE_KEYWORDS = [
        "卡带", "实体", "卡匣",
        "带盒", "带原盒", "带包装", "有盒", "有原盒",
        "成新", "全新", "二手", "闲置",
        "国行", "港版", "港行", "日版", "美版", "欧版",
        "通关", "回血", "出坑",
    ]

    def _filter_cartridge_items(self, items: list, game_name: str = "") -> list:
        """
        过滤非实体卡带商品
        排除数字版/MOD/修改器/攻略/广告等，只保留可能是实体卡带的商品

        两步过滤：
          1. 排除：标题含 EXCLUDE_KEYWORDS 中任一关键词的
          2. 保留：标题含 INCLUDE_KEYWORDS 中任一关键词的，或无法判断的也保留
             （宁可保留误判，也不误杀真实卡带）
        """
        filtered = []
        excluded_count = 0
        weak_keep_count = 0

        for item in items:
            title = (item.get("title") or "").lower()
            excluded = False

            # 第0步：排除广告/推荐块（标题为"为你推荐"等）
            if title in ("为你推荐", "推荐", "广告", "推广"):
                excluded = True
                logger.debug("  排除广告块: %s", item.get("title", "")[:40])
                continue

            # 第一步：排除
            for kw in self.EXCLUDE_KEYWORDS:
                if kw.lower() in title:
                    excluded = True
                    logger.debug("  排除: %s (含'%s')", item.get("title", "")[:40], kw)
                    break

            if excluded:
                excluded_count += 1
                continue

            # 第二步：检查是否包含实体卡带关键词
            has_include_keyword = any(kw.lower() in title for kw in self.INCLUDE_KEYWORDS)

            if not has_include_keyword:
                weak_keep_count += 1

            filtered.append(item)

        if excluded_count > 0 or weak_keep_count > 0:
            parts = []
            if excluded_count:
                parts.append(f"排除 {excluded_count} 个非卡带")
            if weak_keep_count:
                parts.append(f"保留 {weak_keep_count} 个（无明确卡带关键词）")
            logger.info("  过滤: %s, 共保留 %d 个", ", ".join(parts), len(filtered))

        return filtered

    # ------------------------------------------------------------------
    # 完整爬取流程
    # ------------------------------------------------------------------

    def scrape_game(
        self,
        game_name: str,
        keyword: str,
        version: str = "",
        fetch_detail: bool = True,
    ) -> list:
        """
        完整爬取一个游戏的数据：
          1. 搜索关键词
          2. 提取搜索结果
          3. （可选）进入详情页获取更多图片
          4. 添加元数据
        """
        logger.info("=" * 50)
        logger.info("开始爬取: %s (关键词: %s)", game_name, keyword)

        # 1. 搜索
        items = self.search(keyword, game_name)

        if not items:
            logger.warning("未找到商品: %s", game_name)
            return []

        # 1.5 过滤非实体卡带商品（数字版/MOD/修改器/攻略等）
        items = self._filter_cartridge_items(items, game_name)
        if not items:
            logger.warning("过滤后无实体卡带商品: %s", game_name)
            return []

        # 2. 获取详情
        if fetch_detail:
            detail_count = min(len(items), self.max_detail_pages)
            for i, item in enumerate(items[:detail_count]):
                logger.info(
                    "  获取详情 %d/%d: %s",
                    i + 1,
                    detail_count,
                    item.get("title", "")[:40],
                )

                detail = self.get_detail(item["url"])

                if detail:
                    # 合并详情数据（详情页数据优先）
                    item["detail_images"] = detail.get("images", [])
                    item["description"] = detail.get("description", "")
                    item["condition"] = detail.get("condition", "")
                    if detail.get("seller"):
                        item["seller"] = detail["seller"]
                    if detail.get("area"):
                        item["area"] = detail["area"]
                    if detail.get("price") is not None:
                        item["price"] = detail["price"]
                    # 详情页标题更完整，覆盖搜索页截断的标题
                    if detail.get("title"):
                        item["title"] = detail["title"]

                # 随机延迟，避免请求过快
                time.sleep(random.uniform(2, 4))

            # 获取详情后，用完整标题重新过滤（搜索页标题可能被截断导致漏过滤）
            items = self._filter_cartridge_items(items, game_name)
            if not items:
                logger.warning("详情页过滤后无实体卡带商品: %s", game_name)
                return []

        # 3. 按游戏名过滤（剔除搜索匹配但实际不相关的商品）
        # 从游戏名提取有区分度的关键词（如"旷野之息"、"王国之泪"）
        # 只对获取了详情的商品启用（有完整标题），未获取详情的保留
        game_keywords = self._extract_game_keywords(game_name)
        if game_keywords:
            before = len(items)
            filtered = []
            for it in items:
                has_detail = bool(it.get("description") or it.get("detail_images"))
                if not has_detail:
                    filtered.append(it)  # 未获取详情，保留
                elif (self._matches_game(it.get("title", ""), game_keywords)
                      or self._matches_game(it.get("description", ""), game_keywords)):
                    filtered.append(it)  # 标题或描述匹配，保留
                # 否则剔除
            items = filtered
            dropped = before - len(items)
            if dropped:
                logger.info("  游戏名过滤: 剔除 %d 个不相关商品, 保留 %d 个", dropped, len(items))

        # 4. 添加元数据
        scrape_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in items:
            item["game_name"] = game_name
            item["version"] = version
            item["scrape_date"] = scrape_date
            item.setdefault("detail_images", [])
            item.setdefault("description", "")
            item.setdefault("condition", "")

        logger.info("完成爬取: %s, 共 %d 个商品", game_name, len(items))
        return items

    @staticmethod
    def _extract_game_keywords(game_name: str) -> list:
        """从游戏名提取有区分度的关键词用于标题匹配过滤

        只对含冒号的游戏名启用（如"塞尔达传说：旷野之息" → ["旷野之息"]），
        无冒号时不启用过滤，避免因游戏名与搜索词不一致误杀。
        """
        name = game_name.replace("：", ":").replace("·", " ")
        parts = name.split(":")
        if len(parts) < 2:
            return []
        key_part = parts[-1].strip()
        keywords = [w for w in key_part.split() if len(w) >= 2]
        return keywords if keywords else []

    @staticmethod
    def _matches_game(title: str, game_keywords: list) -> bool:
        """检查标题是否包含游戏关键词"""
        title_lower = title.lower()
        return any(kw.lower() in title_lower for kw in game_keywords)

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def _screenshot(self, page: Page, name: str):
        """保存调试截图"""
        try:
            screenshot_dir = Path("data/screenshots")
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = screenshot_dir / f"{name}_{ts}.png"
            page.screenshot(path=str(path), full_page=True)
            logger.info("截图保存到: %s", path)
        except Exception:
            pass
