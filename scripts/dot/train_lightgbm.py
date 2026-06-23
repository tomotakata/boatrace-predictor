#!/usr/bin/env python3
"""DOTレーティング step-2-2 — 本命モデル(LightGBM・読み取り専用)

既存 v58.7 再現エンジン(backend/app/prediction/engine.py)とは完全独立の
新規データ駆動システム。本番 Supabase は SELECT のみ。DB は一切書き込まない。

step-2-1(LogReg)の `train_baseline.py` を流用:
  - データ取得(load_dataset) / 特徴整形(build_features) / 枠内相対化(RELATIVE_FEATURES)
  - 評価ヘルパ(eval_top1_hit / eval_roi_trifecta) / ベースライン(1号ベタ / national順)
  - リーク防止 allowlist(BASE_FEATURES) + blacklist(LEAK_BLACKLIST) の二重ガード

LightGBM 固有の差分:
  1. モデル: LightGBM 二値分類。欠損は **median 補完せずネイティブ処理**
     (general1y_*=カバレッジ22% 等の欠損をそのまま分岐に使える)。
  2. 比較のため median 補完版 LightGBM も任意で併走(--with-impute)。
  3. 非線形・相互作用を捕捉。特徴量重要度(gain/split)を集計して上位を報告。
  4. 分割:
       (a) 6月内 会場層化 K-fold(LogReg と同一 OOF 集合で apples-to-apples 比較)
       (b) 5月train(623R)→6月valid(406R)の時系列ホールドアウト(頑健性確認)
  5. 評価: LogLoss / AUC / Top1的中 / 3連単的中 / 回収率(trifecta_payout)。
     DOT(LightGBM) vs LogReg基準値 vs 1号ベタ vs national順 を同一OOFで比較表。

使い方:
  python3 scripts/dot/train_lightgbm.py
  python3 scripts/dot/train_lightgbm.py --json tmp/dot_lightgbm.json --folds 5
  python3 scripts/dot/train_lightgbm.py --with-impute   # median補完版も比較
"""
import os
import sys
import json
import argparse

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold

# step-2-1 ベースライン資産を流用(同一ディレクトリ)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train_baseline as tb  # noqa: E402

# LogReg ベースラインの確定実測値(tmp/dot_baseline.json / 同一OOF 6月406R)。
# 同一OOF集合・同一回収率定義で比較するための基準。
LOGREG_REF = {
    "is_win": {"logloss": 0.362, "auc": 0.798,
               "top1_hit_rate": 0.5197, "trifecta_hit_rate": 0.0813, "roi": 0.7877},
    "is_top3": {"logloss": 0.591, "auc": 0.749,
                "top1_hit_rate": 0.4803, "trifecta_hit_rate": 0.0887, "roi": 1.0764},
}

# LightGBM パラメータ(小標本 1029R 向けに過学習を抑えた控えめ設定)
LGB_PARAMS = {
    "objective": "binary",
    "metric": "binary_logloss",
    "boosting_type": "gbdt",
    "learning_rate": 0.03,
    "num_leaves": 15,
    "max_depth": 4,
    "min_child_samples": 30,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.5,
    "reg_lambda": 1.0,
    "min_split_gain": 0.0,
    "verbose": -1,
    "seed": 42,
}
NUM_BOOST_ROUND = 600
EARLY_STOPPING = 50

# 学習(train)に合流する『過去月』。検証側(OOF/test)の6月は決して含めない。
# 検証済み(selective_voting_apr.py)の分散縮小(min+11.4pt)を本番化するため、
# 取得済みの4月(2570R)を5月(623R)と併せて常時 train へ合流する。
# リーク防止: TEST_MONTH(=2026-06)は train へ混ぜない(K-fold/holdoutの検証側)。
TRAIN_MONTHS = ["2026-04", "2026-05"]
TEST_MONTH = "2026-06"


