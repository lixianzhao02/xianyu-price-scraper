# -*- coding: utf-8 -*-
"""测试登录检测修复：无Cookie打开闲鱼，验证_check_logged_in返回False"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from core.scraper import XianyuScraper

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

print("=== 测试：无Cookie状态下登录检测 ===\n")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(
        user_agent=UA,
        viewport={"width": 1920, "height": 1080},
        locale="zh-CN",
    )
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

    # 创建scraper实例但不启动浏览器（手动管理）
    scraper = XianyuScraper.__new__(XianyuScraper)
    scraper._context = ctx

    page = ctx.new_page()
    page.goto("https://www.goofish.com", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # 测试新的_check_logged_in
    result = scraper._check_logged_in(page)

    # 也看看页面上的文本证据
    body_text = page.evaluate("() => (document.body.innerText || '').substring(0, 200)")
    has_login_text = "立即登录" in body_text or "请登录" in body_text

    print(f"页面文本包含登录提示: {has_login_text}")
    print(f"_check_logged_in 返回: {result}")
    print(f"期望: False (未登录)")
    print(f"结果: {'✓ 通过' if result == False else '✗ 失败'}")

    print(f"\n页面文本前200字: {body_text[:200]}")

    page.close()
    ctx.close()
    browser.close()

print("\n测试完成")
