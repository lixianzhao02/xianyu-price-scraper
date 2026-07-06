# -*- coding: utf-8 -*-
"""
闲鱼NS卡带价格爬虫 - HTTP API 爬虫模块（替代 Playwright）

基于 XianYuApis 库，通过 HTTP API 直接调用闲鱼接口，
无需浏览器，可在无头 Linux 服务器上运行。

使用:
  scraper = ApiXianyuScraper(cookie_path)
  scraper.login()              # 首次扫码登录（终端显示二维码）
  items = scraper.scrape_game("塞尔达", "switch 卡带 塞尔达")
"""

import json
import time
import random
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

from .xianyu import XianyuApis, qrcode_login, build_initial_cookies

logger = logging.getLogger(__name__)


class ApiXianyuScraper:
    """
    基于 HTTP API 的闲鱼爬虫，无需浏览器。

    使用 XianYuApis 库直接调用闲鱼 mtop API，
    支持 Cookie 持久化、关键词搜索、商品过滤。
    """

    # 非实体卡带关键词（与 scraper.py 保持一致）
    EXCLUDE_KEYWORDS = [
        "数字版", "数字下载", "数字", "下载版", "下载",
        "MOD", "mod", "Mod", "修改", "存档",
        "汉化", "补丁",
        "升级", "通行", "NS2", "switch2", "Switch2",
        "主号", "租号", "共享", "账号",
        "破解", "虚拟", "网盘", "百度网盘",
        "PDF", "pdf", "电子版", "电子", "设定集", "攻略本", "攻略",
        "艺术设定", "完全攻略",
        "兑换码", "激活码", "序列号",
        "eshop", "eShop", "ESHOP", "专用", "任选",
        "明信片", "收纳架", "收纳盒", "保护壳", "包邮送",
        "为你推荐",
    ]

    # 实体卡带关键词
    INCLUDE_KEYWORDS = [
        "卡带", "实体", "卡匣",
        "带盒", "带原盒", "带包装", "有盒", "有原盒",
        "成新", "全新", "二手", "闲置",
        "国行", "港版", "港行", "日版", "美版", "欧版",
        "通关", "回血", "出坑",
    ]

    def __init__(
        self,
        cookie_path: str,
        max_items_per_game: int = 200,
    ):
        self.cookie_path = Path(cookie_path)
        self.max_items_per_game = max_items_per_game
        self.api: Optional[XianyuApis] = None

    # ------------------------------------------------------------------
    # Cookie 持久化
    # ------------------------------------------------------------------

    def _save_cookies(self):
        """保存 Cookie 到 JSON 文件"""
        if not self.api:
            return
        self.cookie_path.parent.mkdir(parents=True, exist_ok=True)
        cookies_dict = {}
        for c in self.api.session.cookies:
            if c.domain and ('.goofish.com' in c.domain or '.mmstat.com' in c.domain):
                cookies_dict[c.name] = c.value
        data = {
            "cookies": cookies_dict,
            "device_id": self.api.device_id,
        }
        with open(self.cookie_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Cookie 已保存到: %s", self.cookie_path)

    def _refresh_token_and_save(self):
        """刷新 token 并保存 Cookie（每次爬取开始时调用一次，自动续期）"""
        if not self.api:
            return
        try:
            # 使用 refresh_token 续期（原版 XianYuApis 每 600s 调一次）
            self.api.refresh_token()
            self._save_cookies()
        except Exception as e:
            logger.debug("Token 刷新失败（不影响搜索）: %s", e)

    def _load_cookies(self) -> Optional[dict]:
        """从 JSON 文件加载 Cookie"""
        if not self.cookie_path.exists():
            return None
        try:
            with open(self.cookie_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.warning("加载 Cookie 失败: %s", e)
            return None

    def _extract_cookies_from_data(self, data: dict) -> tuple:
        """
        从加载的 Cookie 数据中提取 cookies dict 和 device_id。
        所有 cookie 统一用 .goofish.com domain，避免多 domain 冲突。
        """
        cookies = {}
        device_id = ""

        all_cookies = []

        if 'cookies' in data and isinstance(data['cookies'], list):
            all_cookies = data['cookies']
        elif 'cookies' in data and isinstance(data['cookies'], dict):
            for k, v in data['cookies'].items():
                all_cookies.append({'name': k, 'value': v, 'domain': '.goofish.com'})
        elif 'origins' in data:
            for origin in data.get('origins', []):
                for c in origin.get('cookies', []):
                    all_cookies.append(c)

        # 用临时 session 按 domain 优先级合并同名 cookie
        import requests as _requests
        temp_session = _requests.Session()
        for c in all_cookies:
            name = c.get('name', '')
            value = c.get('value', '')
            domain = c.get('domain', '')
            path = c.get('path', '/')
            if name and value:
                temp_session.cookies.set(name, value, domain=domain, path=path)

        # 提取为 dict，统一用 .goofish.com domain
        for c in temp_session.cookies:
            if c.domain and ('.goofish.com' in c.domain or '.mmstat.com' in c.domain):
                cookies[c.name] = c.value

        from .xianyu.utils.goofish_utils import generate_device_id
        device_id = data.get('device_id', '')
        if not device_id:
            device_id = generate_device_id(cookies.get('unb', ''))

        return cookies, device_id

    # ------------------------------------------------------------------
    # 登录
    # ------------------------------------------------------------------

    def login(self, timeout: int = 120) -> bool:
        """
        登录闲鱼。

        首次登录：在终端显示二维码，用户用闲鱼 APP 扫码。
        已有 Cookie：自动复用，检查是否有效。
        """
        # 尝试加载已保存的 Cookie
        saved = self._load_cookies()
        if saved:
            cookies, device_id = self._extract_cookies_from_data(saved)
            if cookies and device_id:
                self.api = XianyuApis(cookies, device_id)
                # 检查 Cookie 是否有效
                if self._check_login_valid():
                    logger.info("Cookie 有效，无需重新登录")
                    return True
                else:
                    logger.info("Cookie 已失效，需要重新登录")

        # 首次登录：终端扫码
        logger.info("=" * 60)
        logger.info("  请在终端中扫描二维码登录闲鱼")
        logger.info("  打开闲鱼 APP → 左上角扫一扫")
        logger.info("=" * 60)

        try:
            self.api = qrcode_login(
                poll_interval=3.0,
                timeout=float(timeout),
                show_qrcode=True,
            )
            self._save_cookies()
            logger.info("登录成功！")
            return True
        except Exception as e:
            logger.error("登录失败: %s", e)
            return False

    def _check_login_valid(self) -> bool:
        """检查当前 Cookie 是否有效（通过 refresh_token 验证）"""
        if not self.api:
            return False
        try:
            res = self.api.refresh_token()
            if isinstance(res, dict):
                ret = res.get("ret", [])
                if ret and "SUCCESS" in str(ret[0]):
                    return True
            return False
        except Exception as e:
            logger.debug("登录检查失败: %s", e)
            return False

    def check_login_valid(self) -> bool:
        """公开接口：检查登录是否有效（自动加载已保存的 Cookie）"""
        if self.api is None:
            saved = self._load_cookies()
            if saved:
                cookies, device_id = self._extract_cookies_from_data(saved)
                if cookies and device_id:
                    self.api = XianyuApis(cookies, device_id)
        return self._check_login_valid()

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------

    def search(self, keyword: str, game_name: str = "") -> list:
        """
        通过 HTTP API 搜索闲鱼商品，支持翻页采集。

        返回商品列表，每项包含:
          itemId, title, price, priceText, image, url, seller, area
        """
        if not self.api:
            logger.error("API 未初始化，请先调用 login()")
            return []

        all_items = []
        seen_urls = set()
        page = 1
        max_pages = 20
        page_size = 30  # API 最大每页 30 条

        logger.info("API搜索: %s", keyword)

        # 刷新 token 并保存 Cookie（自动续期）
        self._refresh_token_and_save()

        while page <= max_pages and len(all_items) < self.max_items_per_game:
            # 翻页间隔（防限流）
            if page > 1:
                delay = random.uniform(1.5, 3.0)
                time.sleep(delay)

            # 请求重试（最多 3 次，应对限流）
            res = None
            for retry in range(3):
                try:
                    res = self.api.search(keyword, page=page, page_size=page_size)
                    # 检查是否被限流
                    ret = res.get("ret", [])
                    if ret and "RGV587_ERROR" in str(ret[0]):
                        wait = (retry + 1) * 5
                        logger.warning("  第 %d 页被限流，等待 %d 秒后重试 (%d/3)...", page, wait, retry + 1)
                        time.sleep(wait)
                        continue
                    break
                except Exception as e:
                    logger.error("搜索第 %d 页失败: %s", page, e)
                    time.sleep(3)
                    continue
            if res is None:
                logger.error("  第 %d 页重试 3 次均失败，停止翻页", page)
                break

            # 解析响应
            items = self._parse_search_response(res)
            if not items:
                logger.info("  第 %d 页无商品，停止翻页", page)
                break

            # 去重
            added = 0
            for item in items:
                url = item.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_items.append(item)
                    added += 1

            logger.info("  第 %d 页: 新增 %d 个, 已收集 %d/%d",
                        page, added, len(all_items), self.max_items_per_game)

            if added == 0:
                break

            page += 1
            # 翻页间隔
            time.sleep(random.uniform(1.0, 2.0))

        # 截断到 max_items
        all_items = all_items[:self.max_items_per_game]

        if not all_items:
            logger.warning("API搜索 '%s' 未找到商品", keyword)
        else:
            logger.info("API搜索 '%s' 共获取 %d 个商品", keyword, len(all_items))

        return all_items

    def _parse_search_response(self, res: dict) -> list:
        """
        解析搜索 API 响应，提取商品列表。

        闲鱼 mtop 搜索 API 返回格式（实际结构）:
        {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "resultList": [
                    {
                        "data": {
                            "item": {
                                "main": {
                                    "clickParam": {
                                        "args": {
                                            "item_id": "...",
                                            "price": "220",
                                            "displayPrice": "220",
                                            ...
                                        }
                                    },
                                    "exContent": {
                                        "area": "广东",
                                        "detailParams": {
                                            "itemId": "...",
                                            "title": "商品标题...",
                                            "userNick": "卖家昵称",
                                            "soldPrice": "220",
                                            ...
                                        },
                                        "picUrl": "http://img.alicdn.com/...",
                                        ...
                                    }
                                }
                            }
                        }
                    }
                ]
            }
        }
        """
        items = []

        try:
            ret = res.get("ret", [])
            if ret and "SUCCESS" not in str(ret[0]):
                logger.warning("API 返回异常: %s", ret)
                return []

            data = res.get("data", {})
            if not data:
                return []

            # 实际返回的是 resultList
            item_list = data.get("resultList") or []

            if not isinstance(item_list, list):
                return []

            for raw in item_list:
                if not isinstance(raw, dict):
                    continue

                # 实际结构: raw.data.item.main
                try:
                    main = raw["data"]["item"]["main"]
                except (KeyError, TypeError):
                    continue

                click_args = main.get("clickParam", {}).get("args", {})
                ex_content = main.get("exContent", {})

                # 商品 ID
                item_id = (
                    click_args.get("item_id")
                    or click_args.get("id")
                    or ex_content.get("detailParams", {}).get("itemId")
                    or ""
                )

                # 标题
                detail_params = ex_content.get("detailParams", {})
                title = detail_params.get("title", "")

                # 价格
                price = None
                price_raw = click_args.get("displayPrice") or click_args.get("price")
                if price_raw:
                    try:
                        price = float(price_raw)
                    except (ValueError, TypeError):
                        pass

                # 合理性校验
                if price is not None and (price < 50 or price > 1500):
                    price = None

                price_text = f"¥{price:.0f}" if price else ""

                # 图片
                image = ex_content.get("picUrl", "")

                # 链接
                item_url = f"https://www.goofish.com/item/{item_id}" if item_id else ""

                # 卖家
                seller = detail_params.get("userNick", "")

                # 地区
                area = ex_content.get("area", "")

                if title and (price is not None or price_text):
                    items.append({
                        "itemId": str(item_id),
                        "title": title.strip()[:200],
                        "price": price,
                        "priceText": price_text,
                        "image": image,
                        "url": item_url,
                        "seller": seller.strip()[:50],
                        "area": area.strip()[:50],
                    })

        except Exception as e:
            logger.error("解析搜索响应失败: %s", e)

        return items

    # ------------------------------------------------------------------
    # 商品过滤
    # ------------------------------------------------------------------

    def _filter_cartridge_items(self, items: list, game_name: str = "") -> list:
        """
        过滤非实体卡带商品（与 scraper.py 逻辑一致）
        """
        filtered = []
        excluded_count = 0
        weak_keep_count = 0

        for item in items:
            title = (item.get("title") or "").lower()

            # 排除广告
            if title in ("为你推荐", "推荐", "广告", "推广"):
                excluded_count += 1
                continue

            # 排除
            excluded = False
            for kw in self.EXCLUDE_KEYWORDS:
                if kw.lower() in title:
                    excluded = True
                    logger.debug("  排除: %s (含'%s')", item.get("title", "")[:40], kw)
                    break
            if excluded:
                excluded_count += 1
                continue

            # 检查是否包含实体卡带关键词
            has_include = any(kw.lower() in title for kw in self.INCLUDE_KEYWORDS)
            if not has_include:
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
        完整爬取一个游戏的数据（API 版本）

        参数:
          game_name: 游戏名称（用于日志和元数据）
          keyword: 搜索关键词
          version: 版本标识（如"卡带"）
          fetch_detail: 是否获取详情（API 模式下暂不支持详情页）

        返回商品列表，每项包含:
          itemId, title, price, priceText, image, url, seller, area,
          game_name, version, scrape_date
        """
        logger.info("=" * 50)
        logger.info("开始爬取: %s (关键词: %s)", game_name, keyword)

        # 1. 搜索
        items = self.search(keyword, game_name)
        if not items:
            logger.warning("未找到商品: %s", game_name)
            return []

        # 2. 过滤非实体卡带
        items = self._filter_cartridge_items(items, game_name)
        if not items:
            logger.warning("过滤后无实体卡带商品: %s", game_name)
            return []

        # 3. 添加元数据
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
