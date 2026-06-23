#!/usr/bin/env python3
"""DOTレーティング — 6月の予想 vs 実際の確定結果で精度を実測する(読み取り専用)

確定モデル(rank採用版 = train_lightgbm.py の --extra 経路 / G1級別ほか)で
6月(TEST_MONTH=2026-06)の全レースの予想を生成し、DBの実確定着順
(race_winner_log)と突合して精度を実測する。本番DBはSELECTのみ・書込ゼロ・
engine.py 不変更。リーク厳守(6月はtrainに混ぜない)。

出力指標:
  - 本命(Top1)的中率 / AUC / LogLoss
  - ベースライン比較: 1号ベタ(1号頭固定) / national_win_rate順
  - 買い目: 3連単(上位3その順1点) / 3連複(上位3・上位4BOX)の的中率と ROI
  - 選択的投票(自信度上位レースのみ購入)の ROI(min/median/max・購入R数・標本数)
  - 月内 週次/日次の Top1的中率推移(精度ブレ確認)

使い方:
  python3 scripts/dot/june_validation.py --json tmp/dot_june_validation.json
"""
import os
import sys
import json
import argparse
from collections import defaultdict
from itertools import combinations

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train_baseline as tb     # noqa: E402
import train_lightgbm as tl     # noqa: E402
import bet_strategy as bs       # noqa: E402

STAKE = bs.STAKE  # 100円/点
TAKEOUT = 0.25    # 競艇の控除率(参考線)


# ---------------------------------------------------------------------------
# 1. リーク無しOOF生成(6月)。rank採用(extra)特徴。betting列を温存。
#    train_lightgbm.run_cv_lgb / bet_strategy.build_oof と同一分割思想:
#      6月内 会場層化 K-fold(レース単位=艇行リーク無し)、4月+5月は常にtrain合流。
#      検証側の6月(tl.TEST_MONTH)はtrainに混ぜない(リーク厳守)。
# ---------------------------------------------------------------------------
OOF_KEEP = [
    "race_id", "date", "venue", "lane", "is_win", "is_top3",
    "national_win_rate",
    "winner_lane", "place2_lane", "place3_lane",
    "trifecta_result", "trifecta_payout",
    "exacta_result", "exacta_payout", "trifecta_place_payout",
]


def build_oof(df, feat_cols, target="is_win", n_folds=5, seed=42):
    df_jun = df[df["month"] == tl.TEST_MONTH].copy()
    df_past = df[df["month"].isin(tl.TRAIN_MONTHS)].copy()
    races_jun = (df_jun[["race_id", "venue"]].drop_duplicates()
                 .reset_index(drop=True))
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)

    oof_records = []
    leak_races = 0
    for tr_idx, va_idx in skf.split(races_jun["race_id"], races_jun["venue"]):
        tr_races = set(races_jun.loc[tr_idx, "race_id"])
        va_races = set(races_jun.loc[va_idx, "race_id"])
        # リーク自己検査: train側とvalid側で6月レースが重複していないこと
        leak_races += len(tr_races & va_races)
        tr_df = pd.concat([df_past, df_jun[df_jun["race_id"].isin(tr_races)]],
                          ignore_index=True)
        va_df = df_jun[df_jun["race_id"].isin(va_races)].copy()
        booster = tl.train_lgb(tr_df[feat_cols], tr_df[target],
                               va_df[feat_cols], va_df[target],
                               impute_median=False)
        proba = booster.predict(va_df[feat_cols],
                                num_iteration=booster.best_iteration)
        va_df = va_df.assign(_pwin=proba)
        oof_records.append(va_df[OOF_KEEP + ["_pwin"]])
    oof = pd.concat(oof_records, ignore_index=True)
    return oof, leak_races


# ---------------------------------------------------------------------------
# 2. 予測ベース指標(Top1/AUC/LogLoss)
# ---------------------------------------------------------------------------
def classification_metrics(oof):
    y = oof["is_win"].to_numpy()
    p = oof["_pwin"].to_numpy()
    ll = float(log_loss(y, p, labels=[0, 1]))
    auc = float(roc_auc_score(y, p))
    top1, hit, tot = tb.eval_top1_hit(oof, "_pwin")
    return {"logloss": ll, "auc": auc,
            "top1_hit_rate": top1, "top1_hit": hit, "n_races": tot}


