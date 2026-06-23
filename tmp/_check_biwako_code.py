from supabase import create_client
URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmEiLCJyZWYiOiJ6b3Rza3JoZXlweHJmc2l5dnd0bCJ9".replace("eyJpc3MiOiJzdXBhYmEiLCJyZWYiOiJ6b3Rza3JoZXlweHJmc2l5dnd0bCJ9","eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ.vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o")
sb = create_client(URL, KEY)
for v in ["びわこ", "住之江"]:
    rwl = sb.table("race_winner_log").select("date,venue,race_no,race_key").eq("venue", v).limit(3).execute().data or []
    print(f"--- race_winner_log {v} ---")
    for r in rwl:
        print("  ", r["date"], r["venue"], "R"+str(r["race_no"]), "race_key=", r["race_key"])
    rc = sb.table("races").select("date,venue,race_no,race_key,venue_code").eq("venue", v).limit(3).execute().data or []
    print(f"--- races {v} ---")
    for r in rc:
        print("  ", r["date"], r["venue"], "R"+str(r["race_no"]), "race_key=", r["race_key"], "venue_code=", r["venue_code"])
