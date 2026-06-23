import httpx
from bs4 import BeautifulSoup
from supabase import create_client
URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ.vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
sb = create_client(URL, KEY)

for d, v in [("2026-06-06", "下関"), ("2026-06-06", "平和島"), ("2026-06-08", "戸田")]:
    rwl = sb.table("race_winner_log").select("race_no,trifecta_result").eq("date", d).eq("venue", v).execute().data or []
    rc = sb.table("races").select("id,source_url,status,race_name,race_key").eq("date", d).eq("venue", v).execute().data or []
    print(f"{v} {d}: race_winner_log={len(rwl)}  races={len(rc)}")
    if rc:
        print("   sample race:", {k: rc[0].get(k) for k in ("id", "status", "race_name", "race_key", "source_url")})

for hd, jcd, name in [("20260606", "19", "下関"), ("20260606", "04", "平和島")]:
    url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?hd={hd}&jcd={jcd}&rno=1"
    r = httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    rows = BeautifulSoup(r.text, "html.parser").select("table tbody tr")
    print(f"official result {name} {hd}: tbody_tr={len(rows)} no_msg={'ありません' in r.text}")