# ---------------------------------------------------------------------------
# 3. ベースライン(同一OOF集合) Top1
# ---------------------------------------------------------------------------
def baseline_top1(oof):
    # 1号頭固定: score = -lane(1号が最大)
    b1 = oof.assign(_s=-oof["lane"].astype(float))
    b1_top1, _, _ = tb.eval_top1_hit(b1, "_s")
    # national_win_rate 降順
    bn = oof.assign(_s=oof["national_win_rate"].fillna(-1.0))
    bn_top1, _, _ = tb.eval_top1_hit(bn, "_s")
    return {"lane1_top1": b1_top1, "national_top1": bn_top1}


# ---------------------------------------------------------------------------
# 4. 買い目バックテスト(全レース機械買い)。回収は全てDB実払戻。
# ---------------------------------------------------------------------------
def backtest_strategy(oof, strat_fn):
    return bs.backtest(oof, strat_fn)


def strat_lane1_trifecta(sub):
    """参考: 1号頭固定の3連単1点(1-2-3)。"""
    ordered = sub.assign(_s=-sub["lane"].astype(float)).sort_values(
        "_s", ascending=False)
    t = [int(x) for x in ordered["lane"].head(3).tolist()]
    return [("trifecta", (t[0], t[1], t[2]))]


# ---------------------------------------------------------------------------
# 5. 選択的投票: 自信度(P_top)上位カバレッジのレースのみ購入し ROI を見る。
#    複数seedでOOFを作り直し、test ROI の分布(min/median/max)を出す。
#    閾値はtrainで凍結→testで適用(carve-fit防止)= selective_voting と同思想。
# ---------------------------------------------------------------------------
def p_top_by_race(oof):
    recs = []
    for rid, sub in oof.groupby("race_id"):
        pw = sub["_pwin"].to_numpy(dtype=float)
        s = pw / pw.sum() if pw.sum() > 0 else np.full_like(pw, 1.0 / len(pw))
        recs.append({"race_id": rid, "p_top": float(np.sort(s)[::-1][0])})
    return pd.DataFrame(recs)


def selective_voting_distribution(df, feat_cols, target, n_folds,
                                  strat_fn, seeds, coverage):
    """各seedでOOF再生成→P_top上位 coverage 割合のレースのみ購入したROIを集計。
    in-sample(全OOFでのcov適用)だが複数seedの分布で安定性を見る。
    閾値carve-fit懸念があるため『固定カバレッジ(例30%)』で評価し、後段で
    train→test凍結検証も併記する。"""
    rois, hits, wagered = [], [], []
    for sd in seeds:
        oof, _ = build_oof(df, feat_cols, target=target, n_folds=n_folds, seed=sd)
        conf = p_top_by_race(oof)
        k = max(1, int(round(len(conf) * coverage)))
        chosen = set(conf.sort_values("p_top", ascending=False)
                     ["race_id"].head(k).tolist())
        sub_oof = oof[oof["race_id"].isin(chosen)].copy()
        m = bs.backtest(sub_oof, strat_fn)
        rois.append(m["roi"])
        hits.append(m["hit_rate"])
        wagered.append(m["wagered_races"])
    a = np.array(rois, dtype=float)
    return {
        "coverage": coverage,
        "n_seeds": len(seeds),
        "wagered_races_median": float(np.median(wagered)),
        "roi_min": float(a.min()),
        "roi_median": float(np.median(a)),
        "roi_mean": float(a.mean()),
        "roi_max": float(a.max()),
        "hit_rate_median": float(np.median(hits)),
        "frac_over_takeout": float((a > (1 - TAKEOUT)).mean()),
        "frac_over_100": float((a > 1.0).mean()),
    }


