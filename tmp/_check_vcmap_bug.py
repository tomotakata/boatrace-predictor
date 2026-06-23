from supabase import create_client
from collections import Counter
URL="https://zotskrheypxrfsiyvwtl.supabase.co"
KEY=open("tmp/_key.txt").read().strip()
sb=create_client(URL,KEY)
rows=[]; start=0
while True:
    r=sb.table("race_winner_log").select("race_key,venue,date,race_no").range(start,start+999).execute().data
    if not r: break
    rows+=r
    if len(r)<1000: break
    start+=1000
print("rwl総数",len(rows))
# jcd = race_key chars [8:10] (date=8桁 YYYYMMDD)
def jcd_of(rk):
    return rk[8:10] if rk and len(rk)>=12 else None
c=Counter()
for x in rows:
    if x["venue"] in ("びわこ","住之江"):
        c[(x["venue"],jcd_of(x["race_key"]))]+=1
for k,v in sorted(c.items()): print("  rwl",k,v)
# どの venue がどの jcd を持つか全体
allc=Counter((x["venue"],jcd_of(x["race_key"])) for x in rows)
print("--- venue->jcd 全体(件数) ---")
for k,v in sorted(allc.items()): print("  ",k,v)
