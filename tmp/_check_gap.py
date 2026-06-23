from supabase import create_client
from collections import defaultdict
URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ.vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
sb = create_client(URL, KEY)
PAGE = 1000


def fa(t, c):
    out = []
    s = 0
    while True:
        b = sb.table(t).select(c).range(s, s + PAGE - 1).execute().data or []
        out.extend(b)
        if len(b) < PAGE:
            break
        s += PAGE
    return out

rwl = fa("race_winner_log", "venue,date,race_no")
races = fa("races", "date,venue,race_no,status")
rwl_dv = set((r["date"], r["venue"]) for r in rwl)
races_dv = set((r["date"], r["venue"]) for r in races)
print("race_winner_log 行数:", len(rwl), " distinct(date,venue):", len(rwl_dv))
print("races 行数:", len(races), " distinct(date,venue):", len(races_dv))
# 桐生 05-05 が rwl にあるか
k = ("2026-05-05", "桐生")
print("rwl に 桐生2026-05-05:", k in rwl_dv)
print("races に 桐生2026-05-05:", k in races_dv)
# races にあって rwl に無い (date,venue)
only_races = sorted(races_dv - rwl_dv)
print("\nraces にあって rwl に無い (date,venue):", len(only_races))
# それらのstatus内訳
st = defaultdict(int)
races_by_dv = defaultdict(list)
for r in races:
    races_by_dv[(r["date"], r["venue"])].append(r.get("status"))
for dv in only_races:
    for s in races_by_dv[dv]:
        st[s] += 1
print("  status内訳(行ベース):", dict(st))
for dv in only_races[:15]:
    print("   ", dv, "status例=", races_by_dv[dv][0], "件数=", len(races_by_dv[dv]))
