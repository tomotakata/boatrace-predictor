from supabase import create_client
URL="https://zotskrheypxrfsiyvwtl.supabase.co"
KEY=open("tmp/_key.txt").read().strip()
sb=create_client(URL,KEY)
rows=[]; start=0
while True:
    r=sb.table("races").select("race_key,venue_code,venue,date,race_no").range(start,start+999).execute().data
    if not r: break
    rows+=r
    if len(r)<1000: break
    start+=1000
tot=len(rows)
rk_null=sum(1 for x in rows if not x.get("race_key"))
vc_null=sum(1 for x in rows if not x.get("venue_code"))
print(f"races総数={tot}  race_key未設定={rk_null}  venue_code未設定={vc_null}")
from collections import Counter
c=Counter((x["venue"],x["venue_code"]) for x in rows if x["venue"] in ("びわこ","住之江"))
for k,v in sorted(c.items()): print("  ",k,v)
# race_key duplicate check
rk=[x["race_key"] for x in rows if x.get("race_key")]
print("race_key重複数=",len(rk)-len(set(rk)))
