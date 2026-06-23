#!/usr/bin/env python3
"""DOTレーティング — 2026-06-06「指定日・全レース」予想 vs 実結果・収支(読み取り専用)

【対象日の根拠】
  直近の予想照合依頼が 6/6(scripts/dot/predict_0606.py が既存)だが、同スクリプトは
  蒲郡/常滑/三国 の 3 会場 36R のみだった。本スクリプトは依頼『全レース(会場×R)』に
  従い 6/6 の DB に存在する全 11 会場 131R を対象にする。別の指定日が判別できなかった
  ため 6/6 を対象にしたことを明記する。

【リーク防止(最重要)】
  6/6 の全 131R を学習データから完全除外して LightGBM を学習し、6/6 を未知データとして
  予想する。確定結果(着順・払戻)は 6/6 の照合・収支計算にのみ使用。

【戦略】
  買い目 = 推奨戦略 E: 3連複 上位4艇BOX(4C3 = 4点 / レース)。
  選択的投票 = 各レースの本命 P(win) 最大値で全 131R を降順に並べ、上位約30%を「勝負」、
  残りを「見送り」。閾値は 6/6 自身の確定結果を一切使わず、P(win) 分布のみで決める
  (上位30%のパーセンタイル切り)。

【出力】
  - レース毎テーブル: 会場・R / 予想買い目(4点) / 勝負or見送り / 実1-2-3着 /
    的中○× / 払戻金 / 投資額(100円×4点=400円) / 収支
  - サマリ: 勝負/全レース 両方の レース数・的中数・的中率・総投資・総払戻・純損益・回収率
  - tmp/dot_0606_fullday_report.md と tmp/dot_0606_fullday.json

本番 Supabase は SELECT のみ。DB 書込なし。engine.py 不変更。
"""
import os
import sys
import json
import argparse
from itertools import combinations

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train_baseline as tb     # noqa: E402  load_dataset_betting? いや bet_strategy 側
import train_lightgbm as tl     # noqa: E402  train_lgb / LGB_PARAMS
import bet_strategy as bs       # noqa: E402  load_dataset_betting / settle_bet

STAKE = bs.STAKE  # 100円/点

TARGET_DATE = "2026-06-06"
# 会場コード(表示用・参考)
VENUE_CODE = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04", "多摩川": "05",
    "浜名湖": "06", "蒲郡": "07", "常滑": "08", "津": "09", "三国": "10",
    "びわこ": "11", "住之江": "12", "尼崎": "13", "鳴門": "14", "丸亀": "15",
    "児島": "16", "宮島": "17", "徳山": "18", "下関": "19", "若松": "20",
    "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24",
}

# 会場の標準的な並び(コード昇順)。レポートの会場順に使用。
VENUE_ORDER = sorted(VENUE_CODE.keys(), key=lambda v: VENUE_CODE[v])


def fit_predict_lightgbm_holdout(train_df, test_df, feat_cols, target, seed=42):
    """LightGBM(欠損ネイティブ)で学習し test の P を返す。

    リーク防止: test(6/6)は early-stopping の検証に一切使わない。
    early-stopping 用の内部 valid は train からレース単位(会場層化)で 15% 抽出。
    train_lightgbm.train_lgb と同一パラメータ(LGB_PARAMS / num_boost / early_stop)。
    """
    rng = np.random.RandomState(seed)
    races = (train_df[["race_id", "venue"]].drop_duplicates()
             .reset_index(drop=True))
    val_races = set()
    for v, sub in races.groupby("venue"):
        ids = sub["race_id"].tolist()
        k = max(1, int(round(len(ids) * 0.15)))
        pick = rng.choice(ids, size=min(k, len(ids)), replace=False)
        val_races.update(pick.tolist())

    inner_tr = train_df[~train_df["race_id"].isin(val_races)]
    inner_va = train_df[train_df["race_id"].isin(val_races)]

    booster = tl.train_lgb(
        inner_tr[feat_cols], inner_tr[target],
        inner_va[feat_cols], inner_va[target],
        impute_median=False,
    )
    best_it = booster.best_iteration
    print(f"  LightGBM: inner_train={inner_tr['race_id'].nunique()}R / "
          f"inner_valid={inner_va['race_id'].nunique()}R / best_iteration={best_it}")
    proba = booster.predict(test_df[feat_cols], num_iteration=best_it)
    return proba


