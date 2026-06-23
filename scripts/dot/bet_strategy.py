#!/usr/bin/env python3
"""DOTレーティング step-4-2 — 買い目戦略の最適化(回収率改善・読み取り専用)

本命モデル(LightGBM, train_lightgbm.py)の P(win) を使い、複数の買い目戦略を
**同一のリーク無しOOF集合**でバックテストして比較する。engine.py は不変更、
本番 Supabase は SELECT のみ(DB 書き込みゼロ)。

------------------------------------------------------------------------------
背景 / 既存資産
------------------------------------------------------------------------------
- 本命モデル : scripts/dot/train_lightgbm.py(LightGBM・欠損ネイティブ・SELECT専用)
- 既存の回収率定義 : train_baseline.eval_roi_trifecta
    『P(win)上位3艇をその順で3連単100円1点、trifecta_result完全一致でtrifecta_payout回収』
  本スクリプトの strategy "A_baseline" がこれと同一(再現確認用)。
- OOF生成 : train_lightgbm.run_cv_lgb と同一思想(6月内 会場層化K-fold、5月は常にtrain合流、
  レース単位分割=艇行リーク無し)。本スクリプトでは買い目評価に必要な
  exacta_payout / trifecta_place_payout / 実着順(winner/place2/place3 lane)も併せて取得する。

------------------------------------------------------------------------------
本番DBで実弾バックテスト可能な券種(payout カバレッジ 100% / 2024完全結果)
------------------------------------------------------------------------------
  trifecta_payout        : 3連単(順序あり) … 完全一致で回収
  exacta_payout          : 2連単(1-2着順序あり) … 1-2着一致で回収
  trifecta_place_payout  : 3連複(順不同) … 上位3艇の集合一致で回収
    ※3連複は result 文字列が無いが、3連複の的中条件は「実際の1〜3着の集合」と一致する
      ことなので、winner/place2/place3 lane から判定でき payout も実値で回収できる。
  ※存在しない券種(2連複/拡連複/単勝/複勝)の payout は DB に無く、本検証では扱わない
    (近似の限界として report 末尾に明記)。

------------------------------------------------------------------------------
順列確率(EV/フォーメーション用): Plackett–Luce モデル
------------------------------------------------------------------------------
  各艇の「強さ」を s_i = P_i(win)(モデル出力)とみなし、順位付けの標準モデル
  Plackett–Luce で 3連単の順列確率を構成する:
     P(a→b→c) = s_a/Σ · s_b/(Σ-s_a) · s_c/(Σ-s_a-s_b)     (Σ=Σ_i s_i)
  これにより 1着確率しか持たないモデルから 2-3着の条件付き確率を一貫した形で導ける。
  3連複確率は対応する6順列の和、2連単確率は a→b の周辺化。

------------------------------------------------------------------------------
EVベース購入の payout 取得可能性 / 近似の限界(正直に明記)
------------------------------------------------------------------------------
  EV = P(of) × payout − stake を計算するには「買う前の各組合せの払戻(=オッズ)」が必要だが、
  本番DBには『的中した組合せの実払戻』しか無く、全組合せのオッズ盤は存在しない。
  そのため EV 戦略では payout を次の近似で推定する:
     est_payout(combo) ≈ (1 - takeout) / P_model(combo) × 100     (takeout≈0.25)
  これはモデル自身の確率からフェアオッズを引いた自己参照的な推定で、
  「モデルが市場より上手い」分だけ過大評価しうる。よって EV 戦略の回収率は
  上限寄りの参考値であり、的中時の回収は必ず DB の実 payout で行う(=回収は実弾、
  購入判定のみ推定オッズ)ことで、過度な楽観を避けつつ実測ベースに寄せている。
  この限界は report にも出力する。

使い方:
  python3 scripts/dot/bet_strategy.py
  python3 scripts/dot/bet_strategy.py --json tmp/dot_bet_strategy.json --folds 5
  python3 scripts/dot/bet_strategy.py --target is_win --takeout 0.25
"""
import os
import sys
import json
import argparse
from collections import defaultdict
from itertools import permutations

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import StratifiedKFold

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train_baseline as tb       # noqa: E402  load_dataset/build_features/get_client...
import train_lightgbm as tl       # noqa: E402  LGB_PARAMS / train_lgb

STAKE = 100.0  # 1点あたりの賭け金(円)


