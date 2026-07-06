# -*- coding: utf-8 -*-
"""诊断脚本：截图并dump闲鱼搜索页DOM结构"""
import sys
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

COOKIE = str(Path(__file__).parent / "data" / "cookies" / "xianyu_state.json")
SHOT_DIR = Path(__file__).parent / "data" / "screenshots"
SHOT_DIR.mkdir(parents=True, exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(
        storage_state=COOKIE,
        user_agent=UA,
        viewport={"width": 1920, "height": 1080},
        locale="zh-CN",
    )
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    page = ctx.new_page()

    # 1. 先看首页，检查登录状态
    print("=== 1. 访问首页 ===")
    page.goto("https://www.goofish.com", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    page.screenshot(path=str(SHOT_DIR / "home.png"), full_page=False)
    print(f"首页URL: {page.url}")
    print(f"首页截图: {SHOT_DIR / 'home.png'}")

    # 检查登录状态
    login_check = page.evaluate("""
        () => {
            const bodyText = document.body.innerText || '';
            const hasLoginBtn = bodyText.includes('请登录') || bodyText.includes('登录');
            const hasUserInfo = bodyText.includes('我的') || bodyText.includes('退出');
            // 找所有可能的登录/用户元素
            const loginEls = document.querySelectorAll('[class*="login"], [class*="sign-in"]');
            const userEls = document.querySelectorAll('[class*="user"], [class*="nick"], [class*="avatar"]');
            return {
                url: location.href,
                hasLoginText: hasLoginBtn,
                hasUserText: hasUserInfo,
                loginElCount: loginEls.length,
                userElCount: userEls.length,
                bodyTextSample: bodyText.substring(0, 500),
            };
        }
    """)
    print(f"登录状态: {json.dumps(login_check, ensure_ascii=False, indent=2)}")

    # 2. 搜索页
    print("\n=== 2. 搜索页 ===")
    search_url = "https://www.goofish.com/search?q=%E5%A1%9E%E5%B0%94%E8%BE%BE%20%E7%8E%8B%E5%9B%BD%E4%B9%8B%E6%B3%AA%20NS%E5%8D%A1%E5%B8%A6"
    print(f"搜索URL: {search_url}")
    page.goto(search_url, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)

    # 滚动
    for _ in range(3):
        page.evaluate("window.scrollBy(0, 500)")
        page.wait_for_timeout(1000)

    page.screenshot(path=str(SHOT_DIR / "search.png"), full_page=False)
    print(f"搜索页截图: {SHOT_DIR / 'search.png'}")
    print(f"搜索页URL: {page.url}")

    # Dump DOM结构
    dom_info = page.evaluate("""
        () => {
            const info = {itemCount: 0, samples: [], bodyTextSample: ''};

            // 看页面文本
            info.bodyTextSample = (document.body.innerText || '').substring(0, 1000);

            // 找所有带 /item/ 的链接
            const itemLinks = document.querySelectorAll('a[href*="/item/"], a[href*="item.htm"], a[href*="item?id="]');
            info.itemLinkCount = itemLinks.length;

            // 取前5个链接的详细信息
            for (let i = 0; i < Math.min(5, itemLinks.length); i++) {
                const a = itemLinks[i];
                const parent = a.closest('div[class]') || a.parentElement;
                info.samples.push({
                    href: a.href,
                    text: (a.textContent || '').trim().substring(0, 100),
                    parentClass: parent ? parent.className : '',
                    parentTag: parent ? parent.tagName : '',
                    innerHTML: parent ? parent.innerHTML.substring(0, 500) : '',
                });
            }

            // 也看看有哪些大的容器
            const containers = document.querySelectorAll('div[class*="item"], div[class*="card"], div[class*="product"], div[class*="feeds"], div[class*="search"], div[class*="result"]');
            info.containerCount = containers.length;
            info.containerClasses = [...new Set(Array.from(containers).map(c => c.className).filter(c => c))].slice(0, 20);

            return info;
        }
    """)
    print(f"\nDOM信息: {json.dumps(dom_info, ensure_ascii=False, indent=2)}")

    page.close()
    ctx.close()
    browser.close()

print("\n诊断完成")