def strat_E_trio_box4_lanes(top4):
    """上位4艇から 3連複 4C3=4点。combo は昇順タプルに正規化。"""
    return [tuple(sorted(c)) for c in combinations(top4, 3)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="tmp/dot_0606_fullday.json")
    ap.add_argument("--md", default="tmp/dot_0606_fullday_report.md")
    ap.add_argument("--target", default="is_win", choices=["is_win", "is_top3"],
                    help="艇スコアの目的変数(本命順位付け)")
    ap.add_argument("--coverage", type=float, default=0.30,
                    help="勝負にするレースの割合(本命P(win)上位X%)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    sb = bs.tb.get_client()
    print("=" * 78)
    print(f"DOT {TARGET_DATE} 全レース予想 vs 実結果・収支"
          f"(LightGBM・3連複4BOX・選択的投票 top{int(args.coverage*100)}%)")
    print("リーク防止: 6/6 全レース除外学習 / 読み取り専用(SELECTのみ)")
    print("=" * 78)

    # --- データ取得(SELECTのみ) ---
    df, used_races = bs.load_dataset_betting(sb)
    df, feat_cols = tb.build_features(df)
    leaked = [c for c in feat_cols if c in tb.LEAK_BLACKLIST]
    assert not leaked, f"リーク列が特徴量に混入: {leaked}"
    print(f"\n全学習可能レース(JOIN成立): {used_races}  特徴量: {len(feat_cols)}列  "
          f"リーク混入: {'NG' if leaked else 'OK(なし)'}")

    # --- 分割: 6/6 全会場 = test, それ以外全部 = train ---
    is_target = (df["date"] == TARGET_DATE)
    test_df = df[is_target].copy()
    train_df = df[~is_target].copy()

    n_test_races = test_df["race_id"].nunique()
    test_venues = sorted(test_df["venue"].unique().tolist(),
                         key=lambda v: VENUE_CODE.get(v, "99"))
    print(f"\n分割: train={train_df['race_id'].nunique()}R ({len(train_df)}艇行) / "
          f"test(6/6 全{len(test_venues)}会場)={n_test_races}R ({len(test_df)}艇行)")
    print(f"  6/6 会場: {', '.join(test_venues)}")

    # リーク確認
    overlap = set(train_df["race_id"]) & set(test_df["race_id"])
    print(f"  リーク確認: train∩test race_id = {len(overlap)} (0であること)")
    assert len(overlap) == 0, "リーク: testレースがtrainに混入"
    # train に 6/6 が一切無いこと
    assert (train_df["date"] != TARGET_DATE).all(), "リーク: trainに6/6が残存"

    # --- 学習(6/6除外) → 6/6 を未知データとして予想 ---
    scores = fit_predict_lightgbm_holdout(train_df, test_df, feat_cols,
                                          args.target, seed=args.seed)
    test_df = test_df.assign(_pwin=scores)

    # --- レース毎 予想生成 + 自信度(本命P(win)最大値) ---
    per_race = []
    for (venue, _rno), sub in test_df.groupby(["venue", "race_id"]):
        sub = sub.sort_values("_pwin", ascending=False).reset_index(drop=True)
        race_no = int(sub["race_id"].iloc[0].split("|")[-1])
        pred_order = [int(x) for x in sub["lane"].tolist()]
        top4 = pred_order[:4]
        p_top = float(sub["_pwin"].iloc[0])  # 本命 P(win)(自信度指標)
        bets = strat_E_trio_box4_lanes(top4)        # 3連複 4点(順不同)
        combo_str = " / ".join("-".join(str(x) for x in c) for c in bets)

        # 実結果
        w = int(sub["winner_lane"].iloc[0])
        p2 = int(sub["place2_lane"].iloc[0])
        p3 = int(sub["place3_lane"].iloc[0])
        actual_set = {w, p2, p3}
        trio_pay = float(sub["trifecta_place_payout"].iloc[0])  # 3連複払戻
        trio_pay = trio_pay if not np.isnan(trio_pay) else 0.0

        # 的中: 4点のうちどれかが {w,p2,p3} と集合一致(3連複BOXは本命3着内集合を内包すれば的中)
        hit = any(set(c) == actual_set for c in bets)
        spent = STAKE * len(bets)               # 400円
        ret = trio_pay if hit else 0.0          # 的中時のみ実払戻(1点のみ的中しうる)
        profit = ret - spent

        per_race.append({
            "venue": venue, "race_no": race_no,
            "pred_order": pred_order, "top4": top4,
            "bets": [list(c) for c in bets], "combo_str": combo_str,
            "p_top": p_top,
            "actual_1": w, "actual_2": p2, "actual_3": p3,
            "trio_payout": trio_pay,
            "hit": bool(hit), "spent": spent, "ret": ret, "profit": profit,
        })

    # --- 選択的投票: 本命P(win)上位 coverage を「勝負」 ---
    p_sorted = sorted((r["p_top"] for r in per_race), reverse=True)
    k = max(1, int(round(len(p_sorted) * args.coverage)))
    # 閾値 = 上位k番目のp_top(これ以上を勝負)。6/6の結果は不使用(P分布のみ)。
    threshold = p_sorted[k - 1]
    n_bet = 0
    for r in per_race:
        r["decision"] = "勝負" if r["p_top"] >= threshold else "見送り"
        if r["decision"] == "勝負":
            n_bet += 1
    print(f"\n選択的投票: 本命P(win)>= {threshold:.4f} を勝負 "
          f"(上位~{int(args.coverage*100)}% → {n_bet}/{len(per_race)}R)")

    per_race.sort(key=lambda r: (VENUE_CODE.get(r["venue"], "99"), r["race_no"]))

    # --- 集計 ---
    def agg(rows):
        n = len(rows)
        if n == 0:
            return {"n_races": 0, "hits": 0, "hit_rate": 0.0,
                    "spent": 0.0, "ret": 0.0, "net": 0.0, "roi": 0.0}
        hits = sum(r["hit"] for r in rows)
        spent = sum(r["spent"] for r in rows)
        ret = sum(r["ret"] for r in rows)
        return {
            "n_races": n, "hits": hits, "hit_rate": hits / n,
            "spent": spent, "ret": ret, "net": ret - spent,
            "roi": (ret / spent) if spent else 0.0,
        }

    bet_rows = [r for r in per_race if r["decision"] == "勝負"]
    all_rows = per_race
    summ_bet = agg(bet_rows)
    summ_all = agg(all_rows)

    # 会場別(全レース基準)
    by_venue = {}
    for v in test_venues:
        vr = [r for r in per_race if r["venue"] == v]
        vb = [r for r in vr if r["decision"] == "勝負"]
        by_venue[v] = {"all": agg(vr), "bet": agg(vb)}

    # --- コンソール出力 ---
    def show(label, m):
        print(f"  {label:10s} R数={m['n_races']:3d} 的中={m['hits']:3d} "
              f"的中率={m['hit_rate']*100:5.1f}% 投資={int(m['spent']):>7d}円 "
              f"払戻={int(m['ret']):>7d}円 収支={int(m['net']):>+8d}円 "
              f"回収率={m['roi']*100:6.1f}%")
    print("\n■ サマリ(買い目=3連複 上位4艇BOX 4点 / 100円)")
    show("勝負のみ", summ_bet)
    show("全レース", summ_all)

    out = {
        "target_date": TARGET_DATE,
        "target_scope": "6/6 全11会場 全レース(DB join成立分)",
        "model": "LightGBM (P(win) 欠損ネイティブ)",
        "strategy": "E: 3連複 上位4艇BOX(4点/レース)",
        "selective_voting": {
            "metric": "本命P(win)最大値",
            "coverage": args.coverage,
            "threshold_pwin": float(threshold),
            "n_bet_races": n_bet,
        },
        "score_target": args.target,
        "n_train_races": int(train_df["race_id"].nunique()),
        "n_test_races": int(n_test_races),
        "test_venues": test_venues,
        "leak_overlap": len(overlap),
        "n_features": len(feat_cols),
        "stake_per_point": STAKE,
        "points_per_race": 4,
        "summary_bet": summ_bet,
        "summary_all": summ_all,
        "by_venue": by_venue,
        "per_race": per_race,
    }
    os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nJSON 保存: {args.json}")

    write_markdown(args.md, out)
    print(f"Markdown 保存: {args.md}")
    print("\n[完了] 本番DBは SELECT のみ・書込なし。engine.py 不変更。"
          "リーク無し(6/6全レース除外学習)。")


def pct(x):
    return f"{x*100:.1f}%"


def yen(x):
    return f"{int(round(x)):,}"


def write_markdown(path, out):
    L = []
    A = L.append
    sb_ = out["summary_bet"]
    sa = out["summary_all"]
    sv = out["selective_voting"]

    A(f"# DOTレーティング 予想 vs 実結果・収支レポート — {out['target_date']}(全レース)")
    A("")
    A(f"> **対象日: {out['target_date']}**(指定日)。"
      f"対象範囲: {out['target_scope']} = **{out['n_test_races']}レース**"
      f"(会場: {', '.join(out['test_venues'])})。")
    A("> ※直近の予想照合依頼が 6/6 で、別の指定日が判別できなかったため **6/6 を対象**にした。"
      "既存 `predict_0606.py` は 3 会場 36R のみだったが、本レポートは依頼『全レース』に従い"
      "6/6 の DB 存在全 11 会場を対象にしている。")
    A(f"> **モデル: DOT {out['model']}**。各艇 P(win) 降順で本命・順位付け。")
    A(f"> **買い目: {out['strategy']}**。1点 {int(out['stake_per_point'])}円 × "
      f"{out['points_per_race']}点 = **1レース {int(out['stake_per_point']*out['points_per_race'])}円**。")
    A(f"> **選択的投票**: 本命 P(win) 最大値で全レースを降順に並べ、"
      f"**上位約{int(sv['coverage']*100)}%(P(win)≥{sv['threshold_pwin']:.4f})を「勝負」**、"
      f"残りを「見送り」(勝負 {sv['n_bet_races']}R)。閾値は 6/6 の結果を使わず P 分布のみで決定。")
    A(f"> **リーク防止**: 6/6 の全 {out['n_test_races']}R を学習から完全除外"
      f"(train={out['n_train_races']}R)。train∩test 重複={out['leak_overlap']}(0=リーク無し)。"
      "6/6 は未知データとして予想。early-stopping 検証も train 内部抽出で 6/6 不使用。")
    A("> 本番DBは SELECT のみ・書込なし。`engine.py` 不変更。")
    A("")

    # 1. サマリ
    A("## 1. サマリ(収支)")
    A("")
    A("| 区分 | レース数 | 的中数 | 的中率 | 総投資 | 総払戻 | 純損益 | 回収率(ROI) |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    A(f"| **勝負のみ**(上位{int(sv['coverage']*100)}%) | {sb_['n_races']} | {sb_['hits']} "
      f"| **{pct(sb_['hit_rate'])}** | {yen(sb_['spent'])}円 | {yen(sb_['ret'])}円 "
      f"| **{yen(sb_['net'])}円** | **{pct(sb_['roi'])}** |")
    A(f"| 全レース | {sa['n_races']} | {sa['hits']} | {pct(sa['hit_rate'])} "
      f"| {yen(sa['spent'])}円 | {yen(sa['ret'])}円 | {yen(sa['net'])}円 | {pct(sa['roi'])} |")
    A("")
    A(f"- 的中=3連複(上位4艇BOX 4点)のいずれかが実際の1〜3着集合と一致したレース。")
    A(f"- 純損益・回収率は全て DB 実払戻(`trifecta_place_payout`)で計算。")
    A("")

    # 2. 会場別
    A("## 2. 会場別サマリ(全レース基準)")
    A("")
    A("| 会場 | R数 | 勝負R | 全的中 | 全ROI | 勝負的中 | 勝負ROI | 全収支 | 勝負収支 |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for v in out["test_venues"]:
        m = out["by_venue"][v]
        a, b = m["all"], m["bet"]
        A(f"| {v}({VENUE_CODE.get(v,'--')}) | {a['n_races']} | {b['n_races']} "
          f"| {a['hits']}/{a['n_races']} | {pct(a['roi'])} "
          f"| {b['hits']}/{b['n_races']} | {pct(b['roi']) if b['n_races'] else '—'} "
          f"| {yen(a['net'])} | {yen(b['net']) if b['n_races'] else '—'} |")
    A("")

    # 3. 勝った/負けたが一目で(勝負レースの収支降順)
    bet_sorted = sorted([r for r in out["per_race"] if r["decision"] == "勝負"],
                        key=lambda r: -r["profit"])
    A("## 3. 勝負レースの損益ランキング(勝った順)")
    A("")
    A("| 順 | 会場 | R | 買い目(3連複4点) | 実1-2-3着 | 的中 | 払戻 | 投資 | 収支 |")
    A("|---:|---|---:|---|:---:|---:|---:|---:|")
    for i, r in enumerate(bet_sorted, 1):
        actual = f"{r['actual_1']}-{r['actual_2']}-{r['actual_3']}"
        hm = "○" if r["hit"] else "×"
        A(f"| {i} | {r['venue']} | {r['race_no']} | {r['combo_str']} | {actual} "
          f"| {hm} | {yen(r['ret'])} | {yen(r['spent'])} | **{yen(r['profit'])}** |")
    A("")

    # 4. 会場別 レース毎 全テーブル
    A("## 4. レース毎 予想 vs 実結果(全レース)")
    A("")
    A("- 買い目=DOT P(win) 上位4艇の 3連複BOX(4点)。勝負=上位約30%、見送り=それ以外。")
    A("- 的中 ○=的中 / ×=不的中 / (見送りは賭けないので収支0)。")
    A("")
    for v in out["test_venues"]:
        vr = [r for r in out["per_race"] if r["venue"] == v]
        if not vr:
            continue
        A(f"### {v}({VENUE_CODE.get(v,'--')})")
        A("")
        A("| R | DOT予想順 | 買い目(3連複4点) | 判断 | 実1-2-3着 | 的中 | 払戻 | 投資 | 収支 |")
        A("|---:|---|---|:---:|---|:---:|---:|---:|---:|")
        for r in sorted(vr, key=lambda x: x["race_no"]):
            pred = "-".join(str(x) for x in r["pred_order"])
            actual = f"{r['actual_1']}-{r['actual_2']}-{r['actual_3']}"
            if r["decision"] == "見送り":
                A(f"| {r['race_no']} | {pred} | {r['combo_str']} | 見送り | {actual} "
                  f"| — | — | 0 | 0 |")
            else:
                hm = "○" if r["hit"] else "×"
                A(f"| {r['race_no']} | {pred} | {r['combo_str']} | **勝負** | {actual} "
                  f"| {hm} | {yen(r['ret'])} | {yen(r['spent'])} | {yen(r['profit'])} |")
        A("")

    # 5. 備考
    A("## 5. 備考・前提")
    A("")
    A(f"- **モデル**: 本命 DOT LightGBM(勾配ブースティング・欠損ネイティブ)。"
      f"目的変数=`{out['score_target']}`、特徴量 {out['n_features']}列(枠内相対化 z-score/順位含む)。"
      "結果系列の列は特徴量から除外済み(リーク防止)。")
    A(f"- **学習データ**: 6/6 を除く全 {out['n_train_races']}R(4〜6月、他日・他会場)。"
      "early-stopping の内部 valid も train から会場層化 15% を抽出し、6/6 は一切使用しない。")
    A("- **回収の定義**: 各レースで DOT P(win) 上位4艇の 3連複を 4C3=4点(各100円)。"
      "実際の1〜3着集合と一致した点のみ `trifecta_place_payout`(3連複・順不同)で回収。"
      "1レース最大1点的中(4点BOXは互いに排他)。")
    A(f"- **選択的投票**: 本命 P(win) 最大値の上位約{int(sv['coverage']*100)}%(={sv['n_bet_races']}R)"
      "のみ「勝負」。閾値はモデル P 分布のみで決定し 6/6 結果は不使用(カーブフィット回避)。")
    A("- **データ品質**: 6/6 の一部会場は選手成績特徴(national/avg_st 等)が NULL。"
      "LightGBM は欠損を分岐側でネイティブ処理するため median 補完・標準化は不要。"
      "`local5y_*`/`general1y_*` はスクレイパ非取得のため全 NULL 継続。")
    A("- **限界(正直な明記)**: 単日 131R(勝負はその約30%)の小標本で、高配当1本で収支が"
      "大きく振れる。回収率は実DB払戻ベースだが分散が大きい点に留意。")
    A("- 本番DBは SELECT のみ・DB書込ゼロ。`engine.py`(v58.7側)不変更。")
    A("")

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
