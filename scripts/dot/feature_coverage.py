#!/usr/bin/env python3
"""DOTレーティング 特徴量改善 step-A — 追加候補列のカバレッジ計測(読み取り専用)

本命LightGBM(train_lightgbm.py)へ追加検討する『DB実在だが未使用の列』について、
学習可能サンプル(boats=6 × 完全確定結果)に対する非欠損率(カバレッジ)を
月別に算出する。カバレッジ閾値で採用候補を絞るための事前計測。

対象列:
  - players.rank(級別 A1/A2/B1/B2) … boats.player_id 経由でJOIN
  - boats 既存だが未使用: boat_place2_rate, c{n}_place2_rate, c{n}_tricast_rate,
    c{n}_sashi/makuri/makurizashi, local5y_sashi/makuri/makurizashi, local5y_races,
    general1y_sashi/makuri/makurizashi, general1y_races,
    escape1y_place2_rate, escape1y_tricast_rate,
    today_st_rank, course1y_st_rank,
    motor_dashfoot, motor_extfoot, motor_eval(文字列)
  - races 気象: weather, temperature, water_temperature, wind_speed,
    wind_direction(文字列), wave_height

本番 Supabase は SELECT のみ。DB は一切書き込まない。

使い方:
  python3 scripts/dot/feature_coverage.py
  python3 scripts/dot/feature_coverage.py --json tmp/dot_feature_coverage.json
"""
import os
import sys
import json
import argparse
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train_baseline as tb  # noqa: E402

# boats 側の追加候補(実スキーマ準拠。数値想定。motor_eval/motor_rank_letterのみ文字列)
BOAT_CANDIDATE_NUM = [
    "c1_place2_rate", "c2_place2_rate", "c3_place2_rate",
    "c4_place2_rate", "c5_place2_rate", "c6_place2_rate",
    "c1_tricast_rate", "c2_tricast_rate", "c3_tricast_rate",
    "c4_tricast_rate", "c5_tricast_rate", "c6_tricast_rate",
    "c1_races", "c2_races", "c3_races", "c4_races", "c5_races", "c6_races",
    "c1_nige", "c1_sashi", "c1_makuri", "c1_makurizashi",
    "c2_nige", "c2_sashi", "c2_makuri", "c2_makurizashi",
    "c3_nige", "c3_sashi", "c3_makuri", "c3_makurizashi",
    "c4_nige", "c4_sashi", "c4_makuri", "c4_makurizashi",
    "c5_nige", "c5_sashi", "c5_makuri", "c5_makurizashi",
    "c6_nige", "c6_sashi", "c6_makuri", "c6_makurizashi",
    "local5y_sashi", "local5y_makuri", "local5y_makurizashi", "local5y_races",
    "general1y_sashi", "general1y_makuri", "general1y_makurizashi",
    "general1y_races",
    "escape1y_place2_rate", "escape1y_tricast_rate",
    "today_st_rank", "course1y_st_rank", "st_advantage_rank",
    "motor_dashfoot", "motor_extfoot",
    "motor_dashfoot_score", "motor_extfoot_score", "motor_rank_order",
    "nige_count", "sashi_count", "makuri_count", "makurisashi_count",
    "nigiri_rate", "is_local",
]
BOAT_CANDIDATE_STR = ["motor_eval", "motor_rank_letter"]

# players 側(boats.player_id 経由)
PLAYER_CANDIDATE_NUM = ["win_rate", "place_rate_2", "place_rate_3"]
PLAYER_CANDIDATE_STR = ["rank", "branch", "birth_place"]

RACE_CANDIDATE_NUM = [
    "temperature", "water_temperature", "wind_speed", "wave_height",
    "tide_score",
]
RACE_CANDIDATE_STR = ["weather", "wind_direction", "tide_type"]


