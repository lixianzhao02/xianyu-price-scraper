# -*- coding: utf-8 -*-
"""
闲鱼NS卡带价格爬虫 - 主程序

使用方法:
  1. 首次登录:     python main.py --login
  2. 执行爬取:     python main.py
  3. 可见浏览器:   python main.py --headful
  4. 不抓详情页:   python main.py --no-detail
  5. 限制商品数:   python main.py --max-items 10
  6. 指定配置:     python main.py --config config/games.yaml

每日定时:
  见 run_daily.bat 和 README.md 中的"定时任务"章节
"""

import sys
import json
import time
import random
import logging
import argparse
from pathlib import Path
from datetime import datetime

import yaml

# 确保能导入core包
sys.path.insert(0, str(Path(__file__).parent))

from core.api_scraper import ApiXianyuScraper
# XianyuScraper is imported lazily inside run() (avoids playwright dependency when using --api)
from core.image_downloader import ImageDownloader
from core.excel_writer import ExcelWriter
from core.db_writer import load_spu_games, save_scraper_record
from core.config_loader import get_scraper_config, get_output_config


# ------------------------------------------------------------------
# 配置
# ------------------------------------------------------------------

PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
COOKIE_PATH = DATA_DIR / "cookies" / "xianyu_state.json"
IMAGE_DIR = DATA_DIR / "images"
OUTPUT_DIR = DATA_DIR / "output"
LOG_PATH = DATA_DIR / "scraper.log"


