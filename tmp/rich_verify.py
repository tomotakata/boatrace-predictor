#!/usr/bin/env python3
"""4-5月リッチ列バックフィル 第1段階検証ツール。

サブコマンド:
  probe   <date>                 : その日の会場別レース数を表示し、VPS疎通確認
  before  <date> <venue...>      : リッチ列の非NULL率(更新前スナップショット)
  scrape  <date> <venue...>      : VPS /scrape (items=motor) を逐次POST
  after   <date> <venue...>      : リッチ列の非NULL率(更新後スナップショット)
  regress <date> <venue...>      : 既存正常列(national_win_rate/avg_st等)の非NULL率
  sample  <date> <venue>         : 1レース分の値サンプル表示(妥当性確認)
"""
import sys, json, time
import httpx
from supabase import create_client
from collections import Counter, defaultdict

URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ."
    "vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
)
VPS = "http://153.121.51.74:8080"
SECRET = "boatrace-sakura-secret-2024"

RICH_COLS = [
    "today_st", "today_st_rank", "course1y_st", "course1y_st_rank",
    "motor_dashfoot", "motor_extfoot", "motor_eval", "entry_course",
    "c1_win_rate", "c2_win_rate", "c3_win_rate", "c4_win_rate", "c5_win_rate", "c6_win_rate",
    "c1_place2_rate", "c2_place2_rate", "c3_place2_rate", "c4_place2_rate", "c5_place2_rate", "c6_place2_rate",
    "c1_makuri", "c2_makuri", "c3_makuri", "c4_makuri", "c5_makuri", "c6_makuri",
    "local5y_win_rate", "local5y_place2_rate",
]
NORMAL_COLS = [
    "national_win_rate", "national_place2_rate",
    "local_win_rate", "local_place2_rate",
    "motor_no", "motor_place2_rate", "boat_no", "avg_st", "weight", "age", "f_count",
]


def sb_client():
    return create_client(URL, KEY)


def race_ids(sb, date, venues):
    rows = sb.table("races").select("id,venue,race_no").eq("date", date).in_("venue", venues).execute().data or []
    return rows


def fetch_boats(sb, rids):
    out = []
    CH = 100
    for i in range(0, len(rids), CH):
        chunk = rids[i:i + CH]
        cols = "id,race_id,lane," + ",".join(RICH_COLS + NORMAL_COLS)
        resp = sb.table("boats").select(cols).in_("race_id", chunk).execute()
        out.extend(resp.data or [])
    return out


def nonnull_report(boats, cols, label):
    n = len(boats)
    print(f"\n=== {label} (boats={n}) ===")
    if n == 0:
        print("  (no boats)")
        return
    for c in cols:
        nn = 0
        nz = 0
        for b in boats:
            v = b.get(c)
            if v is not None:
                nn += 1
                try:
                    if float(v) != 0.0:
                        nz += 1
                except (TypeError, ValueError):
                    if str(v).strip():
                        nz += 1
        print(f"  {c:24s} non-null={nn:4d}/{n} ({100*nn/n:5.1f}%)  non-zero={nz:4d} ({100*nz/n:5.1f}%)")


def cmd_probe(date):
    sb = sb_client()
    rows = sb.table("races").select("venue,race_no").eq("date", date).execute().data or []
    c = Counter(r["venue"] for r in rows)
    print(f"{date} races total={len(rows)}")
    for v, cnt in sorted(c.items(), key=lambda x: -x[1]):
        print(f"  {v}: {cnt}R")
    try:
        r = httpx.get(VPS + "/", timeout=15)
        print("VPS /:", r.status_code, r.text[:200])
    except Exception as e:
        print("VPS ERROR:", e)


def cmd_snapshot(date, venues, cols, label):
    sb = sb_client()
    rows = race_ids(sb, date, venues)
    print(f"target races: {len(rows)} venues={venues}")
    rids = [r["id"] for r in rows]
    boats = fetch_boats(sb, rids)
    nonnull_report(boats, cols, label)


def cmd_scrape(date, venues):
    date_str = date.replace("-", "")
    for v in venues:
        payload = {"date": date_str, "venues": [v], "items": ["motor"], "secret": SECRET}
        print(f"\nPOST /scrape motor {date} {v} ...", flush=True)
        t0 = time.time()
        try:
            r = httpx.post(VPS + "/scrape", json=payload, timeout=600)
            dt = time.time() - t0
            print(f"  status={r.status_code} elapsed={dt:.1f}s")
            try:
                body = r.json()
                print("  body:", json.dumps(body, ensure_ascii=False)[:500])
            except Exception:
                print("  text:", r.text[:500])
        except Exception as e:
            print(f"  ERROR: {e}")
        time.sleep(4)


def cmd_sample(date, venue):
    sb = sb_client()
    rows = race_ids(sb, date, [venue])
    rows = sorted(rows, key=lambda x: x["race_no"])[:1]
    if not rows:
        print("no race")
        return
    rid = rows[0]["id"]
    cols = "lane,entry_course,today_st,course1y_st,motor_dashfoot,motor_extfoot,motor_eval," \
           "c1_win_rate,c2_win_rate,c3_win_rate,c4_win_rate,c5_win_rate,c6_win_rate," \
           "national_win_rate,avg_st,motor_no,motor_place2_rate"
    boats = sb.table("boats").select(cols).eq("race_id", rid).order("lane").execute().data or []
    print(f"sample race {date} {venue} R{rows[0]['race_no']} (race_id={rid})")
    for b in boats:
        print(" ", json.dumps(b, ensure_ascii=False))


def main():
    cmd = sys.argv[1]
    if cmd == "probe":
        cmd_probe(sys.argv[2])
    elif cmd == "before":
        cmd_snapshot(sys.argv[2], sys.argv[3:], RICH_COLS, "BEFORE rich-cols")
    elif cmd == "after":
        cmd_snapshot(sys.argv[2], sys.argv[3:], RICH_COLS, "AFTER rich-cols")
    elif cmd == "regress":
        cmd_snapshot(sys.argv[2], sys.argv[3:], NORMAL_COLS, "REGRESS normal-cols")
    elif cmd == "scrape":
        cmd_scrape(sys.argv[2], sys.argv[3:])
    elif cmd == "sample":
        cmd_sample(sys.argv[2], sys.argv[3])
    else:
        print("unknown cmd", cmd)


if __name__ == "__main__":
    main()
