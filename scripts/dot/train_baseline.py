#!/usr/bin/env python3
"""DOTレーティング step-2-1 — ベースライン学習(LogisticRegression・読み取り専用)

既存 v58.7 再現エンジン(backend/app/prediction/engine.py)とは完全独立の
新規データ駆動システム。本番 Supabase は SELECT のみ。DB は一切書き込まない。

パイプライン:
  1. データ取得  : races × boats × race_winner_log を INNER JOIN(date+venue+race_no)
  2. 特徴量整形  : リーク列除外 + 同レース6艇内の相対特徴(z-score/順位) + 欠損処理
  3. 学習       : LogisticRegression で P(is_win) / P(is_top3)
  4. 評価       : LogLoss / AUC / 的中率 / 回収率(trifecta_payout)
                  ベースライン比較 = (1)1号ベタ (2)national_win_rate順
  分割         : 5月は貧弱(平和島24)のため『6月内 会場層化 K-fold』を主とし
                 5月24レースは常に train に合流。会場層化で偏り汎化を確認。

使い方:
  python scripts/dot/train_baseline.py
  python scripts/dot/train_baseline.py --json tmp/dot_baseline.json --folds 5
"""
import os
import sys
import json
import argparse
from collections import defaultdict

import numpy as np
import pandas as pd

try:
    from supabase import create_client
except Exception:
    print("supabase-py が必要です: pip install supabase", file=sys.stderr)
    raise

from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold

DEFAULT_URL = "https://zotskrheypxrfsiyvwtl.supabase.co"
DEFAULT_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpvdHNrcmhleXB4cmZzaXl2d3RsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzk2MzE2MCwiZXhwIjoyMDkzNTM5MTYwfQ."
    "vPAauv7POeWLAgab1kfgLv5arRgGAlNFE6JsohNM__o"
)
PAGE = 1000

# ---------------------------------------------------------------------------
# リーク防止: 以下は「結果確定後」に決まる列。特徴量に絶対に含めない。
# boats 側には結果列は無いが、念のためブラックリストで二重に弾く。
# ---------------------------------------------------------------------------
LEAK_BLACKLIST = {
    "winner_lane", "winner_course", "place2_lane", "place3_lane",
    "trifecta_result", "exacta_result", "trifecta_payout", "exacta_payout",
    "trifecta_place_payout", "result_all", "is_win", "is_top3", "pos", "rank",
    "finish_order", "result",
}

# レース前に確定する(=リークしない)数値特徴の候補。
# EDA(tmp/dot_eda.json)で全欠損だった列(odds_win, motor_ratio, season_st 等)は除外。
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

# 同レース6艇内で相対化(z-score)する特徴。競艇は絶対値より相対力が効く。
RELATIVE_FEATURES = [
    "national_win_rate", "national_place2_rate",
    "local5y_win_rate", "general1y_win_rate",
    "avg_st", "motor_place2_rate", "weight",
]

# ---------------------------------------------------------------------------
# 特徴量改善(step-A 承認プラン): カバレッジ計測(tmp/dot_feature_coverage.json)で
# 全月(4/5/6)≥30% を満たした『DB実在だが未使用』の列のみを追加候補に採用する。
# 採用候補(全月100%カバレッジ):
#   - players.rank(級別 A1/A2/B1/B2) … boats.player_id 経由でJOIN
#   - is_local(当地選手フラグ)
#   - c{n}_nige/sashi/makuri/makurizashi(コース別決まり手回数, 100%)
#   - local5y_sashi/makuri/makurizashi(当地5年決まり手, 100%)
# 不採用(train月=4/5が0%・6月のみ~10%で構造的に学習不能、または全欠損):
#   気象(weather/wind_*/water_temperature/wave_height/temperature),
#   general1y_*/escape1y_*/*_st_rank/motor_dashfoot/motor_eval,
#   c{n}_place2_rate/c{n}_tricast_rate, players.win_rate/place_rate_*,
#   motor_*_score/motor_rank_*/nigiri_rate/tide_*。
# これらは ADD_* には含めない(=デフォルトでは取得・使用しない)。
# ---------------------------------------------------------------------------
# 追加で取得する boats 列(全月≥30%カバレッジ確認済み)。
ADD_BOAT_COLS = ["player_id", "is_local"]
for _n in range(1, 7):
    ADD_BOAT_COLS += [f"c{_n}_nige", f"c{_n}_sashi",
                      f"c{_n}_makuri", f"c{_n}_makurizashi"]
