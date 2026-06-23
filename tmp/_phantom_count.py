from supabase import create_client
from collections import defaultdict
URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ.vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
sb = create_client(URL, KEY)
PAGE = 1000


def fetch_all(table, cols):
    out = []
    s = 0
    while True:
        b = sb.table(table).select(cols).order("date").range(s, s + PAGE - 1).execute().data or []
        out.extend(b)
        if len(b) < PAGE:
            break
        s += PAGE
    return out

races = fetch_all("races", "id,date,venue,status,race_key,venue_code")
ids = [r["id"] for r in races]
cnt = defaultdict(int)
for i in range(0, len(ids), 200):
    ch = ids[i:i + 200]
    s = 0
    while True:
        b = sb.table("boats").select("race_id").in_("race_id", ch).range(s, s + PAGE - 1).execute().data or []
        for x in b:
            cnt[x["race_id"]] += 1
        if len(b) < PAGE:
            break
        s += PAGE

zero = [r for r in races if cnt.get(r["id"], 0) == 0]
sched = sum(1 for r in zero if r.get("status") == "scheduled")
print(f"races total          : {len(races)}")
print(f"boats=0 races        : {len(zero)}")
print(f"  うち status=scheduled(幻レース): {sched}")
print(f"  うち その他status    : {len(zero) - sched}")
st = defaultdict(int)
for r in zero:
    st[r.get("status")] += 1
print("  boats=0 の status内訳:", dict(st))