# ---------------------------------------------------------------------------
# LightGBM 学習(欠損ネイティブ or median補完)
# ---------------------------------------------------------------------------
def train_lgb(tr_X, tr_y, va_X, va_y, *, impute_median=False):
    """1 fold を学習。impute_median=False なら NaN をネイティブに扱う。"""
    if impute_median:
        med = tr_X.median(numeric_only=True)
        tr_X = tr_X.fillna(med)
        va_X = va_X.fillna(med)

    dtrain = lgb.Dataset(tr_X, label=tr_y, free_raw_data=False)
    dvalid = lgb.Dataset(va_X, label=va_y, reference=dtrain, free_raw_data=False)
    booster = lgb.train(
        LGB_PARAMS, dtrain,
        num_boost_round=NUM_BOOST_ROUND,
        valid_sets=[dvalid],
        callbacks=[lgb.early_stopping(EARLY_STOPPING, verbose=False),
                   lgb.log_evaluation(period=0)],
    )
    return booster


def run_cv_lgb(df, feat_cols, target, n_folds=5, seed=42, impute_median=False):
    """6月内レースを会場層化K-foldで分割。4月+5月レースは常にtrainへ合流。
    fold分割はレース単位(艇行リーク防止)。LogReg(run_cv)と同一の分割思想。
    リーク防止: 検証側の6月(TEST_MONTH)はtrainに混ぜない。"""
    df_jun = df[df["month"] == TEST_MONTH].copy()
    df_past = df[df["month"].isin(TRAIN_MONTHS)].copy()

    races_jun = (df_jun[["race_id", "venue"]].drop_duplicates()
                 .reset_index(drop=True))
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)

    fold_metrics = []
    oof_records = []
    importance_gain = pd.Series(0.0, index=feat_cols)
    importance_split = pd.Series(0.0, index=feat_cols)

    for fold, (tr_idx, va_idx) in enumerate(
        skf.split(races_jun["race_id"], races_jun["venue"])
    ):
        tr_races = set(races_jun.loc[tr_idx, "race_id"])
        va_races = set(races_jun.loc[va_idx, "race_id"])

        tr_df = pd.concat([
            df_past,
            df_jun[df_jun["race_id"].isin(tr_races)],
        ], ignore_index=True)
        va_df = df_jun[df_jun["race_id"].isin(va_races)].copy()

        booster = train_lgb(
            tr_df[feat_cols], tr_df[target],
            va_df[feat_cols], va_df[target],
            impute_median=impute_median,
        )
        va_X = va_df[feat_cols]
        if impute_median:
            va_X = va_X.fillna(tr_df[feat_cols].median(numeric_only=True))
        proba = booster.predict(va_X, num_iteration=booster.best_iteration)
        va_df = va_df.assign(_score=proba)

        ll = log_loss(va_df[target], proba, labels=[0, 1])
        try:
            auc = roc_auc_score(va_df[target], proba)
        except ValueError:
            auc = float("nan")
        hit_rate, hit, tot = tb.eval_top1_hit(va_df, "_score")
        roi, tri_hit, ret, spent, _ = tb.eval_roi_trifecta(va_df, "_score")

        fold_metrics.append({
            "fold": fold, "n_val_races": tot, "n_val_boats": len(va_df),
            "logloss": ll, "auc": auc,
            "top1_hit_rate": hit_rate,
            "trifecta_hit_rate": tri_hit,
            "roi": roi,
            "best_iteration": int(booster.best_iteration or 0),
        })
        importance_gain += pd.Series(
            booster.feature_importance(importance_type="gain"),
            index=booster.feature_name()).reindex(feat_cols).fillna(0.0)
        importance_split += pd.Series(
            booster.feature_importance(importance_type="split"),
            index=booster.feature_name()).reindex(feat_cols).fillna(0.0)

        oof_records.append(va_df[["race_id", "venue", "lane", "is_win", "is_top3",
                                  "national_win_rate",
                                  "trifecta_payout", "trifecta_result",
                                  "_score"]])

    oof = pd.concat(oof_records, ignore_index=True)
    importance_gain /= n_folds
    importance_split /= n_folds
    return fold_metrics, oof, importance_gain, importance_split


