#!/usr/bin/env python3
"""DOTレーティング step-1-1 — データ棚卸し(読み取り専用・非破壊)

races / boats / race_winner_log の在庫・完全性、そして最重要の
「出走表(boats=6) + 完全確定結果」が揃った学習可能サンプル数を
実数で算出する。Supabase は SELECT のみ。DB は一切更新しない。

JOIN 仕様: date + venue + race_no(=race_key 等価) で races×race_winner_log。

使い方:
  python scripts/dot/inventory.py
  python scripts/dot/inventory.py --json tmp/dot_inventory.json
"""
import os
import sys
import json
import argparse
from collections import defaultdict

try:
    from supabase import create_client
except Exception:
    print("supabase-py が必要です: pip install supabase", file=sys.stderr)
    raise

DEFAULT_URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
DEFAULT_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ."
    "vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
)
PAGE = 1000


def get_client():
    url = os.environ.get("SUPABASE_URL", DEFAULT_URL)
    key = os.environ.get("SUPABASE_KEY", DEFAULT_KEY)
    return create_client(url, key)


def fetch_all(sb, table, columns, *, order_col="id"):
    rows = []
    start = 0
    while True:
        resp = (
            sb.table(table).select(columns)
            .order(order_col).range(start, start + PAGE - 1).execute()
        )
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        start += PAGE
    return rows


def pct(n, d):
    return f"{(100.0 * n / d):.1f}%" if d else "n/a"


