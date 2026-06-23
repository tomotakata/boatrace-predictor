from supabase import create_client
URL="https://zotskrheypxrfsiyvwtl.supabase.co"
KEY=open("tmp/_key.txt").read().strip()
sb=create_client(URL,KEY)
for v in ("びわこ","住之江"):
    r=sb.table("race_winner_log").select("race_key,venue,date").eq("venue",v).order("date",desc=True).limit(3).execute().data
    print(v,"最新:",[(x["date"],x["race_key"][:10]) for x in r])
