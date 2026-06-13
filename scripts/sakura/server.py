from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncio, httpx, re
from bs4 import BeautifulSoup
from supabase import create_client
from datetime import datetime
from typing import Optional, List

app = FastAPI()

SUPABASE_URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ.vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
SUPABASE_DB_URL  = "postgresql://postgres:BoatRace2024%21Secure@db.zotskrheypxrfsiyvwtl.supabase.co:5432/postgres"
# IPv6直結が失敗するサーバー向けプーラーDSN（Transaction mode: IPv4 port 6543）
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

VENUE_CODE_MAP = {
    "桐生":"01","戸田":"02","江戸川":"03","平和島":"04","多摩川":"05","浜名湖":"06",
    "蒲郡":"07","常滑":"08","津":"09","三国":"10","びわこ":"11","住之江":"12",
    "尼崎":"13","鳴門":"14","丸亀":"15","児島":"16","宮島":"17","徳山":"18",
    "下関":"19","若松":"20","芦屋":"21","福岡":"22","唐津":"23","大村":"24"
}
# boaters-boatrace.com の会場slug(ローマ字)
BOATERS_SLUG_MAP = {
    "桐生":"kiryu","戸田":"toda","江戸川":"edogawa","平和島":"heiwajima","多摩川":"tamagawa","浜名湖":"hamanako",
    "蒲郡":"gamagori","常滑":"tokoname","津":"tsu","三国":"mikuni","びわこ":"biwako","住之江":"suminoe",
    "尼崎":"amagasaki","鳴門":"naruto","丸亀":"marugame","児島":"kojima","宮島":"miyajima","徳山":"tokuyama",
    "下関":"shimonoseki","若松":"wakamatsu","芦屋":"ashiya","福岡":"fukuoka","唐津":"karatsu","大村":"omura"
}
# 数字コード→会場名の逆引きマップ
VENUE_NAME_MAP = {v: k for k, v in VENUE_CODE_MAP.items()}
# 1桁/2桁どちらでも対応するヘルパー
def resolve_venue(v: str):
    """'丸亀'→('丸亀','15') / '15'→('丸亀','15') / '7'→('蒲郡','07')"""
    if v in VENUE_CODE_MAP:
        return v, VENUE_CODE_MAP[v]
    code = v.zfill(2)
    if code in VENUE_NAME_MAP:
        return VENUE_NAME_MAP[code], code
    return None, None

def fmt(date):
    d = date.replace("-","")
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"

def nums(cell):
    """BeautifulSoup cellから数値リストを抽出(改行区切り)"""
    if hasattr(cell, 'get_text'):
        text = cell.get_text(separator='\n', strip=True)
    else:
        text = str(cell)
    result = []
    for part in text.split('\n'):
        part = part.strip()
        try: result.append(float(part))
        except: pass
    return result

def sf(s):
    try: return float(re.search(r'[\d.]+', str(s)).group())
    except: return None