def setup_logging(verbose: bool = False):
    """配置日志输出"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    logging.basicConfig(
        level=level,
        format=fmt,
        handlers=[
            logging.FileHandler(str(LOG_PATH), encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def load_config(config_path: str) -> dict:
    """加载游戏清单配置"""
    path = Path(config_path)
    if not path.exists():
        logging.error("配置文件不存在: %s", path)
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    games = config.get("games", [])
    if not games:
        logging.warning("配置中没有游戏条目，请在 %s 中添加", path)

    return config


# ------------------------------------------------------------------
# 主流程
# ------------------------------------------------------------------


def run(args):
    """主执行流程"""
    setup_logging(args.verbose)

    scraper_cfg = get_scraper_config()
    output_cfg = get_output_config()

    # 从 product_spu 或 YAML 加载游戏列表
    if args.from_db:
        games = load_spu_games()
        if not games:
            logging.error("product_spu 中没有上架的游戏商品")
            return
        logging.info("从数据库加载 %d 个游戏", len(games))
    else:
        config = load_config(args.config)
        games = config.get("games", [])
        if not games:
            logging.error("没有游戏可爬取，请检查配置文件")
            return

    # 无头模式：--login 或 --headful 时显示浏览器窗口
    headless = not args.headful and not args.login

    logging.info("=" * 60)
    logging.info("闲鱼NS卡带价格爬虫 启动")
    logging.info("模式: %s | 游戏数量: %d | 抓详情: %s | 下载图片: %s",
                 "API" if args.api else "Playwright",
                 len(games), args.max_detail > 0, args.download_images)
    logging.info("=" * 60)

    # 确保目录存在
    COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 输出文件名（使用持续追踪的文件名，便于追加历史）
    excel_name = args.output or "NS卡带价格追踪.xlsx"
    excel_path = OUTPUT_DIR / excel_name
    json_path = OUTPUT_DIR / f"NS卡带价格_{datetime.now().strftime('%Y-%m-%d')}.json"

    all_items = []

    # ── 选择爬虫引擎 ──
    if args.api:
        # HTTP API 模式（无浏览器，适合 Linux 服务器）
        scraper = ApiXianyuScraper(
            cookie_path=str(COOKIE_PATH),
            max_items_per_game=args.max_items,
        )
        try:
            # 登录流程
            need_login = args.login or not COOKIE_PATH.exists()
            if need_login:
                logging.info("需要登录（终端扫码）...")
                if not scraper.login(timeout=120):
                    logging.error("登录失败，请重新运行 --login --api")
                    return
            else:
                if not scraper.check_login_valid():
                    logging.warning("Cookie已失效，需要重新登录")
                    if not scraper.login(timeout=120):
                        logging.error("重新登录失败")
                        return

            # 逐个游戏爬取
            for idx, game in enumerate(games, 1):
                game_name = game["name"]
                search_keyword = game.get("search_keyword", game_name)
                spu_id = game.get("spu_id")

                logging.info("\n[%d/%d] 游戏: %s", idx, len(games), game_name)

                try:
                    items = scraper.scrape_game(
                        game_name=game_name,
                        keyword=search_keyword,
                        version=game.get("version", ""),
                        fetch_detail=False,  # API 模式暂不支持详情页
                    )

                    # 写入数据库（仅 --from-db 模式）
                    if items and spu_id and args.from_db:
                        try:
                            save_scraper_record(spu_id, game_name, items)
                        except Exception as e:
                            logging.warning("写入数据库失败: %s", e)

                    all_items.extend(items)

                except Exception as e:
                    logging.error("爬取 '%s' 出错: %s", game_name, e)
                    continue

                # 游戏间随机延迟
                if idx < len(games):
                    delay = random.uniform(2, 4)
                    logging.info("  等待 %.1f 秒后继续...", delay)
                    time.sleep(delay)
        finally:
            pass  # ApiXianyuScraper 不是上下文管理器
    else:
        # Playwright 浏览器模式（默认）
        from core.scraper import XianyuScraper
        with XianyuScraper(
            cookie_path=str(COOKIE_PATH),
            headless=headless,
            max_items_per_game=args.max_items,
            max_detail_pages=args.max_detail,
            days=args.days,
        ) as scraper:

            # 登录流程
            need_login = args.login or not COOKIE_PATH.exists()
            if need_login:
                logging.info("需要登录，启动浏览器...")
                if not scraper.login(timeout=300):
                    logging.error("登录失败，请重新运行 --login")
                    return
            else:
                # 检查Cookie是否仍然有效
                if not scraper.check_login_valid():
                    logging.warning("Cookie已失效，需要重新登录")
                    if not scraper.login(timeout=300):
                        logging.error("重新登录失败")
                        return

            # 逐个游戏爬取
            for idx, game in enumerate(games, 1):
                game_name = game["name"]
                search_keyword = game.get("search_keyword", game_name)
                spu_id = game.get("spu_id")

                logging.info("\n[%d/%d] 游戏: %s", idx, len(games), game_name)

                try:
                    items = scraper.scrape_game(
                        game_name=game_name,
                        keyword=search_keyword,
                        version=game.get("version", ""),
                        fetch_detail=args.max_detail > 0,
                    )

                    # 下载图片（仅 --download-images 时启用）
                    if items and args.download_images:
                        downloader = ImageDownloader(str(IMAGE_DIR))
                        for item in items:
                            try:
                                downloader.download_item_images(item, game_name)
                            except Exception as e:
                                logging.warning("下载图片失败: %s", e)

                    # 写入数据库（仅 --from-db 模式）
                    if items and spu_id and args.from_db:
                        try:
                            save_scraper_record(spu_id, game_name, items)
                        except Exception as e:
                            logging.warning("写入数据库失败: %s", e)

                    all_items.extend(items)

                except Exception as e:
                    logging.error("爬取 '%s' 出错: %s", game_name, e)
                    continue

                # 游戏间随机延迟
                if idx < len(games):
                    delay = random.uniform(5, 10)
                    logging.info("  等待 %.1f 秒后继续...", delay)
                    time.sleep(delay)

    # 写入Excel（--no-excel 时跳过）
    write_excel = not args.no_excel and output_cfg.get("write_excel", True)
    if all_items:
        if write_excel:
            logging.info("正在写入Excel...")
            writer = ExcelWriter(str(excel_path))
            writer.write(all_items)

        # 保存原始JSON备份
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(all_items, f, ensure_ascii=False, indent=2, default=str)

        logging.info("=" * 60)
        logging.info("爬取完成！")
        logging.info("  商品总数: %d", len(all_items))
        if write_excel:
            logging.info("  Excel文件: %s", excel_path)
        logging.info("  JSON备份: %s", json_path)
        logging.info("=" * 60)
    else:
        logging.warning("未爬取到任何商品数据")

    # 追加每日快照（--no-excel 时跳过）
    if all_items and write_excel:
        daily_excel = OUTPUT_DIR / f"NS卡带价格_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
        try:
            daily_writer = ExcelWriter(str(daily_excel))
            if daily_excel.exists():
                pass
            daily_writer.write(all_items)
            logging.info("每日快照: %s", daily_excel)
        except Exception as e:
            logging.warning("保存每日快照失败: %s", e)


# ------------------------------------------------------------------
# 命令行入口
# ------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="闲鱼NS卡带价格爬虫",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py --login          # 首次扫码登录（Playwright 浏览器）
  python main.py                  # 执行爬取（Playwright 无头模式）
  python main.py --headful        # 可见浏览器运行
  python main.py --no-detail      # 只抓搜索结果，不进详情页
  python main.py --max-items 5    # 每个游戏最多5个商品
  python main.py --games 塞尔达   # 只爬包含"塞尔达"的游戏
  python main.py --api            # 使用 HTTP API 模式（无需浏览器，适合 Linux）
  python main.py --api --login    # API 模式首次登录（终端扫码）
        """,
    )
    parser.add_argument(
        "--api", action="store_true",
        help="使用 HTTP API 模式（无需浏览器，终端扫码登录，适合 Linux 服务器）",
    )
    parser.add_argument(
        "--login", action="store_true",
        help="首次登录（Playwright 模式弹出浏览器，API 模式终端扫码）",
    )
    parser.add_argument(
        "--config", default="config/games.yaml",
        help="游戏配置文件路径 (默认: config/games.yaml)",
    )
    parser.add_argument(
        "--headful", action="store_true",
        help="有头模式（显示浏览器窗口，便于调试）",
    )
    parser.add_argument(
        "--no-detail", action="store_true",
        help="不抓取详情页（速度快，但无详情图片和描述）",
    )
    scraper_cfg = get_scraper_config()
    output_cfg = get_output_config()
    default_max_items = scraper_cfg.get("max_items_per_game", 200)
    default_days = scraper_cfg.get("days", 0)
    default_excel = output_cfg.get("write_excel", True)

    parser.add_argument(
        "--max-items", type=int, default=default_max_items,
        help=f"每个游戏最多抓取的原始商品数量 (默认: {default_max_items})",
    )
    parser.add_argument(
        "--max-detail", type=int, default=0,
        help="每个游戏最多进入多少个详情页 (默认: 0，不抓详情)",
    )
    parser.add_argument(
        "--download-images", action="store_true",
        help="下载商品图片（默认不下载，仅抓价格）",
    )
    parser.add_argument(
        "--output", default=None,
        help="输出Excel文件名 (默认: NS卡带价格追踪.xlsx)",
    )
    parser.add_argument(
        "--no-excel", action="store_true",
        help="不输出Excel文件（定时任务用）",
    )
    parser.add_argument(
        "--games", default=None,
        help="只爬取名称包含指定关键词的游戏（如 --games 塞尔达）",
    )
    parser.add_argument(
        "--days", type=int, default=default_days,
        help=f"只搜最近N天内发布的商品 (默认: {default_days}，不限时间)",
    )
    parser.add_argument(
        "--from-db", action="store_true",
        help="从 product_spu 表加载游戏列表（替代 YAML 配置）",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="详细日志模式",
    )
    return parser.parse_args()


def filter_games(config: dict, keyword: str) -> dict:
    """按关键词过滤游戏"""
    if not keyword:
        return config
    filtered = [
        g for g in config.get("games", [])
        if keyword.lower() in g["name"].lower()
    ]
    config["games"] = filtered
    return config


if __name__ == "__main__":
    args = parse_args()

    if args.games:
        config = load_config(args.config)
        config = filter_games(config, args.games)
        if not config.get("games"):
            print(f"未找到名称包含 '{args.games}' 的游戏")
            sys.exit(1)
        # 临时写过滤后的配置
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump(config, f, allow_unicode=True)
            args.config = f.name

    run(args)
