"""Revised CECL benchmark (v3), addressing the Stage 7 review.

Changes from v2 (cecl.py):
  * The rating system is its own versioned input (player s). Version 1 moves a rollout set of loans
    onto a 20-grade scale via a crosswalk from the underlying risk score. Rating-scale migration is
    therefore a methodology change, not business.
  * Repair is direction-agnostic and never touches the two filed runs.
  * New baselines: targeted merge of dependent inputs {s, m} (the remedy suggested by Mei & Lin,
    arXiv:2608.04547) and a stratified baseline (loans affected by any fallback are attributed to
    business, others by naive Shapley), in the spirit of Rozenfeld (arXiv:2412.13158).
  * Evaluation adds an order-independent truth on static single-cause loans and a rules checklist.

Public-structure sources only; synthetic data only.
"""
from dataclasses import dataclass
from itertools import permutations
import numpy as np
import pandas as pd

PLAYERS = ["b", "c", "r", "s", "m", "v"]
NP = len(PLAYERS)
BIT = {p: 1 << i for i, p in enumerate(PLAYERS)}
NM = 1 << NP
FULL = NM - 1
PIPE = ["r", "s", "m", "v"]
OLD_GRADES = [str(g) for g in range(1, 11)]
NEW_GRADES = [f"N{g:02d}" for g in range(1, 21)]
N_NAICS0, N_NAICS1 = 180, 200
SEGMENTS = ["CRE", "ENERGY", "TECH", "HEALTH", "MANUF", "RETAIL", "FINANCE", "TRANSPORT"]
SMM_Q = 0.02


@dataclass
class Scenario:
    n_loans: int = 10000
    seed: int = 0
    payoff_rate: float = 0.06
    entrant_rate: float = 0.08
    new_naics_share: float = 0.3
    new_product_share: float = 0.1
    rollout_share: float = 0.3        # share of loans the new rating system moves to the 20-grade scale
    remap_share: float = 0.05
    missing_rating_rate: float = 0.02
    prior_corr_rate: float = 0.02
    whitespace_rate: float = 0.02
    silent_share: float = 0.0
    unmarked_share: float = 0.0
    default_pd: float = 0.05
    clean: bool = False


def pd_tables(default_pd):
    base = {str(g): 0.002 * (1.55 ** (g - 1)) for g in range(1, 11)}
    m0 = dict(base, DEFAULT=default_pd)
    m1 = dict(base)
    for g in ["8", "9", "10"]:
        m1[g] = base[g] * 1.30
    for i, g in enumerate(NEW_GRADES):   # new scale, calibrated to the same score range
        m1[g] = 0.002 * (1.55 ** (i / 2.0)) * 0.9
    m1["DEFAULT"] = default_pd
    to_df = lambda d: pd.DataFrame({"grade": list(d), "pd": list(d.values())})
    mult = pd.DataFrame({"segment": SEGMENTS + ["OTHER"], "mult": [1.4, 1.2, 1.0, 0.8, 1.1, 1.0, 0.9, 1.1, 1.0]})
    return to_df(m0), to_df(m1), mult


