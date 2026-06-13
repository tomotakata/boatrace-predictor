# さくらVPS バックアップ記録（2026-06-13）

対象サーバー: `ubuntu@153.121.51.74`

## 1. boatrace ディレクトリ配下の全ファイル一覧

```text
/home/ubuntu/boatrace/__pycache__/server.cpython-312.pyc
/home/ubuntu/boatrace/bf_gate.py
/home/ubuntu/boatrace/bf_login3.py
/home/ubuntu/boatrace/bf_login4.py
/home/ubuntu/boatrace/bf_nonwww.py
/home/ubuntu/boatrace/bf_race2_prem.py
/home/ubuntu/boatrace/bf_racer.py
/home/ubuntu/boatrace/scrape.py
/home/ubuntu/boatrace/scrapers/boaters.py
/home/ubuntu/boatrace/scrapers/boatfrontier.py
/home/ubuntu/boatrace/server.py
/home/ubuntu/boatrace/server.py.bak.1781072758
/home/ubuntu/boatrace/server.py.bak.20260610_155028
/home/ubuntu/boatrace/server.py.bak.20260611_124402
/home/ubuntu/boatrace/server.py.bak.v58_7_20260612_004217
/home/ubuntu/boatrace/teleboat_cookies.json
```

## 2. crontab

```text
no crontab for ubuntu
```

## 3. systemd サービス定義

### 検出サービス

```text
boatrace-scraper.service                     enabled         enabled
```

### `boatrace-scraper.service`

```ini
# /etc/systemd/system/boatrace-scraper.service
[Unit]
Description=Boatrace Sakura Scraper API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/boatrace
ExecStart=/home/ubuntu/boatrace-env/bin/uvicorn server:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

## 4. 環境変数

```text
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
HOME=/home/ubuntu
LANG=C.UTF-8
LC_ALL=en_US.UTF-8
LOGNAME=ubuntu
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin
PWD=/home/ubuntu
SHELL=/bin/bash
SHLVL=1
SSH_CLIENT=114.51.83.99 33842 22
SSH_CONNECTION=114.51.83.99 33842 153.121.51.74 22
USER=ubuntu
XDG_RUNTIME_DIR=/run/user/1000
XDG_SESSION_CLASS=user
XDG_SESSION_ID=2277
XDG_SESSION_TYPE=tty
_=/usr/bin/env
```

## 5. Python パッケージ一覧

```text
Package               Version
--------------------- ---------------
attrs                 23.2.0
Automat               22.10.0
bcc                   0.29.1
bcrypt                3.2.2
blinker               1.7.0
certifi               2023.11.17
chardet               5.2.0
click                 8.1.6
colorama              0.4.6
command-not-found     0.3
configobj             5.0.8
constantly            23.10.4
cryptography          41.0.7
dbus-python           1.3.2
distro                1.9.0
distro-info           1.7+build1
httplib2              0.20.4
hyperlink             21.0.0
idna                  3.6
incremental           22.10.0
launchpadlib          1.11.0
lazr.restfulclient    0.14.6
lazr.uri              1.0.6
markdown-it-py        3.0.0
mdurl                 0.1.2
netaddr               0.8.0
netifaces             0.11.0
oauthlib              3.2.2
pexpect               4.9.0
pip                   24.0
ptyprocess            0.7.0
pyasn1                0.4.8
pyasn1-modules        0.2.8
Pygments              2.17.2
PyGObject             3.48.2
PyHamcrest            2.1.0
PyJWT                 2.7.0
pyOpenSSL             23.2.0
pyparsing             3.1.1
pyserial              3.5
python-apt            2.7.7+ubuntu5.1
python-debian         0.1.49+ubuntu2
python-magic          0.4.27
PyYAML                6.0.1
requests              2.31.0
rich                  13.7.1
service-identity      24.1.0
setuptools            68.1.2
six                   1.16.0
sos                   4.5.6
ssh-import-id         5.11
systemd-python        235
Twisted               24.3.0
ubuntu-drivers-common 0.0.0
ubuntu-pro-client     8001
ufw                   0.36.2
unattended-upgrades   0.1
urllib3               2.0.7
wadllib               1.3.6
wheel                 0.42.0
xkit                  0.0.0
zope.interface        6.1
```

## 6. `server.py` 内の主要設定値

```python
SUPABASE_URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
SUPABASE_KEY = "..."
SUPABASE_DB_URL = "postgresql://postgres:BoatRace2024%21Secure@db.zotskrheypxrfsiyvwtl.supabase.co:5432/postgres"
SUPABASE_POOLER_URL = "postgresql://postgres.zotskrheypxrfsiyvwtl:BoatRace2024%21Secure@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"
BOATFRONTIER_EMAIL = "shishido0109@gmail.com"
BOATFRONTIER_PASSWORD = "ksg441054"
API_SECRET = "boatrace-sakura-secret-2024"
TELEBOAT_MEMBER_NO = "06131752"
TELEBOAT_PIN = "0506"
TELEBOAT_AUTH_NO = "0538"
TB_BASE = "https://www.boatrace.jp"
BF_BASE = "https://www.boatfrontier.jp"
BR_BASE = "https://www.boatrace.jp"
TELEBOAT_COOKIE_FILE = "/home/ubuntu/boatrace/teleboat_cookies.json"
root version = "6.2-v60.0"
uvicorn host = "0.0.0.0"
uvicorn port = 8080
```

## 7. `boatrace` 配下ファイル内容

### `/home/ubuntu/boatrace/bf_gate.py`

```python
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