def safe_float(value, default=0.0):
    try:
        if value in (None, "", "-"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

def safe_int(value, default=0):
    try:
        if value in (None, "", "-"):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default

async def bf_login(client):
    r = await client.get(f"{BF_BASE}/login")
    soup = BeautifulSoup(r.text, "html.parser")
    tok = soup.select_one('input[name="_token"]')
    tok = tok["value"] if tok else ""
    r2 = await client.post(f"{BF_BASE}/login", data={"_token":tok,"email":BOATFRONTIER_EMAIL,"password":BOATFRONTIER_PASSWORD}, follow_redirects=True)
    return "logout" in r2.text.lower()

async def fetch_race_entry(client, sb, date_str, date_fmt, venue, venue_code, race_no):
    """boatrace.jp から1レース分の出走表を取得してDBに保存"""
    url = f"{BR_BASE}/owpc/pc/race/racelist?hd={date_str}&jcd={venue_code}&rno={race_no}"
    resp = await client.get(url)
    if resp.status_code != 200:
        return 0
    soup = BeautifulSoup(resp.text, "html.parser")

    # 出走表テーブルの選手行を取得
    player_rows = soup.select("table tbody tr")
    boats_saved = 0

    # race_id 取得または作成
    ex = sb.table("races").select("id").eq("date",date_fmt).eq("venue",venue).eq("race_no",race_no).execute()
    if ex.data:
        race_id = ex.data[0]["id"]
    else:
        r2 = sb.table("races").insert({"date":date_fmt,"venue":venue,"race_no":race_no,"status":"scheduled"}).execute()
        if not r2.data: return 0
        race_id = r2.data[0]["id"]

    for row in player_rows:
        cells = row.find_all(["td","th"])
        if len(cells) < 20: continue

        # 枠番
        import unicodedata; lane_text = unicodedata.normalize("NFKC", cells[0].get_text(strip=True))
        try:
            lane = int(lane_text)
            if lane < 1 or lane > 6: continue
        except:
            continue

        # 選手名・登録番号・ランク・年齢・体重
        cell2_text = cells[2].get_text(separator="|", strip=True)
        # 登録番号（4桁）
        reg_m = re.search(r'(\d{4})', cell2_text)
        reg_no = reg_m.group(1) if reg_m else f"tmp_{lane}"
        # ランク
        rank_m = re.search(r'([AB][12])', cell2_text)
        rank = rank_m.group(1) if rank_m else ""
        # 名前（全角文字の連続）
        name_parts = [p.strip() for p in cell2_text.split("|") if re.search(r'[\u4e00-\u9fff\u3040-\u309f]', p)]
        name = name_parts[0] if name_parts else ""
        # 年齢（XX歳）
        age_m = re.search(r'(\d{2,3})歳', cell2_text)
        age = int(age_m.group(1)) if age_m else None
        # 体重（XX.Xkg）
        wt_m = re.search(r'([\d.]+)kg', cell2_text)
        weight = float(wt_m.group(1)) if wt_m else None

        # F/L/avgST セル: "F0L00.14"
        fl_text = cells[3].get_text(strip=True) if len(cells)>3 else ""
        f_m = re.search(r'F(\d+)', fl_text)
        l_m = re.search(r'L(\d+)', fl_text)
        st_nums = re.findall(r'\d+\.\d+', fl_text)
        f_count  = int(f_m.group(1)) if f_m else None
        avg_st   = float(st_nums[-1]) if st_nums else None

        # 全国: 勝率/2連率/3連率
        nat_nums = nums(cells[4]) if len(cells)>4 else []
        national_win_rate    = nat_nums[0] if len(nat_nums)>0 else None
        national_place2_rate = nat_nums[1] if len(nat_nums)>1 else None

        # 当地: 勝率/2連率/3連率
        loc_nums = nums(cells[5]) if len(cells)>5 else []
        local_win_rate    = loc_nums[0] if len(loc_nums)>0 else None
        local_place2_rate = loc_nums[1] if len(loc_nums)>1 else None

        # モーター: No/2連率/3連率
        mot_nums = nums(cells[6]) if len(cells)>6 else []
        motor_no          = int(mot_nums[0]) if len(mot_nums)>0 else None
        motor_place2_rate = mot_nums[1] if len(mot_nums)>1 else None

        # ボート: No/2連率/3連率
        boat_nums = nums(cells[7]) if len(cells)>7 else []
        boat_no          = int(boat_nums[0]) if len(boat_nums)>0 else None
        boat_place2_rate = boat_nums[1] if len(boat_nums)>1 else None

        if not name or len(name) < 2: continue

        # players upsert
        pl = sb.table("players").select("id").eq("registration_no", reg_no).execute()
        if pl.data:
            player_id = pl.data[0]["id"]
            sb.table("players").update({"rank":rank,"name":name}).eq("id",player_id).execute()
        else:
            pl2 = sb.table("players").insert({
                "name":name,"rank":rank,"registration_no":reg_no,
                "age":age,
            }).execute()
            if not pl2.data: continue
            player_id = pl2.data[0]["id"]

        bdata = {
            "race_id": race_id, "lane": lane, "player_id": player_id,
            "age": age, "weight": weight, "f_count": f_count,
            "national_win_rate": national_win_rate,
            "national_place2_rate": national_place2_rate,
            "local_win_rate": local_win_rate,
            "local_place2_rate": local_place2_rate,
            "motor_no": motor_no, "motor_place2_rate": motor_place2_rate,
            "boat_no": boat_no,
            "avg_st": avg_st,
        }
        ex2 = sb.table("boats").select("id").eq("race_id",race_id).eq("lane",lane).execute()
        if ex2.data:
            sb.table("boats").update(bdata).eq("id",ex2.data[0]["id"]).execute()
        else:
            sb.table("boats").insert(bdata).execute()
        boats_saved += 1

    return boats_saved

async def scrape_entry(date, venues):
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    date_fmt = fmt(date)
    date_str = date.replace("-","")
    results = []
    async with httpx.AsyncClient(follow_redirects=True, timeout=30,
            headers={"User-Agent":"Mozilla/5.0"}) as client:
        for v in venues:
            vname, vc = resolve_venue(v)
            if not vc:
                results.append({"venue":v,"item":"entry","status":"error","message":"unknown venue"})
                continue
            try:
                # 全12レース並列取得
                tasks = [fetch_race_entry(client, sb, date_str, date_fmt, vname, vc, rno) for rno in range(1,13)]
                counts = await asyncio.gather(*tasks, return_exceptions=True)
                total = sum(c for c in counts if isinstance(c, int))
                results.append({"venue":v,"item":"entry","status":"ok","boats":total})
            except Exception as e:
                results.append({"venue":v,"item":"entry","status":"error","message":str(e)})
    return results

async def scrape_motor(date, venues):
    """boatfrontier.jp /race2/{date}/{jcd}/{rno} からPlaywrightで出足・伸び足・今節STを取得"""
    from playwright.async_api import async_playwright
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    date_str = date.replace("-","")
    date_fmt = fmt(date)
    results = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        context = await browser.new_context()
        page = await context.new_page()

        # ログイン (WordPress会員ログイン: プレミアム会員データ解禁)
        await page.goto("https://boatfrontier.jp/blog/?memberpage=login", timeout=60000, wait_until="networkidle")
        await page.fill("input[name=log]", BOATFRONTIER_EMAIL)
        await page.fill("input[name=pwd]", BOATFRONTIER_PASSWORD)
        try:
            async with page.expect_navigation(timeout=25000):
                await page.eval_on_selector("input[name=pwd]", "el=>el.closest('form').submit()")
        except Exception:
            pass
        await asyncio.sleep(1)
        if "ログアウト" not in (await page.content()) and "マイページ" not in (await page.content()):
            await browser.close()
            return [{"venue":v,"item":"motor","status":"error","message":"boatfrontier login failed"} for v in venues]
        # host-only(boatfrontier.jp)のWPクッキーを.boatfrontier.jpにコピー → www側にも送信されプレミアムデータ解禁
        _cookies = await context.cookies()
        _extra = []
        for ck in _cookies:
            if ck.get("domain") == "boatfrontier.jp":
                nc = dict(ck); nc["domain"] = ".boatfrontier.jp"; _extra.append(nc)
        if _extra:
            await context.add_cookies(_extra)

        for v in venues:
            vname, code = resolve_venue(v)
            if not code:
                results.append({"venue":v,"item":"motor","status":"error","message":"unknown venue"})
                continue
            try:
                races = sb.table("races").select("id,race_no").eq("date",date_fmt).eq("venue",vname).execute().data or []
                saved = 0
                for race in races:
                    race_id = race["id"]
                    race_no = race["race_no"]
                    try:
                        url = f"{BF_BASE}/race2/{date_str}/{int(code)}/{race_no}"
                        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                        await asyncio.sleep(1)
                        soup = BeautifulSoup(await page.content(), "html.parser")
                        tbl = soup.find("table")
                        if not tbl:
                            continue
                        # 枠番行でカラム順を確認 (通常 td=[6,5,4,3,2,1])
                        lane_order = [6,5,4,3,2,1]
                        for row in tbl.find_all("tr"):
                            ths = [t.get_text(strip=True) for t in row.find_all("th")]
                            if ths and ths[0] == "枠":
                                tds = [t.get_text(strip=True) for t in row.find_all("td")]
                                try: lane_order = [int(x) for x in tds if x.isdigit()]
                                except: pass
                                break

                        # 全クラス行をパース: motor_eval / start_data / course_data / local_course_data
                        # lane_order[i] = そのインデックスに対応するlane番号
                        data_per_lane = {lane: {"entry_course": lane} for lane in lane_order}

                        def set_lane_vals(rows_class, th_keyword, field, transform=None):
                            for row in tbl.find_all("tr", class_=lambda c: c and rows_class in c):
                                th = row.find("th")
                                th_text = th.get_text(strip=True) if th else ""
                                if th_keyword not in th_text:
                                    continue
                                tds = [td.get_text(strip=True) for td in row.find_all("td")]
                                for i, val in enumerate(tds):
                                    if i >= len(lane_order): break
                                    lane = lane_order[i]
                                    try:
                                        v = transform(val) if transform else safe_float(val, None)
                                        if v is not None:
                                            data_per_lane[lane][field] = v
                                    except: pass

                        def parse_st_rank(val):
                            """'0.184.6' → (0.18, 4.6)"""
                            m = re.match(r"^(0\.\d{2})([\d.]+)$", val)
                            return (float(m.group(1)), float(m.group(2))) if m else (None, None)

                        def parse_kime(val):
                            """'0/2/2' → (sashi=0, makuri=2, makurizashi=2)"""
                            parts = val.split("/")
                            if len(parts) == 3:
                                return (int(parts[0]), int(parts[1]), int(parts[2]))
                            return (None, None, None)

                        # モーター出足・伸び足・総合評価
                        set_lane_vals("vi-motor_eval", "モーター出足",   "motor_dashfoot")
                        set_lane_vals("vi-motor_eval", "モーター伸び足",  "motor_extfoot")
                        for row in tbl.find_all("tr", class_=lambda c: c and "vi-motor_eval" in c):
                            th = row.find("th")
                            if th and "モーター総合評価" in th.get_text(strip=True):
                                tds = [td.get_text(strip=True) for td in row.find_all("td")]
                                for i, val in enumerate(tds):
                                    if i < len(lane_order) and val:
                                        data_per_lane[lane_order[i]]["motor_eval"] = str(val)

                        # 平均ST / 今節平均ST + 今節スタート順
                        for row in tbl.find_all("tr", class_=lambda c: c and "vi-start_data" in c):
                            th = row.find("th")
                            th_text = th.get_text(strip=True) if th else ""
                            tds = [td.get_text(strip=True) for td in row.find_all("td")]
                            if "今節" in th_text:
                                for i, val in enumerate(tds):
                                    if i >= len(lane_order): break
                                    st, rank = parse_st_rank(val)
                                    if st is not None:
                                        data_per_lane[lane_order[i]]["today_st"] = st
                                        if rank is not None:
                                            data_per_lane[lane_order[i]]["today_st_rank"] = safe_int(round(rank), 0)
                            elif "平均ST" in th_text:
                                for i, val in enumerate(tds):
                                    if i >= len(lane_order): break
                                    try:
                                        if val != "-":
                                            data_per_lane[lane_order[i]]["avg_st"] = safe_float(val, None)
                                    except: pass

                        # コース別データ(直近1年) → 各ボートの担当コース成績
                        for row in tbl.find_all("tr", class_=lambda c: c and "vi-course_data" in c):
                            th = row.find("th")
                            th_text = th.get_text(strip=True) if th else ""
                            tds = [td.get_text(strip=True) for td in row.find_all("td")]
                            for i, val in enumerate(tds):
                                if i >= len(lane_order): break
                                lane = lane_order[i]
                                cx = f"c{lane}"
                                try:
                                    if "平均ST" in th_text:
                                        st, rank = parse_st_rank(val)
                                        if st is not None:
                                            data_per_lane[lane]["course1y_st"] = st
                                            if rank is not None:
                                                data_per_lane[lane]["course1y_st_rank"] = rank
                                    elif "コース別勝率" in th_text:
                                        data_per_lane[lane][f"{cx}_win_rate"] = safe_float(val, None)
                                    elif "コース別2着内率" in th_text:
                                        data_per_lane[lane][f"{cx}_place2_rate"] = safe_float(val, None)
                                    elif "コース別3着内率" in th_text:
                                        data_per_lane[lane][f"{cx}_tricast_rate"] = safe_float(val, None)
                                    elif "コース別決まり手" in th_text:
                                        s, mk, mz = parse_kime(val)
                                        if s is not None:
                                            data_per_lane[lane][f"{cx}_sashi"] = s
                                            data_per_lane[lane][f"{cx}_makuri"] = mk
                                            data_per_lane[lane][f"{cx}_makurizashi"] = mz
                                except: pass

                        # ② 当地コース別データ(直近5年) → local5y_*
                        for row in tbl.find_all("tr", class_=lambda c: c and "vi-local_course_data" in c):
                            th = row.find("th")
                            th_text = th.get_text(strip=True) if th else ""
                            tds = [td.get_text(strip=True) for td in row.find_all("td")]
                            for i, val in enumerate(tds):
                                if i >= len(lane_order): break
                                lane = lane_order[i]
                                try:
                                    if "出走数" in th_text:
                                        data_per_lane[lane]["local5y_races"] = safe_int(val, 0)
                                    elif "コース別勝率" in th_text:
                                        data_per_lane[lane]["local5y_win_rate"] = safe_float(val, None)
                                    elif "コース別2着内率" in th_text:
                                        data_per_lane[lane]["local5y_place2_rate"] = safe_float(val, None)
                                    elif "コース別3着内率" in th_text:
                                        data_per_lane[lane]["local5y_tricast_rate"] = safe_float(val, None)
                                    elif "コース別決まり手" in th_text:
                                        s, mk, mz = parse_kime(val)
                                        if s is not None:
                                            data_per_lane[lane]["local5y_sashi"] = s
                                            data_per_lane[lane]["local5y_makuri"] = mk
                                            data_per_lane[lane]["local5y_makurizashi"] = mz
                                except: pass

                        # ③ 一般戦(G2,G3含む)コース別データ(直近1年) → general1y_* (プレミアム限定/空の場合あり)
                        for row in tbl.find_all("tr", class_=lambda c: c and "vi-optional_course_data" in c):
                            th = row.find("th")
                            th_text = th.get_text(strip=True) if th else ""
                            tds = [td.get_text(strip=True) for td in row.find_all("td")]
                            for i, val in enumerate(tds):
                                if i >= len(lane_order): break
                                lane = lane_order[i]
                                if not val:
                                    continue
                                try:
                                    if "出走数" in th_text:
                                        data_per_lane[lane]["general1y_races"] = safe_int(val, 0)
                                    elif "コース別勝率" in th_text:
                                        data_per_lane[lane]["general1y_win_rate"] = safe_float(val, None)
                                    elif "コース別2着内率" in th_text:
                                        data_per_lane[lane]["general1y_place2_rate"] = safe_float(val, None)
                                    elif "コース別3着内率" in th_text:
                                        data_per_lane[lane]["general1y_tricast_rate"] = safe_float(val, None)
                                    elif "コース別決まり手" in th_text:
                                        s, mk, mz = parse_kime(val)
                                        if s is not None:
                                            data_per_lane[lane]["general1y_sashi"] = s
                                            data_per_lane[lane]["general1y_makuri"] = mk
                                            data_per_lane[lane]["general1y_makurizashi"] = mz
                                except: pass

                        # ④ イン逃げ時コース別データ(直近1年) → escape1y_* (プレミアム限定/空の場合あり)
                        for row in tbl.find_all("tr", class_=lambda c: c and "vi-escape_data" in c):
                            th = row.find("th")
                            th_text = th.get_text(strip=True) if th else ""
                            tds = [td.get_text(strip=True) for td in row.find_all("td")]
                            for i, val in enumerate(tds):
                                if i >= len(lane_order): break
                                lane = lane_order[i]
                                if not val:
                                    continue
                                try:
                                    if "2着内率" in th_text:
                                        data_per_lane[lane]["escape1y_place2_rate"] = safe_float(val, None)
                                    elif "3着内率" in th_text:
                                        data_per_lane[lane]["escape1y_tricast_rate"] = safe_float(val, None)
                                except: pass

                        # DBに保存
                        boats = sb.table("boats").select("id,lane").eq("race_id",race_id).execute().data or []
                        for boat in boats:
                            lane = boat["lane"]
                            bid = boat["id"]
                            upd = data_per_lane.get(lane, {})
                            if upd:
                                sb.table("boats").update(upd).eq("id",bid).execute()
                                saved += 1
                    except Exception as _re:
                        pass  # per-race error is skipped
                results.append({"venue":v,"item":"motor","status":"ok","saved":saved})
            except Exception as e:
                results.append({"venue":v,"item":"motor","status":"error","message":str(e)})

        await browser.close()
    return results

async def scrape_exhibition(date, venues):
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    date_fmt = fmt(date)
    date_str = date.replace("-","")
    results = []

    async def fetch_race(client, race, venue_code):
        race_id = race.get("id"); race_no = race.get("race_no")
        if not race_id: return 0
        try:
            resp = await client.get(f"{BR_BASE}/owpc/pc/race/beforeinfo?hd={date_str}&jcd={venue_code}&rno={race_no}")
            if resp.status_code != 200: return 0
            soup = BeautifulSoup(resp.text, "html.parser")
            tables = soup.find_all("table")
            if not tables: return 0

            # ① 展示タイム: table[0 or 1] に 枠/体重/展示タイム/チルト が並ぶ
            #   cells[0]=枠番, cells[1]=写真(空), cells[2]=選手名, cells[3]=体重, cells[4]=展示タイム
            lane_et = {}
            for tbl in tables:
                header_texts = [th.get_text(strip=True) for th in tbl.find_all("th")]
                if "展示タイム" not in " ".join(header_texts):
                    continue
                for row in tbl.select("tbody tr"):
                    cells = row.select("td")
                    if len(cells) < 5: continue
                    try:
                        lane = int(cells[0].get_text(strip=True))
                        et   = sf(cells[4].get_text(strip=True))
                        if lane and et is not None:
                            lane_et[lane] = et
                    except: pass
                break

            # ② 展示ST: div.table1_boatImage1 → Number=コース, Boat img=艇番, Time=ST
            #   img_boat2_X.png の X が艇番(=lane) に対応
            import re as _re
            lane_es = {}
            for div in soup.select("div.table1_boatImage1"):
                num_span  = div.select_one("span.table1_boatImage1Number")
                time_span = div.select_one("span.table1_boatImage1Time")
                img       = div.select_one("img[src*='img_boat2_']")
                if not (num_span and time_span and img): continue
                m = _re.search(r"img_boat2_(\d+)", img["src"])
                if not m: continue
                lane_num = int(m.group(1))
                st_text  = time_span.get_text(strip=True)  # e.g. "F.02", ".22", ".16"
                try:
                    # F = フライング(マイナス), それ以外は0+
                    if st_text.startswith("F"):
                        es = -float("0" + st_text[1:])
                    elif st_text.startswith("."):
                        es = float("0" + st_text)
                    else:
                        es = float(st_text)
                    lane_es[lane_num] = es
                except: pass

            # ③ 天候データをracesテーブルに保存
            WIND_DIR = {1:"北",2:"北北東",3:"北東",4:"東北東",5:"東",6:"東南東",7:"南東",
                        8:"南南東",9:"南",10:"南南西",11:"南西",12:"西南西",
                        13:"西",14:"西北西",15:"北西",16:"北北西"}
            import re as _re2
            weather_upd = {}
            w_div = soup.find("div", class_="weather1")
            if w_div:
                for unit in w_div.select(".weather1_bodyUnit"):
                    title_el = unit.select_one(".weather1_bodyUnitLabelTitle")
                    data_el  = unit.select_one(".weather1_bodyUnitLabelData")
                    title = title_el.get_text(strip=True) if title_el else ""
                    data  = data_el.get_text(strip=True)  if data_el  else ""
                    if not data and title in ["晴","曇り","雨","曇","小雨","大雨"]:
                        weather_upd["weather"] = title
                    elif title and not data:
                        # 天候は title 側に "雨" などが入る場合
                        weather_upd["weather"] = title
                    elif title == "気温":
                        m = _re2.search(r"([\d.]+)", data)
                        if m: weather_upd["temperature"] = float(m.group(1))
                    elif title == "水温":
                        m = _re2.search(r"([\d.]+)", data)
                        if m: weather_upd["water_temperature"] = float(m.group(1))
                    elif title == "風速":
                        m = _re2.search(r"([\d.]+)", data)
                        if m: weather_upd["wind_speed"] = float(m.group(1))
                    elif title == "波高":
                        m = _re2.search(r"([\d.]+)", data)
                        if m: weather_upd["wave_height"] = float(m.group(1))
                # 風向: is-windDirection の画像クラスから取得
                wd_unit = w_div.select_one(".is-windDirection")
                if wd_unit:
                    img_el = wd_unit.find(class_=_re2.compile(r"is-wind\d+"))
                    if img_el:
                        mm = _re2.search(r"is-wind(\d+)", " ".join(img_el.get("class",[])))
                        if mm:
                            weather_upd["wind_direction"] = WIND_DIR.get(int(mm.group(1)), "")
                # 天候 (weather1_bodyUnit is-weather内のspanタイトル)
                ww_unit = w_div.select_one(".is-weather")
                if ww_unit:
                    wt = ww_unit.select_one(".weather1_bodyUnitLabelTitle")
                    if wt: weather_upd["weather"] = wt.get_text(strip=True)
            if weather_upd:
                sb.table("races").update(weather_upd).eq("id", race_id).execute()

            updated = 0
            for lane in range(1, 7):
                et = lane_et.get(lane)
                es = lane_es.get(lane)
                if et is None and es is None: continue
                ex_b = sb.table("boats").select("id").eq("race_id",race_id).eq("lane",lane).execute()
                if ex_b.data:
                    upd = {}
                    if et is not None: upd["exhibition_time"] = et
                    if es is not None: upd["exhibition_st"]   = es
                    if upd:
                        sb.table("boats").update(upd).eq("id",ex_b.data[0]["id"]).execute()
                        updated += 1
            return updated
        except Exception as _e:
            print(f"fetch_race ERR race_id={race_id}: {_e}")
            return 0

    async with httpx.AsyncClient(follow_redirects=True, timeout=30, headers={"User-Agent":"Mozilla/5.0"}) as client:
        for v in venues:
            vname, vc = resolve_venue(v)
            if not vc:
                results.append({"venue":v,"item":"exhibition","status":"error","message":"unknown venue"})
                continue
            try:
                races = sb.table("races").select("*").eq("date",date_fmt).eq("venue",vname).execute().data or []
                counts = await asyncio.gather(*[fetch_race(client, race, vc) for race in races])
                results.append({"venue":v,"item":"exhibition","status":"ok","updated":sum(counts)})
            except Exception as e:
                results.append({"venue":v,"item":"exhibition","status":"error","message":str(e)})
    return results


async def calc_st_metrics(date, venues):
    """基準ST・優勢順位を avg_st から計算してDBに保存"""
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    date_fmt = fmt(date)
    results = []
    for v in venues:
        vname, _ = resolve_venue(v)
        races = sb.table("races").select("id").eq("date", date_fmt).eq("venue", vname).execute().data or []
        updated = 0
        for race in races:
            race_id = race["id"]
            boats = sb.table("boats").select("id,avg_st").eq("race_id", race_id).execute().data or []
            sts = [b["avg_st"] for b in boats if b.get("avg_st") is not None]
            if len(sts) < 2:
                continue
            standard = round(sum(sts) / len(sts), 3)
            sorted_sts = sorted(sts)
            for boat in boats:
                if boat.get("avg_st") is None:
                    continue
                rank = sorted_sts.index(boat["avg_st"]) + 1
                sb.table("boats").update({
                    "standard_st": standard,
                    "st_advantage_rank": rank
                }).eq("id", boat["id"]).execute()
                updated += 1
        results.append({"venue": v, "item": "st_metrics", "status": "ok", "updated": updated})
    return results


def parse_course_stats(html: str) -> dict:
    """boatfrontier.jp /racer/{toban} のコース別成績テーブルをパース
    列順: コース, 出走数, 1着数, 1着率, 2連対率, 3連対率, 平均ST, 平均ST順, 逃げ, 差し, まくり, まくり差し, 抜き, 恵まれ
    """
    data = {}
    soup = BeautifulSoup(html, "html.parser")
    for tbl in soup.find_all("table"):
        headers = [th.get_text(" ", strip=True) for th in tbl.find_all("th")]
        header_text = " ".join(headers)
        table_text = tbl.get_text(separator=" ", strip=True)
        if "逃げ" not in table_text or "まくり" not in table_text:
            continue
        rows = tbl.select("tbody tr") or tbl.find_all("tr")
        for row in rows:
            cells = row.find_all(["th", "td"])
            values = [cell.get_text(" ", strip=True) for cell in cells]
            if not values:
                continue
            lane_match = re.search(r"([1-6])\s*コース", values[0])
            if not lane_match:
                lane_match = re.search(r"([1-6])\s*コース", " ".join(values[:2]))
            if not lane_match:
                continue
            course = int(lane_match.group(1))
            numeric_values = []
            for value in values[1:]:
                m = re.search(r"\d+(?:\.\d+)?", value.replace(",", ""))
                if m:
                    numeric_values.append(float(m.group(0)))
            if len(numeric_values) < 11:
                flat = row.get_text(separator=" ", strip=True)
                fallback = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", flat)]
                if fallback and int(fallback[0]) == course:
                    fallback = fallback[1:]
                if len(fallback) > len(numeric_values):
                    numeric_values = fallback
            if len(numeric_values) < 11:
                continue
            px = f"c{course}"
            try: data[f"{px}_races"] = int(numeric_values[0])
            except: pass
            try: data[f"{px}_win_rate"] = float(numeric_values[2])
            except: pass
            try: data[f"{px}_place2_rate"] = float(numeric_values[3])
            except: pass
            try: data[f"{px}_tricast_rate"] = float(numeric_values[4])
            except: pass
            try: data[f"{px}_nige"] = int(numeric_values[7])
            except: pass
            try: data[f"{px}_sashi"] = int(numeric_values[8])
            except: pass
            try: data[f"{px}_makuri"] = int(numeric_values[9])
            except: pass
            try: data[f"{px}_makurizashi"] = int(numeric_values[10])
            except: pass
        if data:
            break
    return data



async def tb_login(client) -> bool:
    """boatrace.jp テレボート会員ログイン
    フォーム: in_KanyusyaNo=会員番号, in_AnsyoNo=暗証番号, in_PassWord=認証番号
    """
    try:
        login_url = f"{TB_BASE}/owpc/pc/login"
        r = await client.get(login_url, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        # hidden フィールドを取得
        form_name_input = soup.find("input", {"name": "TENT010_TENTPC010PRForm"})
        vs_input = soup.find("input", {"name": "javax.faces.ViewState"})
        auth_url_input = soup.find("input", {"name": "in_AuthAfterUrl"})

        data = {
            "TENT010_TENTPC010PRForm": form_name_input["value"] if form_name_input else "TENT010_TENTPC010PRForm",
            "in_KanyusyaNo": TELEBOAT_MEMBER_NO,
            "in_AnsyoNo":    TELEBOAT_PIN,
            "in_PassWord":   TELEBOAT_AUTH_NO,
            "check":         "on",
            "in_AuthAfterUrl": auth_url_input["value"] if auth_url_input else "",
            "javax.faces.ViewState": vs_input["value"] if vs_input else "stateless",
        }
        r2 = await client.post(login_url, data=data, follow_redirects=True, timeout=20)
        ok = (
            "ログアウト" in r2.text
            or "logout" in r2.text.lower()
            or "マイページ" in r2.text
            or "in_KanyusyaNo" not in r2.text  # ログイン成功 = フォームが消える
        )
        # 実際にbeforeinfotime にアクセスできるか確認
        if ok:
            test_r = await client.get(
                f"{TB_BASE}/owpc/pc/race/beforeinfotime?hd=20260608&jcd=15&rno=1",
                timeout=15
            )
            ok = "ログインページ" not in test_r.text
        print(f"tb_login status={r2.status_code} ok={ok} url={r2.url}")
        return ok
    except Exception as e:
        print(f"tb_login error: {e}")
        return False


async def scrape_raceinfo_time(date, venues):
    """boatrace.jp beforeinfotime から今節ST/1周T/回り足/出足/伸び足 を取得
    保存済みCookieを使用。未設定の場合はテレボートログインを試みる。
    """
    import os, json as _json
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    date_fmt = fmt(date)
    date_str = date.replace("-", "")
    results = []

    # 保存済みCookieを読み込む
    saved_cookies = {}
    if os.path.exists(TELEBOAT_COOKIE_FILE):
        try:
            with open(TELEBOAT_COOKIE_FILE) as _f:
                saved_cookies = _json.load(_f)
        except: pass

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=30,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        cookies=saved_cookies if saved_cookies else {}
    ) as client:
        # Cookie設定済みの場合はそのまま使用、なければログイン試行
        if not saved_cookies:
            logged_in = await tb_login(client)
            if not logged_in:
                return [{"venue": v, "item": "raceinfo_time", "status": "error",
                         "message": "teleboat login failed. /set_teleboat_cookies でCookieを設定してください"} for v in venues]

        for v in venues:
            vname, vc = resolve_venue(v)
            if not vc:
                results.append({"venue": v, "item": "raceinfo_time", "status": "error", "message": "unknown venue"})
                continue
            try:
                races = sb.table("races").select("id,race_no").eq("date", date_fmt).eq("venue", vname).execute().data or []
                if not races:
                    results.append({"venue": v, "item": "raceinfo_time", "status": "error", "message": "no races"})
                    continue

                updated = 0
                for race in races:
                    race_id = race["id"]
                    race_no = race["race_no"]
                    url = f"{TB_BASE}/owpc/pc/race/beforeinfotime?hd={date_str}&jcd={vc}&rno={race_no}"
                    try:
                        resp = await client.get(url, timeout=20)
                        if resp.status_code != 200:
                            continue
                        soup = BeautifulSoup(resp.text, "html.parser")

                        lane_data = {}
                        for tbl in soup.find_all("table"):
                            headers = [th.get_text(strip=True) for th in tbl.find_all("th")]
                            hdr_txt = " ".join(headers)
                            if "今節ST" not in hdr_txt:
                                continue
                            col_idx = {}
                            for i, h in enumerate(headers):
                                if "今節ST" in h: col_idx["season_st"] = i
                            for row in tbl.select("tbody tr"):
                                cells = row.select("td")
                                if not cells: continue
                                try:
                                    lane = int(cells[0].get_text(strip=True))
                                except:
                                    continue
                                row_data = {}
                                for key, idx in col_idx.items():
                                    if idx < len(cells):
                                        try:
                                            row_data[key] = float(cells[idx].get_text(strip=True))
                                        except:
                                            pass
                                if row_data:
                                    lane_data[lane] = row_data
                            if lane_data:
                                break

                        for lane, data in lane_data.items():
                            if not data: continue
                            ex_b = sb.table("boats").select("id").eq("race_id", race_id).eq("lane", lane).execute()
                            if ex_b.data:
                                sb.table("boats").update(data).eq("id", ex_b.data[0]["id"]).execute()
                                updated += 1
                    except Exception as re_e:
                        print(f"raceinfo_time race_no={race_no} err: {re_e}")
                results.append({"venue": v, "item": "raceinfo_time", "status": "ok", "updated": updated})
            except Exception as e:
                results.append({"venue": v, "item": "raceinfo_time", "status": "error", "message": str(e)})

    return results


async def scrape_odds(date, venues):
    """boaters-boatrace.com から3連単・2連単・単勝オッズを取得してracesに保存。
    オッズは __NEXT_DATA__(Apollo state)の CrawledOdds に埋め込まれている(ログイン不要)。
    URL: https://boaters-boatrace.com/race/{slug}/{YYYY-MM-DD}/{N}R/odds
    """
    import json as _json
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    date_fmt = fmt(date)  # "2026-06-10"
    results = []
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=30,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    ) as client:
        for v in venues:
            vname, vc = resolve_venue(v)
            slug = BOATERS_SLUG_MAP.get(vname)
            if not slug:
                results.append({"venue": v, "item": "odds", "status": "error", "message": "unknown venue"})
                continue
            try:
                races = sb.table("races").select("id,race_no").eq("date", date_fmt).eq("venue", vname).execute().data or []
                if not races:
                    results.append({"venue": v, "item": "odds", "status": "error", "message": "no races"})
                    continue
                updated = 0
                for race in races:
                    race_id = race["id"]; race_no = race["race_no"]
                    url = f"https://boaters-boatrace.com/race/{slug}/{date_fmt}/{race_no}R/odds"
                    try:
                        resp = await client.get(url, timeout=25)
                        if resp.status_code != 200:
                            continue
                        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', resp.text, re.S)
                        if not m:
                            continue
                        data = _json.loads(m.group(1))
                        apollo = data.get("props", {}).get("pageProps", {}).get("initialApolloState", {})
                        odds_obj = None
                        for k, val in apollo.items():
                            if k.startswith("CrawledOdds:"):
                                odds_obj = val; break
                        if not odds_obj:
                            continue
                        o3 = {}; o2 = {}; ow = {}
                        for k, val in odds_obj.items():
                            if val is None or val == 0:
                                continue
                            if k.startswith("_3t") and len(k) == 6:
                                o3[f"{k[3]}-{k[4]}-{k[5]}"] = val
                            elif k.startswith("_2t") and len(k) == 5:
                                o2[f"{k[3]}-{k[4]}"] = val
                            elif re.match(r"^_t\d$", k):
                                ow[k[2]] = val
                        upd = {
                            "odds_3t": o3 or None,
                            "odds_2t": o2 or None,
                            "odds_win": ow or None,
                            "odds_updated_at": odds_obj.get("lastUpdatedAt"),
                        }
                        sb.table("races").update(upd).eq("id", race_id).execute()
                        if o3:
                            updated += 1
                    except Exception as re_e:
                        print(f"odds race_no={race_no} err: {re_e}")
                results.append({"venue": v, "item": "odds", "status": "ok", "updated": updated})
            except Exception as e:
                results.append({"venue": v, "item": "odds", "status": "error", "message": str(e)})
    return results


