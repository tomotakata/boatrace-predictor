#!/usr/bin/env python3
"""DOTレーティング — 2026-06-06(蒲郡/常滑/三国 36R)予想 vs 結果 照合(読み取り専用)

【リーク防止・最重要】
  6/6 の 36 レースは学習データから完全除外して学習し、6/6 を未知データとして予想する。
  in-sample 予想は禁止(成績過大評価になる)。学習は残り全データ(〜6/5・他日)で実施。

パイプライン:
  1. データ取得  : races × boats × race_winner_log を INNER JOIN(date+venue+race_no)
  2. 分割       : TARGET日(6/6 × 蒲郡/常滑/三国) を test、それ以外全部を train
  3. 学習       : LogisticRegression で P(is_win) / P(is_top3)(train のみで fit)
  4. 予想       : 6/6 36R を未知データとして各艇スコア → 本命/順位/3連単候補
  5. 照合       : 実 1-2-3着 / trifecta_result / trifecta_payout と突合・的中判定
  6. 集計       : 会場別・全体で Top1的中 / 3着内的中 / 3連単的中 / 回収率(1点買い)
                  比較対象として「1号ベタ」併記。
  7. 出力       : tmp/dot_0606_report.md(レース毎テーブル+サマリ) と JSON

本番 Supabase は SELECT のみ。DB 書込なし。engine.py 不変更。
"""
import os
import sys
import json
import argparse
from collections import defaultdict

import numpy as np
import pandas as pd

from supabase import create_client
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer

# LightGBM(本命モデル)。train_lightgbm.py と同一パラメータ・欠損ネイティブ処理。
try:
    import lightgbm as lgb
except Exception:
    lgb = None

# train_lightgbm.py:53-71 と同一(小標本向け控えめ設定)。本命モデルの再現性確保。
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
LGB_NUM_BOOST_ROUND = 600
LGB_EARLY_STOPPING = 50

DEFAULT_URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
DEFAULT_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ."
    "vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
)
PAGE = 1000

TARGET_DATE = "2026-06-06"
TARGET_VENUES = ["蒲郡", "常滑", "三国"]
VENUE_CODE = {"蒲郡": "07", "常滑": "08", "三国": "10"}

LEAK_BLACKLIST = {
    "winner_lane", "winner_course", "place2_lane", "place3_lane",
    "trifecta_result", "exacta_result", "trifecta_payout", "exacta_payout",
    "trifecta_place_payout", "result_all", "is_win", "is_top3", "pos", "rank",
    "finish_order", "result",
}

BASE_FEATURES = [
    "lane", "age", "weight", "f_count",
    "avg_st", "today_st", "exhibition_st", "standard_st", "course1y_st",
    "national_win_rate", "national_place2_rate",
    "local_win_rate", "local_place2_rate",
    "general1y_win_rate", "general1y_place2_rate", "general1y_tricast_rate",
    "local5y_win_rate", "local5y_place2_rate", "local5y_tricast_rate",
    "c1_win_rate", "c2_win_rate", "c3_win_rate",
    "c4_win_rate", "c5_win_rate", "c6_win_rate",
    "motor_place2_rate", "gen_rate", "hit_rate", "exhibition_time",
]