ADD_BOAT_COLS += ["local5y_sashi", "local5y_makuri", "local5y_makurizashi"]

# 級別(rank)の順序エンコード。固定辞書なのでデータ依存統計を使わず構造的にリーク無し。
RANK_ORDINAL = {"A1": 4.0, "A2": 3.0, "B1": 2.0, "B2": 1.0}

# 枠内相対化を追加する『改善特徴』(G4)。base列は既にBASE_FEATURESにある100%列のみ。
ST_RELATIVE_EXTRA = ["today_st", "exhibition_st", "course1y_st"]


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


# ---------------------------------------------------------------------------
# 1. データ取得 (SELECT のみ)
# ---------------------------------------------------------------------------
def load_dataset(sb, *, include_extra=False):
    """races × boats × race_winner_log を結合して学習用DataFrameを構築。

    include_extra=True のとき、承認プランで採用した『追加候補列』も取得する:
      - boats: ADD_BOAT_COLS(is_local / コース別決まり手 / local5y決まり手)
      - players.rank(boats.player_id 経由JOIN, 級別)
    include_extra=False(既定)では従来ベースラインと完全に同一の列のみ取得し、
    再現性を保つ。
    """
    races = fetch_all(sb, "races", "id,date,venue,race_no")
    race_by_id = {r["id"]: r for r in races}

    base_boat_cols = ["lane"] + BASE_FEATURES
    extra_cols = list(ADD_BOAT_COLS) if include_extra else []
    bcols_set = ["race_id"] + sorted(set(base_boat_cols + extra_cols))
    boats = fetch_all(sb, "boats", ",".join(bcols_set))
    boats_by_race = defaultdict(list)
    for b in boats:
        boats_by_race[b["race_id"]].append(b)

    rank_by_pid = {}
    if include_extra:
        players = fetch_all(sb, "players", "id,rank")
        rank_by_pid = {p["id"]: p.get("rank") for p in players}

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
            row["month"] = key[0][:7]
            row["lane"] = b.get("lane")
            row["is_win"] = 1 if b.get("lane") == win_lane else 0
            row["is_top3"] = 1 if b.get("lane") in top3 else 0
            row["trifecta_payout"] = to_float(payout)
            row["trifecta_result"] = res.get("trifecta_result")
            if include_extra:
                for c in ADD_BOAT_COLS:
                    if c == "player_id":
                        continue
                    row[c] = to_float(b.get(c))
                pid = b.get("player_id")
                row["rank_raw"] = rank_by_pid.get(pid) if pid is not None else None
            rows.append(row)

    df = pd.DataFrame(rows)
    return df, used_races


# ---------------------------------------------------------------------------
# 2. 特徴量整形 (リーク列除外 + 枠内相対化 + 欠損処理)
# ---------------------------------------------------------------------------
def build_features(df, *, include_extra=False, groups=None):
    """枠内相対化込みで特徴量列を構築。

    include_extra=False(既定)では従来ベースラインの特徴のみ(後方互換)。
    include_extra=True では承認プランの追加特徴グループを構築し、
    (feat_cols, group_map) を返す。group_map[グループ名]=その列リスト。
    groups が指定されればそのグループのみ有効化(ablation用)。
    """
    feat_cols = list(BASE_FEATURES)
    group_map = {"base": list(BASE_FEATURES)}

    g = df.groupby("race_id")
    rel_cols = []
    for f in RELATIVE_FEATURES:
        if f not in df.columns:
            continue
        mean = g[f].transform("mean")
        std = g[f].transform("std")
        z = (df[f] - mean) / std.replace(0, np.nan)
        df[f"{f}_z"] = z
        feat_cols.append(f"{f}_z")
        rel_cols.append(f"{f}_z")
        ascending = f in {"avg_st"}
        rank = g[f].rank(method="average", ascending=ascending)
        df[f"{f}_rank"] = rank
        feat_cols.append(f"{f}_rank")
        rel_cols.append(f"{f}_rank")
    group_map["base_relative"] = rel_cols

    if include_extra:
        ext = _build_extra_features(df, g, group_map)
        feat_cols += ext

    # ablation: 指定グループのみ採用(base は常に含める)
    if groups is not None:
        keep = {"base", "base_relative"} | set(groups)
        feat_cols = [c for grp, cols in group_map.items() if grp in keep
                     for c in cols]

    # リーク列が紛れていないか二重チェック
    leaked = [c for c in feat_cols if c in LEAK_BLACKLIST]
    if leaked:
        raise RuntimeError(f"リーク列が特徴量に混入: {leaked}")

    feat_cols = sorted(set(feat_cols))
    if include_extra:
        return df, feat_cols, group_map
    return df, feat_cols


