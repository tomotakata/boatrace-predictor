#!/usr/bin/env python3
"""DOTレーティング — 4月学習データ活用版の選択的投票検証(読み取り専用)

既存 selective_voting.py は『5月のみtrain合流・6月をK-fold』で、今回大量に
取得できた 4月(2570R)を学習に使っていない。本スクリプトは既存資産
(train_baseline / train_lightgbm / bet_strategy / selective_voting)を
そのまま再利用し、OOF生成時の train 合流に **4月も加える**(=4月+5月をtrain、
6月を会場層化K-fold)版で、本命モデルの精度と選択的投票の頑健性
(test ROI 分布・分散min)が改善するかを測る。

engine.py 不変更・本番DBは SELECT のみ・DB書込ゼロ・リーク無しは厳守
(評価ロジック・指標・閾値選定・seed反復は selective_voting.py と完全同一)。

使い方:
  python3 scripts/dot/selective_voting_apr.py --json tmp/dot_selective_voting_apr.json
"""
import os
import sys
import json
import argparse

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train_baseline as tb      # noqa: E402
import train_lightgbm as tl      # noqa: E402
import bet_strategy as bs        # noqa: E402
import selective_voting as sv    # noqa: E402


# ---------------------------------------------------------------------------
# OOF生成: 4月+5月を常にtrain合流し、6月を会場層化K-fold(=4月活用版)
# selective_voting.build_oof との差分は「df_may → df_apr+df_may」のみ。
# 評価対象(=OOF)は従来どおり6月レースのみ(test側拡大の効果を見る)。
# ---------------------------------------------------------------------------
def build_oof_apr(df, feat_cols, target="is_win", n_folds=5, seed=42):
    df_jun = df[df["month"] == "2026-06"].copy()
    df_train_extra = df[df["month"].isin(["2026-04", "2026-05"])].copy()
    races_jun = (df_jun[["race_id", "venue"]].drop_duplicates()
                 .reset_index(drop=True))
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)

    oof_records = []
    for tr_idx, va_idx in skf.split(races_jun["race_id"], races_jun["venue"]):
        tr_races = set(races_jun.loc[tr_idx, "race_id"])
        va_races = set(races_jun.loc[va_idx, "race_id"])
        tr_df = pd.concat([df_train_extra,
                           df_jun[df_jun["race_id"].isin(tr_races)]],
                          ignore_index=True)
        va_df = df_jun[df_jun["race_id"].isin(va_races)].copy()
        booster = tl.train_lgb(tr_df[feat_cols], tr_df[target],
                               va_df[feat_cols], va_df[target],
                               impute_median=False)
        proba = booster.predict(va_df[feat_cols],
                                num_iteration=booster.best_iteration)
        va_df = va_df.assign(_pwin=proba)
        oof_records.append(va_df[sv.OOF_KEEP + ["_pwin"]])
    oof = pd.concat(oof_records, ignore_index=True)
    return oof