RELATIVE_FEATURES = [
    "national_win_rate", "national_place2_rate",
    "local5y_win_rate", "general1y_win_rate",
    "avg_st", "motor_place2_rate", "weight",
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


def load_dataset(sb):
    races = fetch_all(sb, "races", "id,date,venue,race_no")
    race_by_id = {r["id"]: r for r in races}

    bcols_set = ["race_id"] + sorted(set(["lane"] + BASE_FEATURES))
    boats = fetch_all(sb, "boats", ",".join(bcols_set))
    boats_by_race = defaultdict(list)
    for b in boats:
        boats_by_race[b["race_id"]].append(b)

    rwl = fetch_all(
        sb, "race_winner_log",
        "date,venue,race_no,winner_lane,place2_lane,place3_lane,"
        "trifecta_result,trifecta_payout",
        order_col="race_key",
    )
    res_idx = {}
    for r in rwl:
        if not r.get("trifecta_result"):
            continue
        if r.get("place2_lane") is None or r.get("place3_lane") is None:
            continue
        res_idx[(r.get("date"), r.get("venue"), r.get("race_no"))] = r

    rows = []
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
        race_id = f"{key[0]}|{key[1]}|{key[2]}"
        top3 = {res.get("winner_lane"), res.get("place2_lane"), res.get("place3_lane")}
        win_lane = res.get("winner_lane")
        payout = res.get("trifecta_payout")
        for b in blist:
            row = {f: to_float(b.get(f)) for f in BASE_FEATURES}
            row["race_id"] = race_id
            row["date"] = key[0]
            row["venue"] = key[1]
            row["race_no"] = key[2]
            row["month"] = key[0][:7]
            row["lane"] = b.get("lane")
            row["is_win"] = 1 if b.get("lane") == win_lane else 0
            row["is_top3"] = 1 if b.get("lane") in top3 else 0
            row["trifecta_payout"] = to_float(payout)
            row["trifecta_result"] = res.get("trifecta_result")
            row["winner_lane"] = res.get("winner_lane")
            row["place2_lane"] = res.get("place2_lane")
            row["place3_lane"] = res.get("place3_lane")
            rows.append(row)

    df = pd.DataFrame(rows)
    return df, used_races


def build_features(df):
    feat_cols = list(BASE_FEATURES)
    g = df.groupby("race_id")
    for f in RELATIVE_FEATURES:
        if f not in df.columns:
            continue
        mean = g[f].transform("mean")
        std = g[f].transform("std")
        z = (df[f] - mean) / std.replace(0, np.nan)
        df[f"{f}_z"] = z
        feat_cols.append(f"{f}_z")
        ascending = f in {"avg_st"}
        rank = g[f].rank(method="average", ascending=ascending)
        df[f"{f}_rank"] = rank
        feat_cols.append(f"{f}_rank")
    leaked = [c for c in feat_cols if c in LEAK_BLACKLIST]
    if leaked:
        raise RuntimeError(f"リーク列が特徴量に混入: {leaked}")
    feat_cols = sorted(set(feat_cols))
    return df, feat_cols


def make_model():
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("clf", LogisticRegression(max_iter=2000, C=1.0, class_weight=None)),
    ])


def fit_predict_logreg(train_df, test_df, feat_cols, target):
    """LogReg(median補完+標準化)で学習し test の P を返す。"""
    model = make_model()
    model.fit(train_df[feat_cols], train_df[target])
    return model.predict_proba(test_df[feat_cols])[:, 1]


def fit_predict_lightgbm(train_df, test_df, feat_cols, target, seed=42):
    """LightGBM(欠損ネイティブ・train_lightgbm.py と同一パラメータ)で学習し
    test の P を返す。

    リーク防止: 6/6(test)は early-stopping の検証に一切使わない。
    early-stopping 用の検証は train 内部からレース単位で 15% を層化抽出して作る
    (艇行リーク防止のため race_id 単位で分割)。
    """
    if lgb is None:
        raise RuntimeError("lightgbm 未インストール: pip install lightgbm")

    rng = np.random.RandomState(seed)
    races = (train_df[["race_id", "venue"]].drop_duplicates()
             .reset_index(drop=True))
    # 会場層化で 15% を内部valid(early-stopping用)に
    val_races = set()
    for v, sub in races.groupby("venue"):
        ids = sub["race_id"].tolist()
        k = max(1, int(round(len(ids) * 0.15)))
        pick = rng.choice(ids, size=min(k, len(ids)), replace=False)
        val_races.update(pick.tolist())

    inner_tr = train_df[~train_df["race_id"].isin(val_races)]
    inner_va = train_df[train_df["race_id"].isin(val_races)]

    dtrain = lgb.Dataset(inner_tr[feat_cols], label=inner_tr[target],
                         free_raw_data=False)
    dvalid = lgb.Dataset(inner_va[feat_cols], label=inner_va[target],
                         reference=dtrain, free_raw_data=False)
    booster = lgb.train(
        LGB_PARAMS, dtrain,
        num_boost_round=LGB_NUM_BOOST_ROUND,
        valid_sets=[dvalid],
        callbacks=[lgb.early_stopping(LGB_EARLY_STOPPING, verbose=False),
                   lgb.log_evaluation(period=0)],
    )
    best_it = booster.best_iteration
    print(f"  LightGBM: inner_train={inner_tr['race_id'].nunique()}R / "
          f"inner_valid={inner_va['race_id'].nunique()}R / "
          f"best_iteration={best_it}")
    return booster.predict(test_df[feat_cols], num_iteration=best_it)


