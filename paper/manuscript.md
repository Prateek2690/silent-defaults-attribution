---
title: "Silent Defaults and Phantom Effects: Owner-Aware Attribution of Expected-Loss Changes in Versioned Reporting Pipelines, with Evidence from Public Loan Data"
author:
  - "Prateek Bhatnagar\\thanks{Independent Researcher. Email: bhatnagar.prateek90@gmail.com. ORCID: 0009-0000-0359-3268. This research was conducted independently, without the use of any employer's data, systems, models, code, or confidential information. All cited materials are publicly available and all experiments use synthetic data.}"
date: "Working Paper · September 2026"
abstract: |
  Institutions explain changes in an expected-loss figure by re-running the calculation with some inputs from the prior period and some from the current one, then attributing the change to business movement, reference data, rating systems, models, and code. These what-if runs are assumed to be meaningful. We identify a failure mode in which they are not, yet nothing signals it: reporting pipelines replace inputs they cannot handle with default values, such as a pooled probability of default for an unrecognized grade or a catch-all industry segment, and in what-if runs these defaults fire without errors or missing values. Attribution then books fictitious "phantom" effects to older components. We propose owner-aware differential-fallback repair: each fallback site is instrumented and assigned to the component that owns it, and a what-if evaluation is repaired for a record only when an owned default depends on that component's version and was not already present in the filed run in which that version was in force. The filed runs are never altered, so the attribution reconciles to both filed figures, and the method reports the share of the figure that could not be separated. We evaluate on a portfolio of 292,000 loans built from public U.S. Small Business Administration disclosure files, using the U.S. Census Bureau's official 2017-to-2022 industry-classification revision as the reference-data change, with probability-of-default and loss parameters estimated from realized charge-offs. Standard methods disagree about a \$2.6 billion change by billions of dollars and about the sign of the rating-system effect; they book \$28--46 million of mapping effect on loans whose industry codes never existed under the prior mapping, and one baseline assigns \$4.5 billion of business movement to loans that did not change. A controlled synthetic benchmark, where ground truth exists by construction, confirms the behaviour. The method's central requirement is instrumentation completeness: leaving one fallback site untagged changes the headline effect fourfold.
keywords: "expected credit loss; allowance for credit losses; attribution; Shapley value; counterfactual analysis; data pipelines; data quality; disguised missing values; model risk management; financial reporting"
bibliography: refs.bib
link-citations: true
numbersections: true
geometry: margin=1in
fontsize: 11pt
mainfont: Liberation Serif
linestretch: 1.15
colorlinks: true
header-includes:
  - \usepackage{booktabs}
  - \usepackage{array}
  - \usepackage{amsthm}
  - \newtheorem{proposition}{Proposition}
  - \usepackage{caption}
  - \usepackage{float}
  - \captionsetup{font=small,labelfont=bf}
  - \renewcommand{\topfraction}{0.92}
  - \renewcommand{\bottomfraction}{0.75}
  - \renewcommand{\textfraction}{0.08}
  - \renewcommand{\floatpagefraction}{0.80}
  - \setlength{\floatsep}{10pt plus 2pt minus 2pt}
  - \setlength{\textfloatsep}{14pt plus 2pt minus 3pt}
  - \setlength{\intextsep}{12pt plus 2pt minus 2pt}
  - \raggedbottom
---


**Keywords:** expected credit loss; allowance for credit losses; attribution; Shapley value; counterfactual analysis; data pipelines; data quality; disguised missing values; model risk management; financial reporting

**JEL:** C71, C88, G21, G28, M41

# Introduction

Institutions that report an expected-loss figure must explain how it moved between reporting periods. Under the current expected credit loss (CECL) standard [@fasb2016], the figure is produced by a pipeline that joins a loan-level portfolio snapshot to reference data and a rating system, applies probability-of-default (PD), loss-given-default (LGD), and exposure models, and aggregates the result. Every one of those inputs changes over time. When the figure moves, disclosure committees, model risk functions [@sr117], and auditors need to know how much of the change reflects the portfolio and how much reflects changes to the reporting machinery.

