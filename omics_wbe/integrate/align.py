"""Objective 2: aligning wastewater signals with public health records.

The join is region x epidemiological week. Three decisions in it matter more
than the mechanics:

**Direction of the lag.** Wastewater is compared at lag *k* against clinical
cases at week *t*, so a positive optimal lag means wastewater led the clinical
signal. That is the quantity a health department cares about and it is easy to
report with the sign inverted, so the convention is fixed here and used
everywhere downstream.

**Correlation on ranks.** Spearman rather than Pearson. The relationship
between shedding load and reported incidence is monotonic but not linear —
shedding per case falls over an infection, ascertainment changed enormously
across the study period — and Pearson would report the failure of a linearity
assumption as a weak association.

**Per-region before pooled.** A pooled correlation across counties can be driven
entirely by between-county differences in level rather than by within-county
temporal agreement, which is what surveillance actually needs. Correlations are
therefore computed within region and then summarised.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from omics_wbe.config import AnalysisConfig, DEFAULT_CONFIG


def join_panels(
    wbe_region_week: pd.DataFrame,
    health_region_week: pd.DataFrame,
    *,
    target: str,
    metric: str = "log10_ratio_pmmov_z",
    indicator: str = "covid_cases",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Inner-join one wastewater target to one clinical indicator.

    Returns a region x week panel with both signals, plus a coverage report
    describing what the join lost and why.
    """
    wbe = wbe_region_week[wbe_region_week["target"] == target].copy()
    health = health_region_week[health_region_week["indicator"] == indicator].copy()

    for frame in (wbe, health):
        frame["epiweek_end"] = pd.to_datetime(frame["epiweek_end"])
        frame["region_code"] = frame["region_code"].astype("string")

    panel = wbe.merge(
        health[["region_code", "region_name", "epiweek_end", "cases_week", "case_rate_per_100k"]],
        on=["region_code", "epiweek_end"], how="inner", validate="one_to_one",
    )
    panel = panel.rename(columns={metric: "wbe_signal"})
    panel = panel.sort_values(["region_code", "epiweek_end"]).reset_index(drop=True)
    panel["log_case_rate"] = np.log1p(panel["case_rate_per_100k"].clip(lower=0))

    wbe_weeks = set(zip(wbe["region_code"], wbe["epiweek_end"]))
    health_weeks = set(zip(health["region_code"], health["epiweek_end"]))
    report = {
        "target": target, "indicator": indicator, "metric": metric,
        "wbe_region_weeks": int(len(wbe)),
        "health_region_weeks": int(len(health)),
        "joined_region_weeks": int(len(panel)),
        "wbe_weeks_without_health": int(len(wbe_weeks - health_weeks)),
        "health_weeks_without_wbe": int(len(health_weeks - wbe_weeks)),
        "n_regions": int(panel["region_code"].nunique()),
        "date_min": str(panel["epiweek_end"].min().date()) if len(panel) else None,
        "date_max": str(panel["epiweek_end"].max().date()) if len(panel) else None,
        "regions_with_ge_52_weeks": int(
            (panel.groupby("region_code").size() >= 52).sum()
        ),
    }
    return panel, report


def _lagged(group: pd.DataFrame, lag: int) -> pd.DataFrame:
    """Wastewater from ``lag`` weeks earlier, against this week's cases.

    Reindexed onto a complete weekly calendar first: shifting by row position
    over a series with missing weeks would silently mean a different lag in
    every gap.
    """
    g = group.set_index("epiweek_end").sort_index()
    full = pd.date_range(g.index.min(), g.index.max(), freq="W-SAT")
    g = g.reindex(full)
    out = pd.DataFrame({
        "wbe_lagged": g["wbe_signal"].shift(lag),
        "case_rate": g["case_rate_per_100k"],
        "log_case_rate": g["log_case_rate"],
    })
    return out.dropna(subset=["wbe_lagged", "case_rate"])