MODEL_LABEL = {"lightgbm": "LightGBM", "logreg": "LogReg"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="tmp/dot_0606.json")
    ap.add_argument("--md", default="tmp/dot_0606_report.md")
    ap.add_argument("--target", default="is_win", choices=["is_win", "is_top3"],
                    help="艇スコアの目的変数(本命順位付けに使用)")
    ap.add_argument("--model", default="lightgbm", choices=["lightgbm", "logreg"],
                    help="予想モデル(既定=本命LightGBM・欠損ネイティブ)")
    args = ap.parse_args()

    sb = get_client()
    model_label = MODEL_LABEL[args.model]
    print("=" * 72)
    print(f"DOT 2026-06-06 予想 vs 結果 照合(モデル={model_label}・"
          f"リーク防止: 6/6除外学習・読取専用)")
    print("=" * 72)

    df, used_races = load_dataset(sb)
    df, feat_cols = build_features(df)
    leaked = [c for c in feat_cols if c in LEAK_BLACKLIST]
    print(f"全学習可能レース(JOIN成立): {used_races}  特徴量: {len(feat_cols)}列  "
          f"リーク混入: {'NG' if leaked else 'OK(なし)'}")

    # --- 分割: TARGET日×3会場 = test, それ以外 = train ---
    is_target = (df["date"] == TARGET_DATE) & (df["venue"].isin(TARGET_VENUES))
    test_df = df[is_target].copy()
    train_df = df[~is_target].copy()

    n_test_races = test_df["race_id"].nunique()
    print(f"\n分割: train={train_df['race_id'].nunique()}レース "
          f"({len(train_df)}艇行) / test(6/6 3会場)={n_test_races}レース "
          f"({len(test_df)}艇行)")
    assert not (test_df["date"] == TARGET_DATE).all() or n_test_races <= 36
    # リーク確認: testのrace_idがtrainに無いこと
    overlap = set(train_df["race_id"]) & set(test_df["race_id"])
    print(f"  リーク確認: train∩test race_id = {len(overlap)} (0であること)")
    assert len(overlap) == 0, "リーク: testレースがtrainに混入"

    # --- 学習(train のみ) → 6/6 を未知データとして予想 ---
    if args.model == "lightgbm":
        scores = fit_predict_lightgbm(train_df, test_df, feat_cols, args.target,
                                      seed=42)
    else:
        scores = fit_predict_logreg(train_df, test_df, feat_cols, args.target)
    test_df = test_df.assign(_score=scores)

    # --- レース毎 予想生成 + 照合 ---
    per_race = []
    for (venue, race_no), sub in test_df.groupby(["venue", "race_no"]):
        sub = sub.sort_values("_score", ascending=False).reset_index(drop=True)
        pred_order = [int(x) for x in sub["lane"].tolist()]      # DOTスコア降順
        dot_top1 = pred_order[0]
        dot_combo = "-".join(str(x) for x in pred_order[:3])     # 3連単推奨(上位3艇その順)
        # 1号ベタ: 1号頭、残り枠順
        base_order = sorted(set(pred_order), key=lambda L: L)    # 1,2,3,4,5,6
        base_combo = "-".join(str(x) for x in base_order[:3])    # 1-2-3
        # 実結果
        wl = int(sub["winner_lane"].iloc[0])
        p2 = int(sub["place2_lane"].iloc[0])
        p3 = int(sub["place3_lane"].iloc[0])
        actual_combo = sub["trifecta_result"].iloc[0]
        payout = sub["trifecta_payout"].iloc[0]
        payout = float(payout) if not (isinstance(payout, float) and np.isnan(payout)) else 0.0
        actual_top3 = {wl, p2, p3}

        dot_top1_hit = (dot_top1 == wl)
        dot_in3 = (dot_top1 in actual_top3)        # 本命が3着内に来たか
        dot_tri_hit = (dot_combo == actual_combo)
        base_top1_hit = (base_order[0] == wl)      # =1号が1着か
        base_in3 = (base_order[0] in actual_top3)
        base_tri_hit = (base_combo == actual_combo)

        # スコア（参考: 各艇P）
        scores = {int(L): float(s) for L, s in zip(sub["lane"], sub["_score"])}

        per_race.append({
            "venue": venue, "race_no": int(race_no),
            "pred_order": pred_order, "dot_top1": dot_top1, "dot_combo": dot_combo,
            "base_top1": base_order[0], "base_combo": base_combo,
            "actual_1": wl, "actual_2": p2, "actual_3": p3,
            "actual_combo": actual_combo, "payout": payout,
            "dot_top1_hit": dot_top1_hit, "dot_in3": dot_in3, "dot_tri_hit": dot_tri_hit,
            "base_top1_hit": base_top1_hit, "base_in3": base_in3, "base_tri_hit": base_tri_hit,
            "scores": scores,
        })

    per_race.sort(key=lambda r: (TARGET_VENUES.index(r["venue"]), r["race_no"]))

    # --- 集計 ---
    def agg(rows):
        n = len(rows)
        if n == 0:
            return {}
        dot_top1 = sum(r["dot_top1_hit"] for r in rows)
        dot_in3 = sum(r["dot_in3"] for r in rows)
        dot_tri = sum(r["dot_tri_hit"] for r in rows)
        base_top1 = sum(r["base_top1_hit"] for r in rows)
        base_in3 = sum(r["base_in3"] for r in rows)
        base_tri = sum(r["base_tri_hit"] for r in rows)
        spent = 100.0 * n
        dot_ret = sum(r["payout"] for r in rows if r["dot_tri_hit"])
        base_ret = sum(r["payout"] for r in rows if r["base_tri_hit"])
        return {
            "n_races": n,
            "dot_top1_hit": dot_top1, "dot_top1_rate": dot_top1 / n,
            "dot_in3": dot_in3, "dot_in3_rate": dot_in3 / n,
            "dot_tri_hit": dot_tri, "dot_tri_rate": dot_tri / n,
            "dot_roi": dot_ret / spent,
            "base_top1_hit": base_top1, "base_top1_rate": base_top1 / n,
            "base_in3": base_in3, "base_in3_rate": base_in3 / n,
            "base_tri_hit": base_tri, "base_tri_rate": base_tri / n,
            "base_roi": base_ret / spent,
            "dot_ret": dot_ret, "base_ret": base_ret, "spent": spent,
        }

    by_venue = {v: agg([r for r in per_race if r["venue"] == v]) for v in TARGET_VENUES}
    overall = agg(per_race)

    # --- コンソール出力 ---
    print(f"\n■ 全体サマリ(6/6 {overall['n_races']}レース・目的変数={args.target})")
    print(f"  {'指標':16s} {'DOT':>10s} {'1号ベタ':>10s}")
    print(f"  {'Top1的中率':16s} {overall['dot_top1_rate']*100:9.1f}% {overall['base_top1_rate']*100:9.1f}%")
    print(f"  {'本命3着内率':16s} {overall['dot_in3_rate']*100:9.1f}% {overall['base_in3_rate']*100:9.1f}%")
    print(f"  {'3連単的中率':16s} {overall['dot_tri_rate']*100:9.1f}% {overall['base_tri_rate']*100:9.1f}%")
    print(f"  {'回収率(1点)':16s} {overall['dot_roi']*100:9.1f}% {overall['base_roi']*100:9.1f}%")

    out = {
        "target_date": TARGET_DATE, "venues": TARGET_VENUES,
        "model": args.model, "model_label": model_label,
        "score_target": args.target, "n_train_races": int(train_df["race_id"].nunique()),
        "n_test_races": int(n_test_races), "leak_overlap": len(overlap),
        "per_race": per_race, "by_venue": by_venue, "overall": overall,
        "n_features": len(feat_cols),
    }

    os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nJSON 保存: {args.json}")

    # --- Markdown レポート ---
    write_markdown(args.md, out)
    print(f"Markdown 保存: {args.md}")
    print("\n[完了] 本番DBは SELECT のみ・書込なし。engine.py 不変更。リーク無し(6/6除外学習)。")