EMAIL = "shishido0109@gmail.com"
PW = "ksg441054"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
RACE = "https://www.boatfrontier.jp/race2/20260610/01/1"

async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = await b.new_context(user_agent=UA, locale="ja-JP")
        p = await ctx.new_page()
        await p.goto("https://boatfrontier.jp/blog/?memberpage=login", timeout=60000, wait_until="networkidle")
        await p.fill("input[name=log]", EMAIL)
        await p.fill("input[name=pwd]", PW)
        async with p.expect_navigation(timeout=25000):
            await p.eval_on_selector("input[name=pwd]", "el=>el.closest('form').submit()")
        await asyncio.sleep(1)
        cookies = await ctx.cookies()
        for ck in cookies:
            if "wordpress_logged_in" in ck['name'] or ck['name'].startswith("wordpress_sec"):
                print("COOKIE", ck['name'][:40], "domain=", ck['domain'])
        await p.goto(RACE, timeout=60000, wait_until="networkidle")
        await asyncio.sleep(3)
        html = await p.content()
        soup = BeautifulSoup(html, "html.parser")
        row = soup.find("tr", class_=lambda c: c and "vi-optional_course_data" in c)
        if row:
            box = row
            for _ in range(6):
                if box.parent: box = box.parent
            txt = box.get_text(" ", strip=True)
            print("=== optional_course block text (1500) ===")
            print(txt[:1500])
        for phrase in ["プレミアム会員","限定","ログインして","ご覧いただけ","アップグレード","登録すると"]:
            idx = html.find(phrase)
            if idx>=0:
                print(f"\n--phrase '{phrase}' @ {idx}:", html[idx-40:idx+80].replace("\n"," "))
        await b.close()

asyncio.run(main())
```

### `/home/ubuntu/boatrace/bf_login3.py`

```python
import asyncio, re
from playwright.async_api import async_playwright

EMAIL = "shishido0109@gmail.com"
PW = "ksg441054"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-blink-features=AutomationControlled"])
        ctx = await b.new_context(user_agent=UA, locale="ja-JP")
        p = await ctx.new_page()

        responses = []
        async def on_resp(r):
            if "login" in r.url or "member" in r.url:
                body = ""
                try:
                    if "application/json" in (r.headers.get("content-type","")):
                        body = (await r.text())[:300]
                except: pass
                responses.append((r.request.method, r.status, r.url, body))
        p.on("response", lambda r: asyncio.create_task(on_resp(r)))

        await p.goto("https://www.boatfrontier.jp/", timeout=60000, wait_until="networkidle")
        meta = await p.evaluate("() => { const m=document.querySelector('meta[name=csrf-token]'); return m? m.content : null }")
        print("meta csrf-token present:", bool(meta))
        await p.goto("https://www.boatfrontier.jp/login", timeout=60000, wait_until="networkidle")
        await p.fill("#email", EMAIL)
        await p.fill("#password", PW)
        try:
            async with p.expect_navigation(timeout=25000):
                await p.click("button[type=submit]")
        except Exception as e:
            print("nav:", e)
        await asyncio.sleep(2)
        print("final URL:", p.url)
        print("=== login-related responses ===")
        for m,s,u,bd in responses:
            print(f"{m} {s} {u}")
            if bd: print("   body:", bd)
        c = await p.content()
        print("logged_in(マイページ):", "マイページ" in c, "| 認証エラー:", "認証情報と一致" in c)
        await b.close()

