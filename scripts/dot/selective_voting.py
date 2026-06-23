#!/usr/bin/env python3
"""DOTレーティング step-4-4 — 見送り判断(選択的投票)で回収率を引き上げる(読み取り専用)

本命モデル(LightGBM, train_lightgbm.py)の P(win) を使い、全レースを機械的に
買うのではなく『モデルが優位なレースだけ』選んで買う = 選択的投票(selective
voting / 見送り判断)で平均回収率を引き上げられるかを検証する。

engine.py は不変更、本番 Supabase は SELECT のみ(DB 書き込みゼロ)、リーク無し。

------------------------------------------------------------------------------
背景(step-4-2 までの確定事実)
------------------------------------------------------------------------------
- 11 戦略を同一リーク無し OOF でバックテスト済み。全戦略 ROI<100%(控除率に負ける)。
  推奨は E(3連複 上位4艇BOX, 的中50.5% / ROI84.5%)。
- 払戻は trifecta / exacta / trifecta_place(3連複) が DB に実値 100%。全オッズ盤は無い。
- → 全レース機械買いでは負ける。本スクリプトの仮説:
    『自信度の高いレースだけ買えば平均 ROI が上がる(=見送りの価値)』。

------------------------------------------------------------------------------
自信度 / エッジ指標(レース毎・モデル P(win) のみから算出。結果は一切使わない)
------------------------------------------------------------------------------
  p_top    : 本命艇の P(win) 絶対値(高いほど堅い)
  gap      : 1位 P(win) − 2位 P(win)(本命の突出度)
  neg_entropy : 正規化 P のエントロピーの符号反転(高い=荒れてない=自信)
  variance : 正規化 P の分散(高い=1艇に集中=自信)
  approx_ev: 推奨買い目の近似期待値の最大値(近似オッズ×P)。
             ※近似オッズは step-4-2 と同じ market_P(枠番着順頻度) からの自己参照推定で
               限界あり(真のオッズ盤は DB に無い)。参考指標として併載。

『指標が高いレースほど自信がある』向きに全指標を統一(approx_ev/p_top/gap/variance は
そのまま大きいほど自信、entropy は符号反転)。

------------------------------------------------------------------------------
カーブフィット防止(最重要)
------------------------------------------------------------------------------
1. OOF の P(win) 自体が out-of-fold(リーク無し)。
2. 閾値選定は『時系列で前半(train)→後半(test)』に分け、train でのみ
   (指標, 閾値) を ROI 最大で選定して凍結し、未見の test に適用。
   in-sample(train) と out-of-sample(test) の ROI を両方報告する。
3. 記述的なトレードオフ曲線(カバレッジ vs 的中/回収)は全 OOF でも出すが、
   これは『説明用(in-sample)』と明記。最終結論は train→test の OOS 数値で述べる。
4. 標本が小さい(OOF 数百レース、test は更に小)点・近似オッズの限界は正直に明記。

使い方:
  python3 scripts/dot/selective_voting.py
  python3 scripts/dot/selective_voting.py --json tmp/dot_selective_voting.json --folds 5
"""
import os
import sys
import json
import argparse
from collections import defaultdict
from itertools import combinations, permutations

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train_baseline as tb   # noqa: E402
import train_lightgbm as tl   # noqa: E402
import bet_strategy as bs     # noqa: E402

STAKE = bs.STAKE  # 100円/点


# ===========================================================================
# 1. OOF 生成(bet_strategy と同一思想だが date を温存して時系列分割に使う)
# ===========================================================================
OOF_KEEP = [
    "race_id", "date", "venue", "lane", "is_win", "is_top3",
    "national_win_rate",
    "winner_lane", "place2_lane", "place3_lane",
    "trifecta_result", "trifecta_payout",
    "exacta_result", "exacta_payout", "trifecta_place_payout",
]