def robustness_over_seeds_apr(df, feat_cols, target, n_folds, train_frac,
                              seeds, eval_combos):
    """selective_voting.robustness_over_seeds と同一手順だが OOF は build_oof_apr。"""
    agg = {f"{s}|{m}": [] for (s, _, m) in eval_combos}
    full_test = {s: [] for (s, _, m) in eval_combos}
    per_seed = []
    for sd in seeds:
        oof = build_oof_apr(df, feat_cols, target=target,
                            n_folds=n_folds, seed=sd)
        odds_k, prior, floor = bs.calibrate_odds_k(oof)
        conf = sv.race_confidence_metrics(oof, odds_k, prior, floor)
        conf_dates = (oof[["race_id", "date"]].drop_duplicates()
                      .merge(conf, on="race_id"))
        train_ids, test_ids, cutoff = sv.time_split_races(conf_dates, train_frac)
        seed_rec = {"seed": sd, "cutoff": cutoff,
                    "n_train": len(train_ids), "n_test": len(test_ids),
                    "combos": {}}
        for (sname, fn, metric) in eval_combos:
            sel = sv.select_threshold_on_train(oof, conf, fn, metric, train_ids)
            te = sv.apply_threshold_on_test(oof, conf, fn, metric, test_ids,
                                            sel["threshold_value"])
            agg[f"{sname}|{metric}"].append(te["roi"])
            mft = sv.backtest_subset(oof, fn, test_ids)
            full_test[sname].append(mft["roi"])
            seed_rec["combos"][f"{sname}|{metric}"] = {
                "train_cov": sel["coverage"],
                "train_roi": sel["train_metrics"]["roi"],
                "test_cov": te["coverage_realized"], "test_roi": te["roi"],
                "test_wagered": te["wagered_races"],
            }
        per_seed.append(seed_rec)

    summary = {}
    for key, rois in agg.items():
        a = np.array(rois, dtype=float)
        summary[key] = {
            "n_seeds": len(a),
            "test_roi_min": float(a.min()),
            "test_roi_median": float(np.median(a)),
            "test_roi_mean": float(a.mean()),
            "test_roi_max": float(a.max()),
            "frac_over_100": float((a > 1.0).mean()),
        }
    full_summary = {}
    for s, rois in full_test.items():
        a = np.array(rois, dtype=float)
        full_summary[s] = {"test_roi_median": float(np.median(a)),
                           "test_roi_mean": float(a.mean())}
    return summary, full_summary, per_seed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--target", default="is_win", choices=["is_win", "is_top3"])
    ap.add_argument("--train-frac", type=float, default=0.6)
    args = ap.parse_args()

    sb = tb.get_client()
    print("=" * 80)
    print("DOTレーティング 4月学習データ活用版 選択的投票検証(読み取り専用)")
    print("  差分: OOF生成のtrain合流に 4月(2570R) を追加(従来は5月のみ)")
    print("=" * 80)

    df, used_races = bs.load_dataset_betting(sb)
    print(f"\n■ データ取得(SELECTのみ): 学習可能 {used_races}R / {len(df)}艇行")
    print("  月別: " + ", ".join(f"{m}={n // 6}R" for m, n in
                                  df.groupby('month').size().items()))

    df, feat_cols = tb.build_features(df)
    leaked = [c for c in feat_cols if c in tb.LEAK_BLACKLIST]
    allow = set(tb.BASE_FEATURES)
    for f in tb.RELATIVE_FEATURES:
        allow.add(f + "_z"); allow.add(f + "_rank")
    not_allowed = [c for c in feat_cols if c not in allow]
    print(f"\n■ 特徴量 {len(feat_cols)}列  "
          f"リーク混入={'NG ' + str(leaked) if leaked else 'OK'}  "
          f"allowlist={'NG ' + str(not_allowed) if not_allowed else 'OK'}")

    # 単一seedOOFで基準ROIと買い目を確認
    print(f"\n■ リーク無しOOF生成(4月+5月train合流, 6月会場層化{args.folds}-fold)")
    oof = build_oof_apr(df, feat_cols, target=args.target,
                        n_folds=args.folds, seed=args.seed)
    n_oof = oof["race_id"].nunique()
    n_train_apr = df[df["month"].isin(["2026-04", "2026-05"])]["race_id"].nunique()
    print(f"  OOFレース数(=6月valid): {n_oof}")
    print(f"  train合流(4+5月)レース数: {n_train_apr}  (従来は5月623Rのみ)")

    # 本命モデル精度(同一OOFでTop1/3連単/ROI)
    dot_top1, _, _ = tb.eval_top1_hit(oof.rename(columns={"_pwin": "_score"}),
                                      "_score")
    print(f"  本命Top1的中(6月OOF {n_oof}R): {dot_top1 * 100:.1f}%")

    odds_k, prior, floor = bs.calibrate_odds_k(oof)
    strategies = sv.get_strategies(odds_k, prior, floor)

    # 頑健性(8seed) — selective_voting と同一の combo を評価
    print("\n" + "=" * 80)
    print("■ 頑健性チェック(8seed・4月活用版): train→test を反復, test ROI分布")
    print("=" * 80)
    seeds = [42, 1, 7, 13, 21, 99, 123, 2024]
    conf_metrics_focus = ["p_top", "gap", "neg_entropy", "variance"]
    eval_combos = [(sname, fn, mt)
                   for sname, fn in strategies.items()
                   for mt in conf_metrics_focus]
    rob_summary, rob_full, rob_per_seed = robustness_over_seeds_apr(
        df, feat_cols, args.target, args.folds, args.train_frac,
        seeds, eval_combos)
    print(f"  seeds={seeds}")
    print(f"  {'買い目':20s} {'指標':22s} {'test ROI 中央':>12s} {'min':>7s} "
          f"{'max':>7s} {'>100%割合':>9s}")
    print("  " + "-" * 86)
    for sname, _ in strategies.items():
        for mt in conf_metrics_focus:
            s = rob_summary[f"{sname}|{mt}"]
            mark = "★" if s["test_roi_median"] > 1.0 else " "
            print(f" {mark}{sname:19s} {sv.METRIC_LABEL[mt]:22s} "
                  f"{s['test_roi_median'] * 100:10.1f}% "
                  f"{s['test_roi_min'] * 100:6.0f}% "
                  f"{s['test_roi_max'] * 100:6.0f}% "
                  f"{s['frac_over_100'] * 100:7.0f}%")

    robust_winners = {k: v for k, v in rob_summary.items()
                      if v["test_roi_median"] > 1.0}
    print("\n  [4月活用版 最終判定] test ROI中央値>100%のcombo: "
          f"{len(robust_winners)}件")
    for k, v in sorted(robust_winners.items(),
                       key=lambda kv: -kv[1]["test_roi_median"]):
        print(f"    {k:34s} 中央{v['test_roi_median'] * 100:.0f}% "
              f"[min{v['test_roi_min'] * 100:.0f}/max{v['test_roi_max'] * 100:.0f}] "
              f">100%割合{v['frac_over_100'] * 100:.0f}%")

    out = {
        "variant": "apr_train_merge",
        "target": args.target, "folds": args.folds, "train_frac": args.train_frac,
        "oof_races": int(n_oof),
        "n_train_apr_may": int(n_train_apr),
        "dot_top1_oof": float(dot_top1),
        "leak_free": (not leaked) and (not not_allowed),
        "robustness_seeds": seeds,
        "robustness_summary": rob_summary,
        "robustness_full_test": rob_full,
        "robustness_per_seed": rob_per_seed,
        "robust_winners_over_100_median": list(robust_winners.keys()),
    }
    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\nJSON保存: {args.json}")

    print("\n[完了] 本番DBは SELECT のみ・書込なし。engine.py 不変更。")


if __name__ == "__main__":
    main()
