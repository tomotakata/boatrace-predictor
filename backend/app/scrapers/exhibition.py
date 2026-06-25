"""
Exhibition time scraper from boatrace.jp and boaters.com
Scrapes: 展示タイム・ST・1周・回り足・天候情報
"""
import re
import httpx
from bs4 import BeautifulSoup
from backend.app.config import get_supabase

WIND_DIRECTION_MAP = {
    1: "北", 2: "北北東", 3: "北東", 4: "東北東",
    5: "東", 6: "東南東", 7: "南東", 8: "南南東",
    9: "南", 10: "南南西", 11: "南西", 12: "西南西",
    13: "西", 14: "西北西", 15: "北西", 16: "北北西",
    17: "無風",
}

BOATRACE_BASE_URL = "https://www.boatrace.jp"

VENUE_CODE_MAP = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04",
    "多摩川": "05", "浜名湖": "06", "蒲郡": "07", "常滑": "08",
    "津": "09", "三国": "10", "びわこ": "11", "住之江": "12",
    "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16",
    "宮島": "17", "徳山": "18", "下関": "19", "若松": "20",
    "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24"
}


def _parse_weather(soup: BeautifulSoup) -> dict:
    """Extract weather info from the 水面気象情報 section."""
    weather_data: dict = {}
    weather_div = soup.select_one(".weather1")
    if not weather_div:
        return weather_data

    # 天候 (Weather condition) — text in is-weather unit's LabelTitle
    weather_el = weather_div.select_one(".weather1_bodyUnit.is-weather .weather1_bodyUnitLabelTitle")
    if weather_el:
        weather_data["weather"] = weather_el.text.strip()

    # 気温 (Air temperature) — in is-direction unit's LabelData
    temp_el = weather_div.select_one(".weather1_bodyUnit.is-direction .weather1_bodyUnitLabelData")
    if temp_el:
        try:
            weather_data["temperature"] = float(temp_el.text.strip().replace("℃", ""))
        except ValueError:
            pass

    # 風速 (Wind speed) — in is-wind unit's LabelData
    wind_el = weather_div.select_one(".weather1_bodyUnit.is-wind .weather1_bodyUnitLabelData")
    if wind_el:
        try:
            weather_data["wind_speed"] = int(wind_el.text.strip().replace("m", ""))
        except ValueError:
            pass

    # 風向 (Wind direction) — extracted from class name on the image element
    wind_dir_img = weather_div.select_one(".weather1_bodyUnit.is-windDirection .weather1_bodyUnitImage")
    if wind_dir_img:
        for cls in wind_dir_img.get("class", []):
            m = re.match(r"is-wind(\d+)", cls)
            if m:
                idx = int(m.group(1))
                weather_data["wind_direction"] = WIND_DIRECTION_MAP.get(idx, "")
                break

    # 波高 (Wave height) — in is-wave unit's LabelData
    wave_el = weather_div.select_one(".weather1_bodyUnit.is-wave .weather1_bodyUnitLabelData")
    if wave_el:
        try:
            weather_data["wave_height"] = int(wave_el.text.strip().replace("cm", ""))
        except ValueError:
            pass

    return weather_data


async def scrape_exhibition_data(venue: str, target_date: str) -> None:
    """Scrape exhibition times and weather info from boatrace.jp."""
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

                # --- 天候情報を抽出してracesテーブルに保存 ---
                weather_data = _parse_weather(soup)
                if weather_data:
                    sb.table("races").update(weather_data).eq("id", race_id).execute()

                # --- 展示タイム ---
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