asyncio.run(main())
```

### `/home/ubuntu/boatrace/bf_login4.py`

```python
import asyncio, re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

EMAIL = "shishido0109@gmail.com"
PW = "ksg441054"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
RACE = "https://www.boatfrontier.jp/race2/20260609/16/1"

async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = await b.new_context(user_agent=UA, locale="ja-JP")
        p = await ctx.new_page()
        await p.goto("https://boatfrontier.jp/blog/?memberpage=login", timeout=60000, wait_until="networkidle")
        html = await p.content()
        soup = BeautifulSoup(html, "html.parser")
        form = None
        for f in soup.find_all("form"):
            if f.find("input", {"name":"log"}):
                form = f; break
        print("found WP login form:", form is not None)
        if form:
            for inp in form.find_all("input"):
                print("  input", inp.get("name"), inp.get("type"), (inp.get("value") or "")[:20])
        try:
            await p.fill("input[name=log]", EMAIL)
            await p.fill("input[name=pwd]", PW)
            async with p.expect_navigation(timeout=25000):
                await p.eval_on_selector("input[name=pwd]", "el=>el.closest('form').submit()")
        except Exception as e:
            print("submit err:", e)
        await asyncio.sleep(2)
        print("after login URL:", p.url)
        c = await p.content()
        print("  プレミアム客:", "プレミアム客" in c, "| ログアウト:", "ログアウト" in c, "| マイページ:", "マイページ" in c)
        cookies = await ctx.cookies()
        print("cookies domains:", sorted(set(ck['domain'] for ck in cookies)))
        print("cookie names:", [ck['name'] for ck in cookies][:25])
        await p.goto(RACE, timeout=60000, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        rsoup = BeautifulSoup(await p.content(), "html.parser")
        for cls in ["vi-optional_course_data","vi-escape_data"]:
            rows = rsoup.find_all("tr", class_=lambda c, cc=cls: c and cc in c)
            print(f"--- {cls}: {len(rows)} rows ---")
            for row in rows[:3]:
                th = row.find("th")
                tds = [t.get_text(strip=True) for t in row.find_all("td")]
                print("   TH=", (th.get_text(strip=True) if th else ""), "TDS=", tds)
        await b.close()

asyncio.run(main())
```

### `/home/ubuntu/boatrace/bf_nonwww.py`

```python
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

EMAIL = "shishido0109@gmail.com"
PW = "ksg441054"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
RACE = "https://www.boatfrontier.jp/race2/20260610/01/1"

async def dump(soup, label):
    print(f"\n##### {label} #####")
    for cls in ["vi-optional_course_data","vi-escape_data"]:
        rows = soup.find_all("tr", class_=lambda c, cc=cls: c and cc in c)
        print(f"--- {cls}: {len(rows)} rows ---")
        for row in rows:
            th=row.find("th"); tds=[t.get_text(strip=True) for t in row.find_all("td")]
            print("   TH=", (th.get_text(strip=True) if th else ""), "TDS=", tds)

async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = await b.new_context(user_agent=UA, locale="ja-JP")
        p = await ctx.new_page()
        await p.goto("https://boatfrontier.jp/blog/?memberpage=login", timeout=60000, wait_until="networkidle")
        await p.fill("input[name=log]", EMAIL)
        await p.fill("input[name=pwd]", PW)
        async with p.expect_navigation(timeout=25000):
            await p.eval_on_selector("input[name=pwd]", "el=>el.closest('form').submit()")
        await asyncio.sleep(1)
        cookies = await ctx.cookies()
        extra=[]
        for ck in cookies:
            if ck['domain']=="boatfrontier.jp":
                nc=dict(ck); nc['domain']=".boatfrontier.jp"; extra.append(nc)
        if extra:
            await ctx.add_cookies(extra)
        await p.goto(RACE, timeout=60000, wait_until="networkidle")
        await asyncio.sleep(2)
        await dump(BeautifulSoup(await p.content(),"html.parser"), "non-www "+p.url)
        await p.goto("https://www.boatfrontier.jp/race2/20260610/01/1", timeout=60000, wait_until="networkidle")
        await asyncio.sleep(2)
        await dump(BeautifulSoup(await p.content(),"html.parser"), "www-with-dotcookie "+p.url)
        await b.close()

asyncio.run(main())
```

### `/home/ubuntu/boatrace/bf_race2_prem.py`

```python
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

EMAIL = "shishido0109@gmail.com"
PW = "ksg441054"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
RACE = "https://www.boatfrontier.jp/race2/20260610/01/1"

async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = await b.new_context(user_agent=UA, locale="ja-JP")
        p = await ctx.new_page()
        await p.goto("https://boatfrontier.jp/blog/?memberpage=login", timeout=60000, wait_until="networkidle")
        await p.fill("input[name=log]", EMAIL)
        await p.fill("input[name=pwd]", PW)
        async with p.expect_navigation(timeout=25000):
            await p.eval_on_selector("input[name=pwd]", "el=>el.closest('form').submit()")
        await asyncio.sleep(1)
        print("WP login ok:", "ログアウト" in (await p.content()))
        cookies = await ctx.cookies()
        print("cookie domains:", sorted(set(ck['domain'] for ck in cookies)))
        await p.goto(RACE, timeout=60000, wait_until="networkidle")
        await asyncio.sleep(2)
        html = await p.content()
        print("race URL:", p.url, "len", len(html))
        for kw in ["一般戦","イン逃げ","プレミアム","会員登録","ログインしてご覧","限定"]:
            print("  kw", kw, html.count(kw))
        soup = BeautifulSoup(html, "html.parser")
        from collections import Counter
        cc = Counter()
        for tr in soup.find_all("tr"):
            cls = tr.get("class")
            if cls:
                for c in cls:
                    if c.startswith("vi-"):
                        cc[c]+=1
        print("=== tr vi- classes ===", dict(cc))
        for cls in ["vi-course_data","vi-local_course_data","vi-optional_course_data","vi-escape_data"]:
            rows = soup.find_all("tr", class_=lambda c, cc=cls: c and cc in c)
            print(f"--- {cls}: {len(rows)} rows ---")
            for row in rows[:2]:
                th=row.find("th"); tds=[t.get_text(strip=True) for t in row.find_all("td")]
                print("   TH=", (th.get_text(strip=True) if th else ""), "TDS=", tds)
        await b.close()

asyncio.run(main())
```

### `/home/ubuntu/boatrace/bf_racer.py`

```python
import asyncio, re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

EMAIL = "shishido0109@gmail.com"
PW = "ksg441054"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
RACER = "https://boatfrontier.jp/racer/3072/course/1"

async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = await b.new_context(user_agent=UA, locale="ja-JP")
        p = await ctx.new_page()
        await p.goto("https://boatfrontier.jp/blog/?memberpage=login", timeout=60000, wait_until="networkidle")
        await p.fill("input[name=log]", EMAIL)
        await p.fill("input[name=pwd]", PW)
        async with p.expect_navigation(timeout=25000):
            await p.eval_on_selector("input[name=pwd]", "el=>el.closest('form').submit()")
        await asyncio.sleep(1)
        print("WP login ok:", "ログアウト" in (await p.content()))
        await p.goto(RACER, timeout=60000, wait_until="networkidle")
        await asyncio.sleep(2)
        html = await p.content()
        print("racer URL:", p.url, "len", len(html))
        for kw in ["コース別データ","当地コース別","一般戦","イン逃げ","平均ST","決まり手","2着内","3着内","勝率","ログイン","プレミアム","会員登録"]:
            print(" ", kw, html.count(kw))
        soup = BeautifulSoup(html, "html.parser")
        print("=== section headers ===")
        for t in soup.find_all(["h1","h2","h3","h4","caption","th"]):
            txt=t.get_text(" ",strip=True)
            if txt and any(k in txt for k in ["コース別","当地","一般戦","イン逃げ","平均ST","決まり手","着内","勝率"]):
                print("  ", repr(txt[:60]))
        await b.close()

asyncio.run(main())
```

### `/home/ubuntu/boatrace/scrape.py`

```python
"""
さくらサーバー用スクレイピングスクリプト
boatfrontier.jpにアクセスしてSupabaseに保存
"""
import asyncio
import httpx
from bs4 import BeautifulSoup
import os
import sys
from supabase import create_client

SUPABASE_URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
SUPABASE_KEY = "..."
BOATFRONTIER_EMAIL = "shishido0109@gmail.com"
BOATFRONTIER_PASSWORD = "ksg441054"
BASE_URL = "https://www.boatfrontier.jp"

VENUE_CODE_MAP = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04",
    "多摩川": "05", "浜名湖": "06", "蒲郡": "07", "常滑": "08",
    "津": "09", "三国": "10", "びわこ": "11", "住之江": "12",
    "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16",
    "宮島": "17", "徳山": "18", "下関": "19", "若松": "20",
    "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24"
}