def _safe_ratio(num, den):
    den = den.replace(0, np.nan)
    return num / den


def _build_extra_features(df, g, group_map):
    """承認プラン採用の追加特徴を構築し、追加列名リストを返す。

    全特徴はレース前確定の選手/機材属性のみ。固定辞書エンコード・枠内相対のため
    データ依存統計やtest期間情報を一切使わず構造的にリーク無し。
    """
    added = []

    # --- G1: 級別(rank) ---
    g1 = []
    if "rank_raw" in df.columns:
        df["rank_ord"] = df["rank_raw"].map(RANK_ORDINAL)
        g1.append("rank_ord")
        gg = df.groupby("race_id")
        mean = gg["rank_ord"].transform("mean")
        std = gg["rank_ord"].transform("std")
        df["rank_ord_z"] = (df["rank_ord"] - mean) / std.replace(0, np.nan)
        df["rank_ord_rank"] = gg["rank_ord"].rank(method="average",
                                                  ascending=False)
        g1 += ["rank_ord_z", "rank_ord_rank"]
    group_map["g1_rank"] = g1
    added += g1

    # --- G2: 決まり手(コース別 + 当地5年)比率 ---
    # 各艇の「自分の進入コースでの決まり手傾向」を比率化。
    # コース別: lane に対応する c{lane}_* を選択(逃げ率/まくり率/差し率)。
    g2 = []
    kim_cols = []
    for n in range(1, 7):
        need = [f"c{n}_nige", f"c{n}_sashi", f"c{n}_makuri", f"c{n}_makurizashi"]
        if all(c in df.columns for c in need):
            tot = (df[f"c{n}_nige"].fillna(0) + df[f"c{n}_sashi"].fillna(0)
                   + df[f"c{n}_makuri"].fillna(0) + df[f"c{n}_makurizashi"].fillna(0))
            df[f"c{n}_kim_total"] = tot
    # 自コース(lane)に応じた決まり手比率を抽出
    lane = df["lane"].astype("Int64")
    nige = pd.Series(np.nan, index=df.index)
    aggr = pd.Series(np.nan, index=df.index)   # まくり+まくり差し(攻め)
    sashi = pd.Series(np.nan, index=df.index)
    tot = pd.Series(np.nan, index=df.index)
    for n in range(1, 7):
        if f"c{n}_kim_total" not in df.columns:
            continue
        m = (lane == n).to_numpy()
        nige[m] = df.loc[m, f"c{n}_nige"]
        aggr[m] = df.loc[m, f"c{n}_makuri"].fillna(0) + df.loc[m, f"c{n}_makurizashi"].fillna(0)
        sashi[m] = df.loc[m, f"c{n}_sashi"]
        tot[m] = df.loc[m, f"c{n}_kim_total"]
    if tot.notna().any():
        df["course_nige_ratio"] = _safe_ratio(nige, tot)
        df["course_aggr_ratio"] = _safe_ratio(aggr, tot)
        df["course_sashi_ratio"] = _safe_ratio(sashi, tot)
        df["course_kim_total"] = tot
        kim_cols = ["course_nige_ratio", "course_aggr_ratio",
                    "course_sashi_ratio", "course_kim_total"]
    # 当地5年決まり手(コース非依存・選手の当地傾向)
    l5 = ["local5y_sashi", "local5y_makuri", "local5y_makurizashi"]
    if all(c in df.columns for c in l5):
        l5tot = (df["local5y_sashi"].fillna(0) + df["local5y_makuri"].fillna(0)
                 + df["local5y_makurizashi"].fillna(0))
        df["local5y_aggr_ratio"] = _safe_ratio(
            df["local5y_makuri"].fillna(0) + df["local5y_makurizashi"].fillna(0),
            l5tot)
        df["local5y_kim_total"] = l5tot
        kim_cols += ["local5y_aggr_ratio", "local5y_kim_total"]
    g2 = kim_cols
    group_map["g2_kimarite"] = g2
    added += g2

    # --- G3: is_local(当地選手フラグ) ---
    g3 = []
    if "is_local" in df.columns:
        g3 = ["is_local"]
    group_map["g3_islocal"] = g3
    added += g3

    # --- G4: ST系の枠内相対(today_st / exhibition_st / course1y_st) ---
    g4 = []
    gg = df.groupby("race_id")
    for f in ST_RELATIVE_EXTRA:
        if f not in df.columns:
            continue
        mean = gg[f].transform("mean")
        std = gg[f].transform("std")
        df[f"{f}_z"] = (df[f] - mean) / std.replace(0, np.nan)
        # STは小さいほど良い -> 昇順ランク(1=最速)
        df[f"{f}_rank"] = gg[f].rank(method="average", ascending=True)
        g4 += [f"{f}_z", f"{f}_rank"]
    group_map["g4_st_rel"] = g4
    added += g4

    return added