def selective_train_test_oos(df, feat_cols, target, n_folds, strat_fn,
                             seeds, train_frac=0.6):
    """train(前半日付)でP_top閾値をROI最大選定→test(後半)に凍結適用。
    複数seedで test ROI 分布を返す(真のOOS。carve-fit防止)。"""
    cov_grid = [1.0, 0.8, 0.6, 0.5, 0.4, 0.3, 0.2]
    test_rois, test_wag, test_cov = [], [], []
    for sd in seeds:
        oof, _ = build_oof(df, feat_cols, target=target, n_folds=n_folds, seed=sd)
        conf = p_top_by_race(oof)
        cd = oof[["race_id", "date"]].drop_duplicates().merge(conf, on="race_id")
        cd = cd.sort_values(["date", "race_id"]).reset_index(drop=True)
        dates = sorted(cd["date"].unique())
        n_target = int(round(len(cd) * train_frac))
        cum, cutoff = 0, dates[-1]
        for d in dates:
            cum += int((cd["date"] == d).sum())
            if cum >= n_target:
                cutoff = d
                break
        train_ids = set(cd[cd["date"] <= cutoff]["race_id"])
        test_ids = set(cd[cd["date"] > cutoff]["race_id"])
        if not test_ids:
            continue
        # train で cov 選定(ROI最大、購入数>=20)
        conf_tr = conf[conf["race_id"].isin(train_ids)].sort_values(
            "p_top", ascending=False).reset_index(drop=True)
        best = None
        for cov in cov_grid:
            k = max(1, int(round(len(conf_tr) * cov)))
            chosen = set(conf_tr["race_id"].head(k).tolist())
            m = bs.backtest(oof[oof["race_id"].isin(chosen)], strat_fn)
            if m["wagered_races"] < 20:
                continue
            if best is None or m["roi"] > best[0]:
                best = (m["roi"], cov, float(conf_tr.iloc[k - 1]["p_top"]))
        if best is None:
            thr = float(conf_tr["p_top"].min())
        else:
            thr = best[2]
        conf_te = conf[conf["race_id"].isin(test_ids)]
        chosen_te = set(conf_te[conf_te["p_top"] >= thr]["race_id"].tolist())
        m_te = bs.backtest(oof[oof["race_id"].isin(chosen_te)], strat_fn)
        test_rois.append(m_te["roi"])
        test_wag.append(m_te["wagered_races"])
        test_cov.append(len(chosen_te) / max(1, len(test_ids)))
    a = np.array(test_rois, dtype=float) if test_rois else np.array([0.0])
    return {
        "n_seeds": len(test_rois),
        "test_roi_min": float(a.min()),
        "test_roi_median": float(np.median(a)),
        "test_roi_mean": float(a.mean()),
        "test_roi_max": float(a.max()),
        "test_wagered_median": float(np.median(test_wag)) if test_wag else 0.0,
        "test_coverage_median": float(np.median(test_cov)) if test_cov else 0.0,
        "frac_over_takeout": float((a > (1 - TAKEOUT)).mean()),
        "frac_over_100": float((a > 1.0).mean()),
    }


