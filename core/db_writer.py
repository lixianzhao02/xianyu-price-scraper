# -*- coding: utf-8 -*-
"""
数据库写入模块 — 将爬虫结果写入 MySQL scraper_records 表
"""

import json
import logging
import statistics
import math
from datetime import datetime, date
from collections import Counter

import pymysql
import numpy as np

from .config_loader import get_db_config, get_scraper_config, get_pricing_config

logger = logging.getLogger(__name__)


def get_connection():
    """获取 MySQL 连接"""
    cfg = get_db_config()
    return pymysql.connect(
        host=cfg.get("host", "localhost"),
        port=cfg.get("port", 3306),
        user=cfg.get("user", "root"),
        password=cfg.get("password", ""),
        database=cfg.get("database", "yudao-mall"),
        charset="utf8mb4",
    )

def get_dict_cursor(conn):
    """获取字典游标"""
    return conn.cursor(pymysql.cursors.DictCursor)


def load_spu_games() -> list:
    """
    从 product_spu 表加载上架的游戏商品列表
    返回: [{"spu_id": int, "name": str, "keyword": str, "version": str}, ...]
    """
    conn = get_connection()
    try:
        cursor = get_dict_cursor(conn)
        cursor.execute(
            "SELECT id, name, keyword FROM product_spu WHERE status = 1 AND deleted = 0 ORDER BY id"
        )
        rows = cursor.fetchall()
        games = []
        for row in rows:
            # 优先用 name 作为搜索关键词，更准确
            name = row["name"].strip()
            # 从配置读取搜索模板
            search_template = get_scraper_config().get("search_template", "switch 卡带 {name}")
            search_keyword = search_template.replace("{name}", name)
            games.append({
                "spu_id": row["id"],
                "name": row["name"],
                "search_keyword": search_keyword,
                "version": "卡带",
            })
        logger.info("从 product_spu 加载 %d 个游戏", len(games))
        return games
    finally:
        conn.close()


def _estimate_price(prices: list) -> float:
    """
    二手卡带推荐价格算法

    流程：
        1. IQR 去异常值
        2. 价格分桶（5元）
        3. 找最大价格簇（市场主流价格）
        4. 主价格簇内取中位数
        5. 与整体中位数融合
        6. 回归市场习惯价（5元取整）
    """
    if not prices:
        return 0

    arr = sorted(float(p) for p in prices)
    n = len(arr)

    # 样本太少直接中位数
    if n < 10:
        return round(statistics.median(arr), 2)

    # ---------- IQR 去异常 ----------
    q1 = np.percentile(arr, 25)
    q3 = np.percentile(arr, 75)

    iqr = q3 - q1

    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    cleaned = [
        p for p in arr
        if lower <= p <= upper
    ]

    if len(cleaned) < 5:
        return round(statistics.median(arr), 2)

    # ---------- 价格分桶 ----------
    # 从配置读取分桶大小
    bucket_size = get_pricing_config().get("bucket_size", 10)

    buckets = Counter(
        round(p / bucket_size) * bucket_size
        for p in cleaned
    )

    # 找主价格簇
    main_bucket, count = buckets.most_common(1)[0]

    # ---------- 主价格区 ----------
    hot_zone = [
        p for p in cleaned
        if abs(p - main_bucket) <= bucket_size
    ]

    # 主价格区中位数
    hot_price = (
        statistics.median(hot_zone)
        if hot_zone
        else main_bucket
    )

    # 整体中位数
    median_price = statistics.median(cleaned)

    # ---------- 融合 ----------
    # 卡带市场：主流成交价权重大一些
    final_price = (
        hot_price * 0.7 +
        median_price * 0.3
    )

    # ---------- 稳定性约束 ----------
    # 最终价不能偏离中位数超过 30%，防止小样本抖动
    lower_bound = median_price * 0.7
    upper_bound = median_price * 1.3
    final_price = max(lower_bound, min(final_price, upper_bound))

    # ---------- 1元向上取整 ----------
    final_price = math.ceil(final_price)

    return float(final_price)


def get_last_reference_price(spu_id: int):
    """
    获取最近一次参考价（元）
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT reference_price
            FROM scraper_records
            WHERE spu_id=%s
            ORDER BY scrape_date DESC, id DESC
            LIMIT 1
            """,
            (spu_id,)
        )
        row = cursor.fetchone()
        if row:
            return row[0] / 100.0
        return None
    finally:
        conn.close()


def stabilize_price(current_price, previous_price, max_daily_change=None, alpha=None):
    """
    价格稳定器

    alpha: 今天价格权重（0.3 = 今天占30%，历史占70%）
    max_daily_change: 每天最大波动（元）
    """
    if max_daily_change is None:
        max_daily_change = get_pricing_config().get("max_daily_change", 5)
    if alpha is None:
        alpha = get_pricing_config().get("alpha", 0.3)
    if previous_price is None:
        return current_price

    # 指数平滑
    smooth = previous_price * (1 - alpha) + current_price * alpha

    # 每天最大波动限制
    diff = smooth - previous_price
    if abs(diff) > max_daily_change:
        smooth = (
            previous_price + max_daily_change
            if diff > 0
            else previous_price - max_daily_change
        )

    # 1元向上取整
    smooth = math.ceil(smooth)

    return smooth


def save_scraper_record(spu_id: int, game_name: str, items: list):
    """
    将爬虫结果写入 scraper_records 表
    价格单位转换为分（与 product_spu 一致）
    """
    today = date.today()
    prices = [
        item.get("price") for item in items
        if isinstance(item.get("price"), (int, float)) and item["price"] > 0
    ]

    if not prices:
        logger.warning("无有效价格数据，跳过写入: %s", game_name)
        return

    sample_count = len(prices)
    min_price = min(prices)
    max_price = max(prices)
    avg_price = sum(prices) / sample_count
    median_price = statistics.median(prices)

    # 算法理论价
    raw_reference_price = _estimate_price(prices)

    # 读取上次价格 + 价格稳定器
    last_price = get_last_reference_price(spu_id)
    reference_price = stabilize_price(raw_reference_price, last_price)

    # 转换为分（元→分）
    def to_fen(yuan):
        return int(round(yuan * 100))

    raw_json = json.dumps(items, ensure_ascii=False, default=str)

    conn = get_connection()
    try:
        cursor = conn.cursor()
        # 写入汇总记录
        cursor.execute(
            """INSERT INTO scraper_records
               (spu_id, game_name, scrape_date, sample_count,
                reference_price, min_price, max_price, avg_price, median_price)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                spu_id,
                game_name,
                today,
                sample_count,
                to_fen(reference_price),
                to_fen(min_price),
                to_fen(max_price),
                to_fen(avg_price),
                to_fen(median_price),
            ),
        )
        record_id = cursor.lastrowid

        # 写入原始数据到独立表
        cursor.execute(
            "INSERT INTO scraper_raw_data (record_id, raw_data) VALUES (%s, %s)",
            (record_id, raw_json),
        )
        conn.commit()
        logger.info(
            "写入数据库: %s | 样本%d个 | 新价¥%.0f | 上次¥%s | 最终¥%.0f | 最低¥%.0f | 最高¥%.0f",
            game_name, sample_count, raw_reference_price,
            f"¥{last_price:.0f}" if last_price else "无",
            reference_price, min_price, max_price,
        )
    finally:
        conn.close()
