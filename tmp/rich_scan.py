#!/usr/bin/env python3
"""DB全体でリッチ列が1件でも埋まっている行があるか調査する。"""
from supabase import create_client

URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ."
    "vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
)
sb = create_client(URL, KEY)

# count rows where each rich col is not null
for col in ["today_st", "course1y_st", "motor_dashfoot", "c1_win_rate", "c2_win_rate",
            "c1_place2_rate", "entry_course", "motor_eval", "local5y_win_rate"]:
    try:
        r = sb.table("boats").select("id", count="exact").not_.is_(col, "null").limit(1).execute()
        print(f"{col:20s} not-null count = {r.count}")
    except Exception as e:
        print(f"{col:20s} ERROR {e}")

# total boats
rt = sb.table("boats").select("id", count="exact").limit(1).execute()
print("total boats =", rt.count)

# find ANY boat with today_st not null - get its race/date
r = sb.table("boats").select("id,race_id,today_st,motor_dashfoot,c1_win_rate,entry_course").not_.is_("today_st", "null").limit(5).execute()
print("\nsample today_st not-null rows:", r.data)
r2 = sb.table("boats").select("id,race_id,entry_course").not_.is_("entry_course", "null").limit(5).execute()
print("sample entry_course not-null rows:", r2.data)