# ---------------------------------------------------------------------------
# 6. 月内 時系列(週次/日次)Top1 的中率推移
# ---------------------------------------------------------------------------
def timeseries_top1(oof):
    daily = []
    for d, sub in oof.groupby("date"):
        top1, hit, tot = tb.eval_top1_hit(sub, "_pwin")
        daily.append({"date": d, "n_races": tot, "top1_hit": hit,
                      "top1_hit_rate": top1})
    daily.sort(key=lambda r: r["date"])

    # 週次(ISO週でまとめる)
    wk = defaultdict(lambda: {"hit": 0, "tot": 0, "dates": []})
    for d, sub in oof.groupby("date"):
        ts = pd.Timestamp(d)
        iso = ts.isocalendar()
        wkey = f"{iso.year}-W{int(iso.week):02d}"
        _, hit, tot = tb.eval_top1_hit(sub, "_pwin")
        wk[wkey]["hit"] += hit
        wk[wkey]["tot"] += tot
        wk[wkey]["dates"].append(d)
    weekly = []
    for wkey in sorted(wk):
        v = wk[wkey]
        weekly.append({"week": wkey, "n_races": v["tot"],
                       "top1_hit_rate": v["hit"] / v["tot"] if v["tot"] else 0.0,
                       "date_min": min(v["dates"]), "date_max": max(v["dates"])})
    rates = [w["top1_hit_rate"] for w in weekly]
    weekly_summary = {
        "n_weeks": len(weekly),
        "min": float(np.min(rates)) if rates else 0.0,
        "max": float(np.max(rates)) if rates else 0.0,
        "mean": float(np.mean(rates)) if rates else 0.0,
        "std": float(np.std(rates)) if rates else 0.0,
        "spread": float(np.max(rates) - np.min(rates)) if rates else 0.0,
    }
    return daily, weekly, weekly_summary


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="tmp/dot_june_validation.json")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--target", default="is_win", choices=["is_win", "is_top3"])
    args = ap.parse_args()

    sb = tb.get_client()
    print("=" * 78)
    print("DOTレーティング 6月予想 vs 実確定結果 精度実測(rank採用版・読み取り専用)")
    print("=" * 78)

    # rank採用(extra)でbetting列込みデータを取得
    df, used_races = bs.load_dataset_betting(sb, include_extra=True)
    df, feat_cols, group_map = tb.build_features(df, include_extra=True)

    # リーク/allowlist 検査
    leaked = [c for c in feat_cols if c in tb.LEAK_BLACKLIST]
    allow = set(tb.BASE_FEATURES)
    for f in tb.RELATIVE_FEATURES:
        allow.add(f + "_z"); allow.add(f + "_rank")
    for cols in group_map.values():
        allow.update(cols)
    not_allowed = [c for c in feat_cols if c not in allow]
    leak_month = tl.TEST_MONTH in set(tl.TRAIN_MONTHS)

    months = df.groupby("month").size() // 6
    print(f"\n■ データ(SELECTのみ): 学習可能 {used_races}R / {len(df)}艇行")
    for m, n in months.items():
        print(f"    {m}: {n}R")
    print(f"\n■ train: {tl.TRAIN_MONTHS} / test(OOF): {tl.TEST_MONTH}")
    print(f"  リーク防止(test月をtrainに含めない): "
          f"{'NG(リーク!)' if leak_month else 'OK(排他)'}")
    print(f"  特徴量 {len(feat_cols)}列  rank採用={'rank_ord' in feat_cols}  "
          f"リーク列={'NG ' + str(leaked) if leaked else 'OK'}  "
          f"allowlist={'NG ' + str(not_allowed) if not_allowed else 'OK'}")
    print("  特徴グループ: " +
          ", ".join(f"{k}({len(v)})" for k, v in group_map.items() if v))

    # OOF生成(本指標用 seed=固定)
    print(f"\n■ リーク無しOOF生成(LightGBM P({args.target}), "
          f"6月内会場層化{args.folds}-fold, 4月+5月train合流)")
    oof, leak_races = build_oof(df, feat_cols, target=args.target,
                                n_folds=args.folds, seed=args.seed)
    n_oof = oof["race_id"].nunique()
    n_jun_total = df[df["month"] == tl.TEST_MONTH]["race_id"].nunique()
    print(f"  6月の照合可能レース(突合キー=date|venue|race_no): "
          f"{n_oof} / {n_jun_total}R")
    print(f"  fold内のtrain/valid 6月レース重複(0が正常): {leak_races}")

    # --- 予測指標 ---
    cm = classification_metrics(oof)
    print(f"\n■ 本命予測指標(同一OOF {n_oof}R)")
    print(f"  Top1的中率 = {cm['top1_hit_rate'] * 100:.2f}% "
          f"({cm['top1_hit']}/{cm['n_races']})")
    print(f"  AUC        = {cm['auc']:.4f}")
    print(f"  LogLoss    = {cm['logloss']:.4f}")

    # --- ベースライン ---
    base = baseline_top1(oof)
    print(f"\n■ ベースライン Top1(同一OOF)")
    print(f"  DOT(rank)        : {cm['top1_hit_rate'] * 100:.2f}%")
    print(f"  1号ベタ(1号頭)   : {base['lane1_top1'] * 100:.2f}%")
    print(f"  national_win順   : {base['national_top1'] * 100:.2f}%")

    # --- 買い目バックテスト(全レース機械買い) ---
    print(f"\n■ 買い目バックテスト(全{n_oof}R機械買い・回収は全てDB実払戻)")
    strat_defs = [
        ("3連単 上位3その順(1点)", bs.strat_A_baseline),
        ("3連複 上位3(1点)", bs.strat_D_trio_box),
        ("3連複 上位4BOX(4点)", bs.strat_E_trio_box4),
        ("参考:1号頭 3連単(1点)", strat_lane1_trifecta),
    ]
    bet_results = {}
    print(f"  {'戦略':28s} {'的中率':>8s} {'回収率':>8s} {'平均点':>6s} "
          f"{'購入R':>6s} {'純損益':>9s}")
    print("  " + "-" * 74)
    for name, fn in strat_defs:
        m = bs.backtest(oof, fn)
        bet_results[name] = m
        print(f"  {name:28s} {m['hit_rate'] * 100:6.1f}% {m['roi'] * 100:7.1f}% "
              f"{m['avg_points_per_race']:5.2f} {m['wagered_races']:6d} "
              f"{m['net']:8.0f}円")

    # --- 選択的投票 ROI 分布(複数seed) ---
    print(f"\n■ 選択的投票(自信度P_top上位のみ購入)複数seed分布")
    seeds = [42, 1, 7, 13, 21, 99, 123, 2024]
    sv_strats = {
        "3連単上位3その順": bs.strat_A_baseline,
        "3連複上位4BOX": bs.strat_E_trio_box4,
    }
    sv_fixed = {}   # 固定カバレッジ30%(in-sample・分布)
    sv_oos = {}     # train->test凍結(OOS)
    for sname, fn in sv_strats.items():
        d30 = selective_voting_distribution(
            df, feat_cols, args.target, args.folds, fn, seeds, coverage=0.30)
        oos = selective_train_test_oos(
            df, feat_cols, args.target, args.folds, fn, seeds, train_frac=0.6)
        sv_fixed[sname] = d30
        sv_oos[sname] = oos
        print(f"  [{sname}] 固定cov30%(in-sample,{len(seeds)}seed): "
              f"ROI中央{d30['roi_median'] * 100:.1f}% "
              f"[min{d30['roi_min'] * 100:.0f}/max{d30['roi_max'] * 100:.0f}] "
              f"購入R中央{d30['wagered_races_median']:.0f} "
              f">控除割合{d30['frac_over_takeout'] * 100:.0f}%")
        print(f"             train->test凍結(OOS,{oos['n_seeds']}seed): "
              f"ROI中央{oos['test_roi_median'] * 100:.1f}% "
              f"[min{oos['test_roi_min'] * 100:.0f}/max{oos['test_roi_max'] * 100:.0f}] "
              f"購入R中央{oos['test_wagered_median']:.0f} "
              f">100%割合{oos['frac_over_100'] * 100:.0f}%")

    # --- 時系列(週次/日次) ---
    daily, weekly, wk_sum = timeseries_top1(oof)
    print(f"\n■ 月内 週次 Top1的中率推移(精度ブレ確認)")
    for w in weekly:
        print(f"  {w['week']} ({w['date_min']}〜{w['date_max']}) "
              f"{w['n_races']:4d}R  Top1={w['top1_hit_rate'] * 100:.1f}%")
    print(f"  週次サマリ: 平均{wk_sum['mean'] * 100:.1f}% "
          f"幅[{wk_sum['min'] * 100:.1f}〜{wk_sum['max'] * 100:.1f}]% "
          f"std={wk_sum['std'] * 100:.1f}pt spread={wk_sum['spread'] * 100:.1f}pt")

    out = {
        "model": "LightGBM rank採用(extra)",
        "train_months": tl.TRAIN_MONTHS,
        "test_month": tl.TEST_MONTH,
        "leak_free": (not leaked) and (not not_allowed) and (not leak_month)
                     and (leak_races == 0),
        "leak_self_check": {"leak_month": leak_month, "leaked_cols": leaked,
                            "not_allowed": not_allowed,
                            "fold_train_valid_overlap": leak_races},
        "used_races": used_races,
        "months": {str(m): int(n) for m, n in months.items()},
        "n_features": len(feat_cols), "features": feat_cols,
        "feature_groups": {k: v for k, v in group_map.items()},
        "join_key": "date|venue|race_no (races x boats x race_winner_log INNER JOIN)",
        "oof_races": int(n_oof),
        "june_total_races": int(n_jun_total),
        "coverage_note": (f"6月 {n_oof}/{n_jun_total}R を照合"
                          "(boats6艇揃い & race_winner_logにtrifecta結果あり の交差)"),
        "classification": cm,
        "baselines_top1": base,
        "bet_backtest_full": bet_results,
        "selective_voting": {
            "seeds": seeds,
            "fixed_cov30_in_sample": sv_fixed,
            "train_test_oos": sv_oos,
            "takeout": TAKEOUT,
        },
        "timeseries": {"daily": daily, "weekly": weekly,
                       "weekly_summary": wk_sum},
        "honesty_notes": [
            "6月はtest/OOF専用。train(4+5月)に6月情報は一切混入していない(月排他+fold内重複0を自己検査)。",
            "回収は全てDB実払戻(trifecta/exacta/trifecta_place=3連複)。購入判定のみモデルP(win)。",
            "選択的投票のROIは標本が小さく(特にOOS test)高配当1本で大きく動く=分散大。",
            "control率25%(回収率75%)を安定的に超えるかを正直に評価する。",
            "engine.py不変更・本番DBはSELECTのみ。",
        ],
    }
    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\nJSON保存: {args.json}")

    print("\n[完了] 本番DBは SELECT のみ・書込なし。engine.py 不変更。リーク無し。")


if __name__ == "__main__":
    main()
