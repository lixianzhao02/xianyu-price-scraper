# -*- coding: utf-8 -*-
"""
图片下载模块

功能：
  1. 下载搜索结果中的商品主图（宣传图）
  2. 下载详情页中的所有图片（卡带信息图等）
  3. 自动去重、跳过已下载文件
  4. 处理防盗链（设置Referer）
"""

import re
import logging
from pathlib import Path
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


class ImageDownloader:
    """图片下载器"""

    def __init__(self, base_dir: str = "data/images"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # 使用Session设置headers，处理防盗链
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.goofish.com/",
                "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
            }
        )

    def download_item_images(self, item: dict, game_name: str) -> dict:
        """
        下载一个商品的所有图片

        参数:
            item: 商品数据dict
            game_name: 游戏名（用于创建子目录）
        返回:
            {"promo_images": [路径...], "detail_images": [路径...]}
        """
        game_dir = self._safe_name(game_name)
        item_id = item.get("itemId") or self._url_to_id(item.get("url", ""))
        item_dir = self.base_dir / game_dir / item_id
        item_dir.mkdir(parents=True, exist_ok=True)

        result = {"promo_images": [], "detail_images": []}

        # 下载搜索结果主图（宣传图）
        if item.get("image"):
            path = self._download(item["image"], item_dir, "promo_1")
            if path:
                result["promo_images"].append(path)

        # 下载详情页图片
        for i, img_url in enumerate(item.get("detail_images", [])):
            path = self._download(img_url, item_dir, f"detail_{i + 1}")
            if path:
                result["detail_images"].append(path)

        # 如果没有独立的主图，用第一张详情图作为宣传图
        if not result["promo_images"] and result["detail_images"]:
            result["promo_images"].append(result["detail_images"][0])

        item["downloaded_images"] = result
        return result

    def _download(self, url: str, save_dir: Path, name: str) -> str:
        """下载单张图片，返回本地路径"""
        if not url or not url.startswith("http"):
            return None

        try:
            # 确定文件扩展名
            ext = self._get_extension(url)

            filepath = save_dir / f"{name}{ext}"

            # 如果已存在则跳过
            if filepath.exists() and filepath.stat().st_size > 0:
                return str(filepath).replace("\\", "/")

            resp = self.session.get(url, timeout=15, stream=True)
            resp.raise_for_status()

            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            return str(filepath).replace("\\", "/")

        except requests.exceptions.RequestException as e:
            logger.debug("下载图片失败 %s: %s", url[:80], e)
            return None
        except Exception as e:
            logger.debug("下载图片出错 %s: %s", url[:80], e)
            return None

    @staticmethod
    def _get_extension(url: str) -> str:
        """从URL推断图片扩展名"""
        path = urlparse(url).path.lower()
        if path.endswith(".png"):
            return ".png"
        elif path.endswith(".webp"):
            return ".webp"
        elif path.endswith(".gif"):
            return ".gif"
        elif path.endswith(".bmp"):
            return ".bmp"
        else:
            return ".jpg"

    @staticmethod
    def _safe_name(name: str) -> str:
        """将游戏名转为安全的目录名"""
        # 保留中文、字母、数字、下划线
        safe = re.sub(r"[^\w\u4e00-\u9fff]", "_", name)
        safe = re.sub(r"_+", "_", safe).strip("_")
        return safe if safe else "unknown"

    @staticmethod
    def _url_to_id(url: str) -> str:
        """从URL提取商品ID作为目录名"""
        m = re.search(r"item/(\d+)", url)
        if m:
            return m.group(1)
        m = re.search(r"id=(\d+)", url)
        if m:
            return m.group(1)
        # 用URL的hash作为后备
        return str(abs(hash(url)) % 100000000)