def result_is_complete(r):
    """完全確定結果か: 1〜3着が揃い、trifecta_result がある(不成立/返還除く)。"""
    if r.get("winner_lane") is None:
        return False
    if r.get("place2_lane") is None or r.get("place3_lane") is None:
        return False
    if not r.get("trifecta_result"):
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None, help="集計結果JSONの保存先")
    args = ap.parse_args()

    sb = get_client()
    out = {}

    # ---- races ----
    races = fetch_all(sb, "races", "id,date,venue,race_no,status")
    race_by_id = {r["id"]: r for r in races}
    race_dates = sorted({r["date"] for r in races if r.get("date")})
    race_venues = sorted({r["venue"] for r in races if r.get("venue")})

    # ---- boats (race_id ごとの艇数) ----
    boats = fetch_all(sb, "boats", "id,race_id,lane")
    boats_count = defaultdict(int)
    for b in boats:
        boats_count[b["race_id"]] += 1
    races_full = [rid for rid in race_by_id if boats_count.get(rid, 0) == 6]
    races_partial = [rid for rid in race_by_id if 0 < boats_count.get(rid, 0) < 6]
    races_zero = [rid for rid in race_by_id if boats_count.get(rid, 0) == 0]

    # ---- race_winner_log ----
    rwl = fetch_all(
        sb, "race_winner_log",
        "race_key,date,venue,race_no,winner_lane,place2_lane,place3_lane,trifecta_result",
        order_col="race_key",
    )
    total_rwl = len(rwl)
    tri_nonnull = sum(1 for r in rwl if r.get("trifecta_result"))
    place2_nonnull = sum(1 for r in rwl if r.get("place2_lane") is not None)
    place3_nonnull = sum(1 for r in rwl if r.get("place3_lane") is not None)
    complete_results = [r for r in rwl if result_is_complete(r)]
    rwl_dates = sorted({r["date"] for r in rwl if r.get("date")})

    # 完全結果を (date,venue,race_no) でインデックス
    complete_idx = {}
    for r in complete_results:
        key = (r.get("date"), r.get("venue"), r.get("race_no"))
        complete_idx[key] = r

    # ---- JOIN: 完成出走表(boats=6) × 完全確定結果 ----
    joinable = []
    for rid in races_full:
        r = race_by_id[rid]
        key = (r.get("date"), r.get("venue"), r.get("race_no"))
        if key in complete_idx:
            joinable.append((rid, key))

    # join 済みの会場×月分布
    by_venue_month = defaultdict(int)
    for rid, key in joinable:
        d, v, _rn = key
        by_venue_month[(v, d[:7])] += 1

    # ---- 出力 ----
    print("=" * 72)
    print("DOTレーティング step-1-1 データ棚卸し(読み取り専用)")
    print("=" * 72)

    print("\n■ テーブル在庫")
    print(f"  races            : {len(races)} 行 / {len(race_dates)} 日 / {len(race_venues)} 会場"
          f"  期間 {race_dates[0] if race_dates else '-'} 〜 {race_dates[-1] if race_dates else '-'}")
    print(f"  boats            : {len(boats)} 行")
    print(f"  race_winner_log  : {total_rwl} 行 / {len(rwl_dates)} 日"
          f"  期間 {rwl_dates[0] if rwl_dates else '-'} 〜 {rwl_dates[-1] if rwl_dates else '-'}")

    print("\n■ 出走表完全性(races に対する boats 充足)")
    print(f"  boats=6 (完成)   : {len(races_full)}  ({pct(len(races_full), len(races))})")
    print(f"  0<boats<6(中途)  : {len(races_partial)}")
    print(f"  boats=0 (幻/未取得): {len(races_zero)}")

    print("\n■ 確定結果完全性(race_winner_log)")
    print(f"  trifecta_result 非NULL : {tri_nonnull}  ({pct(tri_nonnull, total_rwl)})")
    print(f"  place2_lane 非NULL     : {place2_nonnull}  ({pct(place2_nonnull, total_rwl)})")
    print(f"  place3_lane 非NULL     : {place3_nonnull}  ({pct(place3_nonnull, total_rwl)})")
    print(f"  完全結果(1〜3着+三連単): {len(complete_results)}  ({pct(len(complete_results), total_rwl)})")
    print(f"  結果欠損(非完全)       : {total_rwl - len(complete_results)}  "
          f"({pct(total_rwl - len(complete_results), total_rwl)})")

    print("\n■ 【学習可能サンプル数】出走表(boats=6) × 完全確定結果 INNER JOIN")
    print(f"  学習可能レース数 : {len(joinable)} レース")
    print(f"  学習可能艇行数   : {len(joinable) * 6} 行 (=レース×6)")
    print(f"  ※律速: 完成出走表={len(races_full)} / 完全結果={len(complete_results)}")

    print("\n■ 学習可能レースの会場×月分布")
    for (v, m), n in sorted(by_venue_month.items(), key=lambda x: (x[0][1], -x[1])):
        print(f"  {m}  {v:6s} : {n}")
    month_tot = defaultdict(int)
    for (v, m), n in by_venue_month.items():
        month_tot[m] += n
    print("  --- 月計 ---")
    for m, n in sorted(month_tot.items()):
        print(f"  {m} : {n} レース")

    out = {
        "tables": {
            "races_rows": len(races), "races_days": len(race_dates),
            "races_venues": len(race_venues),
            "races_period": [race_dates[0] if race_dates else None,
                             race_dates[-1] if race_dates else None],
            "boats_rows": len(boats),
            "rwl_rows": total_rwl, "rwl_days": len(rwl_dates),
            "rwl_period": [rwl_dates[0] if rwl_dates else None,
                           rwl_dates[-1] if rwl_dates else None],
        },
        "entry_completeness": {
            "boats_6": len(races_full),
            "boats_partial": len(races_partial),
            "boats_0": len(races_zero),
        },
        "result_completeness": {
            "trifecta_nonnull": tri_nonnull,
            "place2_nonnull": place2_nonnull,
            "place3_nonnull": place3_nonnull,
            "complete": len(complete_results),
            "total": total_rwl,
        },
        "learnable": {
            "races": len(joinable),
            "boat_rows": len(joinable) * 6,
            "by_venue_month": {f"{m}|{v}": n for (v, m), n in by_venue_month.items()},
            "by_month": dict(month_tot),
        },
    }
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\nJSON 保存: {args.json}")


if __name__ == "__main__":
    main()