def generate(sc: Scenario):
    rng = np.random.default_rng(sc.seed)
    seg0 = rng.integers(0, len(SEGMENTS), N_NAICS0)
    remapped = set(rng.choice(N_NAICS0, int(sc.remap_share * N_NAICS0), replace=False).tolist())
    seg1 = seg0.copy()
    for k in remapped:
        seg1[k] = (seg1[k] + rng.integers(1, len(SEGMENTS))) % len(SEGMENTS)
    r0 = pd.DataFrame({"naics": range(N_NAICS0), "segment": [SEGMENTS[s] for s in seg0], "is_catch_all": 0})
    k = int(round(sc.silent_share * (N_NAICS1 - N_NAICS0)))
    if k:
        silent = rng.choice(np.arange(N_NAICS0, N_NAICS1), k, replace=False)
        marked = (rng.random(k) >= sc.unmarked_share).astype(int)
        r0 = pd.concat([r0, pd.DataFrame({"naics": silent, "segment": "OTHER", "is_catch_all": marked})], ignore_index=True)
    r1 = pd.DataFrame({"naics": range(N_NAICS1), "is_catch_all": 0,
                       "segment": [SEGMENTS[s] for s in np.concatenate([seg1, rng.integers(0, len(SEGMENTS), N_NAICS1 - N_NAICS0)])]})
    pd0, pd1, mult = pd_tables(sc.default_pd)

    def new_loans(n, start, naics_pool, products, probs, score_hi):
        score = rng.uniform(1.0, score_hi, n)
        return pd.DataFrame({"loan_id": np.arange(start, start + n), "naics": rng.choice(naics_pool, n),
                             "product": rng.choice(products, n, p=probs), "score": np.round(score, 3),
                             "rating": [str(int(x)) for x in score],
                             "balance": np.round(rng.lognormal(15.0, 1.0, n), 2), "term_q": rng.integers(4, 21, n)})

    P4 = (["TERM_LOAN", "REVOLVER", "CRE_INVESTOR", "OWNER_OCC_CRE"], [0.35, 0.30, 0.20, 0.15])
    q0 = new_loans(sc.n_loans, 0, np.arange(N_NAICS0), *P4, 10.999)
    hi0 = q0["rating"].isin(["8", "9", "10"]).values
    rem0 = q0["naics"].isin(remapped).values
    occ0 = (q0["product"] == "OWNER_OCC_CRE").values
    if sc.clean:
        q0.loc[hi0 & (rem0 | occ0), ["score", "rating"]] = [5.5, "5"]
        q0.loc[occ0 & rem0, "product"] = "TERM_LOAN"
        hi0 = q0["rating"].isin(["8", "9", "10"]).values
        occ0 = (q0["product"] == "OWNER_OCC_CRE").values
    free0 = ~(hi0 | rem0 | occ0)
    ro0 = (rng.random(len(q0)) < sc.rollout_share) & (free0 if sc.clean else True)
    protected = (hi0 | rem0 | occ0 | ro0) if sc.clean else np.zeros(len(q0), bool)

    payoff = (rng.random(len(q0)) < sc.payoff_rate) & ~protected
    surv = q0[~payoff].copy()
    mov = ~protected[~payoff]
    surv.loc[mov, "balance"] = np.round(surv.loc[mov, "balance"] * np.exp(rng.normal(-0.01, 0.05, mov.sum())), 2)
    surv.loc[mov, "term_q"] = np.maximum(surv.loc[mov, "term_q"] - 1, 1)
    mig = mov & (rng.random(len(surv)) < 0.10)
    cap = 7.999 if sc.clean else 10.999
    surv.loc[mig, "score"] = np.round(np.clip(surv.loc[mig, "score"] + rng.choice([-1.0, 1.0], mig.sum()), 1.0, cap), 3)
    surv["rating"] = [str(int(x)) for x in surv["score"]]

    n_ent = int(sc.entrant_rate * len(q0))
    pool = np.array([x for x in range(N_NAICS0) if not (sc.clean and x in remapped)])
    PE = (["TERM_LOAN", "REVOLVER", "CRE_INVESTOR"], [0.4, 0.35, 0.25]) if sc.clean else P4
    ent = new_loans(n_ent, sc.n_loans, pool, *PE, 7.999 if sc.clean else 10.999)
    kk = rng.random(n_ent) < sc.new_naics_share
    ent.loc[kk, "naics"] = rng.integers(N_NAICS0, N_NAICS1, kk.sum())
    kp = rng.random(n_ent) < sc.new_product_share
    ent.loc[kp, "product"] = "SUST_LINKED"
    ro_e = (rng.random(n_ent) < sc.rollout_share) & ((~kk & ~kp) if sc.clean else True)
    q1 = pd.concat([surv, ent], ignore_index=True)
    rollout = set(q0.loc[ro0, "loan_id"]) | set(ent.loc[ro_e, "loan_id"])

    raw1 = q1.copy()
    in_ro = q1["loan_id"].isin(rollout).values
    untouched = (~q1["loan_id"].isin(ent["loan_id"]) & ~q1["naics"].isin(remapped) & (q1["product"] != "OWNER_OCC_CRE")
                 & q1["rating"].isin([str(g) for g in range(1, 8)])).values & ~in_ro if sc.clean else np.ones(len(q1), bool)
    miss = untouched & (rng.random(len(q1)) < sc.missing_rating_rate)
    raw1.loc[miss, "rating"] = None
    ws = untouched & ~miss & (rng.random(len(q1)) < sc.whitespace_rate) & ~in_ro
    if sc.clean:  # hold whitespace loans still so the ownership test isolates the code fix
        q0i = q0.set_index("loan_id"); ids = q1["loan_id"].values[ws]
        for col in ["balance", "term_q", "score", "rating"]:
            vals = q0i.loc[ids, col].values
            q1.loc[ws, col] = vals; raw1.loc[ws, col] = vals
    raw1.loc[ws, "rating"] = raw1.loc[ws, "rating"].astype(str) + " "
    corr_cur = pd.DataFrame({"quarter": 1, "loan_id": q1["loan_id"].values[miss], "field": "rating",
                             "value": q1["rating"].values[miss], "recorded_in": 1})
    elig0 = q0["loan_id"].isin(q1["loan_id"]).to_numpy().copy()
    if sc.clean:
        elig0 &= ~protected & ~q0["loan_id"].isin(q1["loan_id"].values[miss | ws]).values
    pc = elig0 & (rng.random(len(q0)) < sc.prior_corr_rate)
    filed0 = q0.copy()
    filed0.loc[pc, "balance"] = np.round(q0.loc[pc, "balance"] * rng.choice([0.5, 1.5], pc.sum()), 2)
    corr_prior = pd.DataFrame({"quarter": 0, "loan_id": q0["loan_id"].values[pc], "field": "balance",
                               "value": q0["balance"].values[pc].astype(str), "recorded_in": 1})

    surv_ids = set(surv["loan_id"])
    static = set(q0.loc[protected, "loan_id"]) & surv_ids
    labels = {
        "entrant": set(ent["loan_id"]), "exit": set(q0.loc[payoff, "loan_id"]), "rollout": rollout,
        "rollout_low": set(q1.loc[q1["loan_id"].isin(rollout) & (q1["score"] < 8.0), "loan_id"]),
        "new_code_entrant": set(ent.loc[kk, "loan_id"]),
        "r": set(surv.loc[surv["naics"].isin(remapped), "loan_id"]) if sc.clean else set(),
        "m": set(surv.loc[surv["rating"].isin(["8", "9", "10"]), "loan_id"]) if sc.clean else set(),
        "v": set(surv.loc[surv["product"] == "OWNER_OCC_CRE", "loan_id"]) if sc.clean else set(),
        "s": rollout if sc.clean else set(),
        "c": set(corr_prior["loan_id"]), "v_ws": set(q1["loan_id"].values[ws]) & surv_ids,
        "static": static if sc.clean else set(),
    }
    ng = pd.DataFrame({"bin": range(1, 21), "grade": NEW_GRADES})
    return {"loans_b0": filed0, "loans_b1": raw1, "corr": pd.concat([corr_cur, corr_prior], ignore_index=True),
            "naics_r0": r0, "naics_r1": r1, "pd_m0": pd0, "pd_m1": pd1, "mult_m0": mult, "mult_m1": mult,
            "rollout_s0": pd.DataFrame({"loan_id": pd.Series([], dtype="int64")}),
            "rollout_s1": pd.DataFrame({"loan_id": sorted(rollout)}), "ng": ng, "labels": labels}


