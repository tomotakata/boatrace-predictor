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
    """Scrape race list for a given date."""
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
    """Scrape race entry data (出走表・選手データ) for a venue and date."""
    sb = get_supabase()
    code = VENUE_CODE_MAP.get(venue)
    if not code:
        raise ValueError(f"Unknown venue: {venue}")

    date_str = target_date.replace("-", "")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get list of races for this venue
        races_resp = sb.table("races").select("*").eq("date", target_date).eq("venue", venue).execute()
        races = races_resp.data or []

        if not races:
            # Create races first
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
