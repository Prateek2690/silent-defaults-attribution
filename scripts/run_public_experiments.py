"""Public-data experiments (SBA 7(a) + Census NAICS concordance). Writes results_sba/*.csv."""
import os, time, itertools
import numpy as np, pandas as pd
from walkbench.engine import Engine
from walkbench import sba as S

OUT = "results_sba"; os.makedirs(OUT, exist_ok=True)
SAMPLE = int(os.environ.get("WB_SAMPLE", 0))


def setup():
    cfg = S.Config(sample=SAMPLE)
    d = S.build_inputs(cfg); e = Engine(); S.load(e, d)
    t = time.time(); g, totals, el_full = S.run_and_build(e); rt = time.time() - t
    return d, (totals, el_full), g, rt, 0.0


def main():
    d, (totals, el_full), g, rt, gt = setup()
    b0, b1 = d["loans_b0"], d["loans_b1"]
    cc = d["concordance"]; set17 = set(cc.naics2017); pre17 = {c[:4] for c in set17}
    meta = b1.set_index("loan_id")
    ids0, ids1 = set(b0.loan_id), set(b1.loan_id)
    new_ids = ids1 - ids0
    # real loan groups
    gap_ids = set(meta.index[~meta.naics.isin(set17)])                       # code absent from NAICS 2017
    new_gap = new_ids & gap_ids                                             # new loans with codes the old mapping lacks
    prefix_ids = set(meta.index[(~meta.naics.isin(set17)) & meta.naics.str[:4].isin(pre17)])  # v1 prefix fallback resolves
    common = b0.merge(b1, on="loan_id", suffixes=("_0", "_1"))
    unchanged = set(common.loc[(common.amt_0 == common.amt_1) & (common.term_0 == common.term_1), "loan_id"])
    summary = dict(loans_prior=len(b0), loans_current=len(b1), new_loans=len(new_ids),
                   exposure_prior_busd=b0.amt.sum() / 1e9, exposure_current_busd=b1.amt.sum() / 1e9,
                   el_prior_musd=totals[0] / 1e6, el_current_musd=totals[S.FULL] / 1e6,
                   code_gap_loans=len(gap_ids), new_loans_with_code_gap=len(new_gap),
                   prefix_resolvable_loans=len(prefix_ids), unchanged_loans=len(unchanged),
                   runs_32_sec=rt, games_sec=gt)
    pd.DataFrame([summary]).to_csv(f"{OUT}/summary.csv", index=False)
    print(summary, flush=True)

    rows, checks = [], []
    for m in S.METHODS:
        t = time.time(); att = S.attribute(None, m, cache=g); el = time.time() - t
        tot = att[att.dimension == "total"].set_index("loan_id")
        agg = tot[S.PLAYERS].sum()
        rows.append(dict(method=m, seconds=el, total_change_musd=tot.total_change.sum() / 1e6,
                         **{f"{p}_musd": agg[p] / 1e6 for p in S.PLAYERS},
                         exact_gap_usd=abs(agg.sum() - tot.total_change.sum()),
                         repaired_pct=100 * el_full.reindex(tot.index[tot.repaired]).sum() / totals[S.FULL]))

        def money(ids, col):
            sel = tot.index.isin(ids)
            return tot.loc[sel, col].abs().sum(), tot.loc[sel, "total_change"].abs().sum()
        pm, chg_new = money(new_gap, "m"); pr, _ = money(new_gap, "r")
        vv = tot.loc[tot.index.isin(prefix_ids), "v"].sum()
        bb, chg_unch = money(unchanged, "b")
        checks.append(dict(method=m,
                           phantom_model_on_new_gap_musd=pm / 1e6,
                           phantom_mapping_on_new_gap_musd=pr / 1e6,
                           code_fix_effect_on_prefix_loans_musd=vv / 1e6,
                           business_on_unchanged_musd=bb / 1e6,
                           business_on_unchanged_pct_of_their_change=100 * bb / max(chg_unch, 1),
                           separates_rating_from_model=(m != "targeted_merge")))
    pd.DataFrame(rows).to_csv(f"{OUT}/methods.csv", index=False)
    pd.DataFrame(checks).to_csv(f"{OUT}/checks.csv", index=False)
    print(pd.DataFrame(rows).round(2).to_string(), flush=True)
    print(pd.DataFrame(checks).round(2).to_string(), flush=True)

    # order dependence of a sequential walk over all 120 orders, sector lines
    keys, A, *_ = g["sector"]
    res = []
    for order in itertools.permutations(S.PLAYERS):
        phi = np.zeros((len(keys), S.NP)); mm = 0
        for p in order:
            phi[:, S.PLAYERS.index(p)] = A[:, mm | S.BIT[p]] - A[:, mm]; mm |= S.BIT[p]
        k = keys.copy(); k[S.PLAYERS] = phi; res.append(k.groupby("line")[S.PLAYERS].sum().to_numpy())
    spread = np.stack(res).max(0) - np.stack(res).min(0)
    pd.DataFrame([dict(max_order_spread_musd=spread.max() / 1e6,
                       sector_lines=spread.shape[0],
                       lines_over_10m=int((spread.max(axis=1) > 10e6).sum()))]).to_csv(f"{OUT}/order.csv", index=False)

    # instrumentation: drop one fallback site from the tagging and re-measure phantom effects
    inst = []
    for name, ow in [("all sites tagged", S.OWNERS["proposed"]),
                     ("model site untagged", {"r": "fb_r", "v": "fb_v"}),
                     ("mapping site untagged", {"m": "fb_m", "v": "fb_v"}),
                     ("none tagged", {})]:
        att = S.attribute(None, "x", dims=("total",), cache=g, owners=ow) if ow else \
              S.attribute(None, "precedence_no_repair", dims=("total",), cache=g)
        tot = att.set_index("loan_id")
        sel = tot.index.isin(new_gap)
        inst.append(dict(tagging=name,
                         phantom_model_musd=tot.loc[sel, "m"].abs().sum() / 1e6,
                         phantom_mapping_musd=tot.loc[sel, "r"].abs().sum() / 1e6,
                         rating_system_effect_musd=tot["s"].sum() / 1e6))
    pd.DataFrame(inst).to_csv(f"{OUT}/instrumentation.csv", index=False)
    print(pd.DataFrame(inst).round(2).to_string(), flush=True)


if __name__ == "__main__":
    main()