# ---------------------------------------------------------------------------
# 時系列ホールドアウト: 4月+5月(train)train -> 6月(406R)valid
# ---------------------------------------------------------------------------
def run_holdout_lgb(df, feat_cols, target, impute_median=False):
    df_past = df[df["month"].isin(TRAIN_MONTHS)].copy()
    df_jun = df[df["month"] == TEST_MONTH].copy()

    booster = train_lgb(
        df_past[feat_cols], df_past[target],
        df_jun[feat_cols], df_jun[target],
        impute_median=impute_median,
    )
    va_X = df_jun[feat_cols]
    if impute_median:
        va_X = va_X.fillna(df_past[feat_cols].median(numeric_only=True))
    proba = booster.predict(va_X, num_iteration=booster.best_iteration)
    va_df = df_jun.assign(_score=proba)

    ll = log_loss(va_df[target], proba, labels=[0, 1])
    try:
        auc = roc_auc_score(va_df[target], proba)
    except ValueError:
        auc = float("nan")
    hit_rate, _, tot = tb.eval_top1_hit(va_df, "_score")
    roi, tri_hit, _, _, _ = tb.eval_roi_trifecta(va_df, "_score")

    return {
        "n_train_races": int(df_past["race_id"].nunique()),
        "n_val_races": tot,
        "logloss": ll, "auc": auc,
        "top1_hit_rate": hit_rate, "trifecta_hit_rate": tri_hit, "roi": roi,
        "best_iteration": int(booster.best_iteration or 0),
    }


def eval_feature_set(df, feat_cols, target, n_folds, seed):
    """与えた特徴列集合で OOF(Top1/AUC/3連単/ROI)と時系列holdoutを評価して要約を返す。
    ablation用の軽量サマリ(fold詳細は省く)。"""
    fold_metrics, oof, _, _ = run_cv_lgb(
        df, feat_cols, target, n_folds=n_folds, seed=seed, impute_median=False)
    agg = tb.aggregate(fold_metrics)
    dot_top1, _, _ = tb.eval_top1_hit(oof, "_score")
    dot_roi, dot_tri, _, _, _ = tb.eval_roi_trifecta(oof, "_score")
    holdout = run_holdout_lgb(df, feat_cols, target, impute_median=False)
    return {
        "n_features": len(feat_cols),
        "oof_races": int(oof["race_id"].nunique()),
        "cv_auc": agg["auc"], "cv_top1": agg["top1_hit_rate"],
        "oof_top1": dot_top1, "oof_trifecta": dot_tri, "oof_roi": dot_roi,
        "holdout_auc": holdout["auc"], "holdout_top1": holdout["top1_hit_rate"],
        "holdout_roi": holdout["roi"], "holdout_val_races": holdout["n_val_races"],
    }