TABLES = ["loans_b0", "loans_b1", "corr", "naics_r0", "naics_r1", "pd_m0", "pd_m1", "mult_m0", "mult_m1", "rollout_s0", "rollout_s1", "ng"]


def load(engine, d):
    for k in TABLES:
        engine.load(k, d[k])


def pipeline_sql(b, c, r, s, m, v):
    known = "('TERM_LOAN','REVOLVER','OWNER_OCC_CRE','CRE_INVESTOR')" if v == 0 else "('TERM_LOAN','REVOLVER','OWNER_OCC_CRE','CRE_INVESTOR','SUST_LINKED')"
    klass = ("CASE p.product WHEN 'TERM_LOAN' THEN 'C&I' WHEN 'REVOLVER' THEN 'C&I' WHEN 'OWNER_OCC_CRE' THEN 'C&I' WHEN 'CRE_INVESTOR' THEN 'CRE' ELSE 'C&I' END"
             if v == 0 else
             "CASE p.product WHEN 'TERM_LOAN' THEN 'C&I' WHEN 'REVOLVER' THEN 'C&I' WHEN 'OWNER_OCC_CRE' THEN 'CRE' WHEN 'CRE_INVESTOR' THEN 'CRE' WHEN 'SUST_LINKED' THEN 'CRE' ELSE 'C&I' END")
    rating = "TRIM(COALESCE(kr.value, l.rating))" if v == 1 else "COALESCE(kr.value, l.rating)"
    return f"""
    DROP TABLE IF EXISTS pre;
    CREATE TABLE pre AS
    SELECT l.loan_id, l.naics, l.product, l.term_q, l.score,
           COALESCE(CAST(kb.value AS DOUBLE), l.balance) AS balance,
           CASE WHEN ro.loan_id IS NOT NULL THEN ng.grade ELSE {rating} END AS grade
    FROM loans_b{b} l
    LEFT JOIN (SELECT loan_id, value FROM corr WHERE field = 'rating' AND quarter = {b}) kr ON kr.loan_id = l.loan_id
    LEFT JOIN (SELECT loan_id, value FROM corr WHERE field = 'balance' AND quarter = {b} AND (quarter = 1 OR recorded_in <= {b + c})) kb ON kb.loan_id = l.loan_id
    LEFT JOIN rollout_s{s} ro ON ro.loan_id = l.loan_id
    LEFT JOIN ng ON ng.bin = CAST(l.score * 2 AS INTEGER) - 1;
    DROP TABLE IF EXISTS out_rows;
    CREATE TABLE out_rows AS
    SELECT p.loan_id, p.balance, p.term_q,
           COALESCE(x.segment, 'OTHER') AS segment,
           {klass} AS loan_class,
           CASE WHEN {klass} = 'CRE' THEN 0.30 ELSE 0.40 END AS lgd,
           COALESCE(g.pd, (SELECT pd FROM pd_m{m} WHERE grade = 'DEFAULT')) * COALESCE(mu.mult, 1.0) AS pd_annual,
           CASE WHEN x.segment IS NULL OR x.is_catch_all = 1 THEN 1 ELSE 0 END AS fb_r,
           CASE WHEN x.segment IS NULL THEN 1 ELSE 0 END AS fb_r_null,
           CASE WHEN p.grade IS NOT NULL AND g.pd IS NULL THEN 1 ELSE 0 END AS fb_m,
           CASE WHEN p.product NOT IN {known} THEN 1 ELSE 0 END AS fb_v,
           CASE WHEN p.grade IS NULL THEN 1 ELSE 0 END AS fb_d
    FROM pre p
    LEFT JOIN naics_r{r} x ON x.naics = p.naics
    LEFT JOIN pd_m{m} g ON g.grade = p.grade
    LEFT JOIN mult_m{m} mu ON mu.segment = COALESCE(x.segment, 'OTHER');
    """


