#!/usr/bin/env python3
"""6/6 3会場の boats 特徴量カバレッジ確認(SELECTのみ・読取専用)。"""
import sys
from supabase import create_client

URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ."
    "vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
)
COLS = ["national_win_rate", "local5y_win_rate", "general1y_win_rate",
        "national_place2_rate", "avg_st", "motor_place2_rate", "weight"]


def main():
    sb = create_client(URL, KEY)
    date = "2026-06-06"
    for v in ["蒲郡", "常滑", "三国"]:
        races = sb.table("races").select("id").eq("date", date).eq("venue", v).execute().data
        rids = [r["id"] for r in races]
        rows = []
        for i in range(0, len(rids), 100):
            rows += (sb.table("boats").select(",".join(COLS))
                     .in_("race_id", rids[i:i + 100]).execute().data)
        n = len(rows)
        parts = []
        for c in COLS:
            nn = sum(1 for r in rows if r.get(c) is not None)
            parts.append(f"{c}={nn}/{n}")
        print(f"{v}: " + "  ".join(parts))


if __name__ == "__main__":
    main()