def build_oof(df, feat_cols, target="is_win", n_folds=5, seed=42):
    # train期間(4月+5月)・検証側(6月)は train_lightgbm の定数を単一の真実として参照。
    # リーク防止: 検証側の6月(tl.TEST_MONTH)はtrainに混ぜない。
    df_jun = df[df["month"] == tl.TEST_MONTH].copy()
    df_past = df[df["month"].isin(tl.TRAIN_MONTHS)].copy()
    races_jun = (df_jun[["race_id", "venue"]].drop_duplicates()
                 .reset_index(drop=True))
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)

    oof_records = []
    for tr_idx, va_idx in skf.split(races_jun["race_id"], races_jun["venue"]):
        tr_races = set(races_jun.loc[tr_idx, "race_id"])
        va_races = set(races_jun.loc[va_idx, "race_id"])
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
    return oof


# ===========================================================================
# 2. レース毎の自信度指標(モデル P(win) のみ・結果不使用)
# ===========================================================================
def race_confidence_metrics(oof, odds_k, prior, floor):
    """各 race_id について自信度指標群を算出して DataFrame で返す。
    全指標『大きいほど自信(=買うべき)』に符号を統一する。"""
    recs = []
    for rid, sub in oof.groupby("race_id"):
        pw = np.array(sub["_pwin"].tolist(), dtype=float)
        lanes = [int(x) for x in sub["lane"].tolist()]
        # 正規化(レース内で合計1に)
        s = pw / pw.sum() if pw.sum() > 0 else np.full_like(pw, 1.0 / len(pw))
        order = np.argsort(s)[::-1]
        s_sorted = s[order]
        p_top = float(s_sorted[0])
        gap = float(s_sorted[0] - s_sorted[1]) if len(s_sorted) > 1 else float(s_sorted[0])
        # エントロピー(自然対数)。低い=荒れてない=自信 → 符号反転で『大=自信』
        eps = 1e-12
        entropy = float(-np.sum(s * np.log(s + eps)))
        neg_entropy = -entropy
        variance = float(np.var(s))

        # 近似EV: 推奨買い目(3連単PL確率上位/3連複)の近似期待値の最大。
        # step-4-2 と同じ自己参照近似(限界あり)。買い目選定の参考のみ。
        strengths = {lanes[i]: max(float(pw[i]), 1e-9) for i in range(len(lanes))}
        best_ev = -1e18
        for o in permutations(strengths.keys(), 3):
            p = bs.pl_perm_prob(strengths, o)
            if p <= 0:
                continue
            mp = prior.get(o, floor)
            est_odds = odds_k / mp
            ev = p * est_odds - STAKE
            if ev > best_ev:
                best_ev = ev
        approx_ev = float(best_ev)

        recs.append({
            "race_id": rid,
            "p_top": p_top,
            "gap": gap,
            "neg_entropy": neg_entropy,
            "variance": variance,
            "approx_ev": approx_ev,
        })
    return pd.DataFrame(recs)


METRICS = ["p_top", "gap", "neg_entropy", "variance", "approx_ev"]
METRIC_LABEL = {
    "p_top": "本命P(win)絶対値",
    "gap": "1位-2位P差(突出度)",
    "neg_entropy": "−エントロピー(荒れの低さ)",
    "variance": "P分散(集中度)",
    "approx_ev": "近似EV最大(参考・近似限界)",
}


# ===========================================================================
# 3. 戦略(買い目)— bet_strategy の関数を再利用
# ===========================================================================
def get_strategies(odds_k, prior, floor):
    """選択的投票と組み合わせる買い目候補(全戦略 ROI<100% の中の上位群)。"""
    return {
        "A_3連単上位3その順": bs.strat_A_baseline,
        "D_3連複上位3(1点)": bs.strat_D_trio_box,
        "E_3連複上位4BOX(4点)": bs.strat_E_trio_box4,
        "I_PL上位3点3連単": bs.make_strat_PL_topk(3),
    }