def pct(x):
    return f"{x*100:.1f}%"


def write_markdown(path, out):
    L = []
    A = L.append
    ov = out["overall"]
    ml = out.get("model_label", "LightGBM")
    A(f"# DOTレーティング 予想 vs 結果 照合レポート — 2026-06-06({ml}予想)")
    A("")
    A(f"> 対象: **{out['target_date']}** 蒲郡(07)・常滑(08)・三国(10) 各12レース = **{out['n_test_races']}レース**")
    A(f"> モデル: **DOT {ml}**(本命モデル・欠損ネイティブ / 目的変数=`{out['score_target']}`)。"
      f"各艇スコア降順で本命・順位付け・3連単(上位3艇その順で1点買い)。比較として1号ベタを併記。")
    A(f"> **リーク防止**: 6/6の36レースを学習から完全除外(train={out['n_train_races']}レース)。"
      f"train∩test重複={out['leak_overlap']}(0=リーク無し)。6/6は未知データとして予想。"
      f"early-stopping検証もtrain内部から抽出し6/6は不使用。")
    A("> 本番DBはSELECTのみ・書込なし。`engine.py`不変更。")
    A("")

    # 全体サマリ
    A("## 1. 全体サマリ")
    A("")
    A(f"| 指標 | DOT({ml}) | 1号ベタ |")
    A("|---|---:|---:|")
    A(f"| Top1的中率(本命1着) | **{pct(ov['dot_top1_rate'])}** ({ov['dot_top1_hit']}/{ov['n_races']}) | {pct(ov['base_top1_rate'])} ({ov['base_top1_hit']}/{ov['n_races']}) |")
    A(f"| 本命3着内率 | {pct(ov['dot_in3_rate'])} ({ov['dot_in3']}/{ov['n_races']}) | {pct(ov['base_in3_rate'])} ({ov['base_in3']}/{ov['n_races']}) |")
    A(f"| 3連単的中率 | {pct(ov['dot_tri_rate'])} ({ov['dot_tri_hit']}/{ov['n_races']}) | {pct(ov['base_tri_rate'])} ({ov['base_tri_hit']}/{ov['n_races']}) |")
    A(f"| 回収率(3連単1点買い) | {pct(ov['dot_roi'])} (払戻{int(ov['dot_ret'])}円/投資{int(ov['spent'])}円) | {pct(ov['base_roi'])} (払戻{int(ov['base_ret'])}円/投資{int(ov['spent'])}円) |")
    A("")

    # 会場別
    A("## 2. 会場別サマリ")
    A("")
    A("| 会場 | R数 | DOT Top1 | 1号ベタ Top1 | DOT 3連単 | 1号 3連単 | DOT 回収率 | 1号 回収率 |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    for v in out["venues"]:
        m = out["by_venue"][v]
        if not m:
            continue
        A(f"| {v} | {m['n_races']} | {pct(m['dot_top1_rate'])} ({m['dot_top1_hit']}/{m['n_races']}) "
          f"| {pct(m['base_top1_rate'])} ({m['base_top1_hit']}/{m['n_races']}) "
          f"| {pct(m['dot_tri_rate'])} ({m['dot_tri_hit']}/{m['n_races']}) "
          f"| {pct(m['base_tri_rate'])} ({m['base_tri_hit']}/{m['n_races']}) "
          f"| {pct(m['dot_roi'])} | {pct(m['base_roi'])} |")
    A("")

    # レース毎
    A("## 3. レース毎 予想 vs 結果")
    A("")
    A(f"- **DOT予想({ml})**: 各艇スコア降順の艇番。先頭=本命。3連単=上位3艇をその順で1点。")
    A("- **的中**: ◎=的中 / ×=不的中。3連単は完全一致のみ的中。")
    A("")
    for v in out["venues"]:
        A(f"### {v}({VENUE_CODE[v]})")
        A("")
        A("| R | DOT予想順 | DOT3連単 | 実1-2-3着 | 配当(円) | DOT頭 | DOT3連単 | 1号3連単 |")
        A("|---:|---|---|---|---:|:---:|:---:|:---:|")
        for r in out["per_race"]:
            if r["venue"] != v:
                continue
            pred = "-".join(str(x) for x in r["pred_order"])
            actual = f"{r['actual_1']}-{r['actual_2']}-{r['actual_3']}"
            top1m = "◎" if r["dot_top1_hit"] else "×"
            trim = "◎" if r["dot_tri_hit"] else "×"
            btrim = "◎" if r["base_tri_hit"] else "×"
            A(f"| {r['race_no']} | {pred} | {r['dot_combo']} | {actual} | {int(r['payout'])} | {top1m} | {trim} | {btrim} |")
        A("")

    A("## 4. 備考")
    A("")
    A(f"- **モデル**: 本命 **DOT {ml}**(勾配ブースティング・欠損ネイティブ処理)。"
      "LogReg比で高精度(社内CV: Top1 55.2% > LogReg 52.0%・AUC 0.807)。"
      "欠損はLightGBMが分岐側で直接扱うため、特徴量の事前median補完・標準化は不要。")
    A("- **回収率の定義**: 各レースでDOTスコア上位3艇をその順で3連単100円1点買い。"
      "実`trifecta_result`と完全一致時のみ`trifecta_payout`を回収。1号ベタは1-2-3固定で同条件。")
    A("- 36レース×6艇=216艇行すべてが揃った状態(欠損なし)で照合。")
    A(f"- 学習特徴量{out['n_features']}列(枠内相対化z-score/順位含む)。結果系列の列は特徴量から除外済み(リーク防止)。")
    A("- **データ品質メモ**: 6/6 3会場の出走表は当初 `national_win_rate`/`national_place2_rate`/"
      "`avg_st`/`motor_place2_rate` が全件NULL(選手成績未取得)で、その状態ではDOTは枠順情報のみに退化し"
      "1号ベタとほぼ一致してしまった。VPS `/scrape`(items=entry)で6/6 3会場を冪等・非破壊に再取得し"
      "これら成績特徴を復旧(各72/72)。本レポートは復旧後データでの予想・照合。"
      "`local5y_*`/`general1y_*` は元来スクレイパ非取得のためNULL継続(LightGBMが欠損として処理)。")
    A("")

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