def expected_loss(rows):
    pdq = 1 - (1 - np.clip(rows["pd_annual"].to_numpy(), 0, 0.99)) ** 0.25
    a = pdq + SMM_Q - pdq * SMM_Q
    return rows["balance"].to_numpy() * pdq * rows["lgd"].to_numpy() * (1 - (1 - a) ** rows["term_q"].to_numpy()) / a


def versions(mask):
    return tuple(int(bool(mask & (1 << i))) for i in range(NP))


def run_all(engine):
    runs = {}
    for mask in range(NM):
        engine.execute(pipeline_sql(*versions(mask)))
        rows = engine.query("SELECT * FROM out_rows")
        rows["el"] = expected_loss(rows)
        rows["total"] = "ALLOWANCE"
        runs[mask] = rows
    return runs


FLAGS = ["fb_r", "fb_r_null", "fb_m", "fb_v", "fb_d"]


def game(runs, dim):
    frames = []
    for mask, rows in runs.items():
        g = rows.groupby(["loan_id", dim], as_index=False)["el"].sum(); g["mask"] = mask; frames.append(g)
    wide = pd.concat(frames).pivot_table(index=["loan_id", dim], columns="mask", values="el", aggfunc="sum", fill_value=0.0)
    wide = wide.reindex(columns=range(NM), fill_value=0.0)
    keys = wide.index.to_frame(index=False).rename(columns={dim: "line"})
    loans = np.sort(keys["loan_id"].unique()); pos = {l: i for i, l in enumerate(loans)}
    flags = {f: np.zeros((len(loans), NM), bool) for f in FLAGS}
    for mask, rows in runs.items():
        f = rows.groupby("loan_id")[FLAGS].max()
        idx = np.fromiter((pos[l] for l in f.index), int, len(f))
        for col in FLAGS:
            flags[col][idx, mask] = f[col].to_numpy().astype(bool)
    flags["fb_any"] = flags["fb_r"] | flags["fb_m"] | flags["fb_v"]
    return keys, wide.to_numpy(), keys["loan_id"].map(pos).to_numpy(), flags, loans