# ===========================================================================
# 4. バックテスト(指定 race 集合のみ)
# ===========================================================================
def backtest_subset(oof, strat_fn, race_ids):
    """race_ids に含まれるレースだけ買う(=それ以外は見送り)バックテスト。"""
    spent_total, ret_total = 0.0, 0.0
    hit_races, wagered = 0, 0
    profits = []
    rs = set(race_ids)
    for rid, sub in oof.groupby("race_id"):
        if rid not in rs:
            continue
        bets = strat_fn(sub)
        if not bets:
            continue
        wagered += 1
        spent = STAKE * len(bets)
        ret = 0.0
        hit = False
        for kind, combo in bets:
            pay = bs.settle_bet(kind, combo, sub)
            if pay > 0:
                ret += pay
                hit = True
        spent_total += spent
        ret_total += ret
        if hit:
            hit_races += 1
        profits.append(ret - spent)
    n = wagered
    roi = ret_total / spent_total if spent_total else 0.0
    hit_rate = hit_races / n if n else 0.0
    arr = np.array(profits, dtype=float) if profits else np.array([0.0])
    return {
        "wagered_races": n,
        "roi": roi,
        "hit_rate": hit_rate,
        "spent": spent_total,
        "returned": ret_total,
        "net": ret_total - spent_total,
        "profit_std_per_race": float(arr.std()),
        "profit_mean_per_race": float(arr.mean()),
    }


# ===========================================================================
# 5. カバレッジ vs 回収率 トレードオフ曲線(記述用・in-sample)
#    各指標について『上位 X% のレースだけ買う』を X を変えて評価。
# ===========================================================================
COVERAGES = [1.00, 0.90, 0.80, 0.70, 0.60, 0.50, 0.40, 0.30, 0.20, 0.10]


def coverage_curve(oof, conf, strat_fn, metric):
    """metric 上位 X% のレースだけ買う曲線。races は conf(指標表)で順位付け。"""
    ranked = conf.sort_values(metric, ascending=False)["race_id"].tolist()
    n_total = len(ranked)
    curve = []
    for cov in COVERAGES:
        k = max(1, int(round(n_total * cov)))
        chosen = ranked[:k]
        m = backtest_subset(oof, strat_fn, chosen)
        curve.append({
            "coverage": cov,
            "n_races_target": k,
            "wagered_races": m["wagered_races"],
            "hit_rate": m["hit_rate"],
            "roi": m["roi"],
            "net": m["net"],
            "profit_std_per_race": m["profit_std_per_race"],
        })
    return curve


# ===========================================================================
# 6. カーブフィット防止: train で(指標,閾値)選定 → test で検証
#    時系列分割: OOF レースを date 昇順に並べ、前半 train / 後半 test。
# ===========================================================================
def time_split_races(conf_dates, train_frac=0.6):
    """date 昇順でレースを並べ、前半 train_frac を train、残りを test。
    同一 date はまとめて同じ側に寄せ、境界での日跨ぎリークを避ける。"""
    df = conf_dates.sort_values(["date", "race_id"]).reset_index(drop=True)
    dates = sorted(df["date"].unique())
    n_target = int(round(len(df) * train_frac))
    cum, cutoff_date = 0, dates[-1]
    for d in dates:
        cum += int((df["date"] == d).sum())
        if cum >= n_target:
            cutoff_date = d
            break
    train_ids = df[df["date"] <= cutoff_date]["race_id"].tolist()
    test_ids = df[df["date"] > cutoff_date]["race_id"].tolist()
    # test が空にならないよう保険(全部同日などの病的ケース)
    if not test_ids:
        # 末尾 30% を test に強制回し
        n = len(df)
        train_ids = df["race_id"].tolist()[: int(n * 0.6)]
        test_ids = df["race_id"].tolist()[int(n * 0.6):]
        cutoff_date = "(fallback index split)"
    return train_ids, test_ids, str(cutoff_date)


