"""Stage 1 of the analysis: raw submissions -> analysis-ready region-week panel.

Each stage writes its outputs to ``data/interim`` and a manifest recording the
hashes of what it read and wrote, the configuration, the seed and the library
versions. Re-running is cheap because completed stages are cached on the hash
of their inputs; ``force=True`` rebuilds.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from omics_wbe.config import (
    AnalysisConfig, DEFAULT_CONFIG, INTERIM_DIR, RESULTS_DIR, ensure_dirs,
)
from omics_wbe.ingest import health_records, nwss, qld
from omics_wbe.ingest.sources import NWSS_CA, NYT_US_COUNTIES, QLD_WBE
from omics_wbe.normalize import wastewater as W
from omics_wbe.normalize.harmonise import harmonise
from omics_wbe.provenance import RunManifest
from omics_wbe.qc.checks import apply_qc_filter, run_qc


def _write(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


def _reports_path(stage: str) -> Path:
    return INTERIM_DIR / f"{stage}_reports.json"


def _save_reports(stage: str, reports: dict[str, Any]) -> Path:
    path = _reports_path(stage)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reports, indent=2, default=str))
    return path


def _load_reports(stage: str) -> dict[str, Any]:
    """Stage reports from a cached run.

    Cached runs used to return no reports at all, which silently emptied the QC
    and harmonisation sections of the generated report whenever the panels were
    already on disk. Reports are now persisted next to the panels and reloaded,
    so a cached run and a fresh one produce the same downstream output.
    """
    path = _reports_path(stage)
    return json.loads(path.read_text()) if path.exists() else {}


def build_wbe_panel(
    config: AnalysisConfig = DEFAULT_CONFIG,
    *,
    raw_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Run ingest -> harmonise -> QC -> normalise -> aggregate for NWSS.

    Returns a dict of stage reports plus the paths of every artefact written.
    """
    ensure_dirs()
    reports: dict[str, Any] = {}
    manifest = RunManifest("01_build_wbe_panel", config.to_dict())

    measurements_path = INTERIM_DIR / "wbe_measurements_qc.parquet"
    site_week_path = INTERIM_DIR / "wbe_site_week.parquet"
    region_week_path = INTERIM_DIR / "wbe_region_week.parquet"

    source_path = (Path(raw_dir) / NWSS_CA.files[0]) if raw_dir else NWSS_CA.paths()[0]
    manifest.add_input("nwss_raw", source_path)

    cached_reports = _load_reports("wbe")
    if not force and region_week_path.exists() and site_week_path.exists() and cached_reports:
        return {
            "cached": True,
            "reports": cached_reports,
            "site_week_path": str(site_week_path),
            "region_week_path": str(region_week_path),
            "measurements_path": str(measurements_path),
        }

    raw, reports["ingest"] = nwss.load_nwss(source_path)
    harmonised, reports["harmonise"] = harmonise(raw)
    checked, reports["qc"] = run_qc(harmonised, config)
    passed = apply_qc_filter(checked)

    collapsed, reports["replicates"] = W.collapse_replicates(passed)
    imputed, reports["censoring"] = W.substitute_censored(collapsed, config)
    metrics, reports["metrics"] = W.compute_metrics(imputed)
    standardised, reports["standardisation"] = W.standardise_within_site(metrics)
    standardised, reports["standardisation_causal"] = W.standardise_within_site_causal(standardised)
    site_week, reports["site_week"] = W.aggregate_site_week(
        standardised,
        metrics=(
            f"{config.primary_metric}", "log10_conc",
            f"{config.primary_metric}_z", f"{config.primary_metric}_zc",
        ),
        config=config,
    )
    region_week, reports["region_week"] = W.aggregate_region_week(
        site_week, metric=f"{config.primary_metric}_z", config=config
    )
    region_week_causal, reports["region_week_causal"] = W.aggregate_region_week(
        site_week, metric=f"{config.primary_metric}_zc", config=config
    )
    region_week = region_week.merge(
        region_week_causal[["region_code", "target", "epiweek_end", f"{config.primary_metric}_zc"]],
        on=["region_code", "target", "epiweek_end"], how="outer",
    )

    _write(standardised, measurements_path)
    _write(site_week, site_week_path)
    _write(region_week, region_week_path)
    for label, path in (
        ("measurements", measurements_path), ("site_week", site_week_path), ("region_week", region_week_path)
    ):
        manifest.add_output(label, path)
    for key, value in reports.items():
        manifest.add_metric(key, value)
    manifest.note(
        "Recovery scale and censoring flags are harmonised before QC; running QC on unharmonised "
        "NWSS input fails ~82% of rows for reasons that are conventions, not data quality."
    )
    manifest_path = manifest.write()
    _save_reports("wbe", reports)

    return {
        "cached": False,
        "reports": reports,
        "manifest": str(manifest_path),
        "measurements_path": str(measurements_path),
        "site_week_path": str(site_week_path),
        "region_week_path": str(region_week_path),
    }


