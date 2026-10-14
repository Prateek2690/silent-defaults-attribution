"""Public-data expected-loss attribution benchmark (SBA 7(a) + Census NAICS concordance).

Everything here is built from two public sources:
  * U.S. Small Business Administration, 7(a) FOIA loan-level files (FY2010-FY2019, FY2020-present).
  * U.S. Census Bureau, "2022 to 2017 NAICS" full concordance.

Players (bit order): b business (the loan tape at a snapshot date), r reference data
(NAICS -> sector mapping, 2017-based vs 2022-based), s rating system (risk-band scheme),
m model version (PD/LGD estimated from FY2010-16 vs FY2017-22 resolved cohorts),
v code version (industry-code matching rule and loan-program classification).

Fallback sites and owners (all fire on real records, none planted):
  F_r  sector lookup fails for a NAICS code the mapping version does not contain -> 'XX'   owner r
  F_m  (sector, band) absent from the model's PD table -> pooled default PD               owner m
  F_v  loan program absent from the code version's known list -> 'OTHER' product class     owner v
The v1 code version adds a 4-digit prefix fallback, which resolves some r-owned gaps:
this is the ownership test, on real codes.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd

PLAYERS = ["b", "r", "s", "m", "v"]
NP = len(PLAYERS)
BIT = {p: 1 << i for i, p in enumerate(PLAYERS)}
NM = 1 << NP
FULL = NM - 1
PIPE = ["r", "s", "m", "v"]
import os
from pathlib import Path
# Input files live in the repository's data/ directory unless WB_DATA_DIR points elsewhere.
UPLOADS = os.environ.get("WB_DATA_DIR", str(Path(__file__).resolve().parents[2] / "data"))
FILES = {"2010s": f"{UPLOADS}/FOIA_7a_FY2010_FY2019_asof_260630.csv",
         "2020s": f"{UPLOADS}/FOIA_7a_FY2020_Present_asof_260630.csv"}
CONCORDANCE = f"{UPLOADS}/2022_to_2017_NAICS.xlsx"
COLS = ["ApprovalDate", "ApprovalFY", "GrossApproval", "TermInMonths", "NaicsCode", "LoanStatus",
        "ChargeOffDate", "GrossChargeOffAmount", "PaidInFullDate", "FirstDisbursementDate",
        "RevolverStatus", "ProcessingMethod", "BusinessAge"]
# loan programs present before FY2022 (known to code version v0); later programs hit the ELSE branch
PROGRAMS_V0 = None   # filled in load_public_data


@dataclass
class Config:
    date0: str = "2025-06-30"
    date1: str = "2026-06-30"
    cohort0: tuple = (2010, 2016)     # model version m0 estimated here
    cohort1: tuple = (2017, 2022)     # model version m1
    sample: int = 0                   # 0 = all active loans; otherwise random sample size


def load_public_data(cfg: Config):
    frames = []
    for f in FILES.values():
        frames.append(pd.read_csv(f, usecols=COLS, encoding="latin-1", low_memory=False))
    df = pd.concat(frames, ignore_index=True)
    for c in ["ApprovalDate", "ChargeOffDate", "PaidInFullDate", "FirstDisbursementDate"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["amt"] = pd.to_numeric(df.GrossApproval, errors="coerce")
    df["co_amt"] = pd.to_numeric(df.GrossChargeOffAmount, errors="coerce").fillna(0.0)
    df["naics"] = df.NaicsCode.astype("Int64").astype(str)
    df["term"] = pd.to_numeric(df.TermInMonths, errors="coerce").fillna(0)
    df = df[df.amt > 0].reset_index(drop=True)
    df["loan_id"] = np.arange(len(df))

    cc = pd.read_excel(CONCORDANCE, skiprows=2).iloc[:, :4]
    cc.columns = ["naics2022", "title2022", "naics2017", "title2017"]
    cc["naics2022"] = cc.naics2022.astype(str).str.extract(r"(\d{6})")[0]
    cc["naics2017"] = cc.naics2017.astype(str).str.extract(r"(\d{6})")[0]
    cc = cc.dropna(subset=["naics2022", "naics2017"])

    # reference-data versions: sector (2-digit) by industry code, under each NAICS vintage
    map17 = pd.DataFrame({"naics": sorted(set(cc.naics2017))})
    map17["sector"] = map17.naics.str[:2]
    map22 = pd.DataFrame({"naics": sorted(set(cc.naics2022))})
    map22["sector"] = map22.naics.str[:2]

    global PROGRAMS_V0
    pre = df[df.ApprovalFY <= 2021].ProcessingMethod.dropna().unique()
    PROGRAMS_V0 = sorted(set(pre))
    return df, map17, map22, cc


def snapshot(df, date):
    d = pd.Timestamp(date)
    keep = ((df.ApprovalDate <= d) & (df.LoanStatus != "CANCLD") & df.FirstDisbursementDate.notna()
            & ((df.PaidInFullDate.isna()) | (df.PaidInFullDate > d))
            & ((df.ChargeOffDate.isna()) | (df.ChargeOffDate > d)))
    s = df.loc[keep, ["loan_id", "naics", "amt", "term", "RevolverStatus", "ProcessingMethod", "ApprovalDate"]].copy()
    return s.reset_index(drop=True)


def bands(s, scheme):
    """Rating system versions. s0: four size bands. s1: eight bands combining size and term."""
    amt = s.amt.to_numpy()
    size = np.digitize(amt, [150_000, 500_000, 2_000_000])          # 0..3
    if scheme == 0:
        return pd.Series([f"S{i+1}" for i in size], index=s.index)
    long_term = (s.term.to_numpy() >= 120).astype(int)
    return pd.Series([f"B{i+1}{'L' if l else 'S'}" for i, l in zip(size, long_term)], index=s.index)


def fit_models(df, map17, map22, cfg):
    """PD and LGD by (sector, band) from resolved cohorts. m0 knows only the s0 band scheme;
    m1 (the newer model) supports both schemes, as a bank keeping backward compatibility would."""
    res = df[df.LoanStatus.isin(["CHGOFF", "P I F"])].copy()
    sector_lookup = dict(zip(map22.naics, map22.sector))
    res["sector"] = res.naics.map(sector_lookup).fillna(res.naics.str[:2])
    out = {}
    for tag, (lo, hi), schemes in [("m0", cfg.cohort0, [0]), ("m1", cfg.cohort1, [0, 1])]:
        coh = res[(res.ApprovalFY >= lo) & (res.ApprovalFY <= hi)].copy()
        rows = []
        for scheme in schemes:
            coh["band"] = bands(coh.rename(columns={"amt": "amt", "term": "term"}), scheme)
            g = coh.groupby(["sector", "band"], observed=True).apply(
                lambda x: pd.Series({
                    "n": len(x),
                    "pd": (x.LoanStatus == "CHGOFF").mean(),
                    "lgd": (x.co_amt.sum() / x.loc[x.LoanStatus == "CHGOFF", "amt"].sum())
                           if (x.LoanStatus == "CHGOFF").any() else np.nan}), include_groups=False).reset_index()
            rows.append(g[g.n >= 100])
        t = pd.concat(rows, ignore_index=True)
        t["lgd"] = t.lgd.fillna(t.lgd.median()).clip(0.05, 1.0)
        pooled_pd = (coh.LoanStatus == "CHGOFF").mean()
        pooled_lgd = float(np.clip(coh.co_amt.sum() / max(coh.loc[coh.LoanStatus == "CHGOFF", "amt"].sum(), 1), 0.05, 1.0))
        t = pd.concat([t, pd.DataFrame([{"sector": "DEFAULT", "band": "DEFAULT", "n": len(coh),
                                         "pd": pooled_pd, "lgd": pooled_lgd}])], ignore_index=True)
        out[tag] = t[["sector", "band", "pd", "lgd"]]
    return out


def build_inputs(cfg: Config):
    df, map17, map22, cc = load_public_data(cfg)
    s0, s1 = snapshot(df, cfg.date0), snapshot(df, cfg.date1)
    if cfg.sample:
        ids = set(pd.concat([s0.loan_id, s1.loan_id]).drop_duplicates().sample(cfg.sample, random_state=0))
        s0, s1 = s0[s0.loan_id.isin(ids)], s1[s1.loan_id.isin(ids)]
    models = fit_models(df, map17, map22, cfg)
    for tag, snap in [("b0", s0), ("b1", s1)]:
        snap = snap.copy()
        snap["band_s0"] = bands(snap, 0)
        snap["band_s1"] = bands(snap, 1)
        snap["prog_known_v0"] = snap.ProcessingMethod.isin(PROGRAMS_V0).astype(int)
        snap["naics4"] = snap.naics.str[:4]
        globals()[f"_snap_{tag}"] = snap
    return {"loans_b0": globals()["_snap_b0"], "loans_b1": globals()["_snap_b1"],
            "map_r0": map17, "map_r1": map22, "pd_m0": models["m0"], "pd_m1": models["m1"],
            "raw": df, "concordance": cc}


def load(engine, d):
    for k in ["loans_b0", "loans_b1", "map_r0", "map_r1", "pd_m0", "pd_m1"]:
        engine.load(k, d[k])
    # 4-digit prefix table for the v1 code fallback, per mapping version
    for v, key in [(0, "map_r0"), (1, "map_r1")]:
        t = d[key].copy()
        t["naics4"] = t.naics.str[:4]
        engine.load(f"prefix_{key}", t.groupby("naics4", as_index=False).sector.first())


def pipeline_sql(b, r, s, m, v):
    band = "l.band_s1" if s == 1 else "l.band_s0"
    prefix_join = f"LEFT JOIN prefix_map_r{r} pf ON pf.naics4 = l.naics4" if v == 1 else ""
    sector = ("COALESCE(x.sector, pf.sector, 'XX')" if v == 1 else "COALESCE(x.sector, 'XX')")
    prod = ("CASE WHEN l.prog_known_v0 = 1 THEN (CASE WHEN l.RevolverStatus = 'Y' THEN 'REVOLVER' ELSE 'TERM' END) ELSE 'OTHER' END"
            if v == 0 else
            "CASE WHEN l.RevolverStatus = 'Y' THEN 'REVOLVER' ELSE 'TERM' END")
    return f"""
    DROP TABLE IF EXISTS pre;
    CREATE TABLE pre AS
    SELECT l.loan_id, l.amt, l.term, {band} AS band, {sector} AS sector, {prod} AS product,
           CASE WHEN x.sector IS NULL {"AND pf.sector IS NULL" if v == 1 else ""} THEN 1 ELSE 0 END AS fb_r,
           CASE WHEN l.prog_known_v0 = 0 AND {v} = 0 THEN 1 ELSE 0 END AS fb_v
    FROM loans_b{b} l
    LEFT JOIN map_r{r} x ON x.naics = l.naics
    {prefix_join};
    DROP TABLE IF EXISTS out_rows;
    CREATE TABLE out_rows AS
    SELECT p.loan_id, p.sector, p.product, p.band, p.amt, p.fb_r, p.fb_v,
           CASE WHEN g.pd IS NULL THEN 1 ELSE 0 END AS fb_m,
           COALESCE(g.pd, dm.pd) AS pd_rate,
           COALESCE(g.lgd, dm.lgd) * (CASE WHEN p.product = 'REVOLVER' THEN 1.10
                                           WHEN p.product = 'OTHER' THEN 1.00 ELSE 0.95 END) AS lgd_rate
    FROM pre p
    LEFT JOIN pd_m{m} g ON g.sector = p.sector AND g.band = p.band
    CROSS JOIN (SELECT pd, lgd FROM pd_m{m} WHERE sector = 'DEFAULT') dm;
    """


def expected_loss(rows):
    """Lifetime expected loss on the approved amount: EAD x PD x LGD (no discounting)."""
    return rows.amt.to_numpy() * rows.pd_rate.to_numpy() * rows.lgd_rate.to_numpy()


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


# ---------------------------------------------------------------- attribution
FLAGS = ["fb_r", "fb_m", "fb_v"]
OWNERS = {"proposed": {"r": "fb_r", "m": "fb_m", "v": "fb_v"},
          "unowned": {"r": "fb_any", "s": "fb_any", "m": "fb_any", "v": "fb_any"},
          "null_only": {"r": "fb_r"}}
METHODS = ["proposed", "unowned", "null_only", "precedence_no_repair", "naive_shapley",
           "sequential", "targeted_merge", "stratified"]


def game(runs, dim="total"):
    frames = []
    for mask, rows in runs.items():
        g = rows.groupby(["loan_id", dim], as_index=False)["el"].sum(); g["mask"] = mask; frames.append(g)
    wide = pd.concat(frames).pivot_table(index=["loan_id", dim], columns="mask", values="el",
                                         aggfunc="sum", fill_value=0.0).reindex(columns=range(NM), fill_value=0.0)
    keys = wide.index.to_frame(index=False).rename(columns={dim: "line"})
    loans = np.sort(keys.loan_id.unique()); pos = {l: i for i, l in enumerate(loans)}
    flags = {f: np.zeros((len(loans), NM), bool) for f in FLAGS}
    for mask, rows in runs.items():
        f = rows.groupby("loan_id")[FLAGS].max()
        idx = np.fromiter((pos[l] for l in f.index), int, len(f))
        for col in FLAGS:
            flags[col][idx, mask] = f[col].to_numpy().astype(bool)
    flags["fb_any"] = flags["fb_r"] | flags["fb_m"] | flags["fb_v"]
    return keys, wide.to_numpy(), keys.loan_id.map(pos).to_numpy(), flags


def games(runs, dims=("total", "sector", "product")):
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
    for S_ in range(NM):
        sub = S_
        while True:
            D[:, S_] += (-1) ** (bin(S_).count("1") - bin(sub).count("1")) * A[:, sub]
            if sub == 0:
                break
            sub = (sub - 1) & S_
    return D


def allocate(D, rule):
    phi = np.zeros((D.shape[0], NP))
    for S_ in range(1, NM):
        mem = [i for i in range(NP) if S_ & (1 << i)]
        if rule == "precedence" and len(mem) > 1:
            pipe = [i for i in mem if PLAYERS[i] in PIPE]
            mem = pipe if pipe else [0]
        for i in mem:
            phi[:, i] += D[:, S_] / len(mem)
    return phi


def shapley_blocks(A, blocks):
    from math import factorial
    k = len(blocks); bm = [sum(BIT[p] for p in blk) for blk in blocks]
    phi = np.zeros((A.shape[0], NP))
    for j in range(k):
        for S_ in range(1 << k):
            if S_ & (1 << j):
                continue
            sz = bin(S_).count("1"); w = factorial(sz) * factorial(k - sz - 1) / factorial(k)
            mm = sum(bm[i] for i in range(k) if S_ & (1 << i))
            phi[:, PLAYERS.index(blocks[j][-1])] += w * (A[:, mm | bm[j]] - A[:, mm])
    return phi


def attribute(runs, method, dims=("total", "sector"), cache=None, owners=None):
    out = []
    for dim in dims:
        keys, A, lp, flags = cache[dim] if cache else game(runs, dim)
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
            phi = shapley_blocks(A, [["b"], ["r"], ["s", "m"], ["v"]])
        elif method == "stratified":
            diff = np.zeros(flags["fb_any"].shape[0], bool)
            for col in FLAGS:
                F = flags[col]; diff |= F.any(axis=1) & ~F.all(axis=1)
            phi = allocate(harsanyi(A), "shapley")
            aff = diff[lp]; phi[aff] = 0.0; phi[aff, 0] = A[aff, FULL] - A[aff, 0]
        else:
            raise ValueError(method)
        df = keys.copy(); df[PLAYERS] = phi
        df["total_change"] = A[:, FULL] - A[:, 0]; df["repaired"] = repaired; df["dimension"] = dim
        out.append(df)
    return pd.concat(out, ignore_index=True)


def run_and_build(engine, dims=("total", "sector")):
    """Memory-lean: execute each of the 32 runs, fold it into the per-dimension games, discard it.
    Returns (games, totals_by_mask, el_full_by_loan)."""
    grouped = {d: {} for d in dims}
    flag_rows = {}
    totals = {}
    el_full = None
    for mask in range(NM):
        engine.execute(pipeline_sql(*versions(mask)))
        rows = engine.query("SELECT * FROM out_rows")
        rows["el"] = expected_loss(rows)
        rows["total"] = "ALLOWANCE"
        totals[mask] = float(rows.el.sum())
        if mask == FULL:
            el_full = rows.groupby("loan_id").el.sum()
        for d in dims:
            grouped[d][mask] = rows.groupby(["loan_id", d]).el.sum()
        flag_rows[mask] = rows.groupby("loan_id")[FLAGS].max()
        del rows
    loans = np.sort(np.unique(np.concatenate([f.index.to_numpy() for f in flag_rows.values()])))
    pos = pd.Index(loans)
    flags = {f: np.zeros((len(loans), NM), bool) for f in FLAGS}
    for mask, f in flag_rows.items():
        idx = pos.get_indexer(f.index)
        for col in FLAGS:
            flags[col][idx, mask] = f[col].to_numpy().astype(bool)
    flags["fb_any"] = flags["fb_r"] | flags["fb_m"] | flags["fb_v"]
    games_out = {}
    for d in dims:
        idx = None
        for mask, s_ in grouped[d].items():
            idx = s_.index if idx is None else idx.union(s_.index)
        A = np.zeros((len(idx), NM), dtype=np.float64)
        for mask, s_ in grouped[d].items():
            A[idx.get_indexer(s_.index), mask] = s_.to_numpy()
        keys = idx.to_frame(index=False); keys.columns = ["loan_id", "line"]
        games_out[d] = (keys, A, pos.get_indexer(keys.loan_id.to_numpy()), flags)
        grouped[d] = None
    return games_out, totals, el_full
