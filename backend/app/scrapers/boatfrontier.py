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
    """Login to boatfrontier.jp and return True on success."""
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

        # ログイン成功: logout linkあり or /loginページから離脱
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
    """Scrape motor stats from boatfrontier.jp for a venue and date."""
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