The standard technique is counterfactual re-running. An analyst replaces input blocks with their prior-period versions and records how the output moves. Recent practitioner work formalizes this with exact Shapley, hierarchical (Owen), and sampling-based attribution over input blocks such as launch-point data, macroeconomic scenarios, model specifications including production-code versions, business assumptions, and management overlays [@meilin2026runs], and attributes forecast gaps to component models under the expected-loss identity [@meilin2026gaps]. That work states the central requirement: every what-if run must be executable and economically meaningful. When a model version depends on a particular data schema, it recommends combining the dependent inputs into a single player or a justified hierarchy [@meilin2026runs].

This paper studies the case in which the requirement fails *silently*. Reporting pipelines are designed not to crash. They route what they cannot process into defaults: an unrecognized rating grade receives a default PD, an unknown industry code falls into a catch-all segment, an unanticipated loan program takes the `ELSE` branch of a classification rule. In the filed runs these defaults are deliberate and usually rare. In what-if runs, where a prior-period component meets current-period records, they can fire at scale. Nothing is null, nothing errors, and the numbers look ordinary.

*Example.* An institution moves part of its portfolio to a finer rating scale. Its prior PD model knows only the old grades and assigns a pooled default PD to anything else. A loan graded on the new scale receives its own estimate under the current model. In the what-if run "current rating system, prior model," the loan receives the default, and attribution concludes that the model change moved the figure. That effect is fictitious (Figure 1).

![How a silent default creates a phantom model effect. In the current-period run the loan is scored by a model that recognizes its grade. In the what-if run the prior-period model does not recognize the grade and silently substitutes a default PD; the resulting difference is reported as a model effect even though the prior model never scored the loan.](fig/fig0b_silent.pdf){width=88%}

This is not a hypothetical concern. On a portfolio of 292,000 real loans built from public U.S. Small Business Administration (SBA) disclosure files, using the U.S. Census Bureau's official 2017-to-2022 industry-classification revision as the reference-data change, standard attribution methods disagree about a \$2.6 billion change in expected loss by billions of dollars, and disagree about the *sign* of the rating-system effect. No coverage gap in that exercise was introduced by us: they arise because the classification system changed and the data followed it.

This paper makes four contributions.

1. **Problem characterization.** We identify silent fallback defaults as a failure mode of counterfactual attribution in reporting pipelines, distinct from execution failures and from missing values, and measure it on public data (Section 6).
2. **Owner-aware differential-fallback repair.** Each fallback site is instrumented and assigned to the component that owns it; a what-if evaluation is repaired for a loan only when an owned default depends on the version of its owner *and* is not already present in the filed run in which that version was in force. The filed runs are never altered, and the method reports the share of the figure that could not be separated (Section 4).
3. **Evaluation without a constructed ground truth.** On public data we test behavioral properties any defensible walk should satisfy, rather than agreement with a truth we defined; a controlled synthetic benchmark, where ground truth exists by construction, is a secondary check (Sections 5--7).
4. **Open benchmark and public-data pipeline.** Code that rebuilds the entire study from two public sources, plus the synthetic generator.

We do not claim new cooperative game theory. The allocation is a precedence construction with known antecedents (Section 2.2); the contribution is making what-if runs trustworthy when pipelines conceal their own coverage gaps.

# Related Work

## Attribution of changes in financial figures

Regulatory disclosure already separates business from methodological drivers of risk figures: the revised Pillar 3 framework requires flow statements of risk-weighted assets distinguishing drivers such as asset size, asset quality, model updates, and methodology and policy [@bcbs2015pillar3]. Those statements rest on changes declared by the reporting institution and address risk-weighted assets rather than expected loss. @meilin2026runs compare walk analysis, exact Shapley, Owen, and gradient- and sampling-based methods for attributing differences between CCAR and CECL forecast runs, and identify non-executable or economically meaningless hybrids as a limitation to be handled by combining inputs. @meilin2026gaps attribute expected-loss forecast gaps to PD, LGD, and prepayment components. Neither addresses hybrids that execute normally but silently substitute defaults. In productivity economics, @melitzpolanec2015 decompose aggregate change into contributions of surviving, entering, and exiting firms; our treatment of new loans follows the same principle, with the difference that group membership in a reporting pipeline is itself produced by versioned reference data, rating systems, and code. Our earlier work [@bhatnagar2026gate] gates automated data repairs by their potential to materially misstate a reported figure; it does not attribute period-over-period changes.