def run_ablation(df, group_map, target, n_folds, seed):
    """グループ単位のablation:
      - baseline(base+base_relative のみ)
      - +各グループ単体(base + 1グループ)
      - full(全グループ)
      - leave-one-group-out(fullから各グループを1つ抜く)
    各々 OOF Top1/AUC と holdout を測定。採用判定: Top1かAUCが baseline 改善&両方悪化なし。
    """
    base_keys = {"base", "base_relative"}
    extra_keys = [k for k in group_map if k not in base_keys and group_map[k]]

    def cols_for(active_extra):
        keep = base_keys | set(active_extra)
        return sorted({c for k in keep for c in group_map.get(k, [])})

    results = {}
    print(f"\n  === ablation ({target}) OOF={n_folds}fold + holdout ===")

    base_cols = cols_for([])
    base_eval = eval_feature_set(df, base_cols, target, n_folds, seed)
    results["baseline_noextra"] = base_eval
    print(f"  [baseline(追加なし)] feats={base_eval['n_features']:2d} "
          f"OOF Top1={base_eval['oof_top1']*100:.1f}% AUC={base_eval['cv_auc']:.4f} "
          f"| holdout Top1={base_eval['holdout_top1']*100:.1f}% "
          f"AUC={base_eval['holdout_auc']:.4f}")

    # 単体追加
    single = {}
    for k in extra_keys:
        ev = eval_feature_set(df, cols_for([k]), target, n_folds, seed)
        single[k] = ev
        d_top1 = (ev["oof_top1"] - base_eval["oof_top1"]) * 100
        d_auc = ev["cv_auc"] - base_eval["cv_auc"]
        print(f"  [+{k:14s}] feats={ev['n_features']:2d} "
              f"OOF Top1={ev['oof_top1']*100:.1f}%({d_top1:+.1f}pt) "
              f"AUC={ev['cv_auc']:.4f}({d_auc:+.4f}) "
              f"| holdout Top1={ev['holdout_top1']*100:.1f}% AUC={ev['holdout_auc']:.4f}")
    results["single_add"] = single

    # full
    full_eval = eval_feature_set(df, cols_for(extra_keys), target, n_folds, seed)
    results["full"] = full_eval
    d_top1 = (full_eval["oof_top1"] - base_eval["oof_top1"]) * 100
    d_auc = full_eval["cv_auc"] - base_eval["cv_auc"]
    print(f"  [full(全追加)  ] feats={full_eval['n_features']:2d} "
          f"OOF Top1={full_eval['oof_top1']*100:.1f}%({d_top1:+.1f}pt) "
          f"AUC={full_eval['cv_auc']:.4f}({d_auc:+.4f}) "
          f"| holdout Top1={full_eval['holdout_top1']*100:.1f}% AUC={full_eval['holdout_auc']:.4f}")

    # leave-one-group-out(fullから各グループを抜く)
    loo = {}
    for k in extra_keys:
        rest = [x for x in extra_keys if x != k]
        ev = eval_feature_set(df, cols_for(rest), target, n_folds, seed)
        loo[k] = ev
        d_top1 = (full_eval["oof_top1"] - ev["oof_top1"]) * 100  # full - without = 寄与
        d_auc = full_eval["cv_auc"] - ev["cv_auc"]
        print(f"  [-{k:14s}] feats={ev['n_features']:2d} "
              f"OOF Top1={ev['oof_top1']*100:.1f}% AUC={ev['cv_auc']:.4f} "
              f"(寄与: Top1{d_top1:+.1f}pt AUC{d_auc:+.4f})")
    results["leave_one_out"] = loo

    # 採用判定(単体追加ベース): Top1 or AUC 改善 かつ 両方悪化なし
    decisions = {}
    EPS = 1e-9
    for k in extra_keys:
        ev = single[k]
        d_top1 = ev["oof_top1"] - base_eval["oof_top1"]
        d_auc = ev["cv_auc"] - base_eval["cv_auc"]
        improved = (d_top1 > EPS) or (d_auc > EPS)
        no_degrade = (d_top1 >= -EPS) and (d_auc >= -EPS)
        adopt = bool(improved and no_degrade)
        decisions[k] = {
            "delta_oof_top1": d_top1, "delta_cv_auc": d_auc,
            "adopt": adopt,
            "reason": ("Top1/AUCいずれか改善&両方悪化なし→採用" if adopt
                       else "改善条件未達/悪化あり→不採用"),
        }
    results["decisions"] = decisions
    results["baseline_ref"] = {"oof_top1": base_eval["oof_top1"],
                               "cv_auc": base_eval["cv_auc"]}
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None, help="評価結果JSONの保存先")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--with-impute", action="store_true",
                    help="median補完版 LightGBM も併走して比較する")
    ap.add_argument("--extra", action="store_true",
                    help="承認プランの追加特徴(G1級別/G2決まり手/G3当地/G4 ST相対)を使用")
    ap.add_argument("--ablation", action="store_true",
                    help="特徴量グループ単位のablation(単体追加 + leave-one-group-out)を実行")
    args = ap.parse_args()

    sb = tb.get_client()

    print("=" * 72)
    print("DOTレーティング step-2-2 本命モデル学習(LightGBM・読み取り専用)")
    print("=" * 72)

    use_extra = args.extra or args.ablation
    df, used_races = tb.load_dataset(sb, include_extra=use_extra)
    print(f"\n■ データ取得(SELECTのみ)")
    print(f"  学習可能レース : {used_races}")
    print(f"  艇行数         : {len(df)}")
    print("  月別           : " +
          ", ".join(f"{m}={n//6}R" for m, n in
                    df.groupby('month').size().items()))

    group_map = None
    if use_extra:
        df, feat_cols, group_map = tb.build_features(df, include_extra=True)
    else:
        df, feat_cols = tb.build_features(df)
    leaked = [c for c in feat_cols if c in tb.LEAK_BLACKLIST]
    print(f"\n■ 特徴量(リーク列除外済み・枠内相対化込み): {len(feat_cols)} 列")
    print(f"  リーク列混入チェック: "
          f"{'NG ' + str(leaked) if leaked else 'OK(結果系列なし)'}")
    # allowlist 検証: 特徴は BASE/相対派生/承認済み追加グループのみで構成されているか
    allow = set(tb.BASE_FEATURES)
    for f in tb.RELATIVE_FEATURES:
        allow.add(f + "_z"); allow.add(f + "_rank")
    if group_map is not None:
        for cols in group_map.values():
            allow.update(cols)
    not_allowed = [c for c in feat_cols if c not in allow]
    print(f"  allowlist検証      : "
          f"{'NG ' + str(not_allowed) if not_allowed else 'OK(許可特徴のみ)'}")
    if group_map is not None:
        print("  特徴グループ        : " +
              ", ".join(f"{k}({len(v)})" for k, v in group_map.items() if v))

    # リークガード: trainに使う月(4+5月)と検証側(6月)が排他であることを明示確認
    train_set = set(TRAIN_MONTHS)
    leak_month = TEST_MONTH in train_set
    months_present = sorted(df["month"].unique())
    print(f"\n■ train期間: {TRAIN_MONTHS} / 検証(test/OOF): {TEST_MONTH}")
    print(f"  リーク防止(test月をtrainに含めない): "
          f"{'NG(リークあり)' if leak_month else 'OK(排他)'}")

    out = {
        "model": "LightGBM",
        "lgb_params": LGB_PARAMS,
        "train_months": TRAIN_MONTHS,
        "test_month": TEST_MONTH,
        "months_present": months_present,
        "used_races": used_races, "n_boats": len(df),
        "n_features": len(feat_cols), "features": feat_cols,
        "extra_features": use_extra,
        "feature_groups": ({k: v for k, v in group_map.items()}
                           if group_map else None),
        "leak_free": (not leaked) and (not not_allowed) and (not leak_month),
        "missing_native": True,
        "logreg_reference": LOGREG_REF,
        "targets": {},
    }

    variants = [("native", False)]
    if args.with_impute:
        variants.append(("median_impute", True))

    for target in ["is_win", "is_top3"]:
        print("\n" + "=" * 72)
        print(f"■ 目的変数: {target}")
        print("=" * 72)
        out["targets"][target] = {}

        for vname, do_impute in variants:
            tag = "欠損ネイティブ" if not do_impute else "median補完"
            print("\n" + "-" * 72)
            print(f"[{tag}] 6月内 会場層化{args.folds}-fold / 4月+5月はtrain合流")
            print("-" * 72)
            fold_metrics, oof, imp_gain, imp_split = run_cv_lgb(
                df, feat_cols, target, n_folds=args.folds,
                seed=args.seed, impute_median=do_impute)
            for m in fold_metrics:
                print(f"  fold{m['fold']}: races={m['n_val_races']:3d} "
                      f"it={m['best_iteration']:4d} "
                      f"LogLoss={m['logloss']:.4f} AUC={m['auc']:.4f} "
                      f"Top1={m['top1_hit_rate']*100:5.1f}% "
                      f"3連単={m['trifecta_hit_rate']*100:4.1f}% "
                      f"回収={m['roi']*100:6.1f}%")
            agg = tb.aggregate(fold_metrics)
            print(f"  -- fold平均: LogLoss={agg['logloss']:.4f} "
                  f"AUC={agg['auc']:.4f} "
                  f"Top1={agg['top1_hit_rate']*100:.1f}% "
                  f"3連単={agg['trifecta_hit_rate']*100:.1f}% "
                  f"回収={agg['roi']*100:.1f}%")

            # 同一OOF(6月valid全集合)で apples-to-apples 比較
            dot_top1, _, _ = tb.eval_top1_hit(oof, "_score")
            dot_roi, dot_tri, _, _, _ = tb.eval_roi_trifecta(oof, "_score")
            base1 = tb.baseline_lane1(oof, target)
            base2 = tb.baseline_national(oof, target)
            ref = LOGREG_REF[target]

            print(f"\n  【同一OOF {oof['race_id'].nunique()}レース比較】"
                  f"  ({tag})")
            print(f"  {'モデル':28s} {'Top1':>8s} {'3連単':>8s} {'回収率':>8s}")
            print(f"  {'DOT LightGBM('+target+')':28s} "
                  f"{dot_top1*100:7.1f}% {dot_tri*100:7.1f}% {dot_roi*100:7.1f}%")
            print(f"  {'LogReg基準('+target+')':28s} "
                  f"{ref['top1_hit_rate']*100:7.1f}% "
                  f"{ref['trifecta_hit_rate']*100:7.1f}% {ref['roi']*100:7.1f}%")
            print(f"  {'(1) 1号ベタ':28s} "
                  f"{base1['top1_hit_rate']*100:7.1f}% "
                  f"{base1['trifecta_hit_rate']*100:7.1f}% {base1['roi']*100:7.1f}%")
            print(f"  {'(2) national_win_rate順':28s} "
                  f"{base2['top1_hit_rate']*100:7.1f}% "
                  f"{base2['trifecta_hit_rate']*100:7.1f}% {base2['roi']*100:7.1f}%")

            # 時系列ホールドアウト(5月->6月)
            holdout = run_holdout_lgb(df, feat_cols, target, impute_median=do_impute)
            print(f"\n  [時系列] 4月+5月{holdout['n_train_races']}R train "
                  f"-> 6月{holdout['n_val_races']}R valid: "
                  f"LogLoss={holdout['logloss']:.4f} AUC={holdout['auc']:.4f} "
                  f"Top1={holdout['top1_hit_rate']*100:.1f}% "
                  f"3連単={holdout['trifecta_hit_rate']*100:.1f}% "
                  f"回収={holdout['roi']*100:.1f}%")

            # 特徴量重要度(gain)上位
            top_gain = imp_gain.sort_values(ascending=False).head(15)
            print(f"\n  【特徴量重要度 gain 上位15】({tag})")
            for rank_i, (f, v) in enumerate(top_gain.items(), 1):
                print(f"   {rank_i:2d}. {f:30s} gain={v:12.1f} "
                      f"split={imp_split[f]:6.1f}")

            out["targets"][target][vname] = {
                "fold_metrics": fold_metrics,
                "cv_mean": agg,
                "oof_dot": {"top1_hit_rate": dot_top1,
                            "trifecta_hit_rate": dot_tri, "roi": dot_roi},
                "logreg_reference": ref,
                "baseline_lane1": base1,
                "baseline_national": base2,
                "holdout_may_to_jun": holdout,
                "oof_races": int(oof["race_id"].nunique()),
                "importance_gain": {k: float(v) for k, v in
                                    imp_gain.sort_values(ascending=False).items()},
                "importance_split": {k: float(v) for k, v in
                                     imp_split.sort_values(ascending=False).items()},
            }

        # ablation(グループ寄与 + 採用判定)。--ablation 指定時のみ。
        if args.ablation and group_map is not None:
            abl = run_ablation(df, group_map, target,
                               n_folds=args.folds, seed=args.seed)
            out["targets"][target]["ablation"] = abl
            adopted = [k for k, d in abl["decisions"].items() if d["adopt"]]
            rejected = [k for k, d in abl["decisions"].items() if not d["adopt"]]
            print(f"\n  >> 採用グループ: {adopted if adopted else '(なし)'}")
            print(f"  >> 不採用グループ: {rejected if rejected else '(なし)'}")

    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\nJSON 保存: {args.json}")

    print("\n[完了] 本番DBは SELECT のみ・書込なし。engine.py 不変更。")


if __name__ == "__main__":
    main()