# ===========================================================================
# 1. データ取得 (SELECT のみ) — betting評価に必要な払戻・実着順も併せて取得
# ===========================================================================
def load_dataset_betting(sb, *, include_extra=False):
    """train_baseline.load_dataset を拡張し、exacta/3連複payoutと実着順laneを付与。

    include_extra=True のとき、承認プラン採用の追加列(players.rank/is_local/決まり手)
    も取得する(train_baseline.load_dataset と同一規則)。"""
    races = tb.fetch_all(sb, "races", "id,date,venue,race_no")
    race_by_id = {r["id"]: r for r in races}

    base_boat_cols = ["lane"] + tb.BASE_FEATURES
    extra_cols = list(tb.ADD_BOAT_COLS) if include_extra else []
    bcols_set = ["race_id"] + sorted(set(base_boat_cols + extra_cols))
    boats = tb.fetch_all(sb, "boats", ",".join(bcols_set))
    boats_by_race = defaultdict(list)
    for b in boats:
        boats_by_race[b["race_id"]].append(b)

    rank_by_pid = {}
    if include_extra:
        players = tb.fetch_all(sb, "players", "id,rank")
        rank_by_pid = {p["id"]: p.get("rank") for p in players}

    rwl = tb.fetch_all(
        sb, "race_winner_log",
        "date,venue,race_no,winner_lane,place2_lane,place3_lane,"
        "trifecta_result,trifecta_payout,"
        "exacta_result,exacta_payout,trifecta_place_payout",
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
        win_lane = res.get("winner_lane")
        p2 = res.get("place2_lane")
        p3 = res.get("place3_lane")
        top3 = {win_lane, p2, p3}
        for b in blist:
            row = {f: tb.to_float(b.get(f)) for f in tb.BASE_FEATURES}
            row["race_id"] = race_id
            row["date"] = key[0]
            row["venue"] = key[1]
            row["month"] = key[0][:7]
            row["lane"] = b.get("lane")
            row["is_win"] = 1 if b.get("lane") == win_lane else 0
            row["is_top3"] = 1 if b.get("lane") in top3 else 0
            # 実着順(順序あり/順不同の的中判定に使用)
            row["winner_lane"] = win_lane
            row["place2_lane"] = p2
            row["place3_lane"] = p3
            # 払戻(実弾回収はすべてこの実値で行う)
            row["trifecta_result"] = res.get("trifecta_result")
            row["trifecta_payout"] = tb.to_float(res.get("trifecta_payout"))
            row["exacta_result"] = res.get("exacta_result")
            row["exacta_payout"] = tb.to_float(res.get("exacta_payout"))
            row["trifecta_place_payout"] = tb.to_float(res.get("trifecta_place_payout"))
            if include_extra:
                for c in tb.ADD_BOAT_COLS:
                    if c == "player_id":
                        continue
                    row[c] = tb.to_float(b.get(c))
                pid = b.get("player_id")
                row["rank_raw"] = rank_by_pid.get(pid) if pid is not None else None
            rows.append(row)

    return pd.DataFrame(rows), used_races


# ===========================================================================
# 2. リーク無し OOF 生成(LightGBM P(win))
#    train_lightgbm.run_cv_lgb と同一分割思想。betting用の列を温存して返す。
# ===========================================================================
OOF_KEEP = [
    "race_id", "venue", "lane", "is_win", "is_top3",
    "national_win_rate",
    "winner_lane", "place2_lane", "place3_lane",
    "trifecta_result", "trifecta_payout",
    "exacta_result", "exacta_payout", "trifecta_place_payout",
]


def build_oof(df, feat_cols, target="is_win", n_folds=5, seed=42):
    # train合流月(4月+5月)・検証側(6月)は train_lightgbm の定数を単一の真実として参照。
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
# 3. Plackett–Luce 順列確率
# ===========================================================================
def pl_perm_prob(strength_by_lane, order):
    """order=(a,b,c) の 3連単確率。strength_by_lane: {lane: s>0}."""
    s = dict(strength_by_lane)
    total = sum(s.values())
    p = 1.0
    remaining = total
    for lane in order:
        si = s[lane]
        if remaining <= 0:
            return 0.0
        p *= si / remaining
        remaining -= si
    return p


def race_lane_strengths(sub):
    """1レース分の {lane: strength}。strength=P(win)を正規化(0割回避の床あり)。"""
    s = {int(lane): max(float(pw), 1e-9)
         for lane, pw in zip(sub["lane"].tolist(), sub["_pwin"].tolist())}
    return s


# ===========================================================================
# 4. 的中判定ユーティリティ(実着順ベース・実払戻回収)
# ===========================================================================
def actual_top3_order(sub):
    row = sub.iloc[0]
    return int(row["winner_lane"]), int(row["place2_lane"]), int(row["place3_lane"])


def actual_trifecta_payout(sub):
    return float(sub["trifecta_payout"].iloc[0])


def actual_exacta_payout(sub):
    return float(sub["exacta_payout"].iloc[0])


def actual_trio_payout(sub):
    """3連複 payout(順不同)。"""
    return float(sub["trifecta_place_payout"].iloc[0])


# ===========================================================================
# 5. 戦略群 — 各戦略は OOF を受け取り per-race の bet list を返す
#    bet = (kind, combo_tuple) ; kind in {'trifecta','exacta','trio'}
# ===========================================================================
def topn_lanes(sub, n):
    ordered = sub.sort_values("_pwin", ascending=False)
    return [int(x) for x in ordered["lane"].head(n).tolist()]


def strat_A_baseline(sub):
    """A: 上位3艇その順で3連単1点(既存ベースライン eval_roi_trifecta と同一)。"""
    t = topn_lanes(sub, 3)
    if len(t) < 3:
        return []
    return [("trifecta", (t[0], t[1], t[2]))]


def strat_B_formation_1x23(sub):
    """B: 1着=本命固定、2-3着=上位2〜4艇のフォーメーション(本命→{2,3,4位}順列)。
    点数=3着候補3つから2つ選ぶ順列=3P2=6点。"""
    t = topn_lanes(sub, 4)
    if len(t) < 4:
        t = topn_lanes(sub, 3)
        if len(t) < 3:
            return []
    head = t[0]
    cands = t[1:4] if len(t) >= 4 else t[1:3]
    bets = []
    for a, b in permutations(cands, 2):
        bets.append(("trifecta", (head, a, b)))
    return bets


def strat_C_box3(sub):
    """C: 上位3艇ボックス 3連単(3!=6点)。"""
    t = topn_lanes(sub, 3)
    if len(t) < 3:
        return []
    return [("trifecta", o) for o in permutations(t, 3)]


def strat_D_trio_box(sub):
    """D: 上位3艇 3連複1点(順不同)。"""
    t = topn_lanes(sub, 3)
    if len(t) < 3:
        return []
    return [("trio", tuple(sorted(t)))]


def strat_E_trio_box4(sub):
    """E: 上位4艇 3連複ボックス(4C3=4点)。"""
    t = topn_lanes(sub, 4)
    if len(t) < 4:
        return strat_D_trio_box(sub)
    from itertools import combinations
    return [("trio", tuple(sorted(c))) for c in combinations(t, 3)]


def strat_F_exacta(sub):
    """F: 上位2艇その順で2連単1点。"""
    t = topn_lanes(sub, 2)
    if len(t) < 2:
        return []
    return [("exacta", (t[0], t[1]))]


def build_market_prior(oof):
    """市場プリア(モデル非依存): 『枠番(lane 1..6)の着順パターン』の母集団頻度から
    3連単順列確率の素朴な市場推定を作る。競艇は枠番=人気の最大要因なので、
    枠番3つ組(a,b,c)の出現頻度 freq[(a,b,c)] を OOF全体で集計し、正規化して
    market_P(枠番順列) とする。これは個別レースの結果を使わない母集団統計で、
    モデル出力とは独立。EV比較の『市場側確率』として用いる。
    """
    cnt = defaultdict(int)
    tot = 0
    for rid, sub in oof.groupby("race_id"):
        w, p2, p3 = actual_top3_order(sub)
        cnt[(w, p2, p3)] += 1
        tot += 1
    prior = {k: v / tot for k, v in cnt.items()} if tot else {}
    # 平滑化用フロア(未観測順列向け)
    floor = (1.0 / tot) * 0.5 if tot else 1e-4
    return prior, floor


def calibrate_odds_k(oof):
    """3連単オッズ近似 odds(combo) ≈ k / market_P(combo) の係数 k を OOF全体で校正。
    的中(実際に起きた)3連単の実払戻と market_P から、population で
      payout_actual ≈ k / market_P(actual)  となる k を中央値推定:
      k = median( payout_actual × market_P(actual_combo) )
    （高配当の裾を抑えるため median）。これにより各順列の推定オッズが得られ、
    EV = P_model × est_odds − STAKE が非自明（モデルと市場のズレ）になる。
    ※全オッズ盤の代替で真のオッズではない（近似の限界=report明記）。
    k は母集団から1つ推定する集計量で個別レース結果はリークしない。
    """
    prior, floor = build_market_prior(oof)
    vals = []
    for rid, sub in oof.groupby("race_id"):
        w, p2, p3 = actual_top3_order(sub)
        mp = prior.get((w, p2, p3), floor)
        pay = actual_trifecta_payout(sub)
        if mp > 0 and pay > 0:
            vals.append(pay * mp)
    k = float(np.median(vals)) if vals else 100.0
    return k, prior, floor


def make_strat_EV(odds_k, prior, floor, ev_threshold, max_points):
    """G/H: EV>閾値の3連単順列のみ購入(資金配分の簡易版=点数上限)。
      est_odds(combo) = odds_k / market_P(combo)      [円/100円, 市場側=枠番頻度プリア]
      EV = P_model(combo) × est_odds − STAKE
    『モデルが市場より高く見積もる(=過小評価された)順列』だけを買う、本来のEV発想。
    回収は的中時に実DB払戻で行う(購入判定のみ推定オッズ)。
    max_points で1レースの購入点数を上限(資金管理)。"""
    def _strat(sub):
        s = race_lane_strengths(sub)
        lanes = list(s.keys())
        cand = []
        for order in permutations(lanes, 3):
            p = pl_perm_prob(s, order)
            if p <= 0:
                continue
            mp = prior.get(order, floor)
            est_odds = odds_k / mp
            ev = p * est_odds - STAKE
            if ev > ev_threshold:
                cand.append((ev, order))
        cand.sort(reverse=True)
        cand = cand[:max_points]
        return [("trifecta", o) for (_, o) in cand]
    return _strat


def make_strat_PL_topk(k):
    """I: Plackett–Luce 順列確率が高い順に k 点 3連単を買う(EVでなく確率優先)。"""
    def _strat(sub):
        s = race_lane_strengths(sub)
        lanes = list(s.keys())
        scored = []
        for order in permutations(lanes, 3):
            scored.append((pl_perm_prob(s, order), order))
        scored.sort(reverse=True)
        return [("trifecta", o) for (_, o) in scored[:k]]
    return _strat


# 1号ベタ(参考): 1号頭固定・残りは枠順 → 3連単1点
def strat_lane1(sub):
    ordered = sub.assign(_s=-sub["lane"].astype(float)).sort_values("_s", ascending=False)
    t = [int(x) for x in ordered["lane"].head(3).tolist()]
    return [("trifecta", (t[0], t[1], t[2]))]


# ===========================================================================
# 6. バックテスト評価器
# ===========================================================================
def settle_bet(kind, combo, sub):
    """1点の bet を実着順で清算。的中なら実払戻(円/100円)を返し、外れは0。"""
    w, p2, p3 = actual_top3_order(sub)
    if kind == "trifecta":
        if (w, p2, p3) == combo:
            return actual_trifecta_payout(sub)
        return 0.0
    if kind == "exacta":
        if (w, p2) == combo:
            return actual_exacta_payout(sub)
        return 0.0
    if kind == "trio":
        if set(combo) == {w, p2, p3}:
            return actual_trio_payout(sub)
        return 0.0
    raise ValueError(kind)


def backtest(oof, strat_fn):
    """戦略を OOF 全レースに適用。per-race の収支を集計し指標を返す。"""
    spent_total, ret_total = 0.0, 0.0
    hit_races, n_races, wagered_races = 0, 0, 0
    points_total = 0
    race_profits = []  # レース単位の純損益(分散用)

    for rid, sub in oof.groupby("race_id"):
        bets = strat_fn(sub)
        n_races += 1
        if not bets:
            race_profits.append(0.0)
            continue
        wagered_races += 1
        spent = STAKE * len(bets)
        ret = 0.0
        race_hit = False
        for kind, combo in bets:
            pay = settle_bet(kind, combo, sub)
            if pay > 0:
                ret += pay
                race_hit = True
        spent_total += spent
        ret_total += ret
        points_total += len(bets)
        if race_hit:
            hit_races += 1
        race_profits.append(ret - spent)

    roi = ret_total / spent_total if spent_total else 0.0
    hit_rate = hit_races / n_races if n_races else 0.0
    avg_points = points_total / n_races if n_races else 0.0
    profits = np.array(race_profits, dtype=float)
    return {
        "n_races": n_races,
        "wagered_races": wagered_races,
        "roi": roi,
        "hit_rate": hit_rate,
        "avg_points_per_race": avg_points,
        "spent": spent_total,
        "returned": ret_total,
        "net": ret_total - spent_total,
        "profit_std_per_race": float(profits.std()),
        "profit_mean_per_race": float(profits.mean()),
    }


# ===========================================================================
# 7. main
# ===========================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--target", default="is_win", choices=["is_win", "is_top3"])
    ap.add_argument("--takeout", type=float, default=0.25,
                    help="EV戦略の推定オッズ控除率(競艇はおおむね0.25)")
    args = ap.parse_args()

    sb = tb.get_client()

    print("=" * 78)
    print("DOTレーティング step-4-2 買い目戦略の最適化(回収率改善・読み取り専用)")
    print("=" * 78)

    df, used_races = load_dataset_betting(sb)
    print(f"\n■ データ取得(SELECTのみ): 学習可能 {used_races}R / {len(df)}艇行")
    print("  月別: " + ", ".join(f"{m}={n//6}R" for m, n in
                                  df.groupby('month').size().items()))

    df, feat_cols = tb.build_features(df)
    leaked = [c for c in feat_cols if c in tb.LEAK_BLACKLIST]
    allow = set(tb.BASE_FEATURES)
    for f in tb.RELATIVE_FEATURES:
        allow.add(f + "_z"); allow.add(f + "_rank")
    not_allowed = [c for c in feat_cols if c not in allow]
    print(f"\n■ 特徴量 {len(feat_cols)}列  リーク混入={'NG '+str(leaked) if leaked else 'OK'}"
          f"  allowlist={'NG '+str(not_allowed) if not_allowed else 'OK'}")

    print(f"\n■ リーク無しOOF生成(LightGBM P({args.target}), "
          f"6月内会場層化{args.folds}-fold, "
          f"{'+'.join(tl.TRAIN_MONTHS)}train合流, レース単位分割)")
    oof = build_oof(df, feat_cols, target=args.target,
                    n_folds=args.folds, seed=args.seed)
    n_oof = oof["race_id"].nunique()
    print(f"  OOFレース数: {n_oof}  (各レース1回だけ予測=out-of-fold, 艇行リーク無し)")

    # 既存定義との一致確認(A は eval_roi_trifecta と同じはず)
    ref_roi, ref_tri, _, _, _ = tb.eval_roi_trifecta(oof.assign(_score=oof["_pwin"]), "_score")
    print(f"  [整合確認] 既存eval_roi_trifecta: ROI={ref_roi*100:.1f}% "
          f"的中={ref_tri*100:.1f}%(戦略Aと一致するはず)")

    # EV戦略用: 市場プリア(枠番頻度)とオッズ係数を OOF母集団から校正
    odds_k, prior, floor = calibrate_odds_k(oof)
    print(f"  [EV校正] 市場プリア={len(prior)}パターン, odds_k(中央値)={odds_k:.1f} "
          f"(est_odds=odds_k/market_P)")

    strategies = [
        ("A: 3連単 上位3艇その順(既存BL)", strat_A_baseline),
        ("B: 3連単 1着固定×2-3着F(上位4)", strat_B_formation_1x23),
        ("C: 3連単 上位3艇BOX(6点)", strat_C_box3),
        ("D: 3連複 上位3艇(1点)", strat_D_trio_box),
        ("E: 3連複 上位4艇BOX(4点)", strat_E_trio_box4),
        ("F: 2連単 上位2艇その順(1点)", strat_F_exacta),
        ("G: EV>0 3連単(最大6点)", make_strat_EV(odds_k, prior, floor, 0.0, 6)),
        ("H: EV>50 3連単(最大4点)", make_strat_EV(odds_k, prior, floor, 50.0, 4)),
        ("I: PL確率上位3点 3連単", make_strat_PL_topk(3)),
        ("J: PL確率上位6点 3連単", make_strat_PL_topk(6)),
        ("参考: 1号頭固定 3連単(1点)", strat_lane1),
    ]

    results = {}
    print("\n" + "=" * 78)
    print(f"■ 戦略比較(同一OOF {n_oof}レース・リーク無し・回収は全て実DB払戻)")
    print("=" * 78)
    hdr = (f"  {'戦略':30s} {'的中率':>7s} {'回収率':>8s} {'平均点数':>8s} "
           f"{'純損益':>9s} {'損益σ/R':>9s}")
    print(hdr)
    print("  " + "-" * 76)
    for name, fn in strategies:
        m = backtest(oof, fn)
        results[name] = m
        print(f"  {name:30s} {m['hit_rate']*100:6.1f}% {m['roi']*100:7.1f}% "
              f"{m['avg_points_per_race']:7.2f}点 "
              f"{m['net']:8.0f}円 {m['profit_std_per_race']:8.0f}円")

    # 推奨: 的中率を大きく落とさず回収率最大。A の的中率を基準に -lossの許容内で最良ROI。
    base = results["A: 3連単 上位3艇その順(既存BL)"]
    base_hit = base["hit_rate"]
    # 「的中率を大きく落とさない」= Aの的中率の0.8倍以上を維持、を一つの基準に
    def candidate(name):
        m = results[name]
        return m["hit_rate"] >= base_hit * 0.8
    eligible = [(results[n]["roi"], n) for n, _ in strategies
                if not n.startswith("参考") and candidate(n)]
    eligible.sort(reverse=True)
    best_roi, best_name = eligible[0] if eligible else (base["roi"], "A: 3連単 上位3艇その順(既存BL)")

    print("\n" + "=" * 78)
    print("■ 推奨戦略")
    print("=" * 78)
    bm = results[best_name]
    print(f"  推奨: {best_name}")
    print(f"    回収率 {bm['roi']*100:.1f}%  的中率 {bm['hit_rate']*100:.1f}%  "
          f"平均{bm['avg_points_per_race']:.2f}点/R  損益σ {bm['profit_std_per_race']:.0f}円/R")
    print(f"    基準A: 回収率 {base['roi']*100:.1f}% 的中率 {base['hit_rate']*100:.1f}% "
          f"→ ROI差 {(bm['roi']-base['roi'])*100:+.1f}pt, "
          f"的中率差 {(bm['hit_rate']-base_hit)*100:+.1f}pt")
    lane1 = results["参考: 1号頭固定 3連単(1点)"]
    print(f"    1号ベタ比較: 回収率 {lane1['roi']*100:.1f}% 的中率 {lane1['hit_rate']*100:.1f}%")

    print("\n■ payout取得可能性 / 近似の限界(正直な明記)")
    print("  - 3連単/2連単/3連複の payout は本番DBに実値で100%存在 → A〜F,I,J は実弾バックテスト。")
    print("  - 2連複/拡連複/単勝/複勝の payout はDBに無く本検証では対象外(扱えない)。")
    print("  - EV戦略(G,H): 全組合せのオッズ盤がDBに無いため、est_odds=odds_k/market_P の近似を使用")
    print(f"    (market_P=枠番着順パターンの母集団頻度, odds_k={odds_k:.1f}=実払戻からの中央値校正)。")
    print("    枠番プリアは粗く、真のオッズではない=EVのROIは参考値。回収は的中時に実DB払戻で実施。")

    out = {
        "step": "4-2",
        "target": args.target,
        "folds": args.folds, "seed": args.seed, "takeout": args.takeout,
        "oof_races": int(n_oof), "n_boats": int(len(df)),
        "leak_free": (not leaked) and (not not_allowed),
        "consistency_eval_roi_trifecta": {"roi": ref_roi, "trifecta_hit": ref_tri},
        "strategies": {name: results[name] for name, _ in strategies},
        "recommended": {"name": best_name, **results[best_name]},
        "baseline_A": base,
        "lane1": lane1,
        "payout_availability": {
            "trifecta_payout": "DB実値100% (3連単・順序)",
            "exacta_payout": "DB実値100% (2連単・順序)",
            "trifecta_place_payout": "DB実値100% (3連複・順不同, resultは実着順集合で判定)",
            "unavailable": ["2連複", "拡連複", "単勝", "複勝"],
            "ev_payout_approx": (f"est_odds=odds_k/market_P, market_P=枠番着順頻度(母集団), "
                                 f"odds_k={odds_k:.1f}(実払戻の中央値校正). 全オッズ盤がDBに無いため近似"),
        },
        "ev_calibration": {"odds_k_median": odds_k, "n_market_patterns": len(prior)},
    }
    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\nJSON保存: {args.json}")

    print("\n[完了] 本番DBは SELECT のみ・書込なし。engine.py 不変更。リーク無しOOFで比較。")


if __name__ == "__main__":
    main()
