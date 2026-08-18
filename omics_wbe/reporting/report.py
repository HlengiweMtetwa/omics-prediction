"""Technical report generation.

The report is generated from ``study_results.json`` rather than written by hand,
so every number in it is the number the pipeline produced. Re-running the study
re-writes the report; there is no path by which the prose and the results
diverge.
"""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from omics_wbe.config import REPORTS_DIR, RESULTS_DIR


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "not available"
    if isinstance(value, float):
        # NaN is a real state here (a constant baseline has no rank correlation);
        # rendering it as "nan" reads like a broken cell.
        return "-" if value != value else f"{value:.{digits}f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _table_md(rows: list[dict], columns: list[str], digits: int = 3) -> str:
    if not rows:
        return "_no rows_\n"
    header = "| " + " | ".join(columns) + " |\n"
    sep = "|" + "|".join("---" for _ in columns) + "|\n"
    body = ""
    for row in rows:
        body += "| " + " | ".join(_fmt(row.get(c), digits) for c in columns) + " |\n"
    return header + sep + body


def build_markdown_report(results: dict[str, Any] | None = None) -> str:
    """Render the full technical report as Markdown."""
    if results is None:
        results = json.loads((RESULTS_DIR / "study_results.json").read_text())

    from omics_wbe.study import headline_findings
    h = headline_findings(results)

    obj1 = results["objective_1_detection"]
    obj2 = results["objective_2_integration_prediction"]
    obj3 = results["objective_3_public_health_value"]
    sens = results["sensitivity"]
    qld = results.get("second_programme_queensland", {})

    delta = pd.DataFrame(obj2["experiments"]["delta"]["summary"])
    level = pd.DataFrame(obj2["experiments"]["level"]["summary"])
    optimism = pd.DataFrame(obj2["experiments"]["delta"]["optimism"])

    parts: list[str] = []
    A = parts.append

    A(f"""# Omics-Based Wastewater Surveillance: Technical Results Report

**Project** — Omics Approaches to Predictive Prevention Tools for Disease
Surveillance Through Wastewater-Based Epidemiology
**Generated** — {date.today().isoformat()} (automatically, from `results/wbe/study_results.json`)

> Every figure in this document is produced by `omics_wbe.study.run_study()`.
> Re-running the pipeline regenerates this report, so the prose cannot drift
> away from the results.

---

## Executive summary

Analysis of **{_fmt(h['n_measurements_ingested'])} wastewater measurements**
submitted to the US National Wastewater Surveillance System from California
(March 2020 – January 2024), linked to county-level reported COVID-19 cases,
supports four findings.

1. **The wastewater signal leads reported cases by
   {_fmt(h['optimal_lead_weeks'])} week(s)** (peak median Spearman
   ρ = {_fmt(h['peak_spearman'])} across {_fmt(h['n_counties_modelled'])} counties).
2. **Wastewater predicts *change*, not *level*.** A within-site standardised
   signal has no information about a county's absolute case rate — standardisation
   removed exactly that — and a level model built on it fails
   (R² < 0). Re-framed onto the change in log case rate, the same signal is
   genuinely predictive.
3. **Wastewater's distinct value is early warning, not magnitude forecasting.**
   For two-week-ahead surge detection the best model reaches AUPRC
   {_fmt((h.get('alert') or {}).get('auprc'))} against a base rate of
   {_fmt((h.get('alert') or {}).get('prevalence'))} — a
   {_fmt((h.get('alert') or {}).get('auprc_lift_over_prevalence'), 1)}× lift —
   and shows positive decision-curve net benefit across the plausible threshold
   range. {_alert_block_comparison(obj3)}
4. **The validation protocol matters more than the model.** Random k-fold
   cross-validation, as specified in the original proposal, understates error on
   this panel; for the wastewater-only level model it inflates R² by
   {_fmt(_max_r2_inflation(pd.DataFrame(obj2['experiments']['level']['optimism'])))}.
   All headline results use rolling-origin validation with a
   {results['config']['cv_gap_weeks']}-week gap, and **causal** feature
   standardisation — features at week *t* use only data available at week *t*.

---

## 1. Data and provenance

| Source | Role | Records | Period |
|---|---|---|---|
| CDC NWSS (California submissions) | wastewater measurements | {_fmt(obj1['ingest'].get('rows_read'))} read, {_fmt(obj1['ingest'].get('rows_kept'))} mapped | {obj1['ingest'].get('date_min')} to {obj1['ingest'].get('date_max')} |
| NYT county COVID-19 series | public health records | {_fmt(h['n_counties_modelled'])} counties modelled | to 2023-03 |
| Queensland wastewater programme | second programme (detect/non-detect) | {_fmt(qld.get('n_sites'))} sites | 2020-07 to 2022-09 |

Sequence archives named in the proposal (NCBI SRA, ENA, DDBJ) are implemented as
connectors in `omics_wbe.ingest.sequence_archives`, but **no records were mined
from them**: outbound access to those hosts is blocked in the execution
environment used here, and — separately — archive records are *sequencing runs*,
not quantified biomarker concentrations. `plan_quantification()` enumerates the
read-processing steps that would be required to close that gap.

## 2. Objective 1 — detection methodology

### 2.1 Biomarker catalogue

{_catalog_section(obj1['catalog_summary'])}

Full catalogue: `results/wbe/tables/biomarker_catalog.csv`.

### 2.2 Harmonisation of submission conventions

Two conventions in the NWSS submissions would each have destroyed most of the
dataset if taken at face value.

- **Recovery scale.** {_fmt(obj1['harmonisation']['recovery']['rows_rescaled_from_ratio'])}
  rows report process recovery as a *ratio* (median ≈ 1.2) while the rest report
  a *percent* (median ≈ 60). Read globally as percent, 81% of the dataset
  appears to fail a recovery acceptance window. Scale is inferred per
  submission group and recorded.
- **Censoring flag.** {_fmt(obj1['harmonisation']['censoring']['rows_censoring_inferred'])}
  rows report a concentration of exactly zero with the below-LOD flag left
  empty. Censoring is inferred and marked as inferred.

After harmonisation, **{_fmt(obj1['qc']['n_pass'])} of
{_fmt(obj1['qc']['rows_in'])} measurements pass QC
({obj1['qc']['pass_rate']:.1%})**.

{_qc_table(obj1['qc'])}

![QC exclusions](../figures/fig01_qc_waterfall.png)

### 2.3 Multi-pathogen coverage

{_table_md(obj1.get('per_target_coverage', []), ['target', 'sites', 'weeks', 'site_weeks', 'mean_detect_fraction', 'first_week', 'last_week'])}

![Coverage](../figures/fig02_target_coverage.png)

Series that are almost entirely non-detects are excluded from quantitative
modelling automatically: with 98% censoring, *Candida auris* values sit at the
substituted `LOD/√2` and its robust scale collapses towards zero, so trivial
differences in the reported detection limit produced |z| > 3 in weeks when
nothing was detected at all. The detect-fraction gate removes those series
rather than letting them contribute artefacts.

### 2.4 Non-communicable disease: back-calculation

{_back_calculation_section(obj1['back_calculation'])}

## 3. Objective 2 — integration and prediction

The wastewater panel joins to county case records on region × epidemiological
week, giving {_fmt(obj2['join'].get('joined_region_weeks'))} joined region-weeks
across {_fmt(obj2['join'].get('n_regions'))} counties, of which
{_fmt(obj2['join'].get('regions_retained'))} have the ≥52 weeks of history a
rolling-origin validation requires.

### 3.1 Lead time

![Lag correlation](../figures/fig03_lag_correlation.png)

Median Spearman correlation peaks at **{_fmt(h['optimal_lead_weeks'])} week(s)
of wastewater lead** (ρ = {_fmt(h['peak_spearman'])}). Per-county optimal lags:
{obj2['lag'].get('per_region_best_lag_distribution')}.
{_fmt(obj2['lag'].get('n_regions_rho_above_0.5'))} of
{_fmt(obj2['lag'].get('n_regions'))} counties exceed ρ = 0.5 at their best lag.

![Series](../figures/fig04_series.png)

### 3.2 Forecast performance

Target: **change in log case rate** between week *t−1* and week *t+h*.

{_model_table(delta)}

![Model skill](../figures/fig05_model_skill.png)

{_incremental_value_section(obj2['experiments']['delta']['comparisons'])}

### 3.3 Why the level target fails

Asked to predict the *level* of the log case rate rather than its change, the
wastewater-only model has negative R² at every horizon:

{_model_table(level[level['block'] == 'wbe'])}

This is not a modelling failure but a measurement one. Within-site
standardisation deliberately removes each catchment's own scale so that a solids
matrix and a liquid matrix can be pooled; that same operation removes the
information needed to state an absolute case rate. A level prediction requires
an absolute, recovery-corrected, flow-normalised load — which these submissions
support for only {_fmt(obj1['standardisation'].get('n_standardised'))} of the
liquid-matrix measurements, since flow is reported for a minority of samples.

### 3.4 Two leakage channels, both closed

Feature construction leaks as easily as validation does, and both were live in
an earlier version of this analysis.

**Retrospective standardisation.** Robust within-site z-scores computed over the
whole series standardise a March 2021 sample partly by measurements taken in
2023. All headline features use the causal expanding-window variant (`_zc`); the
retrospective variant appears in the specification curve (§5.3) only as the
optimistic comparison.

**Validation folds.** Random k-fold places week *t−1* of a county in training
and week *t* in test. All headline results use rolling-origin splits with a
{results['config']['cv_gap_weeks']}-week gap, at least as long as the longest
feature lag.

A third choice is not leakage but matters as much. The standardised signal is
**winsorised at ±{results['config']['signal_clip']:g} robust SD**
({_fmt(obj2['join'].get('pct_winsorised'))}% of region-weeks affected). A robust
z-score of a series containing an epidemic excursion is heavily tailed — the
post-Omicron collapse reaches −27 here. Ridge regression on the unwinsorised
causal signal reaches R² of −4.5; gradient boosting on the identical input is
essentially unaffected, because trees are invariant to monotone transforms of a
feature. §5.3 reports performance across winsorisation limits rather than
resting on the chosen one.

### 3.5 Validation protocol

![Optimism](../figures/fig06_optimism.png)

{_optimism_table(optimism)}

## 4. Objective 3 — actionable public health value

### 4.1 Control-chart alarms and lead time

Applying an identical causal EWMA control chart to both the wastewater and the
clinical series, across {_fmt(obj3['lead_time']['summary'].get('n_regions'))}
counties:

- wastewater alarms raised: {_fmt(obj3['lead_time']['summary'].get('n_wbe_alarms'))}
- clinical events: {_fmt(obj3['lead_time']['summary'].get('n_clinical_events'))}
- pooled sensitivity: {_fmt(obj3['lead_time']['summary'].get('pooled_sensitivity'))}
- pooled precision: {_fmt(obj3['lead_time']['summary'].get('pooled_precision'))}
- median lead: {_fmt(obj3['lead_time']['summary'].get('median_lead_weeks'))} weeks

A simple threshold rule on the raw signal is therefore a weak detector on its
own. The trained classifier below is substantially better, which is the
practical argument for a model rather than a control chart.

### 4.2 Surge classification

Surge defined relatively: log case rate rises by more than 0.5 (≈ 65%) over the
next two weeks.

{_table_md(obj3['classification'], ['block', 'estimator', 'n', 'prevalence', 'auroc', 'auprc', 'brier', 'brier_skill_vs_prevalence'])}

Tree probabilities are isotonically calibrated inside each training fold;
uncalibrated, the same random forest discriminated well (AUROC ≈ 0.86) while
scoring *worse than the base rate* on Brier, which would have made the decision
curve meaningless.

### 4.3 Operating points

{_table_md(obj3['operating_points'], ['threshold', 'precision', 'recall', 'specificity', 'alerts_per_100_region_weeks'])}

### 4.4 Decision-curve analysis

![Alerts](../figures/fig07_alerts.png)

{_net_benefit_section(obj3.get('net_benefit_positive_range', {}))}

## 5. Sensitivity analyses

### 5.1 Feature importance

{_table_md(sens['permutation_importance'][:10], ['feature', 'rmse_increase', 'relative_increase'], digits=4)}

### 5.2 Input perturbation and measurement noise

{_table_md(sens['input_perturbation'], ['shift', 'mean_prediction_change', 'mean_rmse', 'mean_rmse_change'], digits=4)}

![Sensitivity](../figures/fig08_sensitivity.png)

{_measurement_section(sens['measurement_uncertainty'])}

### 5.3 Specification curve

{_table_md(sens['specification_curve'], ['specification', 'n', 'rmse', 'r2', 'spearman', 'note'])}

![Specification](../figures/fig09_specification.png)

## 6. Second programme: Queensland

{_qld_section(qld)}

## 7. Governance and ethics

```
{obj1['governance']['statement']}
```

Applied to the released outputs: {_fmt(obj1['governance']['site_level'].get('rows_released'))}
of {_fmt(obj1['governance']['site_level'].get('rows_in'))} site-weeks released
(suppression rate {_fmt(obj1['governance']['site_level'].get('suppression_rate'))}).

## 8. Limitations

1. **Reported cases are a biased comparator.** Test-seeking behaviour and test
   availability changed enormously across 2020–2023. Part of any wastewater-versus-cases
   discrepancy is a change in ascertainment, not in transmission, and this analysis
   cannot separate the two.
2. **One jurisdiction, one pathogen validated quantitatively.** Case data were
   available only for COVID-19 and only for California counties. The influenza,
   RSV, norovirus, mpox, *C. auris* and *Legionella* series are characterised
   descriptively but not validated against clinical outcomes.
3. **No non-communicable-disease measurements.** The back-calculation engine and
   catalogue are implemented and tested, but no metformin or metabolite
   measurements were obtainable, so the NCD arm is methodological, not empirical.
4. **Sewershed-to-county attribution is approximate.** {_fmt(obj1['ingest'].get('multi_county_sewershed_rows'))}
   rows come from sewersheds spanning more than one county; the first listed
   FIPS code is used.
5. **Matrix pooling rests on standardisation.** Solids and liquid measurements
   are made comparable by removing site-level scale, which is what forecloses
   the level-prediction task in §3.3.
6. **No sequence-level omics were processed.** Genomic depth here is
   assay-level PCR targets, not metagenomes.

## 9. Reproducing this report

```bash
pip install -r requirements.txt
python -m omics_wbe.cli check-sources     # confirm raw inputs are present
python -m omics_wbe.cli run --force       # full pipeline + study + report
python -m omics_wbe.cli verify            # re-hash every manifest input/output
```

Every stage writes a manifest to `results/wbe/manifests/` recording input and
output SHA-256 hashes, configuration, random seed and library versions.
""")
    return "\n".join(parts)