def games(runs, dims=("total", "segment", "loan_class")):
    return {d: game(runs, d) for d in dims}


def repair_targets(flags, owners):
    """Flip component p for a loan when a p-owned flag fires at the evaluated mask but not with p
    flipped -- unless that same flag already fires in the filed run in which this version of p was
    actually in force. In that case the default is real reporting history, not an artifact of mixing
    versions, and repairing it would move a genuine version effect onto another cause."""
    n = next(iter(flags.values())).shape[0]; rows = np.arange(n)
    T = np.tile(np.arange(NM), (n, 1))
    for mask in range(1, FULL):
        t = np.full(n, mask)
        for p, col in owners.items():
            F = flags[col]; bp = BIT[p]; flipped = t ^ bp
            filed = np.where((t & bp) != 0, FULL, 0)     # the filed run using this version of p
            t = np.where(F[rows, t] & ~F[rows, flipped] & ~F[rows, filed], flipped, t)
        T[:, mask] = t
    return T


def harsanyi(A):
    D = np.zeros_like(A)
    for S in range(NM):
        sub = S
        while True:
            D[:, S] += (-1) ** (bin(S).count("1") - bin(sub).count("1")) * A[:, sub]
            if sub == 0:
                break
            sub = (sub - 1) & S
    return D


def allocate(D, rule):
    phi = np.zeros((D.shape[0], NP))
    for S in range(1, NM):
        mem = [i for i in range(NP) if S & (1 << i)]
        if rule == "precedence" and len(mem) > 1:
            pipe = [i for i in mem if PLAYERS[i] in PIPE]
            mem = pipe if pipe else [0]
        for i in mem:
            phi[:, i] += D[:, S] / len(mem)
    return phi


OWNERS = {
    "proposed": {"r": "fb_r", "m": "fb_m", "v": "fb_v"},
    "unowned": {"r": "fb_any", "s": "fb_any", "m": "fb_any", "v": "fb_any"},
    "null_only": {"r": "fb_r_null"},
}
METHODS = ["proposed", "unowned", "null_only", "precedence_no_repair", "naive_shapley", "sequential",
           "targeted_merge", "stratified"]


