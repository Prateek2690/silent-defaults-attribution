"""Revised experiments (v3). Writes results_v3/*.csv and results.md."""
import os, time
import numpy as np, pandas as pd
from walkbench.engine import Engine
from walkbench import cecl3 as C

OUT = "results_v3"; os.makedirs(OUT, exist_ok=True)
N = int(os.environ.get("WB_N", 10000)); SEEDS = list(range(int(os.environ.get("WB_SEEDS", 3))))
ONLY = os.environ.get("WB_ONLY", "X1,X2,X3,X4,X5,X6,X7,X8,X9").split(",")
BASE = dict(silent_share=0.5, whitespace_rate=0.05, rollout_share=0.3)


def setup(**kw):
    d = C.generate(C.Scenario(**{"n_loans": N, **kw})); e = Engine(); C.load(e, d); runs = C.run_all(e)
    return d, runs, C.games(runs)


def lines(att):
    return att.groupby(["dimension", "line"])[C.PLAYERS + ["total_change"]].sum()


def collapse(T, method):
    T = T.copy()
    if method == "targeted_merge":
        T["m"] = T["m"] + T["s"]; T["s"] = 0.0
    return T


def err(L, T, dim=None):
    if dim:
        L = L.xs(dim, level=0, drop_level=False); T = T.xs(dim, level=0, drop_level=False)
    L = L[C.PLAYERS].reindex(T.index).fillna(0)
    return (L - T).abs().to_numpy().sum() / max(T.abs().to_numpy().sum(), 1e-9)


def by_loan(att):
    return att[att.dimension == "total"].set_index("loan_id")


def X1():
    rows = []; rng = np.random.default_rng(7)
    for s in SEEDS:
        d, runs, g = setup(seed=s, **BASE)
        for m in C.METHODS:
            L = lines(C.attribute(runs, m, cache=g))
            rows.append(dict(seed=s, method=m, exact_gap=(L[C.PLAYERS].sum(axis=1) - L.total_change).abs().max()))
        keys, A, *_ = g["segment"]; res = []
        for _ in range(60):
            order = list(rng.permutation(C.PLAYERS)); phi = np.zeros((len(keys), C.NP)); mm = 0
            for p in order:
                phi[:, C.PLAYERS.index(p)] = A[:, mm | C.BIT[p]] - A[:, mm]; mm |= C.BIT[p]
            k = keys.copy(); k[C.PLAYERS] = phi; res.append(k.groupby("line")[C.PLAYERS].sum().to_numpy())
        spread = np.stack(res).max(0) - np.stack(res).min(0)
        tot = abs(runs[C.FULL].el.sum() - runs[0].el.sum())
        rows.append(dict(seed=s, method="order_spread", spread_musd=spread.max() / 1e6, spread_pct_change=100 * spread.max() / tot))
    return pd.DataFrame(rows)


def X2():
    rows = []
    for share in [0.0, 0.15, 0.3, 0.6]:
        for s in SEEDS:
            d, runs, g = setup(seed=s, rollout_share=share)
            ro = d["labels"]["rollout_low"]; allow = runs[C.FULL].el.sum(); chg = abs(allow - runs[0].el.sum())
            for m in ["sequential", "naive_shapley", "precedence_no_repair", "null_only", "unowned", "proposed"]:
                att = by_loan(C.attribute(runs, m, dims=("total",), cache=g))
                ph = att.loc[att.index.isin(ro), "m"].abs().sum()
                rows.append(dict(rollout_share=share, seed=s, method=m, phantom_musd=ph / 1e6,
                                 pct_allowance=100 * ph / allow, pct_change=100 * ph / chg))
    return pd.DataFrame(rows)


def X3():
    rows = []
    for share in [0.0, 0.25, 0.5, 1.0]:
        for s in SEEDS:
            d, runs, g = setup(seed=s, clean=True, silent_share=share, new_naics_share=0.5)
            tr = C.truth(d, g)
            for m in ["proposed", "null_only", "naive_shapley", "targeted_merge"]:
                rows.append(dict(silent_share=share, seed=s, method=m, error=err(lines(C.attribute(runs, m, cache=g)), collapse(tr, m))))
    return pd.DataFrame(rows)


def X4():
    rows = []
    for s in SEEDS:
        d, runs, g = setup(seed=s, clean=True, **BASE)
        tl = C.truth(d, g, dims=("total",), by_loan=True).set_index("loan_id")
        ws, ro = d["labels"]["v_ws"], d["labels"]["s"]
        for m in ["proposed", "unowned"]:
            att = by_loan(C.attribute(runs, m, dims=("total",), cache=g))
            rv = att.loc[att.index.isin(ws), "v"].sum() / tl.loc[tl.index.isin(ws), "v"].sum()
            rs = att.loc[att.index.isin(ro), "s"].sum() / tl.loc[tl.index.isin(ro), "s"].sum()
            rows.append(dict(seed=s, method=m, code_fix_recovered_pct=100 * rv, rating_system_recovered_pct=100 * rs))
    return pd.DataFrame(rows)