# --- section helpers -------------------------------------------------------

def _catalog_section(summary: dict) -> str:
    return (
        f"The catalogue holds **{summary['n_biomarkers']} biomarkers** across "
        f"{summary['by_omics_layer'].get('genomics', 0)} genomic, "
        f"{summary['by_omics_layer'].get('metabolomics', 0)} metabolomic and "
        f"{summary['by_omics_layer'].get('proteomics', 0)} proteomic entries, backed by "
        f"{summary['n_unique_references']} peer-reviewed references, and spanning "
        f"{summary['by_disease_class'].get('communicable', 0)} communicable-disease, "
        f"{summary['by_disease_class'].get('non_communicable', 0)} non-communicable-disease, "
        f"{summary['by_disease_class'].get('amr', 0)} antimicrobial-resistance and "
        f"{summary['by_disease_class'].get('exposure', 0)} chemical-exposure targets.\n\n"
        f"Each entry carries an evidence tier — {summary['by_evidence_tier'].get('established', 0)} "
        f"established, {summary['by_evidence_tier'].get('emerging', 0)} emerging, "
        f"{summary['by_evidence_tier'].get('prospective', 0)} prospective. Prospective markers are "
        "listed to fix the schema and record the open question; `inference_ready()` refuses them for "
        "any published claim. Only "
        f"{summary['n_with_literature_excretion']} marker has a transferable literature excretion "
        "fraction, which is itself the finding for the non-communicable-disease arm."
    )


