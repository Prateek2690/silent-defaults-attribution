# Silent Defaults and Phantom Effects

Code and data pipeline for the working paper **"Silent Defaults and Phantom Effects: Owner-Aware Attribution of Expected-Loss Changes in Versioned Reporting Pipelines, with Evidence from Public Loan Data"** by Prateek Bhatnagar ([SSRN 7486440](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7486440), September 2026; a working paper, not yet peer-reviewed). The posted version of the paper is in [`paper/posted-v1.0.0.pdf`](paper/posted-v1.0.0.pdf).

Counterfactual ("what-if") attribution explains how a reported expected-loss figure changed by re-running the
calculation with some inputs from the prior period and some from the current one. This repository shows that such
runs can be **silently invalid**: reporting pipelines replace inputs they cannot process with default values
(a pooled PD for an unrecognised grade, a catch-all industry segment, an `ELSE` branch), and in what-if runs these
defaults fire without errors or missing values. Attribution then books fictitious **phantom effects** to older
components. The repository implements **owner-aware differential-fallback repair** and reproduces every number in
the paper from public data.

## Headline result

On 292,000 loans built from public U.S. Small Business Administration files, with the U.S. Census Bureau's official
2017-to-2022 NAICS revision as the reference-data change, attribution methods disagree about a **-$2,642M** change by
billions of dollars, and disagree about the **sign** of the rating-system effect:

| Method | Business | Mapping | Rating system | Model | Code |
|---|---:|---:|---:|---:|---:|
| Proposed (owner-aware repair) | 115.2 | 16.3 | **-2,768.8** | 31.3 | -35.9 |
| Sequential walk | 124.3 | 58.2 | **+1,290.1** | -3,935.9 | -178.7 |
| Naive Shapley | 24.6 | 9.3 | -670.3 | -1,903.7 | -101.7 |
| Targeted merge | -20.2 | 8.7 | (merged with model) | -2,511.3 | -119.2 |

All figures in $ million. Every method reconciles exactly to the total change.

## Repository layout

```
src/walkbench/      sba.py        public-data pipeline, attribution, repair rule
                    cecl3.py      synthetic benchmark with known ground truth
                    engine.py     SQL engine wrapper (DuckDB if installed, else sqlite3)
scripts/            run_public_experiments.py     reproduces the public-data results
                    run_synthetic_experiments.py  reproduces the synthetic results
results/public/     result tables from the public-data study
results/synthetic/  result tables from the synthetic benchmark
paper/              manuscript source, figures and compiled PDF
data/               where the public input files go (not redistributed; see data/README.md)
```

## Requirements

```
python >= 3.10
pandas, numpy, matplotlib, openpyxl, tabulate
duckdb        # optional; the code falls back to the standard-library sqlite3
              # (the published results were produced with sqlite3)
```

```bash
pip install -r requirements.txt
```

## Reproducing the results

1. **Download the public data** as described in [`data/README.md`](data/README.md): two SBA 7(a) FOIA files and the
   Census 2022-to-2017 NAICS concordance. Nothing else is needed, and no data is redistributed here.
2. **Run the public-data study** (about 5 minutes on a laptop; 32 pipeline runs over ~292,000 loans):

   ```bash
   PYTHONPATH=src python scripts/run_public_experiments.py
   ```

   Writes `results_sba/{summary,methods,checks,order,instrumentation}.csv`.
3. **Run the synthetic benchmark** (ground truth known by construction):

   ```bash
   PYTHONPATH=src WB_N=10000 WB_SEEDS=3 python scripts/run_synthetic_experiments.py
   ```

   Writes `results_v3/X1.csv` ... `X9.csv`.
4. **Rebuild the paper** (requires pandoc and xelatex):

   ```bash
   cd paper && python build.py && pandoc manuscript.md --citeproc --pdf-engine=xelatex -o paper.pdf
   ```

Set `WB_SAMPLE=20000` for a quick public-data run on a random subset.

A fresh re-run of the synthetic benchmark (14 October 2026, sqlite3) reproduced `X1.csv` to `X8.csv` byte for byte.
`X9.csv` records run times, so it varies by machine.

## Method in brief

1. **Instrument every fallback site.** Each point where the pipeline substitutes a default emits a per-row flag.
2. **Give each site an owner** — the component whose version decides what the site can process (mapping, model, code).
3. **Repair differentially.** A what-if evaluation is replaced for a loan only when an owned default fires under one
   version of its owner and not the other, *and* was not already firing in the filed run where that version was in
   force. The filed runs are never altered, so the decomposition still reconciles to both filed figures.
4. **Report separability.** The share of the figure sitting on repaired loans is disclosed rather than hidden inside
   another cause.

The allocation itself (business first, then a Shapley split among pipeline components) is a precedence construction
with known antecedents; it is cited in the paper, not claimed.

## Citing

See [`CITATION.cff`](CITATION.cff). The working paper is the primary reference; this repository is the code artifact.

> Bhatnagar, P. (2026). *Silent Defaults and Phantom Effects: Owner-Aware Attribution of Expected-Loss Changes in
> Versioned Reporting Pipelines, with Evidence from Public Loan Data.* SSRN Working Paper 7486440.

Related work by the same author: *A Safety Gate for AI-Driven Data Repair in Regulated Financial Reporting*
([SSRN 7432699](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7432699); code:
[matrepair](https://github.com/Prateek2690/matrepair)).

## Scope and limitations

- SBA 7(a) loans are government-guaranteed small-business loans, not a bank's wholesale portfolio, and the files
  disclose approved amounts rather than outstanding balances, so exposure is approximate.
- Rating-band schemes and code versions are constructed by the author and documented; loans, industry mapping and
  model parameters come from the public sources.
- The guarantee is conditional on instrumentation completeness. Leaving one fallback site untagged changes the
  headline effect by a factor of four (see `results/public/instrumentation.csv`).
- Nothing in this repository derives from any employer's data, systems, models or code.

## License

Code is released under the MIT License (see [`LICENSE`](LICENSE)). The public input data is U.S. federal government
work and is not redistributed here.
