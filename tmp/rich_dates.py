#!/usr/bin/env python3
"""リッチ列が埋まっているraceの日付分布を調べる。"""
from supabase import create_client
from collections import Counter

URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ."
    "vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
)
sb = create_client(URL, KEY)

def race_dates_for(col):
    rids = set()
    start = 0
    PAGE = 1000
    while True:
        r = sb.table("boats").select("race_id").not_.is_(col, "null").range(start, start+PAGE-1).execute()
        b = r.data or []
        for x in b:
            rids.add(x["race_id"])
        if len(b) < PAGE:
            break
        start += PAGE
    # map race_id -> date
    rids = list(rids)
    dates = Counter()
    CH = 200
    for i in range(0, len(rids), CH):
        chunk = rids[i:i+CH]
        rr = sb.table("races").select("id,date,venue").in_("id", chunk).execute().data or []
        for x in rr:
            dates[x["date"][:7]] += 1
    return len(rids), dates

for col in ["today_st", "c1_win_rate", "motor_dashfoot"]:
    nr, dist = race_dates_for(col)
    print(f"\n{col}: {nr} races with data; month dist=")
    for m, c in sorted(dist.items()):
        print(f"    {m}: {c} races")