## Shapley values with impossible or ordered coalitions

The Shapley value [@shapley1953] underlies most of these methods. Marginal Shapley explanations of machine-learning models evaluate feature combinations that do not occur in data, which distorts attributions; dependence-aware and on-manifold estimators replace such combinations with plausible ones [@aas2021; @frye2021manifold]. @rozenfeld2024 shows that extrapolation in marginal Shapley values yields unintuitive attributions and proposes a stratified approach that computes Shapley values within strata of a dependent feature. Our setting shares the diagnosis that some coalitions correspond to combinations the system cannot evaluate, but differs in two respects: the pipeline conceals which combinations are invalid, so they must be detected record by record from instrumented defaults; and the remedy is deterministic and version-based rather than distributional. We include a stratified baseline. Games restricted to feasible coalitions under precedence constraints [@faiglekern1992], values for games with a priori unions [@owen1977], and asymmetric and causal Shapley values [@frye2020asymmetric; @heskes2020causal] provide the formal background for our precedence allocation, stated using Harsanyi dividends [@harsanyi1963].

## Disguised missing values and default handling

Placeholder values that stand in for missing or unknown data are a recognized data-quality problem [@pearson2006] with automated detectors [@qahtan2018fahes]. SQL style checkers commonly flag `CASE` expressions without an `ELSE` branch, typically encouraging explicit defaults. That work detects or encourages defaults for cleaning and robustness; we use instrumented defaults to decide whether a counterfactual evaluation is valid for a specific record.

## What-if analysis and change verification in data systems

Hypothetical reasoning systems answer what-if and how-to queries over databases using probabilistic causal models [@galhotra2022hyper]. Schema-evolution tooling rewrites queries across schema versions [@curino2008prism]. Data Flow Control enforces declarative safety policies over tuple-level data flows inside a database system [@summerswu2026dfc]. In software engineering, tangled changes complicate analysis of what a change actually did [@herzig2013tangled]. None of these determines whether a hybrid run in a multi-version attribution silently relied on another version's defaults.

# Problem Setting

**Pipeline and runs.** A reporting pipeline maps versioned inputs to loan-level outputs. In the public-data study we use five input blocks, or players: the business state $b$ (the loan tape at a snapshot date), reference data $r$ (industry code to sector mapping), the rating system $s$ (the risk-band scheme in force), the model version $m$ (PD and LGD parameters), and the code version $v$ (industry-code matching and loan-program classification). The synthetic benchmark adds prior-period data corrections $c$, which public disclosure files do not support. Each block takes its prior version (0) or current version (1); a coalition $S \subseteq N$ denotes the blocks at current versions. Running all $2^{|N|}$ combinations yields, for every loan $i$ and disclosure line $\ell$, a value $f_{i\ell}(S)$; $\sum_i f_{i\ell}(\emptyset)$ is the prior filed figure and $\sum_i f_{i\ell}(N)$ the current one. Figure 2 illustrates one what-if run.

