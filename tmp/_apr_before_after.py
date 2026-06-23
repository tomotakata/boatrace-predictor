#!/usr/bin/env python3
"""4月train取り込み前後の before/after 比較(読み取り専用).

同一の6月OOF(1401R)上で、train合流を『5月のみ(before)』『4月+5月(after)』に
切り替えて、LightGBM本命(Top1/AUC/3連単/ROI)と選択的投票(8seed robustness)を
両方測る。DBは1回だけSELECT。tl.TRAIN_MONTHS を monkeypatch して切替える。
"""
import os, sys, json
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "dot"))
sys.path.insert(0, "scripts/dot")
import train_baseline as tb
import train_lightgbm as tl
import bet_strategy as bs
import selective_voting as sv

SEEDS = [42, 1, 7, 13, 21, 99, 123, 2024]
FOCUS = ["p_top", "gap", "neg_entropy", "variance"]


def lgb_oof_metrics(df, feat_cols, target, seed=42, folds=5):
    """sv.build_oof と同一分割で OOF を作り Top1/AUC/3連単/ROI を返す."""
    oof = sv.build_oof(df, feat_cols, target=target, n_folds=folds, seed=seed)
    oof = oof.rename(columns={"_pwin": "_score"})
    top1, _, tot = tb.eval_top1_hit(oof, "_score")
    roi, tri, _, _, _ = tb.eval_roi_trifecta(oof, "_score")
    try:
        auc = roc_auc_score(oof[target], oof["_score"])
    except Exception:
        auc = float("nan")
    return {"oof_races": int(oof["race_id"].nunique()),
            "top1_hit_rate": float(top1), "auc": float(auc),
            "trifecta_hit_rate": float(tri), "roi": float(roi)}


def sv_robustness(df, feat_cols, target="is_win", folds=5, train_frac=0.6):
    oof0 = sv.build_oof(df, feat_cols, target=target, n_folds=folds, seed=42)
    odds_k, prior, floor = bs.calibrate_odds_k(oof0)
    strategies = sv.get_strategies(odds_k, prior, floor)
    eval_combos = [(s, fn, m) for s, fn in strategies.items() for m in FOCUS]
    summ, full, _ = sv.robustness_over_seeds(
        df, feat_cols, target, folds, train_frac, SEEDS, eval_combos)
    return summ, full


def run_variant(df, feat_cols, train_months, label):
    tl.TRAIN_MONTHS = list(train_months)
    res = {"label": label, "train_months": list(train_months),
           "lightgbm": {}, "sv_robustness": {}, "sv_full_test": {}}
    for tgt in ["is_win", "is_top3"]:
        res["lightgbm"][tgt] = lgb_oof_metrics(df, feat_cols, tgt)
    summ, full = sv_robustness(df, feat_cols, target="is_win")
    res["sv_robustness"] = summ
    res["sv_full_test"] = full
    return res


def main():
    sb = tb.get_client()
    df, used = bs.load_dataset_betting(sb)
    df, feat_cols = tb.build_features(df)
    months = {m: int(n // 6) for m, n in df.groupby("month").size().items()}
    print("月別:", months, "used", used)

    before = run_variant(df, feat_cols, ["2026-05"], "before_may_only")
    after = run_variant(df, feat_cols, ["2026-04", "2026-05"], "after_apr_may")
    tl.TRAIN_MONTHS = ["2026-04", "2026-05"]  # 後始末: 本番想定に戻す

    out = {"months": months, "used_races": used,
           "seeds": SEEDS, "focus_metrics": FOCUS,
           "before": before, "after": after, "deltas": {}}

    # LightGBM delta
    for tgt in ["is_win", "is_top3"]:
        b, a = before["lightgbm"][tgt], after["lightgbm"][tgt]
        out["deltas"].setdefault("lightgbm", {})[tgt] = {
            "d_top1_pt": round((a["top1_hit_rate"] - b["top1_hit_rate"]) * 100, 2),
            "d_auc": round(a["auc"] - b["auc"], 4),
            "d_roi_pt": round((a["roi"] - b["roi"]) * 100, 2),
        }
    # SV delta (median / min)
    sv_delta = {}
    for k in before["sv_robustness"]:
        bb, aa = before["sv_robustness"][k], after["sv_robustness"][k]
        sv_delta[k] = {
            "before_median": round(bb["test_roi_median"] * 100, 1),
            "after_median": round(aa["test_roi_median"] * 100, 1),
            "d_median_pt": round((aa["test_roi_median"] - bb["test_roi_median"]) * 100, 1),
            "before_min": round(bb["test_roi_min"] * 100, 1),
            "after_min": round(aa["test_roi_min"] * 100, 1),
            "d_min_pt": round((aa["test_roi_min"] - bb["test_roi_min"]) * 100, 1),
            "before_frac_over_100": round(bb["frac_over_100"] * 100),
            "after_frac_over_100": round(aa["frac_over_100"] * 100),
        }
    out["deltas"]["sv"] = sv_delta

    with open("tmp/dot_apr_before_after.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("\n=== LightGBM before/after (同一6月OOF) ===")
    for tgt in ["is_win", "is_top3"]:
        b, a = before["lightgbm"][tgt], after["lightgbm"][tgt]
        d = out["deltas"]["lightgbm"][tgt]
        print(f"[{tgt}] OOF={a['oof_races']}R  "
              f"Top1 {b['top1_hit_rate']*100:.1f}->{a['top1_hit_rate']*100:.1f} ({d['d_top1_pt']:+.1f}pt)  "
              f"AUC {b['auc']:.3f}->{a['auc']:.3f} ({d['d_auc']:+.3f})  "
              f"ROI {b['roi']*100:.1f}->{a['roi']*100:.1f} ({d['d_roi_pt']:+.1f}pt)")

    print("\n=== 選択的投票 robustness median before->after (8seed) ===")
    print(f"{'combo':40s} {'before':>8s} {'after':>8s} {'Δmed':>7s} {'Δmin':>7s}")
    for k, v in sorted(sv_delta.items(), key=lambda kv: -kv[1]["after_median"]):
        print(f"{k:40s} {v['before_median']:7.1f}% {v['after_median']:7.1f}% "
              f"{v['d_median_pt']:+6.1f} {v['d_min_pt']:+6.1f}")

    dmeds = [v["d_median_pt"] for v in sv_delta.values()]
    dmins = [v["d_min_pt"] for v in sv_delta.values()]
    print(f"\n全{len(sv_delta)}combo平均: Δmedian={np.mean(dmeds):+.1f}pt  Δmin={np.mean(dmins):+.1f}pt")
    print("\nJSON: tmp/dot_apr_before_after.json")


if __name__ == "__main__":
    main()