# ---------------------------------------------------------------------------
# 評価ヘルパ
# ---------------------------------------------------------------------------
def make_model():
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("clf", LogisticRegression(max_iter=2000, C=1.0, class_weight=None)),
    ])


def race_argmax_pick(df_eval, score_col):
    """各レースで score 最大の艇を1着予想として返す -> {race_id: predicted_lane}."""
    picks = {}
    for rid, sub in df_eval.groupby("race_id"):
        idx = sub[score_col].idxmax()
        picks[rid] = int(sub.loc[idx, "lane"])
    return picks


def eval_top1_hit(df_eval, score_col):
    """1着的中率: レースごとに score 最大艇が実際の1着か。"""
    hit, tot = 0, 0
    for rid, sub in df_eval.groupby("race_id"):
        idx = sub[score_col].idxmax()
        tot += 1
        if int(sub.loc[idx, "is_win"]) == 1:
            hit += 1
    return hit / tot if tot else 0.0, hit, tot


def eval_roi_trifecta(df_eval, score_col):
    """回収率(厳密・三連単): 各レースで score 上位3艇をその順で3連単1点買い(100円)。
    実 trifecta_result(=実1-2-3着)と完全一致したレースのみ trifecta_payout を回収。

    payout は 100円あたりの配当(円)。spent=100*レース数。roi=ret/spent。
    これは『艇別スコア→3連単買い目』の実弾ベースの回収率で、リーク無し・検証可能。
    1号ベタ/national順も同一ルール(各々のスコアで上位3艇を順序付け)で比較する。
    """
    stake_per_race = 100.0
    spent, ret, hit = 0.0, 0.0, 0
    for rid, sub in df_eval.groupby("race_id"):
        spent += stake_per_race
        ordered = sub.sort_values(score_col, ascending=False)
        pred_lanes = [int(x) for x in ordered["lane"].head(3).tolist()]
        if len(pred_lanes) < 3:
            continue
        pred_combo = "-".join(str(x) for x in pred_lanes)
        actual = sub["trifecta_result"].iloc[0]
        if actual == pred_combo:
            hit += 1
            pay = sub["trifecta_payout"].iloc[0]
            if not np.isnan(pay):
                ret += pay
    roi = ret / spent if spent else 0.0
    tri_hit_rate = hit / (spent / stake_per_race) if spent else 0.0
    return roi, tri_hit_rate, ret, spent, hit


