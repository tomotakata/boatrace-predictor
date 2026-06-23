from supabase import create_client
from collections import defaultdict
URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ.vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
sb = create_client(URL, KEY)
PAGE = 1000
# race_winner_log から venue -> code(race_key[8:10]) を経験的に導出
rows = []
s = 0
while True:
    b = sb.table("race_winner_log").select("venue,race_no,race_key").range(s, s + PAGE - 1).execute().data or []
    rows.extend(b)
    if len(b) < PAGE:
        break
    s += PAGE
vmap = defaultdict(lambda: defaultdict(int))
bad = 0
for r in rows:
    rk = r.get("race_key")
    v = r.get("venue")
    rno = r.get("race_no")
    if not rk or len(rk) != 12:
        bad += 1
        continue
    code = rk[8:10]
    # 末尾2桁が race_no と一致するか検証
    if rno is not None and rk[10:12] != str(rno).zfill(2):
        bad += 1
    vmap[v][code] += 1
print("race_winner_log rows:", len(rows), "bad/len_mismatch:", bad)
print("venue -> code 経験マップ:")
empirical = {}
for v in sorted(vmap):
    codes = dict(vmap[v])
    chosen = max(codes, key=codes.get)
    empirical[v] = chosen
    flag = "" if len(codes) == 1 else f"  <-- 複数コード! {codes}"
    print(f"  {v:6s}: {chosen} (n={codes[chosen]}){flag}")
print("\n会場数:", len(empirical))
# server.py マップとの差分
SERVER = {"桐生":"01","戸田":"02","江戸川":"03","平和島":"04","多摩川":"05","浜名湖":"06","蒲郡":"07","常滑":"08","津":"09","三国":"10","びわこ":"12","住之江":"11","尼崎":"13","鳴門":"14","丸亀":"15","児島":"16","宮島":"17","徳山":"18","下関":"19","若松":"20","芦屋":"21","福岡":"22","唐津":"23","大村":"24"}
print("\nserver.py マップと不一致の会場:")
for v, c in empirical.items():
    if SERVER.get(v) != c:
        print(f"  {v}: 実データ={c} server.py={SERVER.get(v)}")