async def scrape_results(date, venues):
    """boaters-boatrace.com から確定着順を取得して race_winner_log に保存。
    asyncio.gather で全会場×全Rを並列取得（セマフォ20で同時接続数制御）。
    """
    import asyncio
    import json as _json
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    date_fmt = fmt(date)
    sem = asyncio.Semaphore(20)  # 同時接続数上限

    async def fetch_race(client, vname, slug, rno):
        url = f"https://boaters-boatrace.com/race/{slug}/{date_fmt}/{rno}R"
        async with sem:
            try:
                resp = await client.get(url, timeout=20)
                if resp.status_code != 200:
                    return []
                m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', resp.text, re.S)
                if not m:
                    return []
                apollo = _json.loads(m.group(1)).get("props", {}).get("pageProps", {}).get("initialApolloState", {})
                groups = {}
                for k, val in apollo.items():
                    if not k.startswith("CrawledRaceResultRacer:") or not isinstance(val, dict):
                        continue
                    ref = (val.get("result") or {}).get("__ref")
                    if not ref or not ref.startswith("CrawledRaceResult:"):
                        continue
                    rid = ref.split(":", 1)[1]
                    chaku = str(val.get("chakuPosition") or "")
                    if not chaku or chaku == "None":
                        continue
                    groups.setdefault(rid, {})[chaku] = (
                        val.get("startSinnyu"), val.get("boatNumber"))
                rows = []
                for rid, chmap in groups.items():
                    if len(rid) != 12 or "1" not in chmap:
                        continue
                    course1, lane1 = chmap["1"]
                    if course1 is None and lane1 is None:
                        continue
                    r_date = f"{rid[0:4]}-{rid[4:6]}-{rid[6:8]}"
                    r_vname = VENUE_NAME_MAP.get(rid[8:10], vname)
                    try:
                        r_no = int(rid[10:12])
                    except ValueError:
                        continue
                    result_all = []
                    for pos in range(1, 7):
                        if str(pos) in chmap:
                            c, l = chmap[str(pos)]
                            result_all.append({"pos": pos,
                                               "lane": int(l) if l is not None else None,
                                               "course": int(c) if c is not None else None})
                    place2_lane = int(chmap["2"][1]) if "2" in chmap and chmap["2"][1] is not None else None
                    place3_lane = int(chmap["3"][1]) if "3" in chmap and chmap["3"][1] is not None else None
                    trifecta_result = (f"{int(lane1)}-{place2_lane}-{place3_lane}"
                                       if lane1 is not None and place2_lane and place3_lane else None)
                    exacta_result = (f"{int(lane1)}-{place2_lane}"
                                     if lane1 is not None and place2_lane else None)
                    rows.append({
                        "race_key": rid, "venue": r_vname, "date": r_date, "race_no": r_no,
                        "winner_course": int(course1) if course1 is not None else None,
                        "winner_lane": int(lane1) if lane1 is not None else None,
                        "place2_lane": place2_lane, "place3_lane": place3_lane,
                        "trifecta_result": trifecta_result, "exacta_result": exacta_result,
                        "result_all": _json.dumps(result_all, ensure_ascii=False),
                    })
                return rows
            except Exception as e:
                print(f"results {vname} {rno}R err: {e}")
                return []

    results = []
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=25,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        limits=httpx.Limits(max_connections=30, max_keepalive_connections=20),
    ) as client:
        # 全会場 × 1〜12R のタスクを一斉生成
        tasks = []
        venue_map = {}
        for v in venues:
            vname, vc = resolve_venue(v)
            slug = BOATERS_SLUG_MAP.get(vname)
            if not slug:
                results.append({"venue": v, "item": "results", "status": "error", "message": "unknown venue"})
                continue
            for rno in range(1, 13):
                t = asyncio.create_task(fetch_race(client, vname, slug, rno))
                tasks.append((v, vname, t))

        # 全タスク完了待ち
        venue_saved: dict = {}
        for v, vname, t in tasks:
            rows = await t
            for row in rows:
                try:
                    sb.table("race_winner_log").upsert(row, on_conflict="race_key").execute()
                    venue_saved[v] = venue_saved.get(v, 0) + 1
                except Exception as ue:
                    err_s = str(ue)
                    if any(c in err_s for c in ["place2_lane","place3_lane","trifecta_result","exacta_result","result_all"]):
                        old_row = {k: val for k, val in row.items()
                                   if k in ("race_key","venue","date","race_no","winner_course","winner_lane")}
                        try:
                            sb.table("race_winner_log").upsert(old_row, on_conflict="race_key").execute()
                            venue_saved[v] = venue_saved.get(v, 0) + 1
                        except Exception:
                            pass
                    else:
                        print(f"upsert err {row.get('race_key')}: {ue}")

    seen_venues = set()
    for v in venues:
        vname, _ = resolve_venue(v)
        slug = BOATERS_SLUG_MAP.get(vname)
        if slug and v not in [r["venue"] for r in results]:
            results.append({"venue": v, "item": "results", "status": "ok",
                            "saved": venue_saved.get(v, 0)})
    return results


