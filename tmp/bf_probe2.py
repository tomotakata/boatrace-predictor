#!/usr/bin/env python3
"""URLバリアントとごく最近の日付で /race2 が生きているか確認する。"""
import asyncio
from bs4 import BeautifulSoup

EMAIL = "shishido0109@gmail.com"
PWD = "ksg441054"

async def main():
    from playwright.async_api import async_playwright
    # test several recent dates + url hosts
    candidates = [
        "https://www.boatfrontier.jp/race2/20260620/1/1",
        "https://boatfrontier.jp/race2/20260620/1/1",
        "https://www.boatfrontier.jp/race2/20260622/24/1",   # today, 大村
        "https://www.boatfrontier.jp/race2/20260621/24/1",
        "https://www.boatfrontier.jp/race2/20260615/15/1",   # mid June 丸亀
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
        cookies = await context.cookies()
        extra = []
        for ck in cookies:
            if ck.get("domain") == "boatfrontier.jp":
                nc = dict(ck); nc["domain"] = ".boatfrontier.jp"; extra.append(nc)
        if extra:
            await context.add_cookies(extra)
        for url in candidates:
            try:
                resp = await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                await asyncio.sleep(1)
                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")
                tbl = soup.find("table")
                rich = len(soup.find_all("tr", class_=lambda c: c and "vi-motor_eval" in c))
                print(f"{resp.status if resp else '?'} table={tbl is not None} vi-motor_eval={rich}  {url} -> {page.url}")
            except Exception as e:
                print("ERR", url, e)
        await browser.close()

asyncio.run(main())