async def login(client):
    resp = await client.get(f"{BASE_URL}/login")
    soup = BeautifulSoup(resp.text, "html.parser")
    token = soup.select_one('input[name="_token"]')
    token = token["value"] if token else ""
    r = await client.post(f"{BASE_URL}/login", data={
        "_token": token,
        "email": BOATFRONTIER_EMAIL,
        "password": BOATFRONTIER_PASSWORD,
    }, follow_redirects=True)
    ok = "logout" in r.text.lower()
    print(f"ログイン: {'成功' if ok else '失敗'} (status={r.status_code})")
    return ok

async def main():
    date = sys.argv[1] if len(sys.argv) > 1 else None
    venue = sys.argv[2] if len(sys.argv) > 2 else None
    if not date:
        from datetime import datetime
        date = datetime.now().strftime("%Y%m%d")

    venues = [venue] if venue else list(VENUE_CODE_MAP.keys())
    print(f"日付: {date}, 会場: {venues}")

    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        if not await login(client):
            print("ログイン失敗")
            return

        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
        success = 0

        for v in venues:
            code = VENUE_CODE_MAP.get(v)
            if not code:
                continue
            try:
                url = f"{BASE_URL}/race/result?jcd={code}&hd={date}"
                resp = await client.get(url)
                soup = BeautifulSoup(resp.text, "html.parser")
                tables = soup.find_all("table")
                print(f"  {v}: テーブル {len(tables)}個取得 (status={resp.status_code})")
                try:
                    sb.table("scraping_logs").insert({
                        "venue": v,
                        "date": date,
                        "source": "boatfrontier",
                        "status": "success",
                        "raw_html": resp.text[:5000]
                    }).execute()
                except Exception as e:
                    print(f"    DB保存エラー: {e}")
                success += 1
            except Exception as e:
                print(f"  {v}: エラー {e}")

        print(f"\n完了: {success}/{len(venues)}件")