async def scrape_profile(date, venues):
    """boatfrontier.jp /racer/{toban} からコース別決まり手データを取得してDBに保存
    ・boatfrontierにログイン後、セマフォ5で並列取得
    """
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    date_fmt = fmt(date)
    results = []

    async with httpx.AsyncClient(follow_redirects=True, timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}) as client:
        # boatfrontierにログイン
        if not await bf_login(client):
            return [{"venue": v, "item": "profile", "status": "error", "message": "boatfrontier login failed"} for v in venues]

        for v in venues:
            vname, vc = resolve_venue(v)
            if not vc:
                results.append({"venue": v, "item": "profile", "status": "error", "message": "unknown venue"})
                continue
            try:
                # 全boatを取得
                races = sb.table("races").select("id,race_no").eq("date", date_fmt).eq("venue", vname).execute().data or []
                if not races:
                    results.append({"venue": v, "item": "profile", "status": "error", "message": "no races found"})
                    continue

                race_ids = [r["id"] for r in races]
                boats = sb.table("boats").select("id,lane,player_id").in_("race_id", race_ids).execute().data or []

                # player_id -> registration_no 一括取得
                player_ids = list(set(b["player_id"] for b in boats if b.get("player_id")))
                players = sb.table("players").select("id,registration_no").in_("id", player_ids).execute().data or []
                pid_to_reg = {p["id"]: p["registration_no"] for p in players}

                # ユニーク選手のみ並列取得（セマフォ5）
                unique_regs = list(set(
                    pid_to_reg[b["player_id"]]
                    for b in boats
                    if b.get("player_id") and pid_to_reg.get(b["player_id"])
                    and not pid_to_reg[b["player_id"]].startswith("tmp_")
                ))

                sem = asyncio.Semaphore(5)
                profile_cache = {}

                async def fetch_profile(reg_no: str):
                    async with sem:
                        try:
                            resp = await client.get(f"{BF_BASE}/racer/{reg_no}")
                            if resp.status_code == 200:
                                return reg_no, parse_course_stats(resp.text)
                        except:
                            pass
                        return reg_no, None

                tasks = [fetch_profile(r) for r in unique_regs]
                for reg_no, stats in await asyncio.gather(*tasks):
                    profile_cache[reg_no] = stats

                # DBに一括保存
                saved = 0
                for boat in boats:
                    player_id = boat.get("player_id")
                    boat_id = boat.get("id")
                    if not player_id or not boat_id:
                        continue
                    reg_no = pid_to_reg.get(player_id)
                    if not reg_no:
                        continue
                    stats = profile_cache.get(reg_no)
                    if not stats:
                        continue
                    # 全コース合計の決まり手数を計算
                    stats["nige_count"]        = sum(stats.get(f"c{c}_nige", 0) or 0 for c in range(1, 7))
                    stats["sashi_count"]       = sum(stats.get(f"c{c}_sashi", 0) or 0 for c in range(1, 7))
                    stats["makuri_count"]      = sum(stats.get(f"c{c}_makuri", 0) or 0 for c in range(1, 7))
                    stats["makurisashi_count"] = sum(stats.get(f"c{c}_makurizashi", 0) or 0 for c in range(1, 7))

                    # v58.7 発生率（gen_rate）：進入コースの決まり手に占める捲り＋捲差の比率
                    c0 = safe_int(boat.get("entry_course") or boat.get("lane") or 0, 0)
                    if 1 <= c0 <= 6:
                        mk = (stats.get(f"c{c0}_makuri", 0) or 0) + (stats.get(f"c{c0}_makurizashi", 0) or 0)
                        totc = sum(stats.get(f"c{c0}_{k}", 0) or 0
                                   for k in ("nige", "sashi", "makuri", "makurizashi"))
                        stats["gen_rate"] = round(mk / totc, 4) if totc > 0 else 0.0
                    else:
                        stats["gen_rate"] = 0.0
                    # 全コース捲り比率でフォールバック補完
                    if not stats.get("gen_rate"):
                        tot_all = (stats["nige_count"] + stats["sashi_count"]
                                   + stats["makuri_count"] + stats["makurisashi_count"])
                        if tot_all > 0:
                            stats["gen_rate"] = round(
                                (stats["makuri_count"] + stats["makurisashi_count"]) / tot_all, 4)

                    # v58.7 被弾率（hit_rate・1号評価専用）：1コース2連対率の裏 = 1 - place2/100
                    if c0 == 1:
                        p2 = stats.get("c1_place2_rate")
                        if p2 is not None:
                            stats["hit_rate"] = round(max(0.0, 1.0 - float(p2) / 100.0), 4)
                        else:
                            tot1 = sum(stats.get(f"c1_{k}", 0) or 0
                                       for k in ("nige", "sashi", "makuri", "makurizashi"))
                            nige1 = stats.get("c1_nige", 0) or 0
                            stats["hit_rate"] = round(1 - nige1 / tot1, 4) if tot1 > 0 else 0.0
                    else:
                        stats["hit_rate"] = 0.0

                    try:
                        sb.table("boats").update(stats).eq("id", boat_id).execute()
                    except Exception as upd_err:
                        err_str = str(upd_err)
                        # gen_rate/hit_rate列未追加の場合はそれらを除いて再試行（migrate前の互換）
                        if "gen_rate" in err_str or "hit_rate" in err_str or "PGRST204" in err_str:
                            fallback = {k: v for k, v in stats.items()
                                        if k not in ("gen_rate", "hit_rate")}
                            sb.table("boats").update(fallback).eq("id", boat_id).execute()
                        else:
                            raise
                    saved += 1

                results.append({"venue": v, "item": "profile", "status": "ok", "saved": saved})
            except Exception as e:
                results.append({"venue": v, "item": "profile", "status": "error", "message": str(e)})

    return results