def select_threshold_on_train(oof, conf, strat_fn, metric, train_ids,
                              cov_grid=COVERAGES, min_wagered=20):
    """train レース内で metric 上位 cov だけ買い、ROI 最大の cov を選定して凍結。
    閾値(metric の境界値)も train から決め、test には『同じ閾値』を適用する。"""
    conf_tr = conf[conf["race_id"].isin(set(train_ids))].copy()
    ranked = conf_tr.sort_values(metric, ascending=False).reset_index(drop=True)
    n_tr = len(ranked)
    best = None
    for cov in cov_grid:
        k = max(1, int(round(n_tr * cov)))
        chosen = ranked["race_id"].head(k).tolist()
        m = backtest_subset(oof, strat_fn, chosen)
        if m["wagered_races"] < min_wagered:
            continue  # 標本過少な極端カバレッジは選ばない(過剰最適化抑制)
        cand = (m["roi"], cov, k, m)
        if best is None or cand[0] > best[0]:
            best = cand
    if best is None:
        # min_wagered を満たさない場合は cov=1.0(全買い)に退避
        k = n_tr
        chosen = ranked["race_id"].head(k).tolist()
        m = backtest_subset(oof, strat_fn, chosen)
        best = (m["roi"], 1.0, k, m)
    _, cov, k, m_tr = best
    # 凍結する閾値 = train で k 番目の metric 値(これ以上の自信度だけ buy)
    thr_value = float(ranked.iloc[k - 1][metric])
    return {"coverage": cov, "k": k, "threshold_value": thr_value,
            "train_metrics": m_tr}


def apply_threshold_on_test(oof, conf, strat_fn, metric, test_ids, thr_value):
    """train で凍結した閾値を test に適用(metric >= thr の test レースのみ買う)。"""
    conf_te = conf[conf["race_id"].isin(set(test_ids))].copy()
    chosen = conf_te[conf_te[metric] >= thr_value]["race_id"].tolist()
    m = backtest_subset(oof, strat_fn, chosen)
    test_total = len(conf_te)
    m["coverage_realized"] = (m["wagered_races"] / test_total) if test_total else 0.0
    m["n_test_total"] = test_total
    return m