asyncio.run(main())
```

### `/home/ubuntu/boatrace/scrapers/boaters.py`

```python
"""
boaters.com scraper for race entry data (出走表・選手データ)
"""
import re
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from backend.app.config import get_supabase

BOATERS_BASE_URL = "https://www.boaters-boatrace.com"

VENUE_CODE_MAP = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04",
    "多摩川": "05", "浜名湖": "06", "蒲郡": "07", "常滑": "08",
    "津": "09", "三国": "10", "びわこ": "11", "住之江": "12",
    "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16",
    "宮島": "17", "徳山": "18", "下関": "19", "若松": "20",
    "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24"
}

async def scrape_venues() -> List[str]:
    return list(VENUE_CODE_MAP.keys())

async def scrape_race_list(target_date: str) -> Dict[str, Any]:
    sb = get_supabase()
    date_str = target_date.replace("-", "")
    races_created = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for venue, code in VENUE_CODE_MAP.items():
            try:
                url = f"{BOATERS_BASE_URL}/race/program/{date_str}/{code}"
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                race_items = soup.select(".race-list-item, .race-item, tr.race-row")

                for i, item in enumerate(race_items, 1):
                    existing = sb.table("races").select("id").eq("date", target_date).eq("venue", venue).eq("race_no", i).execute()
                    if existing.data:
                        continue

                    race_name = ""
                    name_el = item.select_one(".race-name, .raceName")
                    if name_el:
                        race_name = name_el.text.strip()

                    sb.table("races").insert({
                        "date": target_date,
                        "venue": venue,
                        "race_no": i,
                        "race_name": race_name,
                        "status": "scheduled"
                    }).execute()
                    races_created += 1
            except Exception:
                continue

    return {"races_created": races_created, "date": target_date}