class ScrapeRequest(BaseModel):
    date: Optional[str] = None
    venues: Optional[List[str]] = None
    items: Optional[List[str]] = None
    source: Optional[str] = None
    secret: str = ""

@app.get("/")
def root():
    return {"status":"ok","service":"boatrace-sakura-scraper","version":"6.2-v59.0"}

@app.post("/migrate")
async def migrate(req: dict = None):
    """boatsテーブルに決まり手カラムを追加するマイグレーション"""
    body = req or {}
    if body.get("secret") != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        import asyncpg
        # プーラーDSN（IPv4経由・Transaction mode port 6543）でIPv6直結失敗を回避
        conn = await asyncpg.connect(SUPABASE_POOLER_URL, ssl="require")
        sql = """
        ALTER TABLE boats
          ADD COLUMN IF NOT EXISTS c1_nige INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c1_sashi INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c1_makuri INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c1_makurizashi INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c2_nige INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c2_sashi INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c2_makuri INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c2_makurizashi INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c3_nige INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c3_sashi INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c3_makuri INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c3_makurizashi INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c4_nige INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c4_sashi INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c4_makuri INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c4_makurizashi INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c5_nige INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c5_sashi INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c5_makuri INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c5_makurizashi INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c6_nige INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c6_sashi INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c6_makuri INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c6_makurizashi INTEGER DEFAULT 0,
          ADD COLUMN IF NOT EXISTS c1_place2_rate FLOAT,
          ADD COLUMN IF NOT EXISTS c2_place2_rate FLOAT,
          ADD COLUMN IF NOT EXISTS c3_place2_rate FLOAT,
          ADD COLUMN IF NOT EXISTS c4_place2_rate FLOAT,
          ADD COLUMN IF NOT EXISTS c5_place2_rate FLOAT,
          ADD COLUMN IF NOT EXISTS c6_place2_rate FLOAT,
          ADD COLUMN IF NOT EXISTS gen_rate FLOAT DEFAULT 0,
          ADD COLUMN IF NOT EXISTS hit_rate FLOAT DEFAULT 0
        """
        await conn.execute(sql)
        # race_winner_log: 逃げ成立度較正(改正46/48)用の実着順テーブル
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS race_winner_log (
          race_key TEXT PRIMARY KEY,
          venue TEXT,
          date DATE,
          race_no INTEGER,
          winner_course INTEGER,
          winner_lane INTEGER,
          created_at TIMESTAMPTZ DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_race_winner_log_venue_date
          ON race_winner_log (venue, date DESC);
        """)
        await conn.close()
        return {"status": "ok", "message": "Migration completed (gen_rate/hit_rate added)"}
    except Exception as e:
        # DB直結・プーラー接続失敗時: Supabase Dashboardで実行するSQLを返す
        manual_sql = """
-- Supabase Dashboard > SQL Editor で以下を実行してください:
ALTER TABLE boats ADD COLUMN IF NOT EXISTS gen_rate FLOAT DEFAULT 0;
ALTER TABLE boats ADD COLUMN IF NOT EXISTS hit_rate FLOAT DEFAULT 0;
"""
        return {"status": "error", "message": str(e),
                "manual_migration_sql": manual_sql,
                "hint": "Supabase Dashboard > SQL Editor で上記SQLを実行してください"}


import json as _json

TELEBOAT_COOKIE_FILE = "/home/ubuntu/boatrace/teleboat_cookies.json"

class CookieRequest(BaseModel):
    secret: str
    cookies: str  # "name=value; name2=value2" 形式 または JSON形式

@app.post("/set_teleboat_cookies")
async def set_teleboat_cookies(req: CookieRequest):
    """boatrace.jpのセッションCookieを保存する。
    ブラウザでログイン後にDevToolsからコピーしたCookie文字列を受け取る。
    """
    if req.secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        # "name=value; name2=value2" 形式をパース
        cookies = {}
        for part in req.cookies.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                cookies[k.strip()] = v.strip()
        with open(TELEBOAT_COOKIE_FILE, "w") as f:
            _json.dump(cookies, f)
        return {"status": "ok", "cookie_count": len(cookies), "names": list(cookies.keys())}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/check_teleboat_cookies")
async def check_teleboat_cookies():
    """保存済みCookieの状態を確認"""
    import os
    if not os.path.exists(TELEBOAT_COOKIE_FILE):
        return {"status": "not_set", "message": "Cookieが未設定です"}
    try:
        with open(TELEBOAT_COOKIE_FILE) as f:
            cookies = _json.load(f)
        return {"status": "ok", "cookie_count": len(cookies), "names": list(cookies.keys())}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/scrape")
async def scrape(req: ScrapeRequest):
    if req.secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    date   = req.date or datetime.now().strftime("%Y%m%d")
    venues = req.venues or list(VENUE_CODE_MAP.keys())
    items  = ["motor"] if (req.source=="boatfrontier" and not req.items) else (req.items or ["entry","motor","exhibition"])
    all_results = []
    if "entry"      in items: all_results += await scrape_entry(date, venues)
    if "motor"      in items: all_results += await scrape_motor(date, venues)
    if "exhibition" in items: all_results += await scrape_exhibition(date, venues)
    if "profile"    in items: all_results += await scrape_profile(date, venues)
    if "raceinfo_time" in items: all_results += await scrape_raceinfo_time(date, venues)
    if "odds"       in items: all_results += await scrape_odds(date, venues)
    if "results"    in items: all_results += await scrape_results(date, venues)
    # motorまたはexhibitionの後に基準ST・優勢順位を自動計算
    if any(i in items for i in ["motor", "exhibition", "st_metrics"]):
        all_results += await calc_st_metrics(date, venues)
    s = sum(1 for r in all_results if r.get("status")=="ok")
    e = sum(1 for r in all_results if r.get("status")=="error")
    return {"date":date,"results":all_results,"summary":f"成功:{s} エラー:{e}"}

class EvaluateRequest(BaseModel):
    secret: str = ""
    from_date: str = ""  # YYYYMMDD or YYYY-MM-DD
    to_date: str = ""

class HistoryRequest(BaseModel):
    secret: str = ""
    from_date: str = ""   # YYYYMMDD
    to_date: str = ""     # YYYYMMDD
    venues: list = []

@app.post("/evaluate")
async def evaluate_predictions(req: EvaluateRequest):
    """予測 vs 実結果を突合して predictions.is_correct_trifecta/exacta を自動更新。
    race_winner_log の trifecta_result が predicted_trifecta の候補リストに含まれているか判定。
    """
    if req.secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    # 日付範囲パース
    def _norm(d: str) -> str:
        d = d.strip()
        if len(d) == 8 and d.isdigit():
            return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        return d

    from_d = _norm(req.from_date) if req.from_date else None
    to_d   = _norm(req.to_date)   if req.to_date   else None

    # predictions を取得（日付フィルタはrace経由で行うためまず全件取得）
    pq = sb.table("predictions").select(
        "id, race_id, predicted_trifecta, predicted_exacta, is_correct_trifecta, is_correct_exacta, detail"
    )
    preds = pq.execute().data or []

    # race_winner_log を取得
    wq = sb.table("race_winner_log").select(
        "race_key, venue, date, race_no, trifecta_result, exacta_result, winner_lane"
    )
    if from_d:
        wq = wq.gte("date", from_d)
    if to_d:
        wq = wq.lte("date", to_d)
    winner_rows = wq.execute().data or []

    # races テーブルで race_id → (date, venue, race_no) のマッピング
    race_ids = list({p["race_id"] for p in preds if p.get("race_id")})
    races_data = {}
    if race_ids:
        chunk = 200
        for i in range(0, len(race_ids), chunk):
            rsp = sb.table("races").select("id, date, venue, race_no").in_("id", race_ids[i:i+chunk]).execute()
            for r in (rsp.data or []):
                races_data[r["id"]] = r

    # winner_log を (date, venue, race_no) キーで索引
    winner_map = {}
    for w in winner_rows:
        key = (w["date"], w["venue"], w["race_no"])
        winner_map[key] = w

    updated = 0
    skipped = 0
    for pred in preds:
        race = races_data.get(pred.get("race_id"))
        if not race:
            skipped += 1
            continue
        # 日付フィルタ（races経由）
        if from_d and race.get("date","") < from_d:
            skipped += 1
            continue
        if to_d and race.get("date","") > to_d:
            skipped += 1
            continue

        key = (race["date"], race["venue"], race["race_no"])
        winner = winner_map.get(key)
        if not winner:
            skipped += 1
            continue

        actual_tri = winner.get("trifecta_result")
        actual_ex  = winner.get("exacta_result")
        if not actual_tri:
            skipped += 1
            continue

        # predicted_trifecta はカンマ区切り候補リスト "1-2-3,1-3-2,..."
        # detail JSON内の honsen_adopted も確認
        pred_tri_str = pred.get("predicted_trifecta") or ""
        pred_ex_str  = pred.get("predicted_exacta") or ""

        # detail から honsen_adopted も取り出して補完
        detail = pred.get("detail") or {}
        if isinstance(detail, str):
            try:
                import json as _j
                detail = _j.loads(detail)
            except Exception:
                detail = {}
        honsen_adopted = detail.get("honsen_adopted", []) if isinstance(detail, dict) else []

        all_tri_combos = set(filter(None, pred_tri_str.split(","))) | set(honsen_adopted)
        all_ex_combos  = set(filter(None, pred_ex_str.split(",")))

        is_tri = actual_tri in all_tri_combos if all_tri_combos else None
        is_ex  = actual_ex  in all_ex_combos  if all_ex_combos  else None

        # payout_grade を detail から取得
        payout_grade = detail.get("payout_grade") if isinstance(detail, dict) else None

        update_body: dict = {
            "is_correct_trifecta": is_tri,
            "actual_trifecta": actual_tri,
        }
        if is_ex is not None:
            update_body["is_correct_exacta"] = is_ex
        if payout_grade:
            update_body["payout_grade"] = payout_grade

        try:
            sb.table("predictions").update(update_body).eq("id", pred["id"]).execute()
            updated += 1
        except Exception as ue:
            print(f"evaluate update {pred['id']} err: {ue}")

    return {
        "status": "ok",
        "updated": updated,
        "skipped": skipped,
        "total": len(preds),
    }


@app.post("/scrape_history")
async def scrape_history(req: HistoryRequest):
    """過去日付の確定着順を並列一括取得。from_date〜to_date の全日付を asyncio.gather で並走。"""
    if req.secret != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    import asyncio
    from datetime import date as _date, timedelta

    def _parse(d: str) -> _date:
        d = d.strip()
        if len(d) == 8 and d.isdigit():
            return _date(int(d[:4]), int(d[4:6]), int(d[6:8]))
        return _date.fromisoformat(d)

    today = _date.today()
    from_d = _parse(req.from_date) if req.from_date else (today - timedelta(days=7))
    to_d   = _parse(req.to_date)   if req.to_date   else (today - timedelta(days=1))
    venues = req.venues or [str(i).zfill(2) for i in range(1, 25)]

    # 最大14日に制限（並列でも負荷制御）
    if (to_d - from_d).days > 14:
        to_d = from_d + timedelta(days=14)

    dates = []
    cur = from_d
    while cur <= to_d:
        dates.append(cur.strftime("%Y%m%d"))
        cur += timedelta(days=1)

    # 日付ごとに並列実行（最大3日同時）
    date_sem = asyncio.Semaphore(3)

    async def scrape_day(date_str):
        async with date_sem:
            return await scrape_results(date_str, venues)

    tasks = [scrape_day(d) for d in dates]
    day_results = await asyncio.gather(*tasks)

    all_results = [r for day in day_results for r in day]
    s = sum(1 for r in all_results if r.get("status") == "ok")
    e = sum(1 for r in all_results if r.get("status") == "error")
    total_saved = sum(r.get("saved", 0) for r in all_results)
    return {
        "from_date": from_d.isoformat(),
        "to_date": to_d.isoformat(),
        "days": len(dates),
        "summary": f"成功:{s} エラー:{e} 保存:{total_saved}件",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
