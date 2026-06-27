#!/usr/bin/env python3
"""DOTレーティング step-3-1 — ホールドアウトバックテスト検証(読み取り専用)

LightGBMモデルと選択的投票戦略をホールドアウトデータでバックテストし、
実戦性能を数値評価する。

設計:
  1. データ現状確認: Supabase DBの現在のレース数・期間
  2. 時系列ホールドアウト: 4月+5月(train) → 6月(test) の完全未来リーク排除
  3. 評価対象:
     a) LightGBM単体: Top1的中率、Top3的中率、AUC
     b) 買い目戦略E(3連複上位4艇BOX): 的中率、回収率(ROI)
     c) 選択的投票(見送り判断付き): 的中率、回収率(ROI)、見送り率
  4. ベースライン比較: 1号ベタ買い
  5. 会場別・条件別の分析

制約:
  - DB書込み一切なし(SELECT専用)
  - engine.pyに触らない
  - 回収は全てDB実払戻

使い方:
  python3 scripts/dot/backtest_holdout.py
  python3 scripts/dot/backtest_holdout.py --json tmp/dot_backtest.json
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train_baseline as tb   # noqa: E402
import train_lightgbm as tl   # noqa: E402
import bet_strategy as bs     # noqa: E402

STAKE = bs.STAKE  # 100円/点


# ===========================================================================
# 1. データ現状確認
# ===========================================================================
def data_inventory(sb):
    """DB内のレース数・期間を確認(SELECT専用)。"""
    races = tb.fetch_all(sb, "races", "id,date,venue,race_no")
    boats = tb.fetch_all(sb, "boats", "id,race_id")
    rwl = tb.fetch_all(
        sb, "race_winner_log",
        "date,venue,race_no,winner_lane,trifecta_result",
        order_col="race_key",
    )
    # 期間
    dates = sorted(set(r["date"] for r in races if r.get("date")))
    # 月別集計
    month_counts = defaultdict(int)
    for r in races:
        if r.get("date"):
            month_counts[r["date"][:7]] += 1
    # 会場一覧
    venues = sorted(set(r["venue"] for r in races if r.get("venue")))
    # rwl で結果あり
    rwl_valid = sum(1 for r in rwl if r.get("trifecta_result"))

    return {
        "n_races": len(races),
        "n_boats": len(boats),
        "n_rwl": len(rwl),
        "n_rwl_valid": rwl_valid,
        "date_min": dates[0] if dates else None,
        "date_max": dates[-1] if dates else None,
        "months": dict(sorted(month_counts.items())),
        "n_venues": len(venues),
        "venues": venues,
    }


# ===========================================================================
# 2. 時系列ホールドアウト: 4月+5月(train) → 6月(test)
#    完全な未来リーク排除: 6月データは一切trainに含めない
# ===========================================================================
def holdout_predict(df, feat_cols, target="is_win"):
    """4月+5月で学習 → 6月全体で予測。OOFではなく純粋なホールドアウト。"""
    df_train = df[df["month"].isin(tl.TRAIN_MONTHS)].copy()
    df_test = df[df["month"] == tl.TEST_MONTH].copy()

    booster = tl.train_lgb(
        df_train[feat_cols], df_train[target],
        df_test[feat_cols], df_test[target],
        impute_median=False,
    )
    proba = booster.predict(df_test[feat_cols],
                            num_iteration=booster.best_iteration)
    df_test = df_test.assign(_pwin=proba)
    return df_test, booster


# ===========================================================================
# 3. 評価関数群
# ===========================================================================
def eval_classification(df_test, target="is_win"):
    """分類指標: Top1的中率、Top3的中率、AUC、LogLoss。"""
    y = df_test[target].to_numpy()
    p = df_test["_pwin"].to_numpy()
    ll = float(log_loss(y, p, labels=[0, 1]))
    auc = float(roc_auc_score(y, p))
    top1, hit1, tot = tb.eval_top1_hit(df_test, "_pwin")

    # Top3的中率: 各レースで_pwin上位3艇が実際のTop3に何艇含まれるか
    top3_hit, top3_tot = 0, 0
    for rid, sub in df_test.groupby("race_id"):
        top3_tot += 1
        pred_top3 = set(sub.nlargest(3, "_pwin")["lane"].tolist())
        actual_top3 = set(sub[sub["is_top3"] == 1]["lane"].tolist())
        if pred_top3 == actual_top3:
            top3_hit += 1
    top3_rate = top3_hit / top3_tot if top3_tot else 0.0

    return {
        "logloss": ll, "auc": auc,
        "top1_hit_rate": top1, "top1_hit": int(hit1), "n_races": int(tot),
        "top3_exact_rate": top3_rate, "top3_hit": top3_hit,
    }


def eval_baseline_lane1(df_test):
    """1号ベタ: 1号頭固定。"""
    tmp = df_test.assign(_pwin=-df_test["lane"].astype(float))
    top1, hit1, tot = tb.eval_top1_hit(tmp, "_pwin")
    m = bs.backtest(tmp, bs.strat_lane1)
    # 3連複上位4BOX(1号ベタ版 = 1-2-3-4号BOX)
    def lane1_trio_box4(sub):
        return [("trio", tuple(sorted(c))) for c in combinations([1, 2, 3, 4], 3)]
    m_trio = bs.backtest(tmp, lane1_trio_box4)
    return {
        "top1_hit_rate": top1, "top1_hit": int(hit1), "n_races": int(tot),
        "trifecta_roi": m["roi"], "trifecta_hit_rate": m["hit_rate"],
        "trio_box4_roi": m_trio["roi"], "trio_box4_hit_rate": m_trio["hit_rate"],
    }


def eval_strategy_E(df_test):
    """戦略E: 3連複上位4艇BOX(4点)。"""
    m = bs.backtest(df_test, bs.strat_E_trio_box4)
    return m


def eval_selective_voting(df_test, coverages=None):
    """選択的投票: P_top上位のレースのみ購入。"""
    if coverages is None:
        coverages = [1.0, 0.8, 0.6, 0.5, 0.4, 0.3, 0.2]

    # レース毎のP_top(本命艇の正規化P(win))
    conf_recs = []
    for rid, sub in df_test.groupby("race_id"):
        pw = sub["_pwin"].to_numpy(dtype=float)
        s = pw / pw.sum() if pw.sum() > 0 else np.full_like(pw, 1.0 / len(pw))
        s_sorted = np.sort(s)[::-1]
        p_top = float(s_sorted[0])
        gap = float(s_sorted[0] - s_sorted[1]) if len(s_sorted) > 1 else float(s_sorted[0])
        conf_recs.append({"race_id": rid, "p_top": p_top, "gap": gap})
    conf = pd.DataFrame(conf_recs)

    ranked = conf.sort_values("p_top", ascending=False)["race_id"].tolist()
    n_total = len(ranked)

    results = []
    for cov in coverages:
        k = max(1, int(round(n_total * cov)))
        chosen = set(ranked[:k])
        sub_test = df_test[df_test["race_id"].isin(chosen)]
        m = bs.backtest(sub_test, bs.strat_E_trio_box4)
        skip_rate = 1.0 - (m["wagered_races"] / n_total) if n_total else 0.0
        results.append({
            "coverage": cov,
            "n_target": k,
            "wagered_races": m["wagered_races"],
            "skip_rate": skip_rate,
            "hit_rate": m["hit_rate"],
            "roi": m["roi"],
            "net": m["net"],
            "spent": m["spent"],
            "returned": m["returned"],
        })
    return results, conf


# ===========================================================================
# 4. 会場別分析
# ===========================================================================
def venue_analysis(df_test, min_races=10):
    """会場ごとの性能差。min_races以上のデータがある会場のみ。"""
    venue_results = []
    for venue, sub in df_test.groupby("venue"):
        n_races = sub["race_id"].nunique()
        if n_races < min_races:
            continue
        # Top1的中率
        top1, hit1, tot = tb.eval_top1_hit(sub, "_pwin")
        # 1号ベタ Top1
        tmp = sub.assign(_pwin=-sub["lane"].astype(float))
        lane1_top1, _, _ = tb.eval_top1_hit(tmp, "_pwin")
        # 戦略E ROI
        m_e = bs.backtest(sub, bs.strat_E_trio_box4)
        # 1号勝率(インコース有利度の指標)
        lane1_win_rate = float(sub[sub["lane"] == 1]["is_win"].mean())

        venue_results.append({
            "venue": venue,
            "n_races": n_races,
            "top1_hit_rate": top1,
            "lane1_top1": lane1_top1,
            "lane1_win_rate": lane1_win_rate,
            "strat_E_roi": m_e["roi"],
            "strat_E_hit_rate": m_e["hit_rate"],
            "model_vs_lane1": top1 - lane1_top1,
        })
    venue_results.sort(key=lambda x: -x["n_races"])
    return venue_results


def incourse_analysis(df_test, venue_results):
    """インコース有利度が高い/低い会場での性能差。"""
    if not venue_results:
        return None
    median_lane1 = float(np.median([v["lane1_win_rate"] for v in venue_results]))
    high = [v for v in venue_results if v["lane1_win_rate"] >= median_lane1]
    low = [v for v in venue_results if v["lane1_win_rate"] < median_lane1]

    def agg(group):
        if not group:
            return None
        return {
            "n_venues": len(group),
            "avg_top1": float(np.mean([v["top1_hit_rate"] for v in group])),
            "avg_lane1_top1": float(np.mean([v["lane1_top1"] for v in group])),
            "avg_strat_E_roi": float(np.mean([v["strat_E_roi"] for v in group])),
            "avg_lane1_win_rate": float(np.mean([v["lane1_win_rate"] for v in group])),
            "avg_model_vs_lane1": float(np.mean([v["model_vs_lane1"] for v in group])),
        }
    return {
        "median_lane1_win_rate": median_lane1,
        "high_incourse": agg(high),
        "low_incourse": agg(low),
    }


# ===========================================================================
# 5. レポート生成
# ===========================================================================
def generate_report(inv, clf, baseline, strat_e, sv_results, venue_results,
                    incourse, n_train, n_test):
    """Markdownレポートを生成。"""
    lines = []
    lines.append("# DOTレーティング Step 3-1: ホールドアウトバックテスト検証レポート")
    lines.append("")
    lines.append("## 1. データ現状")
    lines.append("")
    lines.append(f"| 項目 | 値 |")
    lines.append(f"|------|-----|")
    lines.append(f"| races テーブル | {inv['n_races']} 件 |")
    lines.append(f"| boats テーブル | {inv['n_boats']} 件 |")
    lines.append(f"| race_winner_log | {inv['n_rwl']} 件 (結果あり: {inv['n_rwl_valid']}) |")
    lines.append(f"| 期間 | {inv['date_min']} 〜 {inv['date_max']} |")
    lines.append(f"| 会場数 | {inv['n_venues']} |")
    lines.append("")
    lines.append("### 月別レース数")
    lines.append("")
    lines.append("| 月 | レース数 |")
    lines.append("|-----|---------|")
    for m, n in inv["months"].items():
        lines.append(f"| {m} | {n} |")
    lines.append("")

    lines.append("## 2. ホールドアウト設計")
    lines.append("")
    lines.append(f"- **学習期間**: {', '.join(tl.TRAIN_MONTHS)} ({n_train}R)")
    lines.append(f"- **テスト期間**: {tl.TEST_MONTH} ({n_test}R)")
    lines.append("- **リーク防止**: テスト期間のデータは学習に一切含めない(完全時系列分割)")
    lines.append("- **モデル**: LightGBM (欠損ネイティブ処理)")
    lines.append("")

    lines.append("## 3. LightGBM単体性能")
    lines.append("")
    lines.append("| 指標 | DOTモデル | 1号ベタ | 差分 |")
    lines.append("|------|----------|---------|------|")
    lines.append(f"| Top1的中率 | **{clf['top1_hit_rate']*100:.1f}%** "
                 f"({clf['top1_hit']}/{clf['n_races']}) | "
                 f"{baseline['top1_hit_rate']*100:.1f}% | "
                 f"{(clf['top1_hit_rate']-baseline['top1_hit_rate'])*100:+.1f}pt |")
    lines.append(f"| Top3完全一致率 | {clf['top3_exact_rate']*100:.1f}% | - | - |")
    lines.append(f"| AUC | {clf['auc']:.4f} | - | - |")
    lines.append(f"| LogLoss | {clf['logloss']:.4f} | - | - |")
    lines.append("")

    lines.append("## 4. 買い目戦略バックテスト")
    lines.append("")
    lines.append("### 4a. 全レース機械買い")
    lines.append("")
    lines.append("| 戦略 | 的中率 | 回収率(ROI) | 純損益 | ROI>100%? |")
    lines.append("|------|--------|------------|--------|-----------|")
    # 戦略E
    roi_flag = "YES" if strat_e["roi"] > 1.0 else "NO"
    lines.append(f"| E: 3連複上位4艇BOX(4点) | {strat_e['hit_rate']*100:.1f}% | "
                 f"**{strat_e['roi']*100:.1f}%** | {strat_e['net']:.0f}円 | {roi_flag} |")
    # 1号ベタ 3連複BOX
    lines.append(f"| 1号ベタ 3連複1-2-3-4BOX | {baseline['trio_box4_hit_rate']*100:.1f}% | "
                 f"{baseline['trio_box4_roi']*100:.1f}% | - | "
                 f"{'YES' if baseline['trio_box4_roi'] > 1.0 else 'NO'} |")
    # 1号ベタ 3連単
    lines.append(f"| 1号ベタ 3連単(1点) | {baseline['trifecta_hit_rate']*100:.1f}% | "
                 f"{baseline['trifecta_roi']*100:.1f}% | - | "
                 f"{'YES' if baseline['trifecta_roi'] > 1.0 else 'NO'} |")
    lines.append("")

    lines.append("### 4b. 選択的投票(見送り判断付き)")
    lines.append("")
    lines.append("戦略E(3連複上位4艇BOX)× P_top(本命P(win))上位のレースのみ購入:")
    lines.append("")
    lines.append("| カバレッジ | 購入R | 見送り率 | 的中率 | 回収率(ROI) | 純損益 | ROI>100%? |")
    lines.append("|-----------|-------|---------|--------|------------|--------|-----------|")
    for r in sv_results:
        roi_flag = "**YES**" if r["roi"] > 1.0 else "NO"
        lines.append(f"| {r['coverage']*100:.0f}% | {r['wagered_races']} | "
                     f"{r['skip_rate']*100:.0f}% | {r['hit_rate']*100:.1f}% | "
                     f"**{r['roi']*100:.1f}%** | {r['net']:.0f}円 | {roi_flag} |")
    lines.append("")

    # ROI>100%の判定
    best_sv = max(sv_results, key=lambda x: x["roi"])
    lines.append(f"**最良**: カバレッジ{best_sv['coverage']*100:.0f}%で "
                 f"ROI={best_sv['roi']*100:.1f}% "
                 f"({'ROI>100%達成' if best_sv['roi'] > 1.0 else 'ROI>100%未達'})")
    lines.append("")

    lines.append("## 5. 会場別分析")
    lines.append("")
    if venue_results:
        lines.append("| 会場 | R数 | DOT Top1 | 1号ベタTop1 | モデル優位 | 1号勝率 | E:ROI |")
        lines.append("|------|-----|----------|-----------|----------|---------|-------|")
        for v in venue_results:
            lines.append(f"| {v['venue']} | {v['n_races']} | "
                         f"{v['top1_hit_rate']*100:.1f}% | {v['lane1_top1']*100:.1f}% | "
                         f"{v['model_vs_lane1']*100:+.1f}pt | "
                         f"{v['lane1_win_rate']*100:.1f}% | {v['strat_E_roi']*100:.1f}% |")
        lines.append("")
    else:
        lines.append("(十分なデータのある会場なし)")
        lines.append("")

    if incourse:
        lines.append("### インコース有利度別")
        lines.append("")
        lines.append(f"1号勝率の中央値: {incourse['median_lane1_win_rate']*100:.1f}%")
        lines.append("")
        lines.append("| グループ | 会場数 | DOT Top1 | 1号ベタTop1 | モデル優位 | E:ROI |")
        lines.append("|---------|--------|----------|-----------|----------|-------|")
        for label, key in [("インコース有利(高)", "high_incourse"),
                           ("インコース不利(低)", "low_incourse")]:
            g = incourse.get(key)
            if g:
                lines.append(f"| {label} | {g['n_venues']} | "
                             f"{g['avg_top1']*100:.1f}% | {g['avg_lane1_top1']*100:.1f}% | "
                             f"{g['avg_model_vs_lane1']*100:+.1f}pt | "
                             f"{g['avg_strat_E_roi']*100:.1f}% |")
        lines.append("")

    lines.append("## 6. 総合判定")
    lines.append("")
    # 判定ロジック
    model_beats_lane1 = clf["top1_hit_rate"] > baseline["top1_hit_rate"]
    any_roi_over_100 = any(r["roi"] > 1.0 for r in sv_results)
    full_roi_over_100 = strat_e["roi"] > 1.0

    lines.append(f"- **モデル vs 1号ベタ(Top1)**: "
                 f"{'DOTモデル優位' if model_beats_lane1 else '1号ベタ優位'} "
                 f"({clf['top1_hit_rate']*100:.1f}% vs {baseline['top1_hit_rate']*100:.1f}%)")
    lines.append(f"- **全レース機械買い(E)**: ROI={strat_e['roi']*100:.1f}% "
                 f"({'100%超え' if full_roi_over_100 else '100%未達'})")
    lines.append(f"- **選択的投票(最良)**: ROI={best_sv['roi']*100:.1f}% "
                 f"(cov={best_sv['coverage']*100:.0f}%) "
                 f"({'100%超え' if best_sv['roi'] > 1.0 else '100%未達'})")
    lines.append("")

    lines.append("## 7. 注意事項・限界")
    lines.append("")
    lines.append("- テスト期間は6月のみ(標本が限定的)。高配当1本で大きく動く可能性あり。")
    lines.append("- 選択的投票のカバレッジが低い場合、購入レース数が少なく統計的信頼性が低下。")
    lines.append("- 回収は全てDB実払戻(trifecta/exacta/trifecta_place)。購入判定のみモデルP(win)。")
    lines.append("- engine.py不変更・本番DBはSELECTのみ・DB書込ゼロ。")
    lines.append("")

    return "\n".join(lines)


# ===========================================================================
# main
# ===========================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    ap.add_argument("--report", default="tmp/dot_backtest_report.md")
    ap.add_argument("--target", default="is_win", choices=["is_win", "is_top3"])
    ap.add_argument("--extra", action="store_true",
                    help="承認プランの追加特徴(rank等)を使用")
    args = ap.parse_args()

    sb = tb.get_client()

    print("=" * 78)
    print("DOTレーティング step-3-1 ホールドアウトバックテスト検証(読み取り専用)")
    print("=" * 78)

    # --- 1. データ現状確認 ---
    print("\n■ 1. データ現状確認")
    inv = data_inventory(sb)
    print(f"  races: {inv['n_races']}件  boats: {inv['n_boats']}件  "
          f"race_winner_log: {inv['n_rwl']}件(結果あり: {inv['n_rwl_valid']})")
    print(f"  期間: {inv['date_min']} 〜 {inv['date_max']}")
    print(f"  会場数: {inv['n_venues']}")
    print("  月別: " + ", ".join(f"{m}={n}" for m, n in inv["months"].items()))

    # --- 2. データ取得・特徴量構築 ---
    print("\n■ 2. データ取得・特徴量構築")
    df, used_races = bs.load_dataset_betting(sb, include_extra=args.extra)
    if args.extra:
        df, feat_cols, group_map = tb.build_features(df, include_extra=True)
    else:
        df, feat_cols = tb.build_features(df)
        group_map = None

    leaked = [c for c in feat_cols if c in tb.LEAK_BLACKLIST]
    print(f"  学習可能レース: {used_races}R / {len(df)}艇行")
    print("  月別: " + ", ".join(f"{m}={n//6}R" for m, n in
                                  df.groupby('month').size().items()))
    print(f"  特徴量: {len(feat_cols)}列  リーク={'NG' if leaked else 'OK'}")

    n_train = df[df["month"].isin(tl.TRAIN_MONTHS)]["race_id"].nunique()
    n_test = df[df["month"] == tl.TEST_MONTH]["race_id"].nunique()
    print(f"\n■ 3. ホールドアウト分割")
    print(f"  train: {tl.TRAIN_MONTHS} → {n_train}R")
    print(f"  test:  {tl.TEST_MONTH} → {n_test}R")
    if n_test < 100:
        print(f"  ⚠ テストレース数が{n_test}R(<100R)。統計的信頼性に注意。")

    # --- 3. ホールドアウト予測 ---
    print("\n■ 4. ホールドアウト予測(4月+5月train → 6月test)")
    df_test, booster = holdout_predict(df, feat_cols, target=args.target)
    print(f"  テストレース: {df_test['race_id'].nunique()}R / {len(df_test)}艇行")
    print(f"  best_iteration: {booster.best_iteration}")

    # --- 4. LightGBM単体評価 ---
    print("\n■ 5. LightGBM単体性能")
    clf = eval_classification(df_test, target=args.target)
    print(f"  Top1的中率: {clf['top1_hit_rate']*100:.1f}% ({clf['top1_hit']}/{clf['n_races']})")
    print(f"  Top3完全一致率: {clf['top3_exact_rate']*100:.1f}%")
    print(f"  AUC: {clf['auc']:.4f}")
    print(f"  LogLoss: {clf['logloss']:.4f}")

    # --- 5. ベースライン ---
    print("\n■ 6. ベースライン(1号ベタ)")
    baseline = eval_baseline_lane1(df_test)
    print(f"  Top1的中率: {baseline['top1_hit_rate']*100:.1f}%")
    print(f"  3連単ROI: {baseline['trifecta_roi']*100:.1f}%")
    print(f"  3連複1-2-3-4BOX ROI: {baseline['trio_box4_roi']*100:.1f}%")

    diff = (clf["top1_hit_rate"] - baseline["top1_hit_rate"]) * 100
    print(f"\n  DOT vs 1号ベタ(Top1): {diff:+.1f}pt "
          f"({'DOTモデル優位' if diff > 0 else '1号ベタ優位'})")

    # --- 6. 戦略E(3連複上位4艇BOX) ---
    print("\n■ 7. 戦略E: 3連複上位4艇BOX(全レース機械買い)")
    strat_e = eval_strategy_E(df_test)
    print(f"  的中率: {strat_e['hit_rate']*100:.1f}%")
    print(f"  回収率(ROI): {strat_e['roi']*100:.1f}%")
    print(f"  純損益: {strat_e['net']:.0f}円")
    print(f"  ROI>100%: {'YES' if strat_e['roi'] > 1.0 else 'NO'}")

    # --- 7. 選択的投票 ---
    print("\n■ 8. 選択的投票(P_top上位のみ購入)")
    sv_results, conf = eval_selective_voting(df_test)
    print(f"  {'cov':>5s} {'購入R':>5s} {'見送り':>6s} {'的中':>6s} {'ROI':>7s} {'純損益':>8s}")
    print("  " + "-" * 48)
    for r in sv_results:
        star = "★" if r["roi"] > 1.0 else " "
        print(f" {star}{r['coverage']*100:4.0f}% {r['wagered_races']:5d} "
              f"{r['skip_rate']*100:5.0f}% {r['hit_rate']*100:5.1f}% "
              f"{r['roi']*100:6.1f}% {r['net']:7.0f}円")

    # --- 8. 会場別分析 ---
    print("\n■ 9. 会場別分析")
    v_results = venue_analysis(df_test, min_races=10)
    if v_results:
        print(f"  {'会場':>8s} {'R数':>4s} {'DOT Top1':>9s} {'1号ベタ':>7s} "
              f"{'優位':>6s} {'1号勝率':>7s} {'E:ROI':>7s}")
        print("  " + "-" * 58)
        for v in v_results:
            print(f"  {v['venue']:>8s} {v['n_races']:4d} "
                  f"{v['top1_hit_rate']*100:8.1f}% {v['lane1_top1']*100:6.1f}% "
                  f"{v['model_vs_lane1']*100:+5.1f}pt {v['lane1_win_rate']*100:6.1f}% "
                  f"{v['strat_E_roi']*100:6.1f}%")
    else:
        print("  (十分なデータのある会場なし)")

    inc = incourse_analysis(df_test, v_results)
    if inc:
        print(f"\n  インコース有利度別(1号勝率中央値: {inc['median_lane1_win_rate']*100:.1f}%)")
        for label, key in [("高(有利)", "high_incourse"), ("低(不利)", "low_incourse")]:
            g = inc.get(key)
            if g:
                print(f"    {label}: {g['n_venues']}会場 DOT Top1={g['avg_top1']*100:.1f}% "
                      f"1号ベタ={g['avg_lane1_top1']*100:.1f}% "
                      f"優位={g['avg_model_vs_lane1']*100:+.1f}pt "
                      f"E:ROI={g['avg_strat_E_roi']*100:.1f}%")

    # --- 9. レポート生成 ---
    report = generate_report(inv, clf, baseline, strat_e, sv_results,
                             v_results, inc, n_train, n_test)
    os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n■ レポート保存: {args.report}")

    # --- JSON出力 ---
    out = {
        "step": "3-1",
        "target": args.target,
        "extra_features": args.extra,
        "data_inventory": inv,
        "holdout": {
            "train_months": tl.TRAIN_MONTHS,
            "test_month": tl.TEST_MONTH,
            "n_train_races": n_train,
            "n_test_races": n_test,
        },
        "classification": clf,
        "baseline_lane1": baseline,
        "strategy_E_full": strat_e,
        "selective_voting": sv_results,
        "venue_analysis": v_results,
        "incourse_analysis": inc,
        "leak_free": not leaked,
        "report_path": args.report,
    }
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2, default=str)
        print(f"  JSON保存: {args.json}")

    print("\n[完了] 本番DBは SELECT のみ・書込なし。engine.py 不変更。")


if __name__ == "__main__":
    main()