def lag_correlations(
    panel: pd.DataFrame,
    *,
    max_lag: int = 6,
    min_lag: int = -2,
    min_weeks: int = 30,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Spearman correlation at each lag, per region.

    ``lag > 0`` means the wastewater measurement precedes the clinical week, so
    the lag maximising correlation is the apparent lead time of the wastewater
    signal.
    """
    rows = []
    for region, group in panel.groupby("region_code"):
        if len(group) < min_weeks:
            continue
        for lag in range(min_lag, max_lag + 1):
            paired = _lagged(group, lag)
            if len(paired) < min_weeks:
                continue
            rho, p = stats.spearmanr(paired["wbe_lagged"], paired["case_rate"])
            if np.isnan(rho):
                continue
            rows.append({
                "region_code": region, "lag_weeks": lag, "spearman_rho": float(rho),
                "p_value": float(p), "n_weeks": int(len(paired)),
            })

    result = pd.DataFrame(rows)
    if result.empty:
        return result, {"n_regions": 0, "note": "no region met the minimum-weeks threshold"}

    best = result.loc[result.groupby("region_code")["spearman_rho"].idxmax()]
    pooled = result.groupby("lag_weeks").agg(
        median_rho=("spearman_rho", "median"),
        mean_rho=("spearman_rho", "mean"),
        n_regions=("region_code", "nunique"),
    ).reset_index()

    report = {
        "n_regions": int(result["region_code"].nunique()),
        "lags_tested": [min_lag, max_lag],
        "pooled_by_lag": pooled.to_dict("records"),
        "best_lag_median_rho": int(pooled.loc[pooled["median_rho"].idxmax(), "lag_weeks"]),
        "best_lag_value": float(pooled["median_rho"].max()),
        "per_region_best_lag_distribution": best["lag_weeks"].value_counts().sort_index().to_dict(),
        "median_best_rho": float(best["spearman_rho"].median()),
        "n_regions_rho_above_0.5": int((best["spearman_rho"] > 0.5).sum()),
        "n_regions_rho_below_0.2": int((best["spearman_rho"] < 0.2).sum()),
    }
    return result, report


def coverage_table(panel: pd.DataFrame) -> pd.DataFrame:
    """Per-region coverage, for the report's data-availability table."""
    return (
        panel.groupby(["region_code", "region_name"], as_index=False)
        .agg(
            weeks=("epiweek_end", "nunique"),
            first_week=("epiweek_end", "min"),
            last_week=("epiweek_end", "max"),
            median_sites=("n_sites", "median"),
            population_covered=("population_covered", "median"),
            mean_case_rate=("case_rate_per_100k", "mean"),
            mean_detect_fraction=("detect_fraction", "mean"),
        )
        .sort_values("weeks", ascending=False)
        .reset_index(drop=True)
    )


def build_analysis_panel(
    wbe_region_week: pd.DataFrame,
    health_region_week: pd.DataFrame,
    *,
    target: str = "sars_cov_2",
    config: AnalysisConfig = DEFAULT_CONFIG,
    min_weeks_per_region: int = 52,
    metric: str | None = None,
    clip: float | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """The joined, winsorised panel, restricted to regions with enough history.

    Two defaults carry weight.

    The signal is the **causal** standardisation (``_zc``) unless overridden.
    The retrospective variant standardises each sample partly by measurements
    taken years later; using it as a model feature is leakage, and it is
    retained only as a specification-curve comparison.

    The signal is **winsorised** at ``config.signal_clip`` robust SD units. A
    robust z-score of a series containing an epidemic excursion is heavily
    tailed — the post-Omicron collapse reaches −27 in these data — and ridge
    regression on the unclipped signal reaches R² of −4.5 while gradient
    boosting is essentially unaffected. Clipping is applied here, at the
    modelling boundary, so the region-week table keeps its unclipped values.
    """
    metric = metric or f"{config.primary_metric}_{config.signal_variant}"
    clip = config.signal_clip if clip is None else clip

    panel, report = join_panels(wbe_region_week, health_region_week, target=target, metric=metric)
    report["signal_metric"] = metric

    if clip and len(panel):
        outside = (panel["wbe_signal"].abs() > clip).sum()
        report["signal_clip"] = float(clip)
        report["rows_winsorised"] = int(outside)
        report["pct_winsorised"] = round(100.0 * outside / len(panel), 3)
        panel["wbe_signal"] = panel["wbe_signal"].clip(-clip, clip)
    counts = panel.groupby("region_code")["epiweek_end"].nunique()
    keep = counts[counts >= min_weeks_per_region].index
    filtered = panel[panel["region_code"].isin(keep)].copy()

    report["min_weeks_per_region"] = min_weeks_per_region
    report["regions_dropped_short_history"] = int(counts.shape[0] - len(keep))
    report["regions_retained"] = int(len(keep))
    report["rows_retained"] = int(len(filtered))
    return filtered, report