# ---------------------------------------------------------------------------
# 3+4. 学習 + 評価 (6月内 会場層化 K-fold)
# ---------------------------------------------------------------------------
def run_cv(df, feat_cols, target, n_folds=5, seed=42):
    """6月内レースを会場層化K-foldで分割。5月レースは常にtrainへ合流。

    fold分割はレース単位(艇行単位だとリーク)。会場で層化。
    """
    df_jun = df[df["month"] == "2026-06"].copy()
    df_may = df[df["month"] == "2026-05"].copy()

    # レース単位のテーブル(層化キー=venue)
    races_jun = (df_jun[["race_id", "venue"]].drop_duplicates()
                 .reset_index(drop=True))
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)

    fold_metrics = []
    oof_records = []  # 全fold out-of-fold 予測を集約

    X_all_cols = feat_cols
    for fold, (tr_idx, va_idx) in enumerate(
        skf.split(races_jun["race_id"], races_jun["venue"])
    ):
        tr_races = set(races_jun.loc[tr_idx, "race_id"])
        va_races = set(races_jun.loc[va_idx, "race_id"])

        tr_df = pd.concat([
            df_may,                                   # 5月は常にtrain
            df_jun[df_jun["race_id"].isin(tr_races)],
        ], ignore_index=True)
        va_df = df_jun[df_jun["race_id"].isin(va_races)].copy()

        model = make_model()
        model.fit(tr_df[X_all_cols], tr_df[target])
        proba = model.predict_proba(va_df[X_all_cols])[:, 1]
        va_df = va_df.assign(_score=proba)

        ll = log_loss(va_df[target], proba, labels=[0, 1])
        try:
            auc = roc_auc_score(va_df[target], proba)
        except ValueError:
            auc = float("nan")

        hit_rate, hit, tot = eval_top1_hit(va_df, "_score")
        roi, tri_hit, ret, spent, _ = eval_roi_trifecta(va_df, "_score")

        fold_metrics.append({
            "fold": fold, "n_val_races": tot, "n_val_boats": len(va_df),
            "logloss": ll, "auc": auc,
            "top1_hit_rate": hit_rate,
            "trifecta_hit_rate": tri_hit,
            "roi": roi,
        })
        oof_records.append(va_df[["race_id", "venue", "lane", "is_win", "is_top3",
                                  "national_win_rate",
                                  "trifecta_payout", "trifecta_result",
                                  "_score"]])

    oof = pd.concat(oof_records, ignore_index=True)
    return fold_metrics, oof


def baseline_lane1(df_eval, target):
    """ベースライン①: 1号頭固定。1号艇を頭に、残りは枠順(2,3...)で3連単。"""
    tmp = df_eval.assign(_score=-df_eval["lane"].astype(float))
    hit_rate, hit, tot = eval_top1_hit(tmp, "_score")
    roi, tri_hit, ret, spent, _ = eval_roi_trifecta(tmp, "_score")
    return {"top1_hit_rate": hit_rate, "trifecta_hit_rate": tri_hit, "roi": roi}


def baseline_national(df_eval, target):
    """ベースライン②: national_win_rate 降順で頭〜3着を並べて3連単。"""
    col = "national_win_rate"
    tmp = df_eval.copy()
    tmp["_score"] = tmp[col].fillna(-1.0)
    hit_rate, hit, tot = eval_top1_hit(tmp, "_score")
    roi, tri_hit, ret, spent, _ = eval_roi_trifecta(tmp, "_score")
    return {"top1_hit_rate": hit_rate, "trifecta_hit_rate": tri_hit, "roi": roi}