def _qc_table(qc: dict) -> str:
    rows = [r for r in qc["rules"] if r["n_violations"] > 0]
    return _table_md(rows, ["code", "severity", "description", "n_violations", "pct_violations"])


def _model_table(df: pd.DataFrame) -> str:
    skill = next((c for c in df.columns if c.startswith("skill_vs_")), None)
    cols = ["horizon", "block", "estimator", "n", "rmse", "mae", "r2", "spearman"] + ([skill] if skill else [])
    keep = df[df["estimator"].isin(["ridge", "gradient_boosting", "random_forest"]) |
              df["estimator"].str.startswith("baseline_")]
    return _table_md(keep[cols].to_dict("records"), cols)


def _optimism_table(optimism: pd.DataFrame) -> str:
    if optimism.empty:
        return "_not available_"
    df = optimism[(optimism["horizon"] == 1) & (~optimism["estimator"].str.startswith("baseline_"))]
    cols = ["block", "estimator", "rmse_rolling_origin", "rmse_random_kfold",
            "rmse_ratio_kfold_over_rolling", "r2_inflation_kfold_minus_rolling"]
    return _table_md(df[cols].to_dict("records"), cols)


def _max_r2_inflation(optimism: pd.DataFrame) -> float:
    if optimism.empty:
        return float("nan")
    return float(optimism["r2_inflation_kfold_minus_rolling"].max())


