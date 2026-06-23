#!/usr/bin/env python3
"""boatfrontier /race2 ページ構造を April vs June で比較する。
リッチ行クラス(vi-motor_eval/vi-start_data/vi-course_data 等)が
過去ページに存在するかを確認する。Playwrightでログインして取得。"""
import asyncio, sys, re
from bs4 import BeautifulSoup

EMAIL = "shishido0109@gmail.com"
PWD = "ksg441054"
BF = "https://www.boatfrontier.jp"

RICH_CLASSES = ["vi-motor_eval", "vi-start_data", "vi-course_data",
                "vi-local_course_data", "vi-optional_course_data", "vi-escape_data"]

async def main():
    from playwright.async_api import async_playwright
    targets = [
        ("20260415", 1, 1, "April 桐生 R1"),
        ("20260610", 1, 1, "June 桐生 R1"),
    ]
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://boatfrontier.jp/blog/?memberpage=login", timeout=60000, wait_until="networkidle")
        await page.fill("input[name=log]", EMAIL)
        await page.fill("input[name=pwd]", PWD)
        try:
            async with page.expect_navigation(timeout=25000):
                await page.eval_on_selector("input[name=pwd]", "el=>el.closest('form').submit()")
        except Exception:
            pass
        await asyncio.sleep(1)
        content = await page.content()
        logged = ("ログアウト" in content) or ("マイページ" in content)
        print("LOGIN OK =", logged)
        cookies = await context.cookies()
        extra = []
        for ck in cookies:
            if ck.get("domain") == "boatfrontier.jp":
                nc = dict(ck); nc["domain"] = ".boatfrontier.jp"; extra.append(nc)
        if extra:
            await context.add_cookies(extra)

        for date_str, jcd, rno, label in targets:
            url = f"{BF}/race2/{date_str}/{jcd}/{rno}"
            print("\n" + "="*60)
            print(label, url)
            try:
                resp = await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                await asyncio.sleep(1.5)
                html = await page.content()
                print("  http status =", resp.status if resp else "?", "len=", len(html))
                print("  final url =", page.url)
                soup = BeautifulSoup(html, "html.parser")
                tbl = soup.find("table")
                print("  <table> found =", tbl is not None)
                # count rich class rows
                for cls in RICH_CLASSES:
                    rows = soup.find_all("tr", class_=lambda c: c and cls in c)
                    print(f"    tr.{cls:26s} rows={len(rows)}")
                # show th labels present
                ths = [t.get_text(strip=True) for t in soup.find_all("th")]
                kws = [t for t in ths if any(k in t for k in ["モーター","平均ST","今節","コース別","出走数","決まり手"])]
                print("  rich-th labels:", kws[:20])
                # detect login/paywall messaging
                low = html.lower()
                for kw in ["ログイン","会員","プレミアム","有効期限","データがありません","開催されていません","not found","404"]:
                    if kw.lower() in low:
                        print(f"  PAGE-MARKER contains: {kw}")
            except Exception as e:
                print("  ERROR:", e)
        await browser.close()

asyncio.run(main())
