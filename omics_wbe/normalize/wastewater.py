"""Normalisation: measurements -> comparable, aggregated surveillance signals.

Four problems stand between a wastewater PCR result and something a model can
use, and this module handles them in order.

1. **Analytical replicates.** Collapsed on the log scale (geometric mean),
   because qPCR concentrations are log-normally distributed; an arithmetic mean
   of two replicates is pulled towards the higher one.

2. **Left-censored non-detects.** Substituted at ``LOD / sqrt(2)`` (Hornung &
   Reed 1990), the standard treatment for environmental data with a modest
   censoring fraction. Where no LOD was submitted, a *cohort* LOD is estimated
   as the 1st percentile of detected values in the same target-unit-matrix
   group and the substitution route is recorded per row.

3. **Incomparable matrices.** These submissions mix ``copies/L wastewater`` with
   ``copies/g dry sludge``. There is no conversion between them without solids
   content, which is not reported. Two routes are provided instead:
   the **faecal-normalised ratio** (target / PMMoV), which is dimensionless and
   therefore matrix-comparable, and **within-site standardisation**, which
   removes each site's own scale and leaves relative temporal dynamics. The
   ratio is the primary metric; standardisation is what makes pooling across
   sites defensible.

4. **Irregular sampling.** Sites sample on different days at different
   frequencies, so everything is aggregated to epidemiological weeks
   (MMWR convention, week ending Saturday) before any join to case data.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from omics_wbe.config import AnalysisConfig, DEFAULT_CONFIG

#: 1 million US gallons per day, in litres per day.
MGD_TO_L_PER_DAY = 3_785_411.784

_REPLICATE_KEYS = ("source", "site_id", "target", "collect_date", "sample_id")


def collapse_replicates(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Collapse analytical replicates to one row per sample and target.

    Aggregation rules, and why each is what it is:

    * concentration - geometric mean of positive values (qPCR concentrations are
      log-normal). If every replicate is a non-detect, the result is a non-detect.
    * ``below_lod`` - True only if *all* replicates were non-detects. One
      confirmed detection is a detection.
    * ``lod`` - the maximum across replicates, the conservative choice.
    * ``recovery_pct`` / ``normaliser_conc`` - median.
    * ``replicate_log10_sd`` - retained as a per-sample measurement-uncertainty
      estimate, which the Monte-Carlo sensitivity analysis consumes.
    """
    keys = [k for k in _REPLICATE_KEYS if k in df.columns]
    before = len(df)

    work = df.copy()
    conc = pd.to_numeric(work["concentration"], errors="coerce")
    work["_log10"] = np.log10(conc.where(conc > 0))
    is_detect = ~work["below_lod"].astype("boolean").fillna(False).astype(bool)
    # Non-detects are excluded from the geometric mean; a detect and a
    # non-detect average to the detect, not to something in between.
    work["_log10_detect"] = work["_log10"].where(is_detect)

    grouped = work.groupby(keys, dropna=False, sort=False)
    out = grouped.agg(
        _log10_mean=("_log10_detect", "mean"),
        _n_detects=("_log10_detect", "count"),
        replicate_log10_sd=("_log10_detect", "std"),
        lod=("lod", "max"),
        normaliser_conc=("normaliser_conc", "median"),
        recovery_pct=("recovery_pct", "median"),
        flow_rate=("flow_rate", "median"),
        population_served=("population_served", "median"),
        n_replicates=("_log10", "size"),
        region_code=("region_code", "first"),
        site_name=("site_name", "first"),
        matrix=("matrix", "first"),
        unit=("unit", "first"),
        censoring_inferred=("censoring_inferred", "any"),
    ).reset_index()

    any_detect = out["_n_detects"] > 0
    out["concentration"] = np.where(any_detect, np.power(10.0, out["_log10_mean"]), 0.0)
    out["below_lod"] = ~any_detect
    out = out.drop(columns=["_log10_mean", "_n_detects"])

    # gene_target is aggregated separately: de-duplicating first makes the
    # per-group join operate on one- or two-element lists.
    gt = (
        work[keys + ["gene_target"]].dropna(subset=["gene_target"])
        .astype({"gene_target": "string"}).drop_duplicates()
        .sort_values(keys + ["gene_target"])
        .groupby(keys, dropna=False, sort=False)["gene_target"].agg("|".join)
        .rename("gene_target").reset_index()
    )
    out = out.merge(gt, on=keys, how="left")

    report = {
        "rows_in": int(before),
        "rows_out": int(len(out)),
        "rows_collapsed": int(before - len(out)),
        "samples_with_replicates": int((out["n_replicates"] > 1).sum()),
        "median_replicate_log10_sd": (
            float(out["replicate_log10_sd"].median()) if out["replicate_log10_sd"].notna().any() else None
        ),
    }
    return out, report


