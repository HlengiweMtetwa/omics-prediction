# Manuscript Outlines

Three manuscripts, matching the three open-access publications budgeted in the
proposal (R40,000 each). Each is built from results already produced by
`omics_wbe.study.run_study()`; the tables and figures named exist in
`results/wbe/`.

---

## Manuscript 1 — Methods

**Working title:** *Random k-fold cross-validation systematically overstates the
performance of wastewater-based epidemiological forecasting models*

**Target:** *Science of the Total Environment* or *Water Research*

**Argument.** Wastewater surveillance panels are overlapping, autocorrelated
weekly time series. Random k-fold cross-validation, near-universal in the applied
WBE modelling literature, places week *t−1* of a catchment in training and week
*t* in test. We quantify the resulting optimism on a real multi-year panel and
propose rolling-origin validation with an explicit gap as the minimum standard.

**Key results (measured):**
- Random k-fold reduces reported RMSE by ~10% relative to rolling-origin
- R² inflation up to **0.56** for the wastewater-only level model
- Retrospective within-site standardisation is a second, independent leakage
  channel. Switching to the causal expanding variant changed the headline
  conclusions materially: the apparent incremental value of wastewater for
  magnitude forecasting went from "interval excludes zero at every horizon" to
  "conclusive only at two weeks ahead". The specification curve reports both.
- Winsorisation of the standardised signal is a third, non-leakage choice with a
  comparable effect size: unwinsorised, ridge reaches R² of −4.5 on the identical
  input on which gradient boosting is unaffected

**Figures:** `fig06_optimism.png`, `fig09_specification.png`
**Tables:** `sars_cov_2_delta_model_optimism.csv`, `sensitivity_specification.csv`

**Contribution.** A negative methodological result with an immediately adoptable
remedy, plus reference code (SOP 03).

---

## Manuscript 2 — Applied surveillance

**Working title:** *Wastewater surveillance predicts epidemic acceleration but
not case burden: a three-year multi-pathogen panel analysis*

**Target:** *The Lancet Microbe* or *Environment International*

**Argument.** The central practical question for a surveillance programme is not
whether wastewater correlates with cases but *what decision it can support*. We
show the signal is strong for direction-of-change and surge warning, and fails
for absolute burden — and that this follows from the normalisation required to
make heterogeneous sampling matrices comparable, not from model choice.

**Key results (measured):**
- Wastewater leads reported cases by 1–3 weeks (pooled peak median ρ = 0.57 at
  3 weeks; modal per-county optimum 2 weeks; 17 counties)
- Level prediction from a standardised signal fails (R² < 0 at all horizons)
- Change prediction succeeds (Spearman 0.60–0.62, skill 0.18–0.22 vs no-change)
- Surge warning: AUPRC 0.34 against a 0.103 base rate (3.3× lift)
- Wastewater **roughly doubles** the surge-warning AUPRC of clinical
  autoregression alone (0.32–0.34 vs 0.138) while being merely comparable to it
  for magnitude forecasting — the asymmetry is the paper's central point
- Positive decision-curve net benefit at 23 of 30 thresholds (0.06–0.60)

**Figures:** `fig03_lag_correlation.png`, `fig04_series.png`,
`fig05_model_skill.png`, `fig07_alerts.png`
**Tables:** `panel_coverage.csv`, `lag_correlations.csv`, `alert_operating_points.csv`

**Contribution.** Reframes the value proposition of WBE from case estimation to
decision triggering, with operating points a health department can act on.

---

## Manuscript 3 — Non-communicable disease and governance

**Working title:** *Non-communicable disease biomarkers in wastewater-based
epidemiology: an evidence-tiered catalogue and the parameter problem*

**Target:** *Journal of Hazardous Materials* or *Environmental Science & Technology*

**Argument.** Extending WBE to non-communicable disease is widely proposed and
rarely quantified honestly. We present an evidence-tiered biomarker catalogue
spanning genomic, proteomic and metabolomic layers, and show that the binding
constraint is not analytical sensitivity but **excretion-parameter
availability**: of the non-communicable-disease and exposure markers catalogued,
only one carries a transferable literature excretion fraction. We quantify the
resulting uncertainty and propose a mechanical refusal gate.

**Key results (measured):**
- 36 biomarkers, 4 omics/disease strata, 24 peer-reviewed references
- Evidence tiers: 19 established, 13 emerging, 4 prospective
- Only **1 of 36** has a transferable literature excretion fraction
- Worked back-calculation: 95% interval spans >3× the median from parameter
  uncertainty alone, excluding structural transferability uncertainty
- A software gate that refuses to produce a prevalence estimate from an
  uncalibrated parameter

**Tables:** `biomarker_catalog.csv`
**Supplementary:** `docs/ETHICS_AND_GOVERNANCE.md`

**Contribution.** A reusable catalogue with explicit evidence tiers, an honest
accounting of what blocks the NCD arm, and a governance framework treating group
privacy — not individual privacy — as the operative concern.

---

## Authorship and open science

- Data and code released under the repository licence; every result carries a
  run manifest with input and output SHA-256 hashes.
- Third-party data are **not** redistributed. `docs/DATA_ACQUISITION.md` gives
  the retrieval procedure and checksums, and licences are recorded per source
  (the NYT county series is CC BY-NC 4.0 — non-commercial use only).
- All analyses reproducible via `python -m omics_wbe.cli run --force`.
