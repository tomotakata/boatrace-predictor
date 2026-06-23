#!/usr/bin/env python3
"""DOTレーティング step-1-1 — 初期相関分析(読み取り専用・非破壊)

学習可能 join 標本(出走表 boats=6 × 完全確定結果)に対して、
各艇特徴量と is_win(1着)/is_top3(3着内) の単変量相関(point-biserial
= 二値変数との Pearson)を算出する。枠別1着率/3着内率も出力。
Supabase は SELECT のみ。

使い方:
  python scripts/dot/eda_correlation.py
  python scripts/dot/eda_correlation.py --json tmp/dot_eda.json
"""
import os
import sys
import json
import argparse
from collections import defaultdict

import numpy as np

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

# レース前に確定する(=リークしない)数値特徴の候補
FEATURES = [
    "lane", "age", "weight", "f_count", "avg_st", "today_st", "exhibition_st",
    "standard_st", "course1y_st", "season_st", "start_timing",
    "national_win_rate", "national_place2_rate", "national_place3_rate",
    "local_win_rate", "local_place2_rate",
    "general1y_win_rate", "general1y_place2_rate", "general1y_tricast_rate",
    "local5y_win_rate", "local5y_place2_rate", "local5y_tricast_rate",
    "c1_win_rate", "c2_win_rate", "c3_win_rate", "c4_win_rate", "c5_win_rate", "c6_win_rate",
    "motor_place2_rate", "motor_ratio", "boat_ratio", "deashi", "nobashi",
    "gen_rate", "hit_rate",
    "exhibition_time", "exhibition_1lap", "exhibition_turning", "exhibition_straight",
    "lap1_time", "turn_time", "odds_win",
]


def get_client():
    url = os.environ.get("SUPABASE_URL", DEFAULT_URL)
    key = os.environ.get("SUPABASE_KEY", DEFAULT_KEY)
    return create_client(url, key)


def fetch_all(sb, table, columns, *, order_col="id"):
    rows, start = [], 0
    while True:
        resp = (sb.table(table).select(columns)
                .order(order_col).range(start, start + PAGE - 1).execute())
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        start += PAGE
    return rows


def to_float(v):
    try:
        if v is None:
            return np.nan
        return float(v)
    except (TypeError, ValueError):
        return np.nan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    sb = get_client()

    # races (boats=6 のみ join 対象)
    races = fetch_all(sb, "races", "id,date,venue,race_no")
    race_by_id = {r["id"]: r for r in races}

    # boats 全列
    bcols = "race_id,lane," + ",".join(FEATURES)
    boats = fetch_all(sb, "boats", bcols)
    boats_by_race = defaultdict(list)
    for b in boats:
        boats_by_race[b["race_id"]].append(b)

    # 完全結果を (date,venue,race_no) で索引
    rwl = fetch_all(
        sb, "race_winner_log",
        "date,venue,race_no,winner_lane,place2_lane,place3_lane,trifecta_result",
        order_col="race_key",
    )
    res_idx = {}
    for r in rwl:
        if not r.get("trifecta_result"):
            continue
        if r.get("place2_lane") is None or r.get("place3_lane") is None:
            continue
        res_idx[(r.get("date"), r.get("venue"), r.get("race_no"))] = r

    # join: boats=6 のレースのみ、結果と突合して艇行データセット構築
    samples = []  # dict per boat: features + is_win + is_top3
    used_races = 0
    for rid, blist in boats_by_race.items():
        if len(blist) != 6:
            continue
        r = race_by_id.get(rid)
        if not r:
            continue
        key = (r.get("date"), r.get("venue"), r.get("race_no"))
        res = res_idx.get(key)
        if not res:
            continue
        used_races += 1
        top3 = {res.get("winner_lane"), res.get("place2_lane"), res.get("place3_lane")}
        win_lane = res.get("winner_lane")
        for b in blist:
            row = {f: to_float(b.get(f)) for f in FEATURES}
            row["is_win"] = 1 if b.get("lane") == win_lane else 0
            row["is_top3"] = 1 if b.get("lane") in top3 else 0
            row["_lane"] = b.get("lane")
            samples.append(row)

    n_boats = len(samples)
    print("=" * 72)
    print("DOTレーティング step-1-1 初期相関分析(読み取り専用)")
    print("=" * 72)
    print(f"\n対象: {used_races} レース / {n_boats} 艇行")

    def corr(feat, target):
        xs, ys = [], []
        for s in samples:
            v = s[feat]
            if v is None or (isinstance(v, float) and np.isnan(v)):
                continue
            xs.append(v); ys.append(s[target])
        if len(xs) < 30:
            return None, len(xs)
        x = np.array(xs, dtype=float); y = np.array(ys, dtype=float)
        if x.std() == 0 or y.std() == 0:
            return 0.0, len(xs)
        return float(np.corrcoef(x, y)[0, 1]), len(xs)

    results = []
    for f in FEATURES:
        cw, nw = corr(f, "is_win")
        ct, nt = corr(f, "is_top3")
        results.append((f, cw, nw, ct, nt))

    # is_win 相関の絶対値でソート
    results.sort(key=lambda r: (abs(r[1]) if r[1] is not None else -1), reverse=True)

    print("\n■ 特徴量 × is_win / is_top3 相関(point-biserial, |is_win|降順)")
    print(f"  {'feature':24s} {'N':>5s} {'corr_win':>9s} {'corr_top3':>9s}")
    for f, cw, nw, ct, nt in results:
        cws = f"{cw:+.3f}" if cw is not None else "  n/a"
        cts = f"{ct:+.3f}" if ct is not None else "  n/a"
        print(f"  {f:24s} {nw:>5d} {cws:>9s} {cts:>9s}")

    # 枠別1着率/3着内率
    lane_win = defaultdict(lambda: [0, 0])   # lane -> [win, total]
    lane_top3 = defaultdict(lambda: [0, 0])
    for s in samples:
        ln = s["_lane"]
        if ln is None:
            continue
        lane_win[ln][0] += s["is_win"]; lane_win[ln][1] += 1
        lane_top3[ln][0] += s["is_top3"]; lane_top3[ln][1] += 1

    print("\n■ 枠別 1着率 / 3着内率")
    print(f"  {'lane':>4s} {'N':>5s} {'win_rate':>9s} {'top3_rate':>9s}")
    lane_stats = {}
    for ln in sorted(k for k in lane_win if k is not None):
        w, tw = lane_win[ln]
        t3, t3t = lane_top3[ln]
        wr = w / tw if tw else 0
        t3r = t3 / t3t if t3t else 0
        lane_stats[ln] = {"n": tw, "win_rate": wr, "top3_rate": t3r}
        print(f"  {ln:>4d} {tw:>5d} {wr*100:>8.1f}% {t3r*100:>8.1f}%")

    if args.json:
        out = {
            "races": used_races, "boat_rows": n_boats,
            "correlations": [
                {"feature": f, "n": nw, "corr_win": cw, "corr_top3": ct}
                for f, cw, nw, ct, nt in results
            ],
            "lane_stats": lane_stats,
        }
        with open(args.json, "w", encoding="utf-8") as fp:
            json.dump(out, fp, ensure_ascii=False, indent=2)
        print(f"\nJSON 保存: {args.json}")


if __name__ == "__main__":
    main()
