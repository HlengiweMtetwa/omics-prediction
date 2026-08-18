"""Operational surveillance view: the analysis outputs as a decision surface.

The proposal's public health outcome is an "enhanced surveillance system ...
allowing real-time monitoring and rapid response". A report answers "what did we
learn"; this module answers the question a health department actually asks on a
Monday morning — *which catchments need attention this week, and how confident
should I be?*

Three properties matter more than the presentation.

**Governance is applied before anything is shown.** The dashboard consumes
:func:`omics_wbe.governance.ethics.apply_publication_policy` output, not the raw
panel, so a catchment below the population floor cannot reach a screen. A
suppression control that a dashboard can bypass is not a control.

**Status is computed causally.** Every level uses only data up to the week being
scored, so a status shown for week *t* is one the system could genuinely have
produced at week *t*. Back-filling a dashboard with hindsight makes it look far
more useful than it is.

**Staleness is a status, not a gap.** A catchment that stopped reporting three
weeks ago is not "normal"; it is unknown, and it is reported as ``no_recent_data``.
Treating silence as reassurance is the failure mode this guards against.

One asymmetry is deliberate. Status is computed on the **winsorised** signal
while :func:`target_timeseries` returns the signal **unwinsorised** for display.
A control limit built from an expanding standard deviation is permanently
desensitised by a single deep excursion — San Francisco's post-Omicron collapse
reaches −10 robust SD in these data, which would raise that catchment's alarm
threshold for the remainder of the series. Clipping the input to the control
chart prevents that. The chart a human reads should still show the real
excursion, so the display is not clipped.

The data here is a retrospective research extract, not a live feed.
:attr:`SurveillanceSnapshot.as_of` is the latest week *in the data*, and
:attr:`SurveillanceSnapshot.is_live` is always ``False``. Any deployment reading
a live feed must set that honestly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from omics_wbe.biomarkers.catalog import BiomarkerCatalog, default_catalog
from omics_wbe.config import AnalysisConfig, DEFAULT_CONFIG, INTERIM_DIR, RESULTS_DIR
from omics_wbe.governance.ethics import apply_publication_policy
from omics_wbe.surveillance.alerts import ewma_alarms

#: Ordered worst-first, so a sort on this ordering surfaces what needs attention.
STATUS_ORDER = ("alert", "watch", "normal", "no_recent_data", "insufficient_history")

STATUS_DESCRIPTIONS = {
    "alert": "Signal above the control limit and rising: escalate.",
    "watch": "Signal elevated against this catchment's own recent history.",
    "normal": "Signal within the range this catchment normally shows.",
    "no_recent_data": "No sample within the staleness window. Status unknown, not reassuring.",
    "insufficient_history": "Too little history in this catchment to set a control limit.",
}


@dataclass
class RegionStatus:
    region_code: str
    target: str
    status: str
    signal: float | None
    trend_4wk: float | None
    weeks_since_last_report: int | None
    percentile_in_own_history: float | None
    n_sites: int
    population_covered: float | None
    detect_fraction: float | None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class SurveillanceSnapshot:
    """Everything the dashboard renders, computed once."""

    as_of: pd.Timestamp
    is_live: bool
    statuses: pd.DataFrame
    coverage: dict[str, Any]
    suppression: dict[str, Any]
    targets: list[str]
    config: dict[str, Any] = field(default_factory=dict)

    def needing_attention(self) -> pd.DataFrame:
        return self.statuses[self.statuses["status"].isin(("alert", "watch"))]

    def status_counts(self) -> dict[str, int]:
        counts = self.statuses["status"].value_counts().to_dict()
        return {s: int(counts.get(s, 0)) for s in STATUS_ORDER}


def _classify(
    series: pd.Series,
    *,
    config: AnalysisConfig,
    min_history: int,
    watch_percentile: float,
) -> tuple[str, float | None, float | None]:
    """Status, percentile and 4-week trend for one catchment-target series.

    ``series`` must be indexed by week, ascending, and end at the week being
    scored — the control limit is computed from prior weeks only, inside
    :func:`ewma_alarms`.

    The control chart runs on the winsorised series so that one deep excursion
    cannot inflate the expanding standard deviation and desensitise the alarm
    for every week after it. The reported signal, percentile and trend are taken
    from the unclipped values, which are what a reader should see.
    """
    clean = series.dropna()
    if len(clean) < min_history:
        return "insufficient_history", None, None

    limit = config.signal_clip
    for_chart = series.clip(-limit, limit) if limit else series
    chart = ewma_alarms(for_chart, lam=config.ewma_lambda,
                        sigma_multiple=config.alert_sigma, burn_in=min_history)
    latest = clean.iloc[-1]
    percentile = float((clean < latest).mean())
    trend = float(latest - clean.iloc[-5]) if len(clean) >= 5 else None

    alarm = bool(chart["alarm"].iloc[-1])
    rising = trend is not None and trend > 0
    if alarm and rising:
        status = "alert"
    elif alarm or percentile >= watch_percentile:
        status = "watch"
    else:
        status = "normal"
    return status, percentile, trend


def build_snapshot(
    region_week: pd.DataFrame,
    *,
    config: AnalysisConfig = DEFAULT_CONFIG,
    metric: str | None = None,
    as_of: pd.Timestamp | str | None = None,
    staleness_weeks: int = 3,
    min_history: int = 12,
    watch_percentile: float = 0.90,
    apply_governance: bool = True,
) -> SurveillanceSnapshot:
    """Compute the current surveillance picture across every catchment and target.

    ``as_of`` defaults to the latest week present in the data. Passing an earlier
    week reconstructs the view the system would have shown then — which is how
    the status logic is tested, and how a programme can audit a past decision.
    """
    metric = metric or f"{config.primary_metric}_{config.signal_variant}"
    df = region_week.copy()
    df["epiweek_end"] = pd.to_datetime(df["epiweek_end"])

    suppression: dict[str, Any] = {"applied": apply_governance}
    if apply_governance:
        df, suppression = apply_publication_policy(df, config=config, level="region")
        suppression["applied"] = True

    as_of = pd.Timestamp(as_of) if as_of is not None else df["epiweek_end"].max()
    df = df[df["epiweek_end"] <= as_of]

    rows: list[RegionStatus] = []
    for (region, target), group in df.groupby(["region_code", "target"], sort=True):
        g = group.sort_values("epiweek_end").set_index("epiweek_end")
        if metric not in g.columns:
            continue
        full = pd.date_range(g.index.min(), as_of, freq=config.week_anchor)
        series = g[metric].reindex(full)

        observed = series.dropna()
        if observed.empty:
            continue
        weeks_since = int((as_of - observed.index[-1]).days // 7)

        if weeks_since > staleness_weeks:
            status, percentile, trend = "no_recent_data", None, None
            signal = None
        else:
            status, percentile, trend = _classify(
                series, config=config, min_history=min_history,
                watch_percentile=watch_percentile,
            )
            signal = float(observed.iloc[-1])

        latest_row = g.iloc[-1]
        rows.append(RegionStatus(
            region_code=str(region), target=str(target), status=status, signal=signal,
            trend_4wk=trend, weeks_since_last_report=weeks_since,
            percentile_in_own_history=percentile,
            n_sites=int(latest_row.get("n_sites", 0) or 0),
            population_covered=_maybe_float(latest_row.get("population_covered")),
            detect_fraction=_maybe_float(latest_row.get("detect_fraction")),
        ))

    statuses = pd.DataFrame([r.to_dict() for r in rows])
    if not statuses.empty:
        statuses["status_rank"] = statuses["status"].map(
            {s: i for i, s in enumerate(STATUS_ORDER)}
        )
        statuses = statuses.sort_values(
            ["status_rank", "target", "region_code"]
        ).drop(columns="status_rank").reset_index(drop=True)

    coverage = {
        "n_regions": int(df["region_code"].nunique()),
        "n_targets": int(df["target"].nunique()),
        "population_covered": _population_covered(df, as_of),
        "latest_week": str(as_of.date()),
        "weeks_of_history": int(df["epiweek_end"].nunique()),
    }

    return SurveillanceSnapshot(
        as_of=as_of,
        is_live=False,  # retrospective research extract; a live deployment must set this
        statuses=statuses,
        coverage=coverage,
        suppression=suppression,
        targets=sorted(df["target"].unique()),
        config={"metric": metric, "staleness_weeks": staleness_weeks,
                "min_history": min_history, "watch_percentile": watch_percentile,
                "ewma_lambda": config.ewma_lambda, "alert_sigma": config.alert_sigma},
    )


def _maybe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out


def _population_covered(df: pd.DataFrame, as_of: pd.Timestamp) -> float | None:
    """Population under surveillance in the most recent week, not double-counted."""
    recent = df[df["epiweek_end"] == as_of]
    if recent.empty or "population_covered" not in recent:
        return None
    per_region = recent.groupby("region_code")["population_covered"].max()
    total = float(per_region.sum())
    return total if total > 0 else None


def target_timeseries(
    region_week: pd.DataFrame,
    *,
    target: str,
    regions: list[str] | None = None,
    metric: str | None = None,
    config: AnalysisConfig = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """Wide week × region frame for one target, for plotting."""
    metric = metric or f"{config.primary_metric}_{config.signal_variant}"
    df = region_week[region_week["target"] == target].copy()
    if regions:
        df = df[df["region_code"].isin(regions)]
    df["epiweek_end"] = pd.to_datetime(df["epiweek_end"])
    return df.pivot_table(index="epiweek_end", columns="region_code", values=metric).sort_index()


def pathogen_activity(
    region_week: pd.DataFrame,
    *,
    config: AnalysisConfig = DEFAULT_CONFIG,
    metric: str | None = None,
    weeks: int = 8,
    as_of: pd.Timestamp | str | None = None,
) -> pd.DataFrame:
    """Recent activity per pathogen: where each target sits against its own history.

    Cross-pathogen comparison of the raw metric would be meaningless — the
    targets have different shedding rates, assays and detection limits — so each
    is expressed as a percentile within its own historical distribution.
    """
    metric = metric or f"{config.primary_metric}_{config.signal_variant}"
    df = region_week.copy()
    df["epiweek_end"] = pd.to_datetime(df["epiweek_end"])
    as_of = pd.Timestamp(as_of) if as_of is not None else df["epiweek_end"].max()
    window_start = as_of - pd.Timedelta(weeks=weeks)

    rows = []
    for target, group in df.groupby("target"):
        history = group[metric].dropna()
        recent = group[(group["epiweek_end"] > window_start) &
                       (group["epiweek_end"] <= as_of)][metric].dropna()
        if history.empty or recent.empty:
            continue
        recent_mean = float(recent.mean())
        rows.append({
            "target": target,
            "recent_mean": recent_mean,
            "percentile_of_own_history": float((history < recent_mean).mean()),
            "n_region_weeks_recent": int(len(recent)),
            "n_regions_reporting": int(group[(group["epiweek_end"] > window_start)]
                                       ["region_code"].nunique()),
            "mean_detect_fraction": float(
                group[(group["epiweek_end"] > window_start)]["detect_fraction"].mean()
            ) if "detect_fraction" in group else np.nan,
        })
    return (
        pd.DataFrame(rows)
        .sort_values("percentile_of_own_history", ascending=False)
        .reset_index(drop=True)
    )


def model_performance_card(results_path: Path | str | None = None) -> dict[str, Any]:
    """The honest performance summary a dashboard must show beside any forecast.

    A surveillance screen that displays a prediction without its measured skill
    invites the reader to trust it more than the evidence supports.
    """
    import json

    path = Path(results_path) if results_path else RESULTS_DIR / "study_results.json"
    if not path.exists():
        return {"available": False,
                "reason": f"{path} not found; run `python -m omics_wbe.cli run`"}

    results = json.loads(path.read_text())
    obj2 = results.get("objective_2_integration_prediction", {})
    obj3 = results.get("objective_3_public_health_value", {})

    classification = pd.DataFrame(obj3.get("classification", []))
    best_alert = (
        classification.sort_values("auprc", ascending=False).iloc[0].to_dict()
        if not classification.empty else {}
    )
    ar_only = (
        classification[classification["block"] == "ar"].sort_values("auprc", ascending=False)
        .iloc[0].to_dict() if not classification.empty
        and (classification["block"] == "ar").any() else {}
    )

    return {
        "available": True,
        "lead_weeks": obj2.get("lag", {}).get("best_lag_median_rho"),
        "lead_correlation": obj2.get("lag", {}).get("best_lag_value"),
        "surge_auprc": best_alert.get("auprc"),
        "surge_auroc": best_alert.get("auroc"),
        "surge_base_rate": best_alert.get("prevalence"),
        "surge_block": best_alert.get("block"),
        "clinical_only_auprc": ar_only.get("auprc"),
        "operating_points": obj3.get("operating_points", []),
        "net_benefit": obj3.get("net_benefit_positive_range", {}),
        "median_alarm_lead_weeks": obj3.get("lead_time", {}).get("summary", {}).get("median_lead_weeks"),
        "caveats": [
            "The signal predicts direction of change, not absolute case counts.",
            "Never publish a wastewater value as a case number.",
            "Lead time is county-specific; the pooled figure is not a local guarantee.",
            "Reported-case comparators are affected by changes in testing behaviour.",
        ],
    }


def catalog_view(catalog: BiomarkerCatalog | None = None) -> pd.DataFrame:
    """Catalogue entries a dashboard may display, with prospective markers marked.

    Prospective markers are shown rather than hidden — the open question is part
    of the scientific record — but flagged so nobody reads one as a finding.
    """
    catalog = catalog or default_catalog()
    table = catalog.to_table()
    table["usable_for_inference"] = table["biomarker_id"].map(catalog.inference_ready)
    return table


def load_region_week(path: Path | str | None = None) -> pd.DataFrame | None:
    """Load the analysis panel, or ``None`` if the pipeline has not been run."""
    path = Path(path) if path else INTERIM_DIR / "wbe_region_week.parquet"
    return pd.read_parquet(path) if path.exists() else None
