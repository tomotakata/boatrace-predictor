import sys, json
sys.path.insert(0, 'scripts/dot')
import train_baseline as tb
import train_lightgbm as tl
import bet_strategy as bs
import selective_voting as sv

sb = tb.get_client()
df, used = bs.load_dataset_betting(sb)
df, feat_cols = tb.build_features(df)

seeds = [42, 1, 7, 13, 21, 99, 123, 2024]
focus = ["p_top", "gap", "neg_entropy", "variance"]

sb_strat_oof = sv.build_oof(df, feat_cols, target="is_win", n_folds=5, seed=42)
odds_k, prior, floor = bs.calibrate_odds_k(sb_strat_oof)
strategies = sv.get_strategies(odds_k, prior, floor)
eval_combos = [(s, fn, m) for s, fn in strategies.items() for m in focus]

def run(label, train_months):
    tl.TRAIN_MONTHS = train_months
    summ, full, _ = sv.robustness_over_seeds(df, feat_cols, "is_win", 5, 0.6, seeds, eval_combos)
    return summ, full

# 従来(5月のみ)
leg_summ, leg_full = run("legacy_may", ["2026-05"])
# 新(4+5月)
new_summ, new_full = run("new_apr_may", ["2026-04", "2026-05"])

out = {"seeds": seeds, "legacy": leg_summ, "new": new_summ,
       "legacy_full": leg_full, "new_full": new_full}
json.dump(out, open("tmp/dot_sv_compare.json","w"), ensure_ascii=False, indent=2)

print("combo(E×指標)            従来min  新min  Δmin | 従来med 新med Δmed | 従来max 新max")
for s, fn in strategies.items():
    if not s.startswith("E_"): continue
    for m in focus:
        k=f"{s}|{m}"; L=leg_summ[k]; N=new_summ[k]
        dmin=(N['test_roi_min']-L['test_roi_min'])*100
        dmed=(N['test_roi_median']-L['test_roi_median'])*100
        print(f"{m:12s} | min {L['test_roi_min']*100:5.1f}->{N['test_roi_min']*100:5.1f} ({dmin:+5.1f}) | med {L['test_roi_median']*100:5.1f}->{N['test_roi_median']*100:5.1f} ({dmed:+5.1f}) | max {L['test_roi_max']*100:5.1f}->{N['test_roi_max']*100:5.1f}")

# 全16combo平均
import numpy as np
dmins=[]; dmeds=[]
for k in leg_summ:
    dmins.append((new_summ[k]['test_roi_min']-leg_summ[k]['test_roi_min'])*100)
    dmeds.append((new_summ[k]['test_roi_median']-leg_summ[k]['test_roi_median'])*100)
print(f"\n全{len(leg_summ)}combo平均: Δmin={np.mean(dmins):+.1f}pt  Δmedian={np.mean(dmeds):+.1f}pt")
