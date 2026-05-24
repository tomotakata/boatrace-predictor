"""
Exhibition time scraper from boatrace.jp and boaters.com
Scrapes: 展示タイム・ST・1周・回り足
"""
import httpx
from bs4 import BeautifulSoup
from backend.app.config import get_supabase

BOATRACE_BASE_URL = "https://www.boatrace.jp"

VENUE_CODE_MAP = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04",
    "多摩川": "05", "浜名湖": "06", "蒲郡": "07", "常滑": "08",
    "津": "09", "三国": "10", "びわこ": "11", "住之江": "12",
    "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16",
    "宮島": "17", "徳山": "18", "下関": "19", "若松": "20",
    "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24"
}


async def scrape_exhibition_data(venue: str, target_date: str) -> None:
    """Scrape exhibition times from boatrace.jp."""
    sb = get_supabase()
    code = VENUE_CODE_MAP.get(venue)
    if not code:
        raise ValueError(f"Unknown venue: {venue}")

    date_str = target_date.replace("-", "")

    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    ) as client:
        races_resp = sb.table("races").select("*").eq("date", target_date).eq("venue", venue).execute()
        races = races_resp.data or []

        for race in races:
            race_id = race.get("id")
            race_no = race.get("race_no")
            if not race_id:
                continue

            try:
                # boatrace.jp exhibition times
                url = f"{BOATRACE_BASE_URL}/owpc/pc/race/beforeinfo?hd={date_str}&jcd={code}&rno={race_no}"
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                rows = soup.select(".is-fs12.is-lineH2 tbody tr, .table1 tbody tr")

                for row in rows:
                    cells = row.select("td")
                    if len(cells) < 3:
                        continue

                    try:
                        lane = int(cells[0].text.strip())
                    except (ValueError, IndexError):
                        continue

                    try:
                        exhibition_time = float(cells[1].text.strip())
                    except (ValueError, IndexError):
                        exhibition_time = None

                    try:
                        exhibition_st = float(cells[2].text.strip())
                    except (ValueError, IndexError):
                        exhibition_st = None

                    existing_boat = sb.table("boats").select("id").eq("race_id", race_id).eq("lane", lane).execute()
                    if existing_boat.data:
                        update_data = {}
                        if exhibition_time is not None:
                            update_data["exhibition_time"] = exhibition_time
                        if exhibition_st is not None:
                            update_data["exhibition_st"] = exhibition_st
                        if update_data:
                            sb.table("boats").update(update_data).eq("id", existing_boat.data[0]["id"]).execute()

            except Exception:
                continue
