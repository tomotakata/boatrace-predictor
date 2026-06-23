from supabase import create_client
URL="https://zotskrheypxrfsiyvwtl.supabase.co"
KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ.vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
sb=create_client(URL,KEY)
import sys
date=sys.argv[1] if len(sys.argv)>1 else "2026-06-06"
venue=sys.argv[2] if len(sys.argv)>2 else "丸亀"
rows=sb.table("race_winner_log").select("race_key,race_no,trifecta_result,result_all,place2_lane,place3_lane").eq("date",date).eq("venue",venue).order("race_no").execute().data or []
print(f"{venue} {date}: {len(rows)} rows")
tri_ok=sum(1 for r in rows if r.get("trifecta_result"))
ra_list=sum(1 for r in rows if isinstance(r.get("result_all"),list))
ra_str=sum(1 for r in rows if isinstance(r.get("result_all"),str))
print(f"  trifecta_result 非NULL: {tri_ok}/{len(rows)}")
print(f"  result_all list型: {ra_list}  str型(壊れ): {ra_str}")
for r in rows[:3]:
    print("  R%s tri=%s ra_type=%s place2=%s place3=%s" % (r["race_no"], r.get("trifecta_result"), type(r.get("result_all")).__name__, r.get("place2_lane"), r.get("place3_lane")))