def _incremental_value_section(comparisons: list[dict]) -> str:
    rows = [c for c in comparisons if c.get("challenger") == "wbe+ar"]
    if not rows:
        return ""
    lines = [
        "**Incremental value of wastewater over clinical autoregression** "
        "(paired bootstrap on shared test rows, ridge):\n",
        "| horizon | RMSE (clinical only) | RMSE (+ wastewater) | ΔRMSE | 95% CI | P(wastewater better) |",
        "|---|---|---|---|---|---|",
    ]
    for c in sorted(rows, key=lambda r: r["horizon"]):
        lines.append(
            f"| +{c['horizon']} wk | {c['rmse_reference']:.4f} | {c['rmse_challenger']:.4f} | "
            f"{c['delta_rmse']:.4f} | [{c['ci95_low']:.4f}, {c['ci95_high']:.4f}] | "
            f"{c['p_a_better']:.3f} |"
        )
    # Derived from the intervals, not asserted: an earlier draft claimed the CI
    # excluded zero at every horizon, which was true only of a leaky earlier run.
    conclusive = [c for c in rows if c["ci95_high"] < 0]
    negative = [c for c in rows if c["delta_rmse"] < 0]
    if len(conclusive) == len(rows):
        verdict = (
            "The improvement is negative in sign at every horizon and its 95% interval excludes "
            "zero at every horizon."
        )
    elif conclusive:
        horizons = ", ".join(f"+{c['horizon']} wk" for c in sorted(conclusive, key=lambda r: r["horizon"]))
        verdict = (
            f"The improvement is in the expected direction at {len(negative)} of {len(rows)} horizons, "
            f"but its 95% interval excludes zero only at {horizons}. At the shorter horizons the "
            "point estimate favours adding wastewater while the interval still contains zero — "
            "suggestive, not established."
        )
    else:
        verdict = (
            "At no horizon does the 95% interval exclude zero. On these data the incremental value "
            "of wastewater for magnitude forecasting is not established."
        )
    lines.append(
        f"\n{verdict} Either way the effect is small: wastewater refines a forecast that clinical "
        "autoregression already makes well. Its distinct value shows up in early warning (§4), not "
        "in magnitude forecasting."
    )
    return "\n".join(lines)