def is_missing(v):
    if v is None:
        return True
    if isinstance(v, float) and np.isnan(v):
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    sb = tb.get_client()

    print("=" * 78)
    print("DOTレーティング 特徴量改善 step-A 追加候補列カバレッジ計測(読み取り専用)")
    print("=" * 78)

    # races
    races = tb.fetch_all(
        sb, "races",
        "id,date,venue,race_no," + ",".join(RACE_CANDIDATE_NUM + RACE_CANDIDATE_STR))
    race_by_id = {r["id"]: r for r in races}

    # boats(候補 + player_id)
    bcols = ["race_id", "lane", "player_id"] + BOAT_CANDIDATE_NUM + BOAT_CANDIDATE_STR
    boats = tb.fetch_all(sb, "boats", ",".join(bcols))
    boats_by_race = defaultdict(list)
    for b in boats:
        boats_by_race[b["race_id"]].append(b)

    # players(rank/win_rate/branch等)
    players = tb.fetch_all(
        sb, "players",
        "id," + ",".join(PLAYER_CANDIDATE_NUM + PLAYER_CANDIDATE_STR))
    player_by_pid = {p["id"]: p for p in players}

    # 完全確定結果(学習可能サンプルに絞るため)
    rwl = tb.fetch_all(
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

    # 学習可能サンプル構築(boats=6 × 完全結果)
    boat_rows = []   # 1艇=1行(boats候補 + rank)
    race_rows = []   # 1レース=1行(races候補)
    months = []
    used_races = 0
    for rid, blist in boats_by_race.items():
        if len(blist) != 6:
            continue
        r = race_by_id.get(rid)
        if not r:
            continue
        key = (r.get("date"), r.get("venue"), r.get("race_no"))
        if key not in res_idx:
            continue
        used_races += 1
        month = (key[0] or "")[:7]
        months.append(month)
        race_rows.append({"month": month, **{c: r.get(c)
                          for c in RACE_CANDIDATE_NUM + RACE_CANDIDATE_STR}})
        for b in blist:
            row = {"month": month}
            for c in BOAT_CANDIDATE_NUM + BOAT_CANDIDATE_STR:
                row[c] = b.get(c)
            pid = b.get("player_id")
            p = player_by_pid.get(pid) if pid is not None else None
            for c in PLAYER_CANDIDATE_NUM + PLAYER_CANDIDATE_STR:
                row[c] = (p.get(c) if p else None)
            boat_rows.append(row)

    boat_df = pd.DataFrame(boat_rows)
    race_df = pd.DataFrame(race_rows)
    all_months = sorted(set(months))
    print(f"\n対象: {used_races} レース / {len(boat_df)} 艇行  月別="
          + ", ".join(f"{m}={ (boat_df['month']==m).sum()//6 }R" for m in all_months))

    def coverage_table(df, cols, grain):
        """各列の月別+全体カバレッジ(非欠損率)を算出して表示・記録。"""
        recs = []
        print(f"\n■ {grain} カバレッジ(非欠損率)")
        header = f"  {'column':28s} {'overall':>8s} " + \
                 " ".join(f"{m[5:]:>7s}" for m in all_months)
        print(header)
        for c in cols:
            if c not in df.columns:
                line = f"  {c:28s} {'(列なし)':>8s}"
                print(line)
                recs.append({"column": c, "grain": grain, "exists": False,
                             "overall": None, "by_month": {}})
                continue
            total = len(df)
            nonnull = int((~df[c].apply(is_missing)).sum())
            overall = nonnull / total if total else 0.0
            by_month = {}
            cells = []
            for m in all_months:
                sub = df[df["month"] == m]
                t = len(sub)
                nn = int((~sub[c].apply(is_missing)).sum())
                cov = nn / t if t else 0.0
                by_month[m] = cov
                cells.append(f"{cov*100:6.1f}%")
            print(f"  {c:28s} {overall*100:7.1f}% " + " ".join(cells))
            recs.append({"column": c, "grain": grain, "exists": True,
                         "overall": overall, "nonnull": nonnull, "total": total,
                         "by_month": by_month})
        return recs

    recs = []
    recs += coverage_table(boat_df, PLAYER_CANDIDATE_NUM, "players数値(艇行)")
    recs += coverage_table(boat_df, PLAYER_CANDIDATE_STR, "players文字列(艇行)")
    recs += coverage_table(boat_df, BOAT_CANDIDATE_NUM, "boats数値(艇行)")
    recs += coverage_table(boat_df, BOAT_CANDIDATE_STR, "boats文字列(艇行)")
    recs += coverage_table(race_df, RACE_CANDIDATE_NUM, "races数値(レース)")
    recs += coverage_table(race_df, RACE_CANDIDATE_STR, "races文字列(レース)")

    str_cols = BOAT_CANDIDATE_STR + RACE_CANDIDATE_STR + PLAYER_CANDIDATE_STR
    # 文字列カテゴリの値分布(エンコード設計のため)
    print("\n■ 文字列列のユニーク値(エンコード設計用)")
    for c in str_cols:
        src = boat_df if (c in boat_df.columns) else race_df
        if c not in src.columns:
            continue
        vc = (src[c].dropna().astype(str).str.strip()
              .replace("", np.nan).dropna().value_counts())
        print(f"  {c}: " + ", ".join(f"{k}({v})" for k, v in vc.head(20).items()))

    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        out = {
            "used_races": used_races, "n_boats": len(boat_df),
            "months": all_months,
            "coverage": recs,
            "string_value_counts": {
                c: (boat_df if c in boat_df.columns else race_df)[c]
                .dropna().astype(str).str.strip().replace("", np.nan).dropna()
                .value_counts().head(30).to_dict()
                for c in str_cols
                if (c in boat_df.columns or c in race_df.columns)
            },
        }
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\nJSON保存: {args.json}")

    print("\n[完了] 本番DBは SELECT のみ・書込なし。")


if __name__ == "__main__":
    main()
