#!/usr/bin/env python3
"""v58.7 engine.py が消費する『決定論指標の入力列』の実効カバレッジ計測(読み取り専用)。

dot_feature_coverage.py が測っていない engine.py 固有入力列を補完計測する:
  - c{n}_win_rate (course_win_rates / EI成分A・TI・逃げ成立度フォールバック)
  - season_st, deashi, nobashi (EI成分F=出足/伸び・season_st補正)
  - gen_rate, hit_rate (攻め発生率/被弾率: v58.7のスクレイピング導出値)
  - nigiri_occurrence (握り発生率)
  - entry_course (進入コース: 決まり手スライス・P2/P3判定の起点)
  - exhibition_time / exhibition_st (展示補正)
本番 Supabase は SELECT のみ。書込なし。
"""
import os
import sys
import json
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts", "dot"))
import train_baseline as tb  # noqa: E402

# engine.py が race_dict_to_input で参照する入力列(未計測分を中心に)
BOAT_COLS = [
    "entry_course",
    "c1_win_rate", "c2_win_rate", "c3_win_rate",
    "c4_win_rate", "c5_win_rate", "c6_win_rate",
    "season_st", "deashi", "nobashi",
    "gen_rate", "hit_rate", "nigiri_occurrence",
    "exhibition_time", "exhibition_st",
    "today_st", "course1y_st",
]


def is_missing(v):
    if v is None:
        return True
    if isinstance(v, float) and np.isnan(v):
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


def main():
    sb = tb.get_client()
    races = tb.fetch_all(sb, "races", "id,date,venue,race_no")
    race_by_id = {r["id"]: r for r in races}

    # 列が存在しない可能性があるので段階的にSELECT(失敗列はスキップ)
    avail = []
    for c in BOAT_COLS:
        try:
            sb.table("boats").select(c).limit(1).execute()
            avail.append(c)
        except Exception as e:
            print(f"[列なし/不可] {c}: {str(e)[:80]}")
    bcols = ["race_id", "lane"] + avail
    boats = tb.fetch_all(sb, "boats", ",".join(bcols))
    boats_by_race = defaultdict(list)
    for b in boats:
        boats_by_race[b["race_id"]].append(b)

    # 完全確定結果に絞る(学習可能サンプル基準)
    rwl = tb.fetch_all(
        sb, "race_winner_log",
        "date,venue,race_no,winner_lane,place2_lane,place3_lane,trifecta_result",
        order_col="race_key")
    res_idx = {}
    for r in rwl:
        if not r.get("trifecta_result"):
            continue
        if r.get("place2_lane") is None or r.get("place3_lane") is None:
            continue
        res_idx[(r.get("date"), r.get("venue"), r.get("race_no"))] = r

    rows = []
    used = 0
    for rid, blist in boats_by_race.items():
        if len(blist) != 6:
            continue
        r = race_by_id.get(rid)
        if not r:
            continue
        key = (r.get("date"), r.get("venue"), r.get("race_no"))
        if key not in res_idx:
            continue
        used += 1
        month = (key[0] or "")[:7]
        for b in blist:
            row = {"month": month, "lane": b.get("lane")}
            for c in avail:
                row[c] = b.get(c)
            rows.append(row)
    df = pd.DataFrame(rows)
    months = sorted(df["month"].dropna().unique().tolist())
    print(f"\n対象: {used}R / {len(df)}艇行 月別="
          + ", ".join(f"{m}={(df['month']==m).sum()//6}R" for m in months))

    # course_win_rate の『自コース(=lane)スライス』実効カバレッジを別途算出
    def self_course_cov(df):
        vals = pd.Series(np.nan, index=df.index)
        for n in range(1, 7):
            col = f"c{n}_win_rate"
            if col in df.columns:
                m = (df["lane"] == n).to_numpy()
                vals[m] = df.loc[m, col]
        return vals

    print("\n■ engine.py入力列 実効カバレッジ(非欠損率)")
    print(f"  {'column':22s} {'overall':>8s} " +
          " ".join(f"{m[5:]:>7s}" for m in months))
    recs = []
    for c in avail:
        total = len(df)
        nn = int((~df[c].apply(is_missing)).sum())
        overall = nn / total if total else 0.0
        cells, by_month = [], {}
        for m in months:
            sub = df[df["month"] == m]
            t = len(sub)
            x = int((~sub[c].apply(is_missing)).sum())
            cov = x / t if t else 0.0
            by_month[m] = cov
            cells.append(f"{cov*100:6.1f}%")
        print(f"  {c:22s} {overall*100:7.1f}% " + " ".join(cells))
        recs.append({"column": c, "overall": overall, "by_month": by_month,
                     "nonnull": nn, "total": total})

    # 自コース c{lane}_win_rate
    sc = self_course_cov(df)
    df["_self_course_wr"] = sc
    cells, by_month = [], {}
    for m in months:
        sub = df[df["month"] == m]
        t = len(sub)
        x = int((~sub["_self_course_wr"].apply(is_missing)).sum())
        cov = x / t if t else 0.0
        by_month[m] = cov
        cells.append(f"{cov*100:6.1f}%")
    nn = int((~df["_self_course_wr"].apply(is_missing)).sum())
    print(f"  {'self c{lane}_win_rate':22s} {nn/len(df)*100:7.1f}% " + " ".join(cells))
    recs.append({"column": "self_course_win_rate", "overall": nn/len(df),
                 "by_month": by_month, "nonnull": nn, "total": len(df)})

    # 100%カバレッジ列の情報量チェック(nunique / 0率 / 統計)= is_local罠の検出
    print("\n■ 100%カバレッジ列の情報量チェック(定数/ゼロ偏り検出)")
    info = {}
    for c in ["gen_rate", "hit_rate"]:
        if c not in df.columns:
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        nun = int(s.nunique(dropna=True))
        zero = float((s == 0).mean())
        info[c] = {"nunique": nun, "zero_rate": zero,
                   "mean": float(s.mean()), "std": float(s.std()),
                   "min": float(s.min()), "max": float(s.max())}
        print(f"  {c:12s} nunique={nun:5d} zero率={zero*100:5.1f}% "
              f"mean={s.mean():.4f} std={s.std():.4f} "
              f"min={s.min():.3f} max={s.max():.3f}")
        for m in months:
            sm = pd.to_numeric(df[df['month'] == m][c], errors="coerce")
            print(f"      {m}: nunique={sm.nunique(dropna=True):4d} "
                  f"zero率={(sm==0).mean()*100:5.1f}% mean={sm.mean():.4f}")

    out = {"used_races": used, "n_boats": len(df), "months": months,
           "coverage": recs, "info_quality": info}
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "v587_engine_input_coverage.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nJSON保存: {path}")
    print("[完了] SELECTのみ・書込なし。")


if __name__ == "__main__":
    main()