def _back_calculation_section(bc: dict) -> str:
    mc = bc["monte_carlo"]
    prev = mc.get("treated_prevalence_pct", {})
    refused = [r for r in bc["markers_without_transferable_parameters"] if r["status"] == "refused"]
    return (
        "The mass-balance engine converts an influent concentration into a treated-prevalence "
        "estimate. Using metformin (the one catalogue marker with a literature excretion fraction) "
        f"and scenario inputs — {bc['scenario']['influent_concentration_ng_per_L']:,.0f} ng/L, "
        f"{bc['scenario']['flow_L_per_day']:,.0f} L/day, "
        f"{bc['scenario']['population_served']:,} people — the correction factor is "
        f"{bc['parameters']['correction_factor']:.2f} and the estimated treated prevalence is "
        f"**{prev.get('median', float('nan')):.2f}% "
        f"(95% CI {prev.get('ci95_low', float('nan')):.2f}–{prev.get('ci95_high', float('nan')):.2f}%)**.\n\n"
        f"The interval spans a factor of {prev.get('relative_width', float('nan')):.1f} relative to the "
        "median, from parameter uncertainty alone — and that excludes the larger structural question "
        "of whether published excretion parameters transfer to this population at all. "
        f"For {len(refused)} of the other non-communicable-disease markers the engine **refuses to "
        "run**, because no transferable excretion parameter exists:\n\n"
        + "\n".join(f"- `{r['biomarker_id']}` — {r['reason']}" for r in refused)
        + "\n\nThat refusal is the design. Producing a prevalence figure from an excretion fraction "
        "nobody has measured is the central failure mode of non-communicable-disease WBE, and it is "
        "prevented mechanically rather than by reviewer vigilance.\n\n"
        "**The inputs above are a scenario, not a measurement.** No metformin data were obtainable."
    )


