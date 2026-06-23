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

# 経験マップ
rwl = fa("race_winner_log", "venue,race_key,date,race_no")
vmap = {}
cnt = defaultdict(lambda: defaultdict(int))
rwl_keys = set()
for r in rwl:
    rk = r.get("race_key")
    if rk and len(rk) == 12:
        cnt[r["venue"]][rk[8:10]] += 1
        rwl_keys.add(rk)
for v, c in cnt.items():
    vmap[v] = max(c, key=c.get)

races = fa("races", "id,date,venue,race_no")
# 各 races 行の計算race_key が race_winner_log に存在するか(join成立)
match = 0
nomatch = 0
nomatch_samples = []
for r in races:
    vc = vmap.get(r["venue"])
    if vc is None or r["race_no"] is None:
        continue
    rk = f"{r['date'].replace('-', '')}{vc}{str(r['race_no']).zfill(2)}"
    if rk in rwl_keys:
        match += 1
    else:
        nomatch += 1
        if len(nomatch_samples) < 8:
            nomatch_samples.append((r["date"], r["venue"], r["race_no"], rk))
print(f"races総数={len(races)}")
print(f"計算race_keyが race_winner_log に存在(join成立)= {match}")
print(f"join不成立 = {nomatch}")
print("join不成立サンプル(=結果未取得の幻レース等):")
for s in nomatch_samples:
    print("   ", s)
