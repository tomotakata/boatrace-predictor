from supabase import create_client
from collections import defaultdict
URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ.vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
sb = create_client(URL, KEY)
VENUE_CODE_MAP = {
    "桐生":"01","戸田":"02","江戸川":"03","平和島":"04","多摩川":"05","浜名湖":"06",
    "蒲郡":"07","常滑":"08","津":"09","三国":"10","びわこ":"12","住之江":"11",
    "尼崎":"13","鳴門":"14","丸亀":"15","児島":"16","宮島":"17","徳山":"18",
    "下関":"19","若松":"20","芦屋":"21","福岡":"22","唐津":"23","大村":"24",
}
PAGE = 1000
rows = []
s = 0
while True:
    b = sb.table("races").select("id,date,venue,race_no,race_key,venue_code").order("date").range(s, s + PAGE - 1).execute().data or []
    rows.extend(b)
    if len(b) < PAGE:
        break
    s += PAGE
print("races total:", len(rows))
# venue名がマップに無いものを検出
unknown_venues = sorted(set(r["venue"] for r in rows if r["venue"] not in VENUE_CODE_MAP))
print("マップに無いvenue:", unknown_venues)
# 計算race_keyの重複(date+venue+race_no 一意性)
calc = defaultdict(list)
none_rno = 0
for r in rows:
    v = r["venue"]; rno = r["race_no"]
    if v not in VENUE_CODE_MAP or rno is None:
        if rno is None:
            none_rno += 1
        continue
    vc = VENUE_CODE_MAP[v]
    rk = f"{r['date'].replace('-','')}{vc}{str(rno).zfill(2)}"
    calc[rk].append(r["id"])
dups = {k: v for k, v in calc.items() if len(v) > 1}
print("race_no=None 行:", none_rno)
print("計算race_keyのユニーク数:", len(calc))
print("重複race_keyの数:", len(dups))
for k, v in list(dups.items())[:10]:
    print("   dup", k, v)