def substitute_censored(
    df: pd.DataFrame,
    config: AnalysisConfig = DEFAULT_CONFIG,
    cohort_keys: tuple[str, ...] = ("target", "unit", "matrix"),
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Replace non-detects with ``LOD / sqrt(2)``.

    Adds ``concentration_imputed`` and ``lod_route`` (``submitted`` / ``cohort``
    / ``none``). Rows with no usable LOD by either route keep a NaN
    concentration rather than a fabricated one — a censored value with no
    detection limit carries no quantitative information at all.
    """
    out = df.copy()
    conc = pd.to_numeric(out["concentration"], errors="coerce")
    censored = out["below_lod"].astype("boolean").fillna(False).astype(bool)
    lod = pd.to_numeric(out.get("lod", pd.Series(np.nan, index=out.index)), errors="coerce")

    present = [c for c in cohort_keys if c in out.columns]
    detected_log = np.log10(conc.where(~censored & (conc > 0)))
    if present:
        cohort_lod = 10 ** detected_log.groupby([out[c].astype("string") for c in present]).transform(
            lambda s: s.quantile(0.01) if s.notna().sum() >= 20 else np.nan
        )
    else:
        cohort_lod = pd.Series(np.nan, index=out.index)

    route = pd.Series("none", index=out.index, dtype="object")
    effective_lod = pd.Series(np.nan, index=out.index, dtype="float64")
    route[lod.notna() & (lod > 0)] = "submitted"
    effective_lod[lod.notna() & (lod > 0)] = lod
    use_cohort = (route == "none") & cohort_lod.notna() & (cohort_lod > 0)
    route[use_cohort] = "cohort"
    effective_lod[use_cohort] = cohort_lod[use_cohort]

    imputed = conc.copy()
    substitution = effective_lod / np.sqrt(2.0)
    imputed[censored] = substitution[censored]

    out["concentration_imputed"] = imputed
    out["lod_effective"] = effective_lod
    out["lod_route"] = route.where(censored, "not_censored")
    out["censored"] = censored

    report = {
        "n_rows": int(len(out)),
        "n_censored": int(censored.sum()),
        "censoring_fraction": round(float(censored.mean()), 4) if len(out) else 0.0,
        "censored_lod_route": out.loc[censored, "lod_route"].value_counts().to_dict(),
        "n_censored_unresolvable": int((censored & imputed.isna()).sum()),
        "substitution_rule": config.censored_substitution,
        "censoring_fraction_by_target": (
            out.groupby("target")["censored"].mean().round(4).to_dict() if "target" in out else {}
        ),
    }
    return out, report


def compute_metrics(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Derive the analysis metrics from an imputed concentration.

    * ``log10_conc`` - raw scale. Comparable only within a matrix.
    * ``log10_ratio_pmmov`` - target / faecal marker, dimensionless and therefore
      comparable across matrices. The primary metric.
    * ``log10_load_per_capita`` - flow-normalised daily load per 100k people.
      Only computable for liquid matrices with a reported flow; NaN elsewhere,
      never imputed from a plant's design capacity.
    """
    out = df.copy()
    conc = pd.to_numeric(out["concentration_imputed"], errors="coerce")
    out["log10_conc"] = np.log10(conc.where(conc > 0))

    norm = pd.to_numeric(out.get("normaliser_conc", pd.Series(np.nan, index=out.index)), errors="coerce")
    ratio = conc / norm.where(norm > 0)
    out["ratio_pmmov"] = ratio
    out["log10_ratio_pmmov"] = np.log10(ratio.where(ratio > 0))

    flow = pd.to_numeric(out.get("flow_rate", pd.Series(np.nan, index=out.index)), errors="coerce")
    pop = pd.to_numeric(out.get("population_served", pd.Series(np.nan, index=out.index)), errors="coerce")
    is_liquid = out.get("unit", pd.Series("", index=out.index)).astype("string").eq("copies/L wastewater")
    load = conc * flow.where(flow > 0) * MGD_TO_L_PER_DAY
    per_capita = (load / pop.where(pop > 0)) * 100_000
    out["log10_load_per_100k"] = np.log10(per_capita.where(is_liquid & (per_capita > 0)))

    report = {
        "n_rows": int(len(out)),
        "coverage": {
            "log10_conc": int(out["log10_conc"].notna().sum()),
            "log10_ratio_pmmov": int(out["log10_ratio_pmmov"].notna().sum()),
            "log10_load_per_100k": int(out["log10_load_per_100k"].notna().sum()),
        },
    }
    return out, report


def standardise_within_site(
    df: pd.DataFrame,
    metric: str = "log10_ratio_pmmov",
    group_cols: tuple[str, ...] = ("site_id", "target"),
    min_observations: int = 20,
    min_detect_fraction: float = 0.2,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Robust within-site z-score, so sites on different scales can be pooled.

    Uses median and MAD rather than mean and SD: an epidemic wave is a genuine
    excursion, and standardising by an SD that the wave itself inflated shrinks
    exactly the signal being measured.

    Two gates, both necessary:

    ``min_observations``
        A z-score from a handful of points is noise with a scale attached.

    ``min_detect_fraction``
        A series that is almost entirely non-detects sits at the substituted
        value ``LOD/sqrt(2)``, so its MAD collapses towards zero and dividing by
        it turns trivial differences in the reported LOD into large z-scores.
        In these data that is not hypothetical: *Candida auris* is 98% censored
        and produced |z| > 3 for weeks in which nothing was detected at all.
        Such series are returned as NaN and counted, so they are visibly
        excluded from quantitative modelling rather than quietly contributing
        artefacts to it.
    """
    out = df.copy()
    values = pd.to_numeric(out[metric], errors="coerce")
    keys = [out[c] for c in group_cols if c in out.columns]
    grp = values.groupby(keys)

    med = grp.transform("median")
    mad = grp.transform(lambda s: (s - s.median()).abs().median())
    n = grp.transform("count")
    scale = (mad * 1.4826).replace(0, np.nan)

    if "censored" in out.columns:
        detected = (~out["censored"].astype(bool)).astype(float)
        detect_fraction = detected.groupby(keys).transform("mean")
    else:
        detect_fraction = pd.Series(1.0, index=out.index)

    usable = (n >= min_observations) & (detect_fraction >= min_detect_fraction)
    out[f"{metric}_z"] = ((values - med) / scale).where(usable)
    out[f"{metric}_site_median"] = med
    out[f"{metric}_site_scale"] = scale
    out[f"{metric}_series_detect_fraction"] = detect_fraction

    series_sizes = grp.size()
    series_detect = detect_fraction.groupby(keys).first()
    report = {
        "metric": metric,
        "min_observations": min_observations,
        "min_detect_fraction": min_detect_fraction,
        "n_series": int(len(series_sizes)),
        "n_series_below_min_observations": int((series_sizes < min_observations).sum()),
        "n_series_below_min_detect_fraction": int((series_detect < min_detect_fraction).sum()),
        "n_standardised": int(out[f"{metric}_z"].notna().sum()),
        "n_excluded": int(out[f"{metric}_z"].isna().sum()),
    }
    return out, report


def standardise_within_site_causal(
    df: pd.DataFrame,
    metric: str = "log10_ratio_pmmov",
    group_cols: tuple[str, ...] = ("site_id", "target"),
    min_window: int = 20,
    min_detect_fraction: float = 0.2,
    date_col: str = "collect_date",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Expanding-window standardisation, using only each sample's own past.

    :func:`standardise_within_site` centres and scales each series by its
    *whole-series* median and MAD. That is fine for description, but as a model
    feature it leaks: the z-score of a sample in March 2021 is computed partly
    from measurements taken in 2023, information no forecaster could have had.

    This variant computes the median and MAD from observations strictly *before*
    each sample, so the feature at week t depends only on data available at week
    t. The first ``min_window`` observations of every series are NaN, since there
    is not yet a past to standardise against.

    Both are produced by the pipeline and both are modelled, so the size of the
    optimism introduced by the retrospective version is measured rather than
    assumed.
    """
    out = df.sort_values(list(group_cols) + [date_col]).copy()
    values = pd.to_numeric(out[metric], errors="coerce")
    keys = [out[c] for c in group_cols if c in out.columns]
    grp = values.groupby(keys)

    # shift(1) so the current observation never contributes to its own centre.
    past = grp.shift(1)
    past_grp = past.groupby(keys)
    med = past_grp.transform(lambda s: s.expanding(min_periods=min_window).median())
    mad = past_grp.transform(
        lambda s: s.expanding(min_periods=min_window).apply(
            lambda w: np.nanmedian(np.abs(w - np.nanmedian(w))), raw=True
        )
    )
    scale = (mad * 1.4826).replace(0, np.nan)

    if "censored" in out.columns:
        detected = (~out["censored"].astype(bool)).astype(float)
        detect_fraction = detected.groupby(keys).transform("mean")
    else:
        detect_fraction = pd.Series(1.0, index=out.index)

    col = f"{metric}_zc"
    out[col] = ((values - med) / scale).where(detect_fraction >= min_detect_fraction)

    report = {
        "metric": metric,
        "variant": "causal_expanding",
        "min_window": min_window,
        "min_detect_fraction": min_detect_fraction,
        "n_standardised": int(out[col].notna().sum()),
        "n_excluded": int(out[col].isna().sum()),
    }
    return out, report


def to_epiweek(dates: pd.Series, anchor: str = "W-SAT") -> pd.Series:
    """Map dates to the end of their epidemiological week (MMWR: Sun-Sat)."""
    return pd.to_datetime(dates).dt.to_period(anchor).dt.end_time.dt.normalize()


def aggregate_site_week(
    df: pd.DataFrame,
    metrics: tuple[str, ...] = ("log10_ratio_pmmov", "log10_conc", "log10_ratio_pmmov_z"),
    config: AnalysisConfig = DEFAULT_CONFIG,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """One row per site, target and epidemiological week.

    The median, not the mean: a single very high sample in a week should move
    the weekly value, but not dominate it.
    """
    out = df.copy()
    out["epiweek_end"] = to_epiweek(out["collect_date"], config.week_anchor)

    present = [m for m in metrics if m in out.columns]
    agg: dict[str, Any] = {m: (m, "median") for m in present}
    agg.update({
        "n_samples": ("concentration_imputed", "size"),
        "n_detects": ("censored", lambda s: int((~s.astype(bool)).sum())),
        "population_served": ("population_served", "median"),
        "region_code": ("region_code", "first"),
        "matrix": ("matrix", "first"),
        "site_name": ("site_name", "first"),
    })
    grouped = out.groupby(["source", "site_id", "target", "epiweek_end"], dropna=False).agg(**agg).reset_index()
    grouped["detect_fraction"] = grouped["n_detects"] / grouped["n_samples"]

    before = len(grouped)
    grouped = grouped[grouped["n_samples"] >= config.min_samples_per_site_week]

    report = {
        "rows_in": int(len(out)),
        "site_weeks": int(len(grouped)),
        "site_weeks_dropped_min_samples": int(before - len(grouped)),
        "n_sites": int(grouped["site_id"].nunique()),
        "weeks": int(grouped["epiweek_end"].nunique()),
        "median_samples_per_site_week": float(grouped["n_samples"].median()) if len(grouped) else None,
        "overall_detect_fraction": round(float(grouped["detect_fraction"].mean()), 4) if len(grouped) else None,
    }
    return grouped, report


def aggregate_region_week(
    site_weeks: pd.DataFrame,
    metric: str = "log10_ratio_pmmov_z",
    config: AnalysisConfig = DEFAULT_CONFIG,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Population-weighted roll-up from sewersheds to the reporting region.

    A county's wastewater signal is the weighted mean of its sewersheds'
    standardised signals, weighted by served population, because a plant serving
    500,000 people should not count the same as one serving 4,000.
    """
    df = site_weeks.copy()
    df = df[df[metric].notna() & df["region_code"].notna()]
    weight = pd.to_numeric(df["population_served"], errors="coerce").fillna(0.0).clip(lower=0.0)
    # A site with no population figure still carries signal; give it the
    # smallest positive weight rather than dropping it or weighting it equally.
    positive = weight[weight > 0]
    weight = weight.mask(weight <= 0, positive.min() if len(positive) else 1.0)
    df = df.assign(_w=weight, _wx=weight * df[metric])

    grouped = df.groupby(["region_code", "target", "epiweek_end"], dropna=False).agg(
        wsum=("_w", "sum"), wxsum=("_wx", "sum"),
        n_sites=("site_id", "nunique"), n_samples=("n_samples", "sum"),
        detect_fraction=("detect_fraction", "mean"),
        population_covered=("population_served", "sum"),
    ).reset_index()
    grouped[metric] = grouped["wxsum"] / grouped["wsum"]
    grouped = grouped.drop(columns=["wsum", "wxsum"])

    before = len(grouped)
    grouped = grouped[grouped["n_sites"] >= config.min_sites_per_region_week]

    report = {
        "metric": metric,
        "region_weeks": int(len(grouped)),
        "region_weeks_dropped_min_sites": int(before - len(grouped)),
        "n_regions": int(grouped["region_code"].nunique()),
        "median_sites_per_region_week": float(grouped["n_sites"].median()) if len(grouped) else None,
    }
    return grouped, report