def aggregate(fold_metrics):
    keys = ["logloss", "auc", "top1_hit_rate", "trifecta_hit_rate", "roi"]
    agg = {}
    for k in keys:
        vals = [m[k] for m in fold_metrics if not (isinstance(m[k], float) and np.isnan(m[k]))]
        agg[k] = float(np.mean(vals)) if vals else float("nan")
        agg[k + "_std"] = float(np.std(vals)) if vals else float("nan")
    return agg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None, help="評価結果JSONの保存先")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    sb = get_client()

    print("=" * 72)
    print("DOTレーティング step-2-1 ベースライン学習(LogReg・読み取り専用)")
    print("=" * 72)

    df, used_races = load_dataset(sb)
    print(f"\n■ データ取得(SELECTのみ)")
    print(f"  学習可能レース : {used_races}")
    print(f"  艇行数         : {len(df)}")
    print(f"  月別           : " +
          ", ".join(f"{m}={n//6}R" for m, n in
                    df.groupby('month').size().items()))

    df, feat_cols = build_features(df)
    print(f"\n■ 特徴量(リーク列除外済み・枠内相対化込み): {len(feat_cols)} 列")
    print("  " + ", ".join(feat_cols))
    # リーク防止の明示確認
    leaked = [c for c in feat_cols if c in LEAK_BLACKLIST]
    print(f"  リーク列混入チェック: {'NG ' + str(leaked) if leaked else 'OK(結果系列なし)'}")

    out = {"used_races": used_races, "n_boats": len(df),
           "n_features": len(feat_cols), "features": feat_cols,
           "leak_free": not leaked, "targets": {}}

    for target in ["is_win", "is_top3"]:
        print("\n" + "-" * 72)
        print(f"■ 目的変数: {target}  (6月内 会場層化{args.folds}-fold / 5月はtrain合流)")
        print("-" * 72)
        fold_metrics, oof = run_cv(df, feat_cols, target,
                                   n_folds=args.folds, seed=args.seed)
        for m in fold_metrics:
            print(f"  fold{m['fold']}: races={m['n_val_races']:3d} "
                  f"LogLoss={m['logloss']:.4f} AUC={m['auc']:.4f} "
                  f"Top1={m['top1_hit_rate']*100:5.1f}% "
                  f"3連単的中={m['trifecta_hit_rate']*100:4.1f}% "
                  f"回収率={m['roi']*100:6.1f}%")
        agg = aggregate(fold_metrics)
        print(f"  -- fold平均: LogLoss={agg['logloss']:.4f} AUC={agg['auc']:.4f} "
              f"Top1的中={agg['top1_hit_rate']*100:.1f}% "
              f"3連単的中={agg['trifecta_hit_rate']*100:.1f}% "
              f"回収率={agg['roi']*100:.1f}%")

        # ベースライン比較は同一の OOF(6月valid全集合)で評価して apples-to-apples に
        dot_top1, _, _ = eval_top1_hit(oof, "_score")
        dot_roi, dot_tri, _, _, _ = eval_roi_trifecta(oof, "_score")
        base1 = baseline_lane1(oof, target)
        base2 = baseline_national(oof, target)

        print(f"\n  【ベースライン比較(6月OOF {oof['race_id'].nunique()}レース・同一集合)】")
        print(f"  {'モデル':26s} {'Top1的中':>9s} {'3連単的中':>9s} {'回収率':>9s}")
        print(f"  {'DOT LogReg('+target+')':26s} "
              f"{dot_top1*100:8.1f}% {dot_tri*100:8.1f}% {dot_roi*100:8.1f}%")
        print(f"  {'(1) 1号ベタ':26s} "
              f"{base1['top1_hit_rate']*100:8.1f}% {base1['trifecta_hit_rate']*100:8.1f}% "
              f"{base1['roi']*100:8.1f}%")
        print(f"  {'(2) national_win_rate順':26s} "
              f"{base2['top1_hit_rate']*100:8.1f}% {base2['trifecta_hit_rate']*100:8.1f}% "
              f"{base2['roi']*100:8.1f}%")

        out["targets"][target] = {
            "fold_metrics": fold_metrics,
            "cv_mean": agg,
            "oof_dot": {"top1_hit_rate": dot_top1,
                        "trifecta_hit_rate": dot_tri, "roi": dot_roi},
            "baseline_lane1": base1,
            "baseline_national": base2,
            "oof_races": int(oof["race_id"].nunique()),
        }

    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\nJSON 保存: {args.json}")

    print("\n[完了] 本番DBは SELECT のみ・書込なし。engine.py 不変更。")


if __name__ == "__main__":
    main()