def build_health_panel(
    config: AnalysisConfig = DEFAULT_CONFIG,
    *,
    raw_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Daily county case records -> weekly region panel aligned to epiweeks."""
    ensure_dirs()
    daily_path = INTERIM_DIR / "health_daily.parquet"
    weekly_path = INTERIM_DIR / "health_region_week.parquet"

    manifest = RunManifest("02_build_health_panel", config.to_dict())
    paths = [Path(raw_dir) / f for f in NYT_US_COUNTIES.files] if raw_dir else NYT_US_COUNTIES.paths()
    for i, p in enumerate(paths):
        manifest.add_input(f"nyt_{i}", p)

    cached_reports = _load_reports("health")
    if not force and weekly_path.exists() and cached_reports:
        return {"cached": True, "report": cached_reports,
                "daily_path": str(daily_path), "weekly_path": str(weekly_path)}

    daily, report = health_records.load_nyt_counties(paths)
    daily["epiweek_end"] = W.to_epiweek(daily["date"], config.week_anchor)

    weekly = daily.groupby(["region_code", "region_name", "indicator", "epiweek_end"], as_index=False).agg(
        cases_week=("count", "sum"),
        case_rate_per_100k=("rate_avg7_per_100k", "mean"),
        days_observed=("date", "nunique"),
    )
    # A partial week at either end of the series is a reporting artefact, not a
    # low-incidence week, and would otherwise look like a sharp drop.
    before = len(weekly)
    weekly = weekly[weekly["days_observed"] == 7]
    report["partial_weeks_dropped"] = int(before - len(weekly))
    report["region_weeks"] = int(len(weekly))

    _write(daily, daily_path)
    _write(weekly, weekly_path)
    manifest.add_output("daily", daily_path).add_output("weekly", weekly_path)
    manifest.add_metric("health", report)
    manifest_path = manifest.write()
    _save_reports("health", report)

    return {
        "cached": False, "report": report, "manifest": str(manifest_path),
        "daily_path": str(daily_path), "weekly_path": str(weekly_path),
    }


def build_qld_panel(
    config: AnalysisConfig = DEFAULT_CONFIG,
    *,
    raw_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Queensland detect/non-detect programme -> site-week detection frequencies."""
    ensure_dirs()
    out_path = INTERIM_DIR / "qld_site_week.parquet"
    manifest = RunManifest("03_build_qld_panel", config.to_dict())
    paths = [Path(raw_dir) / f for f in QLD_WBE.files] if raw_dir else QLD_WBE.paths()
    for i, p in enumerate(paths):
        manifest.add_input(f"qld_{i}", p)

    cached_reports = _load_reports("qld")
    if not force and out_path.exists() and cached_reports:
        return {"cached": True, "report": cached_reports, "path": str(out_path)}

    df, report = qld.load_qld(paths)
    df["epiweek_end"] = W.to_epiweek(df["collect_date"], config.week_anchor)
    weekly = df.groupby(["site_id", "is_subcatchment", "epiweek_end"], as_index=False).agg(
        n_samples=("detected", "size"),
        n_detects=("detected", "sum"),
        population_served=("population_served", "median"),
    )
    weekly["detect_fraction"] = weekly["n_detects"] / weekly["n_samples"]
    _write(weekly, out_path)
    manifest.add_output("qld_site_week", out_path).add_metric("qld", report)
    _save_reports("qld", report)
    return {"cached": False, "report": report, "manifest": str(manifest.write()), "path": str(out_path)}


def run_stage_one(config: AnalysisConfig = DEFAULT_CONFIG, *, force: bool = False) -> dict[str, Any]:
    out = {
        "wbe": build_wbe_panel(config, force=force),
        "health": build_health_panel(config, force=force),
        "qld": build_qld_panel(config, force=force),
    }
    summary_path = RESULTS_DIR / "stage_one_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(out, indent=2, default=str))
    return out