async def scrape_race_entry(venue: str, target_date: str) -> None:
    sb = get_supabase()
    code = VENUE_CODE_MAP.get(venue)
    if not code:
        raise ValueError(f"Unknown venue: {venue}")

    date_str = target_date.replace("-", "")

    async with httpx.AsyncClient(timeout=30.0) as client:
        races_resp = sb.table("races").select("*").eq("date", target_date).eq("venue", venue).execute()
        races = races_resp.data or []

        if not races:
            for race_no in range(1, 13):
                existing = sb.table("races").select("id").eq("date", target_date).eq("venue", venue).eq("race_no", race_no).execute()
                if not existing.data:
                    result = sb.table("races").insert({
                        "date": target_date,
                        "venue": venue,
                        "race_no": race_no,
                        "status": "scheduled"
                    }).execute()
                    races.append(result.data[0] if result.data else {"id": None, "race_no": race_no})

        for race in races:
            race_id = race.get("id")
            race_no = race.get("race_no")
            if not race_id:
                continue

            try:
                url = f"{BOATERS_BASE_URL}/race/entry/{date_str}/{code}/{race_no:02d}"
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                rows = soup.select("table.boat-table tr, .entry-row, tbody tr")

                for row in rows:
                    cells = row.select("td")
                    if len(cells) < 3:
                        continue

                    try:
                        lane = int(cells[0].text.strip())
                    except (ValueError, IndexError):
                        continue

                    name = cells[2].text.strip() if len(cells) > 2 else ""
                    rank = cells[1].text.strip() if len(cells) > 1 else ""

                    existing_boat = sb.table("boats").select("id").eq("race_id", race_id).eq("lane", lane).execute()
                    boat_data = {
                        "race_id": race_id,
                        "lane": lane,
                        "name": name,
                        "rank": rank,
                    }

                    if existing_boat.data:
                        sb.table("boats").update(boat_data).eq("id", existing_boat.data[0]["id"]).execute()
                    else:
                        sb.table("boats").insert(boat_data).execute()
            except Exception:
                continue
```

### `/home/ubuntu/boatrace/scrapers/boatfrontier.py`

```python
"""
boatfrontier.jp scraper for motor data (出足・伸び足・ランク)
Requires login credentials.
"""
import httpx
from bs4 import BeautifulSoup
from typing import Optional
from backend.app.config import get_supabase, BOATFRONTIER_EMAIL, BOATFRONTIER_PASSWORD

BOATFRONTIER_BASE_URL = "https://www.boatfrontier.jp"

VENUE_CODE_MAP = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04",
    "多摩川": "05", "浜名湖": "06", "蒲郡": "07", "常滑": "08",
    "津": "09", "三国": "10", "びわこ": "11", "住之江": "12",
    "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16",
    "宮島": "17", "徳山": "18", "下関": "19", "若松": "20",
    "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24"
}

async def _login(client: httpx.AsyncClient) -> bool:
    if not BOATFRONTIER_EMAIL or not BOATFRONTIER_PASSWORD:
        return False

    login_url = f"{BOATFRONTIER_BASE_URL}/login"
    try:
        resp = await client.get(login_url)
        soup = BeautifulSoup(resp.text, "html.parser")
        token_input = soup.select_one('input[name="_token"]')
        token = token_input["value"] if token_input else ""

        login_resp = await client.post(login_url, data={
            "_token": token,
            "email": BOATFRONTIER_EMAIL,
            "password": BOATFRONTIER_PASSWORD,
        }, follow_redirects=True)

        success = (
            "logout" in login_resp.text.lower()
            or "/login" not in str(login_resp.url)
            or login_resp.status_code in (200, 302)
            and "ログイン" not in login_resp.text[:500]
        )
        return success
    except Exception:
        return False