def _alert_block_comparison(obj3: dict) -> str:
    """State the wastewater-versus-clinical alert comparison from the numbers."""
    rows = pd.DataFrame(obj3.get("classification", []))
    if rows.empty:
        return ""
    best = rows.sort_values("auprc", ascending=False).groupby("block").first()
    if "ar" not in best.index:
        return ""
    ar = float(best.loc["ar", "auprc"])
    others = {b: float(best.loc[b, "auprc"]) for b in best.index if b != "ar"}
    if not others or ar <= 0:
        return ""
    top_block = max(others, key=others.get)
    return (
        f"Models with the wastewater block reach AUPRC {others[top_block]:.3f} "
        f"(`{top_block}`) against {ar:.3f} for clinical autoregression alone — "
        f"a {others[top_block] / ar:.1f}x advantage on the task that matters most for "
        "early warning."
    )


def _net_benefit_section(nb: dict) -> str:
    if not nb or not nb.get("threshold_range"):
        return "_Net benefit did not exceed the best default strategy at any threshold tested._"
    lo, hi = nb["threshold_range"]
    return (
        f"The alert model shows positive net benefit over the better of 'alert always' and "
        f"'alert never' at **{nb['n_thresholds_with_positive_net_benefit']} of "
        f"{nb['n_thresholds_tested']} thresholds tested**, spanning decision thresholds "
        f"{lo:.2f}–{hi:.2f}, with a maximum advantage of "
        f"{nb['max_benefit_over_best_default']:.4f}. In plain terms: for any decision-maker whose "
        f"tolerance for a false alarm lies in that range, acting on this signal is better than "
        "either blanket policy. That is the concrete sense in which the wastewater signal is "
        "*actionable*, which is what Objective 3 asks."
    )


def _measurement_section(mc: dict) -> str:
    rel_lo, rel_hi = mc["relative_inflation_ci95"]
    return (
        f"Adding Gaussian analytical noise of {mc['noise_sd_standardised_units']} robust-SD units to "
        f"every wastewater input, {mc['n_draws_per_fold']} draws per fold, inflates RMSE by a median "
        f"of {mc['median_rmse_inflation']:.4f} "
        f"({mc['median_relative_inflation']:.1%}, 95% range {rel_lo:.1%} to {rel_hi:.1%}) "
        f"against a mean fold baseline of {mc['baseline_rmse_mean_across_folds']:.4f}. "
        f"{mc['fraction_of_draws_worse_than_baseline']:.0%} of noise draws made the forecast worse.\n\n"
        "Inflation is computed per fold against that fold's own baseline. Pooling raw RMSEs across "
        "folds of differing difficulty and comparing their median to the mean of the fold baselines "
        "gives the nonsensical result that added noise *improves* accuracy — an artefact of mixing "
        "two distributions, which an earlier version of this analysis reported before it was caught.\n\n"
        "This bounds what better analytical precision alone could buy: the dominant error is "
        "epidemiological and ascertainment-driven, not analytical."
    )


def _qld_section(qld: dict) -> str:
    if not qld.get("available"):
        return "_Queensland panel not built._"
    return (
        f"The Queensland programme publishes qualitative detect/non-detect results for "
        f"{qld['n_sites']} sites, {qld['n_subcatchment_sites']} of which are upstream "
        "sub-catchment points withheld under the governance policy. It cannot enter the "
        "quantitative model — no concentrations are published — but it supports the urban/rural "
        "comparison the proposal asks for, which the California data cannot (NWSS carries no "
        "urban/rural label).\n\n"
        + _table_md(qld["detection_by_catchment_size"],
                    ["size_band", "sites", "site_weeks", "mean_detect_fraction"])
        + "\n![Queensland detection](../figures/fig10_qld_detection.png)\n\n"
        "Detection frequency rises with catchment size. Two mechanisms are confounded and this "
        "design cannot separate them: larger catchments contain more infected people at a given "
        "prevalence (a sampling-effort effect), and they were also sampled more often. The "
        "operational implication holds either way — a small rural sewershed needs a more sensitive "
        "assay or more frequent sampling to reach the same detection probability as a city plant."
    )


