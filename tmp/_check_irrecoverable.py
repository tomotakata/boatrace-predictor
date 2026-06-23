import httpx
from bs4 import BeautifulSoup
from supabase import create_client
URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ.vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
sb = create_client(URL, KEY)
VC = {"芦屋": "21", "尼崎": "13"}
for d, v, hd in [("2026-06-08", "芦屋", "20260608"), ("2026-06-11", "尼崎", "20260611")]:
    rows = sb.table("race_winner_log").select("race_no,trifecta_result,result_all").eq("date", d).eq("venue", v).order("race_no").execute().data or []
    bad = [r for r in rows if isinstance(r.get("result_all"), str)]
    for b in bad:
        rno = b["race_no"]
        url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?hd={hd}&jcd={VC[v]}&rno={rno}"
        r = httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        txt = r.text
        flags = [k for k in ["不成立", "中止", "返還", "選手変更", "欠場"] if k in txt]
        # 三連単払戻の有無
        has_3t = "3連単" in txt or "３連単" in txt
        print(f"{v} {d} R{rno}: 公式flags={flags} stored_result_all={b.get('result_all')[:80]}")