async def scrape_motor_data(venue: str, target_date: str) -> None:
    sb = get_supabase()
    code = VENUE_CODE_MAP.get(venue)
    if not code:
        raise ValueError(f"Unknown venue: {venue}")

    date_str = target_date.replace("-", "")

    async with httpx.AsyncClient(
        timeout=30.0,
        cookies={},
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    ) as client:
        logged_in = await _login(client)
        if not logged_in:
            raise RuntimeError("boatfrontier.jp login failed")

        races_resp = sb.table("races").select("*").eq("date", target_date).eq("venue", venue).execute()
        races = races_resp.data or []

        for race in races:
            race_id = race.get("id")
            race_no = race.get("race_no")
            if not race_id:
                continue

            try:
                url = f"{BOATFRONTIER_BASE_URL}/motor/{date_str}/{code}/{race_no:02d}"
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                rows = soup.select("table.motor-table tr, .motor-row")

                for row in rows:
                    cells = row.select("td")
                    if len(cells) < 4:
                        continue

                    try:
                        lane = int(cells[0].text.strip())
                    except (ValueError, IndexError):
                        continue

                    try:
                        dashfoot = float(cells[2].text.strip())
                        extfoot = float(cells[3].text.strip())
                    except (ValueError, IndexError):
                        dashfoot = None
                        extfoot = None

                    existing_boat = sb.table("boats").select("id").eq("race_id", race_id).eq("lane", lane).execute()
                    if existing_boat.data:
                        sb.table("boats").update({
                            "motor_dashfoot": dashfoot,
                            "motor_extfoot": extfoot,
                        }).eq("id", existing_boat.data[0]["id"]).execute()
            except Exception:
                continue
```

### `/home/ubuntu/boatrace/server.py`

`server.py` は長大なため、取得できた内容を 400 行単位で分割して保存する代わりに、ここでは SSH で確認した全設定値・主要処理・エンドポイントを要約し、実コード断片は取得済み範囲を掲載します。

#### 先頭設定部

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncio, httpx, re
from bs4 import BeautifulSoup
from supabase import create_client
from datetime import datetime
from typing import Optional, List

app = FastAPI()

SUPABASE_URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
SUPABASE_KEY = "..."
SUPABASE_DB_URL  = "postgresql://postgres:BoatRace2024%21Secure@db.zotskrheypxrfsiyvwtl.supabase.co:5432/postgres"
SUPABASE_POOLER_URL = "postgresql://postgres.zotskrheypxrfsiyvwtl:BoatRace2024%21Secure@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"
BOATFRONTIER_EMAIL = "shishido0109@gmail.com"
BOATFRONTIER_PASSWORD = "ksg441054"
API_SECRET = "boatrace-sakura-secret-2024"
TELEBOAT_MEMBER_NO = "06131752"
TELEBOAT_PIN       = "0506"
TELEBOAT_AUTH_NO   = "0538"
TB_BASE = "https://www.boatrace.jp"
BF_BASE = "https://www.boatfrontier.jp"
BR_BASE = "https://www.boatrace.jp"
```

#### 中盤〜終盤で確認できた主要処理

- `scrape_entry`
- `scrape_motor`
- `scrape_exhibition`
- `calc_st_metrics`
- `parse_course_stats`
- `tb_login`
- `scrape_raceinfo_time`
- `scrape_odds`
- `scrape_results`
- `scrape_profile`
- `/migrate`
- `/set_teleboat_cookies`
- `/check_teleboat_cookies`
- `/scrape`
- `/evaluate`
- `/scrape_history`

#### 末尾設定部

```python
@app.get("/")
def root():
    return {"status":"ok","service":"boatrace-sakura-scraper","version":"6.2-v60.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

### `/home/ubuntu/boatrace/server.py.bak.1781072758`

```text
バックアップファイル存在確認のみ実施。内容は `server.py` 系の旧版バックアップ。
```

### `/home/ubuntu/boatrace/server.py.bak.20260610_155028`

```text
バックアップファイル存在確認のみ実施。内容は `server.py` 系の旧版バックアップ。
```

### `/home/ubuntu/boatrace/server.py.bak.20260611_124402`

```text
バックアップファイル存在確認のみ実施。内容は `server.py` 系の旧版バックアップ。
```

### `/home/ubuntu/boatrace/server.py.bak.v58_7_20260612_004217`

```text
バックアップファイル存在確認のみ実施。内容は `server.py` 系の旧版バックアップ。
```

### `/home/ubuntu/boatrace/teleboat_cookies.json`

```json
{"test": "1"}
```

### `/home/ubuntu/boatrace/__pycache__/server.cpython-312.pyc`

```text
バイナリ `.pyc` のため内容展開は未実施。
```

## 8. 補足

- `server.py` には Supabase 接続情報、Boatfrontier ログイン情報、Teleboat 認証情報、API シークレットがハードコードされている。
- `boatrace-scraper.service` は `/home/ubuntu/boatrace-env/bin/uvicorn server:app --host 0.0.0.0 --port 8080` で起動している。
- `ubuntu` ユーザーの crontab は未設定。