def X5():
    rows = []
    for u in [0.0, 0.25, 0.5, 1.0]:
        for s in SEEDS:
            d, runs, g = setup(seed=s, clean=True, silent_share=1.0, unmarked_share=u, new_naics_share=0.5)
            tr = C.truth(d, g)
            for m in ["proposed", "naive_shapley", "targeted_merge"]:
                rows.append(dict(unmarked_share=u, seed=s, method=m, error=err(lines(C.attribute(runs, m, cache=g)), collapse(tr, m))))
    return pd.DataFrame(rows)


def X6():
    rows = []
    for s in SEEDS:
        d, runs, g = setup(seed=s, clean=True, **BASE)
        tr = C.truth(d, g); tl = C.truth(d, g, dims=("total",), by_loan=True).set_index("loan_id")
        static = d["labels"]["static"]
        for m in C.METHODS:
            att = C.attribute(runs, m, cache=g); L = lines(att); T = collapse(tr, m)
            bl = by_loan(att); TL = collapse(tl[C.PLAYERS], m)
            sel = bl.index.isin(static)
            st = (bl.loc[sel, C.PLAYERS] - TL.loc[bl.index[sel]]).abs().to_numpy().sum() / TL.loc[bl.index[sel]].abs().to_numpy().sum()
            rep = runs[C.FULL].groupby("loan_id").el.sum().reindex(bl.index[bl.repaired]).sum() / runs[C.FULL].el.sum()
            rows.append(dict(seed=s, method=m, error_total_line=err(L, T, "total"), error_segment_lines=err(L, T, "segment"),
                             static_loan_error=st, repaired_allowance_pct=100 * rep))
    return pd.DataFrame(rows)


def X7():
    rows = []
    for s in SEEDS:
        d, runs, g = setup(seed=s, clean=True, **BASE)
        lab = d["labels"]; tl = C.truth(d, g, dims=("total",), by_loan=True).set_index("loan_id")
        for m in C.METHODS:
            L = lines(C.attribute(runs, m, cache=g)); att = by_loan(C.attribute(runs, m, dims=("total",), cache=g))
            def share(ids, col):
                sel = att.index.isin(ids); den = att.loc[sel, "total_change"].abs().sum()
                return att.loc[sel, col].abs().sum() / max(den, 1e-9)
            ws = att.index.isin(lab["v_ws"]); ro = att.index.isin(lab["s"])
            rows.append(dict(seed=s, method=m,
                R1_exact=(L[C.PLAYERS].sum(axis=1) - L.total_change).abs().max() < 1.0,
                R2_order_independent=(m != "sequential"),
                R3_no_phantom_model=(np.nan if m == "targeted_merge" else share(lab["s"], "m") < 0.01),
                R4_no_phantom_mapping=share(lab["new_code_entrant"], "r") < 0.01,
                R5_keeps_code_fix=abs(att.loc[ws, "v"].sum() / tl.loc[tl.index.isin(lab["v_ws"]), "v"].sum() - 1) < 0.05,
                R6_keeps_rating_system_effect=(False if m == "targeted_merge" else abs(att.loc[ro, "s"].sum() / tl.loc[tl.index.isin(lab["s"]), "s"].sum() - 1) < 0.05),
                R7_no_business_on_static=share(lab["static"], "b") < 0.01))
    return pd.DataFrame(rows)


def X8():
    rows = []
    for dp in [0.05, 0.02, 0.01]:
        for s in SEEDS[:2]:
            d, runs, g = setup(seed=s, rollout_share=0.3, default_pd=dp)
            ro = d["labels"]["rollout_low"]; chg = abs(runs[C.FULL].el.sum() - runs[0].el.sum())
            for m in ["sequential", "naive_shapley", "proposed"]:
                att = by_loan(C.attribute(runs, m, dims=("total",), cache=g))
                rows.append(dict(default_pd=dp, seed=s, method=m, pct_change=100 * att.loc[att.index.isin(ro), "m"].abs().sum() / chg))
    return pd.DataFrame(rows)


def X9():
    rows = []
    for n in [5000, 10000, 20000]:
        t0 = time.time(); d = C.generate(C.Scenario(n_loans=n)); e = Engine(); C.load(e, d); runs = C.run_all(e)
        t1 = time.time(); g = C.games(runs); C.attribute(runs, "proposed", cache=g); t2 = time.time()
        rows.append(dict(n_loans=n, engine=e.name, runs_64_sec=t1 - t0, attribution_sec=t2 - t1))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    fns = dict(X1=X1, X2=X2, X3=X3, X4=X4, X5=X5, X6=X6, X7=X7, X8=X8, X9=X9)
    for k in ONLY:
        t = time.time(); fns[k]().to_csv(f"{OUT}/{k}.csv", index=False); print(k, f"{time.time()-t:.1f}s", flush=True)