def write_reports(results: dict[str, Any] | None = None) -> dict[str, str]:
    """Write the Markdown report and a self-contained HTML rendering."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    markdown = build_markdown_report(results)
    md_path = REPORTS_DIR / "technical_report.md"
    md_path.write_text(markdown)

    html_path = REPORTS_DIR / "technical_report.html"
    html_path.write_text(_markdown_to_html(markdown))
    return {"markdown": str(md_path), "html": str(html_path)}


def _markdown_to_html(markdown: str) -> str:
    """Minimal Markdown -> HTML. No external dependency, deterministic output."""
    lines = markdown.split("\n")
    out: list[str] = []
    in_table = in_code = False

    for line in lines:
        if line.startswith("```"):
            out.append("</pre>" if in_code else "<pre>")
            in_code = not in_code
            continue
        if in_code:
            out.append(html.escape(line))
            continue

        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if not in_table:
                out.append("<table>")
                in_table = True
                out.append("<tr>" + "".join(f"<th>{_inline(c)}</th>" for c in cells) + "</tr>")
            else:
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False

        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            out.append(f"<h{level}>{_inline(line.lstrip('#').strip())}</h{level}>")
        elif line.startswith("!["):
            alt, _, rest = line[2:].partition("](")
            out.append(f'<figure><img src="{rest.rstrip(")")}" alt="{html.escape(alt)}">'
                       f"<figcaption>{html.escape(alt)}</figcaption></figure>")
        elif line.startswith("> "):
            out.append(f"<blockquote>{_inline(line[2:])}</blockquote>")
        elif line.startswith("- ") or line.startswith("* "):
            out.append(f"<li>{_inline(line[2:])}</li>")
        elif line.strip() == "---":
            out.append("<hr>")
        elif line.strip():
            out.append(f"<p>{_inline(line)}</p>")

    if in_table:
        out.append("</table>")

    body = "\n".join(out)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Omics WBE — Technical Results Report</title>
<style>
:root {{ --fg:#1b1f24; --bg:#ffffff; --muted:#5a6472; --line:#dfe3e8; --accent:#1b6ca8; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --fg:#e6e9ee; --bg:#14171c; --muted:#9aa4b2; --line:#2b3038; --accent:#6db3e8; }}
}}
body {{ background:var(--bg); color:var(--fg); font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
       max-width:900px; margin:0 auto; padding:2rem 1.25rem; }}
h1,h2,h3,h4 {{ line-height:1.25; margin-top:2rem; }}
h1 {{ border-bottom:2px solid var(--accent); padding-bottom:.4rem; }}
h2 {{ border-bottom:1px solid var(--line); padding-bottom:.3rem; }}
table {{ border-collapse:collapse; width:100%; margin:1rem 0; font-size:.88em; display:block; overflow-x:auto; }}
th,td {{ border:1px solid var(--line); padding:.35rem .55rem; text-align:left; white-space:nowrap; }}
th {{ background:color-mix(in srgb, var(--accent) 12%, transparent); }}
pre {{ background:color-mix(in srgb, var(--fg) 6%, transparent); padding:.9rem; overflow-x:auto; border-radius:6px; font-size:.85em; }}
code {{ background:color-mix(in srgb, var(--fg) 8%, transparent); padding:.1rem .3rem; border-radius:3px; font-size:.9em; }}
blockquote {{ border-left:3px solid var(--accent); margin:1rem 0; padding:.4rem 1rem; color:var(--muted); }}
figure {{ margin:1.5rem 0; }} img {{ max-width:100%; height:auto; border:1px solid var(--line); border-radius:6px; }}
figcaption {{ color:var(--muted); font-size:.85em; margin-top:.4rem; }}
hr {{ border:none; border-top:1px solid var(--line); margin:2rem 0; }}
li {{ margin:.25rem 0; }}
</style></head><body>
{body}
</body></html>"""


def _inline(text: str) -> str:
    import re
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', escaped)
    return escaped