![Counterfactual attribution with what-if runs. Each run takes every input block at either its prior-period (old) or current-period (new) version. The what-if run shown differs from the current-period run only in the PD/LGD model, so the difference between the two runs measures the model's effect, provided the what-if run is meaningful.](fig/fig0a_whatif.pdf){width=88%}

**The rating system is methodology, not business.** Moving a loan to a different scale changes how its risk is expressed, not the risk itself; treating a scale migration as portfolio movement would misstate the distinction the exercise exists to draw.

**Fallback sites.** A fallback site is a point in the pipeline that substitutes a default when it cannot process an input: an unmatched mapping lookup or a catch-all row; a parameter lookup whose key is unknown to the model; a `CASE ... ELSE` over loan programs. Each site has an owner: the block whose version defines what the site can process.

**Silent invalidity.** A what-if evaluation $f_{i\ell}(S)$ is silently invalid with respect to component $p$ if loan $i$ takes a $p$-owned fallback under the version of $p$ in $S$ but not under the other version of $p$, *and* that fallback does not already fire in the filed run in which the version of $p$ used in $S$ was actually in force. The last clause matters in practice: a model that genuinely could not score a loan in its own period produced a default in the filed figure, and that default is reporting history rather than an artifact of mixing versions. We encountered this case only on real data, where sparsely populated parameter cells occur naturally (Section 8).

# Method

Figure 3 summarizes the method: fallback sites are instrumented, each is assigned an owner, and what-if evaluations are repaired only where an owned default depends on its owner's version.

![Overview of owner-aware differential-fallback repair. The output is an attribution that reconciles to both filed figures without phantom effects, together with the share of the figure whose effects cannot be separated.](fig/fig0c_method.pdf){width=80%}

## Instrumentation

Each fallback site is rewritten to emit a per-row flag alongside its output, for example `CASE WHEN x.sector IS NULL THEN 1 ELSE 0 END AS fb_r`. Flags are recorded in every run. In a columnar in-process engine this adds one column per site and no additional runs.

## Owner-aware differential-fallback repair

For loan $i$ and each non-filed coalition $S$, consider each owned component $p$ in turn, and let $S'$ be $S$ with the version of $p$ flipped. The loan is evaluated under $S'$ instead of $S$ when all of the following hold: the $p$-owned flag is set under $S$; it is not set under $S'$; and it is not set in the filed run in which the version of $p$ used in $S$ was in force. Repaired values may coincide with a filed run's value; the filed runs themselves are never altered. Data-owned fallbacks are never repaired.

Ownership matters because one component's version can resolve a default owned by another. In the public-data pipeline, the current code version adds a four-digit prefix fallback for industry codes the mapping does not contain exactly, resolving mapping-owned gaps for 8,045 real loans. Owner-aware repair keeps that effect with the code version, while a rule that repairs whichever component happens to remove the flag erases it.

## Precedence allocation

Define Harsanyi dividends $d(T) = \sum_{U \subseteq T} (-1)^{|T|-|U|} \tilde f(U)$. Each dividend is allocated equally among the pipeline players it contains; dividends containing only business (and, in the synthetic setting, corrections) go to business. Equivalently: business first, then a Shapley split among pipeline components, measured on the portfolio being reported. This is a presentation policy with known antecedents (Section 2.2); other orderings are defensible and are not evaluated here.

## Separability report

The method reports the share of the current figure on loans for which any repair occurred. For those loans one version of a component cannot be applied, so its separate effect is undefined; disclosing the share makes the extent of that limitation visible rather than hiding it inside another cause.

\begin{proposition}[Reconciliation]
For every loan and disclosure line, the allocated effects sum to $f(N) - f(\emptyset)$.
\end{proposition}

*Proof sketch.* Repair applies only to non-filed coalitions, so $\tilde f(N) = f(N)$ and $\tilde f(\emptyset) = f(\emptyset)$; dividends of any set function sum to $\tilde f(N) - \tilde f(\emptyset)$, and the allocation distributes each dividend completely. $\square$

This property holds for every method we compare and is a sanity check rather than a result.

\begin{proposition}[Conditional soundness]
If every fallback site owned by $p$ is instrumented, no evaluation used in the allocation applies a $p$-owned default to a loan when the other version of $p$ covers it and that default was not already present in the corresponding filed run.
\end{proposition}

*Proof sketch.* Immediate from the repair rule. The guarantee is conditional on instrumentation completeness, examined empirically in Sections 6.5 and 7. $\square$

# Public-Data Study

## Sources

Two public U.S. federal government publications reproduce the entire study.

- **SBA 7(a) FOIA loan-level files** (FY2010--FY2019 and FY2020--present, as of 30 June 2026): one record per guaranteed loan with industry code, approval date, gross approval amount, term, loan program, loan status, charge-off date and amount.
- **U.S. Census Bureau, 2022-to-2017 NAICS concordance:** the official correspondence between the 2017 and 2022 revisions of the industry classification.

SBA adopted the 2022 classification for loans approved from FY2022 onward. From that year, between 6.0% and 11.2% of newly approved loans per year carry industry codes absent from the 2017 classification, corresponding to \$2.0--4.5 billion of approvals annually. This is a real reference-data change met by real records.

## Pipeline and input versions

Table 1 lists the versions of each input. Two snapshots of loans outstanding, at 30 June 2025 and 30 June 2026, are built from approval, disbursement, paid-in-full, and charge-off dates. Expected loss is computed per loan as exposure $\times$ PD $\times$ LGD, following the loan-level formulation of @meilin2026gaps, with the approved amount as exposure.

```{=latex}
\begin{table}[htbp]
\centering\small
\caption{Input versions in the public-data pipeline. Loans, industry mapping, and model parameters come from the public sources; band schemes and code versions are constructed and documented.}
\begin{tabular}{l>{\raggedright\arraybackslash}p{0.392\textwidth}>{\raggedright\arraybackslash}p{0.438\textwidth}}
\toprule
Player & Prior version & Current version \\
\midrule
$b$ business & loans outstanding 30 June 2025 & loans outstanding 30 June 2026 \\
$r$ reference data & sector mapping over NAICS 2017 codes & sector mapping over NAICS 2022 codes \\
$s$ rating system & four size-based risk bands & eight bands combining size and term \\
$m$ model & PD and LGD by sector and band, FY2010--16 cohorts & same from FY2017--22 cohorts, supporting both band schemes \\
$v$ code & exact six-digit code match; pre-FY2022 loan programs & adds four-digit prefix fallback and later programs \\
\bottomrule
\end{tabular}
\end{table}
```

Model versions are estimated from real outcomes: the overall charge-off rate is 7.30% for FY2010--16 resolved cohorts and 9.06% for FY2017--22, and aggregate loss severity on charged-off loans rises from 58.6% to 70.0% (22,492 and 16,105 charge-offs respectively).

## Portfolio

Table 2 summarises the portfolio and the change to be explained.

```{=latex}
\begin{table}[htbp]
\centering\small
\caption{The public portfolio and the change to be explained.}
\begin{tabular}{>{\raggedright\arraybackslash}p{0.830\textwidth}r}
\toprule
Quantity & Value \\
\midrule
Loans outstanding, prior / current & 292,774 / 292,194 \\
Exposure, prior / current & \$162.4B / \$166.4B \\
New loans in the current snapshot & 35,816 \\
Expected loss, prior / current & \$5,340M / \$2,698M \\
Change to be explained & −\$2,642M \\
Loans with codes absent from NAICS 2017 & 22,043 \\
... of which new in the current snapshot & 4,044 \\
Loans resolvable only by the code version's prefix fallback & 8,045 \\
Loans unchanged in amount and term across snapshots & 256,378 \\
\bottomrule
\end{tabular}
\end{table}
```

## Methods compared

Sequential walk (order $b, r, s, m, v$); naive Shapley; precedence allocation without repair; repair of unmatched codes only; unowned repair; **targeted merge**, an exact Shapley value in which the dependent inputs rating system and model switch together, following @meilin2026runs; **stratified**, which assigns loans affected by any version-dependent default entirely to business and attributes the rest by naive Shapley, in the spirit of @rozenfeld2024; and the proposed method.

## Evaluation without a constructed ground truth

Public data has no ground-truth decomposition, so we test properties that do not depend on one: no mapping or model effect on loans that are new and carry codes the prior mapping never contained; no business movement on loans identical in amount and term across snapshots; credit to the code version for the prefix fallback it introduces; independence from the order in which inputs are considered; separate reporting of rating-system and model effects; and sensitivity to removing a fallback site from the instrumentation.

# Results on Public Data

## Methods disagree by billions, and on the sign

Table 3 reports the attributed effects of each method.

```{=latex}
\begin{table}[htbp]
\centering\footnotesize
\caption{Attributed effects on the change in expected loss, public SBA portfolio, 30 June 2025 to 30 June 2026 (\$ million). The change to be explained is −\$2,642M; every method reconciles to it exactly.}
\begin{tabular}{lcccccc}
\toprule
Method & Business & Mapping & Rating system & Model & Code & Repaired \\
\midrule
Proposed & 115.2 & 16.3 & −2,768.8 & 31.3 & −35.9 & 84.5\% \\
Unowned repair & 115.2 & 21.8 & −1,401.8 & −1,333.6 & −43.6 & 89.4\% \\
Unmatched-only repair & 119.3 & −7.8 & −703.1 & −2,014.9 & −35.5 & 3.2\% \\
Precedence, no repair & 124.3 & −12.8 & −694.9 & −1,955.2 & −103.4 & 0.0\% \\
Naive Shapley & 24.6 & 9.3 & −670.3 & −1,903.7 & −101.7 & 0.0\% \\
Sequential walk & 124.3 & 58.2 & +1,290.1 & −3,935.9 & −178.7 & 0.0\% \\
Targeted merge & −20.2 & 8.7 & (merged) & −2,511.3 & −119.2 & 0.0\% \\
Stratified & −2,665.0 & 0.0 & 0.0 & 23.1 & 0.0 & 0.0\% \\
\bottomrule
\end{tabular}
\end{table}
```

The sequential walk reports the rating-system change as *increasing* expected loss by \$1.29 billion; the proposed method reports it as *reducing* expected loss by \$2.77 billion. The sequential figure comes from a run in which the new bands are scored by a model that has no parameters for them, so most loans receive a pooled default rate (Figure 4).

![Attributed effects on the public SBA portfolio by method. The rating-system and model effects vary by billions across methods, and the rating-system effect changes sign.](fig/fig4_real_methods.pdf){width=92%}

## Phantom effects on real records

Table 4 reports two checks that need no ground truth.

```{=latex}
\begin{table}[htbp]
\centering\small
\caption{Effects booked on the 4,044 new loans whose industry codes are absent from the prior mapping, where any mapping or model effect is spurious, and business effect booked on the 256,378 loans unchanged in amount and term (\$ million).}
\begin{tabular}{l>{\raggedright\arraybackslash}p{0.277\textwidth}>{\raggedright\arraybackslash}p{0.296\textwidth}>{\raggedright\arraybackslash}p{0.258\textwidth}}
\toprule
Method & Model effect on new-gap loans & Mapping effect on new-gap loans & Business on unchanged loans \\
\midrule
Proposed & 21.4 & 0.0 & 0.0 \\
Unowned repair & 55.2 & 3.4 & 0.0 \\
Unmatched-only repair & 60.3 & 0.0 & 0.0 \\
Precedence, no repair & 21.5 & 45.8 & 0.0 \\
Naive Shapley & 21.4 & 30.1 & 0.0 \\
Sequential walk & 97.7 & 28.5 & 0.0 \\
Targeted merge & 26.3 & 35.0 & 0.0 \\
Stratified & 0.0 & 0.0 & 4,463.7 \\
\bottomrule
\end{tabular}
\end{table}
```

The proposed method books no mapping effect on loans whose codes never existed under the prior mapping, while other methods book \$28--46 million. Its residual model effect of \$21.4 million on those loans is not phantom: it arises where the current model itself falls back for sparsely populated cells, which the method deliberately preserves. The stratified approach avoids phantom effects by assigning affected loans to business, and in doing so books \$4.46 billion of business movement on loans that did not change, 99.5\% of their movement.

## Order dependence

Across all 120 orders of a sequential walk, attribution moves by up to \$669.7 million on a single industry line, and 21 of 25 lines move by more than \$10 million.

## The genuine code effect

The prefix fallback added by the current code version resolves mapping gaps for 8,045 real loans. The proposed method credits −\$36.3 million to the code version for these loans, essentially matching unmatched-only repair (−\$36.3 million); the sequential walk credits only −\$4.0 million, absorbing the remainder elsewhere.

## Instrumentation sensitivity

Table 5 removes fallback sites from the instrumentation one at a time.

```{=latex}
\begin{table}[htbp]
\centering\small
\caption{Effect of removing fallback sites from the instrumentation (\$ million).}
\begin{tabular}{lrr>{\raggedright\arraybackslash}p{0.610\textwidth}}
\toprule
Tagging & Phantom model effect & Phantom mapping effect & Reported rating-system effect \\
\midrule
All sites tagged & 21.4 & 0.0 & −2,768.8 \\
Model site untagged & 60.3 & 0.0 & −703.0 \\
Mapping site untagged & 20.9 & 58.6 & −2,728.6 \\
None tagged & 21.5 & 45.8 & −694.9 \\
\bottomrule
\end{tabular}
\end{table}
```

Leaving the model's fallback untagged changes the reported rating-system effect by a factor of four. Instrumentation completeness determines the headline number (Figure 5).

![Left: effects booked on new loans with unrecognised industry codes, by method. Right: phantom effects as fallback sites are removed from the instrumentation.](fig/fig5_real_phantom.pdf)

## Runtime

Thirty-two runs over 292,000 loans complete in 37.8 seconds, with attribution across two disclosure dimensions in 0.1--3.9 seconds per method, in a single process on an embedded SQL engine (SQLite for the results reported here; the pipeline runs unchanged on DuckDB [@raasveldt2019duckdb]).

# Controlled Synthetic Check

Public data cannot supply a ground-truth decomposition, so we retain a synthetic benchmark of 10,000 wholesale-style loans with planted events (rating-scale rollout, model recalibration, industry remapping, silent catch-all rows, a code reclassification, a whitespace-trimming fix, and prior-period corrections), three seeds, and known effects.

Table 6 reports the rules checklist and Table 7 the recovery error.

```{=latex}
\begin{table}[htbp]
\centering\footnotesize
\caption{Synthetic rules checklist (all three seeds must pass). Prop. = proposed; Unown. = unowned repair; Unmat. = unmatched-only repair; No rep. = precedence without repair; Naive = naive Shapley; Seq. = sequential walk; Merge = targeted merge; Strat. = stratified.}
\begin{tabular}{>{\raggedright\arraybackslash}p{0.368\textwidth}rrrrrrrr}
\toprule
Rule & Prop. & Unown. & Unmat. & No rep. & Naive & Seq. & Merge & Strat. \\
\midrule
R1 Reconciles to filings & Yes & Yes & Yes & Yes & Yes & Yes & Yes & Yes \\
R2 Order-independent & Yes & Yes & Yes & Yes & Yes & No & Yes & Yes \\
R3 No phantom model effect & Yes & No & No & No & No & No & n/a & Yes \\
R4 No phantom mapping effect & Yes & No & No & No & No & No & No & Yes \\
R5 Keeps genuine code fix & Yes & No & Yes & Yes & No & Yes & No & No \\
R6 Keeps rating-system effect & Yes & No & No & No & No & No & No & No \\
R7 No business on unchanged loans & Yes & Yes & Yes & Yes & Yes & Yes & Yes & No \\
\bottomrule
\end{tabular}
\end{table}
```

```{=latex}
\begin{table}[htbp]
\centering\small
\caption{Synthetic recovery error (mean across three seeds). The static-loan column uses an order-independent truth defined only for loans with one cause and no business movement; the others use the full truth, which adopts the method's own current-portfolio semantics and therefore validates implementation rather than semantics.}
\begin{tabular}{lrrrr}
\toprule
Method & Static-loan error & Total-line error & Segment-line error & Repaired \\
\midrule
Sequential walk & 2.565 & 2.192 & 2.074 & 0.0\% \\
Naive Shapley & 1.283 & 1.140 & 1.076 & 0.0\% \\
Precedence, no repair & 1.282 & 1.099 & 1.107 & 0.0\% \\
Unmatched-only repair & 1.282 & 1.099 & 1.038 & 0.4\% \\
Unowned repair & 0.039 & 0.226 & 0.211 & 8.8\% \\
Stratified & 0.079 & 0.222 & 0.198 & 0.0\% \\
Targeted merge & 0.001 & 0.110 & 0.168 & 0.0\% \\
Proposed & 0.000 & 0.000 & 0.000 & 8.1\% \\
\bottomrule
\end{tabular}
\end{table}
```

The proposed method is the only one satisfying all seven rules. On the order-independent truth, targeted merge is nearly exact once its joint rating-system-and-model effect is compared with the summed truth: its limitation is loss of separation rather than accuracy. Where catch-all defaults are deliberately left untagged, the proposed method's error rises from 0.000 to 0.092 and exceeds targeted merge (0.079), consistent with the public-data sensitivity above.

# Discussion and Limitations

**What the public data does and does not establish.** It establishes that real classification revisions create coverage gaps at material scale, that standard attribution methods disagree by billions on a real portfolio, and that the disagreement is driven by silently invalid runs. It does not establish how often institutions are misled in practice, because we observe neither their pipelines nor their published walks.

**Setting.** SBA 7(a) loans are government-guaranteed small-business loans, not a bank's wholesale portfolio, and the files disclose approved amounts rather than outstanding balances, so exposure is approximate. Public disclosure files contain no prior-period corrections, so that player appears only in the synthetic benchmark. Rating-band schemes and code versions are constructed, and documented as such.

**Estimation artifacts are real, and instructive.** Parameters estimated from public outcomes leave some sector-and-band cells sparsely populated or at a zero estimated default rate. This produced the case that led to the filed-run clause in the repair rule: a default already present in a filed run is reporting history, not an artifact of mixing. The synthetic benchmark, whose models covered every cell, could not have revealed it.

**Instrumentation completeness.** The guarantee is conditional on every fallback site being instrumented and owned; the public-data sensitivity shows the headline effect changing fourfold when one site is untagged. Defaults that are not simple on-off branches (caps, floors, clipped inputs), defaults inside trained models scoring unseen categories, and defaults applied upstream of the pipeline fall outside the method. Automating the discovery of fallback sites in SQL and Python code, and measuring how many real sites such a tool finds, is the most important next step.

**When simpler alternatives suffice.** If an institution does not need to separate dependent components, targeted merging is accurate, simpler, and needs no instrumentation. The proposed method is warranted when separate effects must be reported, or when silent catch-all mappings affect reference data.

**Semantics and scope.** Measuring pipeline effects on the current portfolio is a presentation policy; alternative orderings are not evaluated. The method addresses additive figures; ratio disclosures require separate treatment. Exact enumeration requires $2^{|N|}$ runs, feasible here at five and six players, and combining repair with hierarchical or sampling estimators remains to be demonstrated.

# Conclusion

Counterfactual attribution of expected-loss changes is only as reliable as its what-if runs, and reporting pipelines are built to conceal the runs that should not be trusted. On a public portfolio of 292,000 loans and an official industry-classification revision, standard methods disagree by billions of dollars and about the direction of a rating-system change. Instrumenting fallback sites, assigning each to its owner, and repairing only version-dependent defaults that were not already present in the filed runs yields an attribution that reconciles to both filed figures, removes phantom effects on records the prior pipeline never covered, and discloses the share that cannot be separated. The approach depends on finding every default; where that cannot be assured and separate effects are not required, targeted merging of dependent inputs is a strong alternative.

# Declarations {-}

**Data and code availability.** All data are public: SBA 7(a) FOIA loan-level files and the U.S. Census Bureau 2022-to-2017 NAICS concordance. The code that rebuilds the study from those sources, together with the synthetic generator, will be released in a public repository with an archived DOI.

**Use of AI tools.** Literature search, code scaffolding, and drafting were assisted by an AI system (Claude, Anthropic). The author designed the study and reviewed all code, results, and text, and takes full responsibility for the content.

**Competing interests.** The author declares no competing interests.

# References {-}

::: {#refs}
:::