def shapley_blocks(A, blocks):
    """Exact Shapley over blocks (each block = list of players that switch together)."""
    k = len(blocks); bm = [sum(BIT[p] for p in blk) for blk in blocks]
    phi = np.zeros((A.shape[0], NP))
    from math import factorial
    for j in range(k):
        for S in range(1 << k):
            if S & (1 << j):
                continue
            size = bin(S).count("1"); w = factorial(size) * factorial(k - size - 1) / factorial(k)
            m = sum(bm[i] for i in range(k) if S & (1 << i))
            contrib = w * (A[:, m | bm[j]] - A[:, m])
            phi[:, PLAYERS.index(blocks[j][-1])] += contrib   # merged block credited to its last player
    return phi


def attribute(runs, method, dims=("total", "segment", "loan_class"), cache=None, owners=None):
    out = []
    for dim in dims:
        keys, A, lp, flags, loans = cache[dim] if cache else game(runs, dim)
        repaired = np.zeros(len(keys), bool)
        if method in OWNERS or owners is not None:
            T = repair_targets(flags, owners or OWNERS[method])[lp]
            repaired = (T != np.arange(NM)).any(axis=1)
            phi = allocate(harsanyi(np.take_along_axis(A, T, axis=1)), "precedence")
        elif method == "precedence_no_repair":
            phi = allocate(harsanyi(A), "precedence")
        elif method == "naive_shapley":
            phi = allocate(harsanyi(A), "shapley")
        elif method == "sequential":
            phi = np.zeros((len(keys), NP)); mm = 0
            for p in PLAYERS:
                phi[:, PLAYERS.index(p)] = A[:, mm | BIT[p]] - A[:, mm]; mm |= BIT[p]
        elif method == "targeted_merge":
            phi = shapley_blocks(A, [["b"], ["c"], ["r"], ["s", "m"], ["v"]])   # joint s+m reported in column m
        elif method == "stratified":
            diff = np.zeros(flags["fb_any"].shape[0], bool)
            for col in ["fb_r", "fb_m", "fb_v"]:
                F = flags[col]; diff |= F.any(axis=1) & ~F.all(axis=1)
            phi = allocate(harsanyi(A), "shapley")
            aff = diff[lp]
            phi[aff] = 0.0; phi[aff, 0] = A[aff, FULL] - A[aff, 0]
        else:
            raise ValueError(method)
        df = keys.copy(); df[PLAYERS] = phi
        df["total_change"] = A[:, FULL] - A[:, 0]; df["repaired"] = repaired; df["dimension"] = dim
        out.append(df)
    return pd.concat(out, ignore_index=True)


def truth(d, cache, dims=("total", "segment", "loan_class"), by_loan=False):
    """Clean-mode truth (current-portfolio semantics). Labeled pipeline cause p: f(N)-f(N minus p);
    prior corrections: f({c})-f(empty); remainder to business."""
    lab = d["labels"]; cause = {}
    for p in ["r", "m", "v"]:
        for i in lab[p]:
            cause[i] = p
    for i in lab["v_ws"]:
        cause[i] = "v"
    for i in lab["s"]:
        cause[i] = "s"
    out = []
    for dim in dims:
        keys, A, *_ = cache[dim]
        T = np.zeros((len(keys), NP)); pl = keys["loan_id"].map(cause).to_numpy()
        isc = keys["loan_id"].isin(lab["c"]).to_numpy()
        T[isc, 1] = A[isc, BIT["c"]] - A[isc, 0]
        for p in PIPE:
            sel = pl == p
            T[sel, PLAYERS.index(p)] = A[sel, FULL] - A[sel, FULL & ~BIT[p]]
        T[:, 0] = (A[:, FULL] - A[:, 0]) - T[:, 1:].sum(axis=1)
        k = keys.copy(); k[PLAYERS] = T; k["dimension"] = dim
        out.append(k if by_loan else k.groupby(["dimension", "line"])[PLAYERS].sum())
    return pd.concat(out)