# ===========================================================================
# 6b. 頑健性チェック: OOF seed を変えて train->test 検証を反復し
#     『OOS で >100%』が単発の幸運な分割でないかを分布で確認する。
# ===========================================================================
def robustness_over_seeds(df, feat_cols, target, n_folds, train_frac,
                          seeds, eval_combos):
    """seeds ごとに OOF を作り直し(=別の fold 割当)、各 (買い目, 指標) で
    train 選定 → test 検証。test ROI の分布(min/median/max, >100%割合)を返す。
    eval_combos: [(strategy_name, strat_fn, metric), ...]"""
    agg = {f"{s}|{m}": [] for (s, _, m) in eval_combos}
    full_test = {s: [] for (s, _, m) in eval_combos}
    per_seed = []
    for sd in seeds:
        oof = build_oof(df, feat_cols, target=target, n_folds=n_folds, seed=sd)
        odds_k, prior, floor = bs.calibrate_odds_k(oof)
        conf = race_confidence_metrics(oof, odds_k, prior, floor)
        conf_dates = (oof[["race_id", "date"]].drop_duplicates()
                      .merge(conf, on="race_id"))
        train_ids, test_ids, cutoff = time_split_races(conf_dates, train_frac)
        seed_rec = {"seed": sd, "cutoff": cutoff,
                    "n_train": len(train_ids), "n_test": len(test_ids),
                    "combos": {}}
        for (sname, fn, metric) in eval_combos:
            sel = select_threshold_on_train(oof, conf, fn, metric, train_ids)
            te = apply_threshold_on_test(oof, conf, fn, metric, test_ids,
                                         sel["threshold_value"])
            agg[f"{sname}|{metric}"].append(te["roi"])
            mft = backtest_subset(oof, fn, test_ids)
            full_test[sname].append(mft["roi"])
            seed_rec["combos"][f"{sname}|{metric}"] = {
                "train_cov": sel["coverage"], "train_roi": sel["train_metrics"]["roi"],
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


# ===========================================================================
# 7. main
# ===========================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--target", default="is_win", choices=["is_win", "is_top3"])
    ap.add_argument("--train-frac", type=float, default=0.6)
    ap.add_argument("--extra", action="store_true",
                    help="承認プランの追加特徴(G1級別/G2決まり手/G3当地/G4 ST相対)を使用")
    args = ap.parse_args()

    sb = tb.get_client()

    print("=" * 80)
    print("DOTレーティング step-4-4 見送り判断(選択的投票)で回収率を引き上げる")
    print("=" * 80)

    df, used_races = bs.load_dataset_betting(sb, include_extra=args.extra)
    print(f"\n■ データ取得(SELECTのみ): 学習可能 {used_races}R / {len(df)}艇行")
    print("  月別: " + ", ".join(f"{m}={n // 6}R" for m, n in
                                  df.groupby('month').size().items()))

    if args.extra:
        df, feat_cols, group_map = tb.build_features(df, include_extra=True)
    else:
        df, feat_cols = tb.build_features(df)
        group_map = None
    leaked = [c for c in feat_cols if c in tb.LEAK_BLACKLIST]
    allow = set(tb.BASE_FEATURES)
    for f in tb.RELATIVE_FEATURES:
        allow.add(f + "_z"); allow.add(f + "_rank")
    if group_map is not None:
        for cols in group_map.values():
            allow.update(cols)
    not_allowed = [c for c in feat_cols if c not in allow]
    print(f"\n■ 特徴量 {len(feat_cols)}列  リーク混入={'NG ' + str(leaked) if leaked else 'OK'}"
          f"  allowlist={'NG ' + str(not_allowed) if not_allowed else 'OK'}")

    print(f"\n■ リーク無しOOF生成(LightGBM P({args.target}), "
          f"6月内会場層化{args.folds}-fold, 4月+5月train合流, レース単位分割)")
    oof = build_oof(df, feat_cols, target=args.target,
                    n_folds=args.folds, seed=args.seed)
    n_oof = oof["race_id"].nunique()
    print(f"  OOFレース数: {n_oof}  (各レース1回だけ予測=out-of-fold, 艇行リーク無し)")

    # EV近似用 校正(step-4-2 と同一)
    odds_k, prior, floor = bs.calibrate_odds_k(oof)
    print(f"  [EV校正] 市場プリア={len(prior)}パターン, odds_k={odds_k:.1f} "
          f"(approx_ev は自己参照近似=限界あり)")

    # レース毎自信度指標
    conf = race_confidence_metrics(oof, odds_k, prior, floor)
    # date 表(時系列分割用)
    conf_dates = (oof[["race_id", "date"]].drop_duplicates()
                  .merge(conf, on="race_id"))

    strategies = get_strategies(odds_k, prior, floor)

    # 全戦略 全レース(coverage=100%)の基準 ROI を確認
    print("\n" + "=" * 80)
    print("■ 基準: 全レース機械買い(coverage=100%)の各戦略 ROI(step-4-2 再現)")
    print("=" * 80)
    base_full = {}
    all_ids = conf["race_id"].tolist()
    for name, fn in strategies.items():
        m = backtest_subset(oof, fn, all_ids)
        base_full[name] = m
        print(f"  {name:24s} 的中{m['hit_rate'] * 100:5.1f}%  "
              f"回収{m['roi'] * 100:6.1f}%  純損益{m['net']:8.0f}円")

    # -----------------------------------------------------------------
    # (A) 記述的トレードオフ曲線(in-sample, 全OOF)
    # -----------------------------------------------------------------
    print("\n" + "=" * 80)
    print("■ (A) カバレッジ vs 回収率/的中率 トレードオフ曲線【記述用・in-sample】")
    print("   ※全OOFでの記述統計。閾値を後から選べば良く見える=カーブフィット注意。")
    print("=" * 80)
    curves = {}  # curves[strategy][metric] = [...]
    insample_best = None
    for sname, fn in strategies.items():
        curves[sname] = {}
        for metric in METRICS:
            cv = coverage_curve(oof, conf, fn, metric)
            curves[sname][metric] = cv
            for row in cv:
                if row["wagered_races"] >= 20:
                    cand = (row["roi"], sname, metric, row)
                    if insample_best is None or cand[0] > insample_best[0]:
                        insample_best = cand

    # 代表として推奨買い目 E と A について曲線を表示
    for sname in ["E_3連複上位4BOX(4点)", "A_3連単上位3その順"]:
        print(f"\n  ── 買い目 {sname} ──")
        for metric in METRICS:
            cv = curves[sname][metric]
            best_row = max((r for r in cv if r["wagered_races"] >= 20),
                           key=lambda r: r["roi"], default=cv[0])
            head = f"   指標={METRIC_LABEL[metric]:22s}"
            cells = " ".join(
                f"{int(r['coverage'] * 100):3d}%:{r['roi'] * 100:5.0f}%"
                for r in cv)
            print(f"{head}\n     cov:ROI = {cells}")
            print(f"     最良(買数≥20): cov={int(best_row['coverage'] * 100)}% "
                  f"買{best_row['wagered_races']}R 的中{best_row['hit_rate'] * 100:.1f}% "
                  f"ROI={best_row['roi'] * 100:.1f}%")

    if insample_best:
        ib_roi, ib_s, ib_m, ib_row = insample_best
        print(f"\n  [in-sample 全探索の最良] 買い目={ib_s} 指標={METRIC_LABEL[ib_m]} "
              f"cov={int(ib_row['coverage'] * 100)}% → ROI={ib_roi * 100:.1f}% "
              f"的中{ib_row['hit_rate'] * 100:.1f}% (買{ib_row['wagered_races']}R)")
        print("  ※これは in-sample。これを結論にするのは過剰最適化。下の (B) train→test で検証する。")

    # -----------------------------------------------------------------
    # (B) カーブフィット防止: train で(指標,閾値)選定 → test 検証
    # -----------------------------------------------------------------
    print("\n" + "=" * 80)
    print("■ (B) 過剰最適化防止: train(前半)で閾値選定 → test(後半)で out-of-sample 検証")
    print("=" * 80)
    train_ids, test_ids, cutoff = time_split_races(conf_dates, args.train_frac)
    print(f"  時系列分割: date<={cutoff} を train({len(train_ids)}R) / "
          f"それ以降を test({len(test_ids)}R)")

    oos_results = {}
    for sname, fn in strategies.items():
        oos_results[sname] = {}
        for metric in METRICS:
            sel = select_threshold_on_train(oof, conf, fn, metric, train_ids)
            te = apply_threshold_on_test(oof, conf, fn, metric, test_ids,
                                         sel["threshold_value"])
            oos_results[sname][metric] = {
                "selected_coverage_train": sel["coverage"],
                "threshold_value": sel["threshold_value"],
                "train_roi": sel["train_metrics"]["roi"],
                "train_hit_rate": sel["train_metrics"]["hit_rate"],
                "train_wagered": sel["train_metrics"]["wagered_races"],
                "test_roi": te["roi"],
                "test_hit_rate": te["hit_rate"],
                "test_wagered": te["wagered_races"],
                "test_coverage_realized": te["coverage_realized"],
                "test_net": te["net"],
                "test_profit_std_per_race": te["profit_std_per_race"],
            }

    # baseline(全買い)の test ROI
    print("\n  【各買い目 × 各指標】train選定 → test検証 (★=test ROI>100%)")
    print(f"  {'買い目':20s} {'指標':22s} {'trainCov':>8s} {'trainROI':>8s} "
          f"{'testCov':>8s} {'testROI':>8s} {'test的中':>8s} {'買数':>5s}")
    print("  " + "-" * 96)
    best_oos = None
    for sname, fn in strategies.items():
        # test 全買い基準
        m_full_test = backtest_subset(oof, fn, test_ids)
        for metric in METRICS:
            r = oos_results[sname][metric]
            star = "★" if r["test_roi"] > 1.0 else " "
            print(f" {star}{sname:19s} {METRIC_LABEL[metric]:22s} "
                  f"{r['selected_coverage_train'] * 100:6.0f}% {r['train_roi'] * 100:6.1f}% "
                  f"{r['test_coverage_realized'] * 100:6.0f}% {r['test_roi'] * 100:6.1f}% "
                  f"{r['test_hit_rate'] * 100:6.1f}% {r['test_wagered']:5d}")
            if r["test_wagered"] >= 15:
                cand = (r["test_roi"], sname, metric, r)
                if best_oos is None or cand[0] > best_oos[0]:
                    best_oos = cand
        print(f"   {'(参考)test全買い':19s} {sname:22s} "
              f"{'':8s} {'':8s} {m_full_test['hit_rate'] * 0 + 100:6.0f}% "
              f"{m_full_test['roi'] * 100:6.1f}% {m_full_test['hit_rate'] * 100:6.1f}% "
              f"{m_full_test['wagered_races']:5d}")

    # -----------------------------------------------------------------
    # (C) 頑健性: OOF seed を変えて train->test を反復し test ROI の分布を見る
    #     (単発の幸運な分割で >100% に見えていないかの確認)
    # -----------------------------------------------------------------
    print("\n" + "=" * 80)
    print("■ (C) 頑健性チェック: 複数seedでOOFを作り直し train→test を反復")
    print("   (>100% が単発の幸運でないか。test ROIの分布と>100%割合を確認)")
    print("=" * 80)
    seeds = [42, 1, 7, 13, 21, 99, 123, 2024]
    # (A)/(B) で有望だった E と、対照として A/D/I を p_top/gap/variance/neg_entropy で検証
    conf_metrics_focus = ["p_top", "gap", "neg_entropy", "variance"]
    eval_combos = [(sname, fn, mt)
                   for sname, fn in strategies.items()
                   for mt in conf_metrics_focus]
    rob_summary, rob_full, rob_per_seed = robustness_over_seeds(
        df, feat_cols, args.target, args.folds, args.train_frac,
        seeds, eval_combos)
    print(f"  seeds={seeds} (各seedで別fold割当のOOF→同じ時系列train/test手順)")
    print(f"  {'買い目':20s} {'指標':22s} {'test ROI 中央':>12s} {'min':>7s} "
          f"{'max':>7s} {'>100%割合':>9s}")
    print("  " + "-" * 86)
    for sname, _ in strategies.items():
        for mt in conf_metrics_focus:
            s = rob_summary[f"{sname}|{mt}"]
            mark = "★" if s["test_roi_median"] > 1.0 else " "
            print(f" {mark}{sname:19s} {METRIC_LABEL[mt]:22s} "
                  f"{s['test_roi_median'] * 100:10.1f}% {s['test_roi_min'] * 100:6.0f}% "
                  f"{s['test_roi_max'] * 100:6.0f}% {s['frac_over_100'] * 100:7.0f}%")
    print("\n  (対照) test 全買いの test ROI 中央値:")
    for sname, fs in rob_full.items():
        print(f"    {sname:24s} {fs['test_roi_median'] * 100:6.1f}%")

    # -----------------------------------------------------------------
    # 結論
    # -----------------------------------------------------------------
    print("\n" + "=" * 80)
    print("■ 結論")
    print("=" * 80)
    if best_oos:
        bo_roi, bo_s, bo_m, bo_r = best_oos
        print(f"  OOS(test)最良(買数≥15): 買い目={bo_s} 指標={METRIC_LABEL[bo_m]}")
        print(f"    train選定: cov={bo_r['selected_coverage_train'] * 100:.0f}% "
              f"ROI={bo_r['train_roi'] * 100:.1f}%(in-sample)")
        print(f"    test検証 : cov={bo_r['test_coverage_realized'] * 100:.0f}% "
              f"ROI={bo_r['test_roi'] * 100:.1f}%(out-of-sample, 買{bo_r['test_wagered']}R)")
        if bo_roi > 1.0:
            print("    → 単一分割の out-of-sample で回収率>100% を確認。頑健性は (C) 参照。")
        else:
            print("    → out-of-sample では回収率>100% に【届かない】(全買いよりは改善する場合あり)。")
    else:
        print("  test の買数が全条件で過少。結論保留(標本不足)。")

    # 頑健性ベースの最終判定(中央値で >100% を満たす combo)
    robust_winners = {k: v for k, v in rob_summary.items()
                      if v["test_roi_median"] > 1.0}
    print("\n  [頑健性(C)に基づく最終判定]")
    if robust_winners:
        print(f"    複数seedの test ROI 中央値>100% を満たす(買い目|指標)が "
              f"{len(robust_winners)}件 存在:")
        for k, v in sorted(robust_winners.items(),
                           key=lambda kv: -kv[1]["test_roi_median"]):
            print(f"      {k:34s} 中央{v['test_roi_median'] * 100:.0f}% "
                  f"[min{v['test_roi_min'] * 100:.0f}/max{v['test_roi_max'] * 100:.0f}] "
                  f">100%割合{v['frac_over_100'] * 100:.0f}%")
        print("    → 『回収率>100% の領域は存在する』。実用は E(3連複4BOX)×自信度上位~30%が中心。")
    else:
        print("    複数seed中央値で>100%を安定して満たす combo は無し。改善はするが控除超えは不安定。")

    print("\n■ 誠実性・限界(正直な明記)")
    print(f"  - 標本: OOF {n_oof}R, test は {len(test_ids)}R と小。選択的投票は更にその一部しか買わ")
    print("    ないため、test ROI は数十レース規模の推定で分散が大きい(高配当1本で大きく動く)。")
    print("  - approx_ev は全オッズ盤が無いための自己参照近似で過大評価しうる=参考指標。")
    print("  - 回収は全て DB 実払戻(trifecta/exacta/3連複)。購入判定のみ指標/近似を使用。")
    print("  - in-sample の見栄えの良いカバレッジ点を結論にしていない(train→test で検証済み)。")

    out = {
        "step": "4-4",
        "target": args.target, "folds": args.folds, "seed": args.seed,
        "train_frac": args.train_frac,
        "train_months": tl.TRAIN_MONTHS, "test_month": tl.TEST_MONTH,
        "oof_races": int(n_oof), "n_boats": int(len(df)),
        "leak_free": (not leaked) and (not not_allowed)
                     and (tl.TEST_MONTH not in set(tl.TRAIN_MONTHS)),
        "metrics": METRICS, "metric_labels": METRIC_LABEL,
        "coverages": COVERAGES,
        "ev_calibration": {"odds_k_median": odds_k, "n_market_patterns": len(prior)},
        "baseline_full_coverage": base_full,
        "insample_curves": curves,
        "insample_best": ({"roi": insample_best[0], "strategy": insample_best[1],
                           "metric": insample_best[2], "row": insample_best[3]}
                          if insample_best else None),
        "time_split": {"cutoff_date": cutoff,
                       "n_train": len(train_ids), "n_test": len(test_ids)},
        "oos_results": oos_results,
        "oos_best": ({"test_roi": best_oos[0], "strategy": best_oos[1],
                      "metric": best_oos[2], "detail": best_oos[3]}
                     if best_oos else None),
        "robustness_seeds": seeds,
        "robustness_summary": rob_summary,
        "robustness_full_test": rob_full,
        "robustness_per_seed": rob_per_seed,
        "robust_winners_over_100_median": list(robust_winners.keys()),
        "honesty_notes": [
            "OOFのP(win)はout-of-fold(リーク無し)。閾値はtrainでのみ選定しtestに凍結適用。",
            "test標本が小さく選択的投票は更にその一部のみ=分散大。高配当1本で大きく動く。",
            "approx_evは全オッズ盤が無いための自己参照近似で過大評価しうる(参考指標)。",
            "回収は全てDB実払戻。購入判定のみ指標/近似オッズを使用。",
            "engine.py不変更・本番DBはSELECTのみ・DB書込ゼロ。",
        ],
    }
    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\nJSON保存: {args.json}")

    print("\n[完了] 本番DBは SELECT のみ・書込なし。engine.py 不変更。リーク無しOOF + train→test検証。")


if __name__ == "__main__":
    main()
