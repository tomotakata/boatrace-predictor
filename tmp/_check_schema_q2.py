from supabase import create_client
URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ.vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
sb = create_client(URL, KEY)
# races 1行で列確認
rc = sb.table("races").select("*").limit(1).execute().data[0]
print("races cols:", sorted(rc.keys()))
print("races sample race_key/venue_code:", rc.get("race_key"), rc.get("venue_code"))
# race_winner_log の race_key サンプル(venue別)
rwl = sb.table("race_winner_log").select("race_key,date,venue,race_no").limit(5).execute().data
for r in rwl:
    print("rwl:", r["date"], r["venue"], "R"+str(r["race_no"]), "race_key=", r["race_key"])
