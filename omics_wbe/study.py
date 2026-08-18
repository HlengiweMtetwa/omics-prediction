"""The full study: every objective, executed end to end.

Stage 1 (:mod:`omics_wbe.pipeline`) turns raw submissions into analysis panels.
This module is stage 2: it runs the analyses that answer the three research
objectives, writes every table and figure, and returns a result bundle the
report generator consumes.

Objective 1 - detection methodology
    Catalogue coverage, QC yield, censoring behaviour, multi-pathogen coverage,
    and a worked back-calculation for a non-communicable-disease marker.

Objective 2 - integration and prediction
    Wastewater-to-case alignment, lead-time correlation, forecast models under
    both validation protocols, and the incremental value of wastewater over
    routine clinical surveillance.

Objective 3 - actionable public health value
    Early-warning alarms, lead time, surge classification, decision-curve net
    benefit, and sensitivity of all of it to inputs and analysis choices.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from omics_wbe.biomarkers.catalog import default_catalog
from omics_wbe.config import (
    DEFAULT_CONFIG, AnalysisConfig, INTERIM_DIR, RESULTS_DIR, TABLES_DIR, ensure_dirs,
)
from omics_wbe.features.build import build_features, feature_columns, prepare_supervised
from omics_wbe.governance.ethics import apply_publication_policy, governance_statement
from omics_wbe.integrate.align import build_analysis_panel, coverage_table, lag_correlations
from omics_wbe.modeling import regression as R
from omics_wbe.modeling import sensitivity as S
from omics_wbe.modeling.classification import (
    classifier_zoo, evaluate_surge_classification, operating_points,
)
from omics_wbe.modeling.experiment import run_experiment
from omics_wbe.modeling.sensitivity import adaptive_splitter
from omics_wbe.modeling.validation import RollingOriginSplit
from omics_wbe.normalize.back_calculation import (
    ExcretionParameters, back_calculate, back_calculate_mc, parameters_from_catalog,
)
from omics_wbe.pipeline import run_stage_one
from omics_wbe.provenance import RunManifest
from omics_wbe.reporting import figures as F
from omics_wbe.surveillance.alerts import decision_curve, lead_time_analysis, surge_labels

PRIMARY_TARGET = "sars_cov_2"


def _table(frame: pd.DataFrame, name: str) -> str:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    path = TABLES_DIR / f"{name}.csv"
    frame.to_csv(path, index=False)
    return str(path)


# ---------------------------------------------------------------------------
# Objective 1
# ---------------------------------------------------------------------------

def objective_one(stage_one: dict[str, Any], config: AnalysisConfig) -> dict[str, Any]:
    catalog = default_catalog()
    region_week = pd.read_parquet(INTERIM_DIR / "wbe_region_week.parquet")
    site_week = pd.read_parquet(INTERIM_DIR / "wbe_site_week.parquet")
    reports = stage_one["wbe"].get("reports", {})

    out: dict[str, Any] = {
        "catalog_summary": catalog.summary(),
        "ingest": reports.get("ingest", {}),
        "harmonisation": reports.get("harmonise", {}),
        "qc": reports.get("qc", {}),
        "censoring": reports.get("censoring", {}),
        "standardisation": reports.get("standardisation", {}),
        "standardisation_causal": reports.get("standardisation_causal", {}),
        "site_week": reports.get("site_week", {}),
        "region_week": reports.get("region_week", {}),
        "tables": {}, "figures": {},
    }

    out["tables"]["biomarker_catalog"] = _table(catalog.to_table(), "biomarker_catalog")

    per_target = (
        site_week.groupby("target", as_index=False)
        .agg(site_weeks=("epiweek_end", "size"), sites=("site_id", "nunique"),
             weeks=("epiweek_end", "nunique"),
             mean_detect_fraction=("detect_fraction", "mean"),
             first_week=("epiweek_end", "min"), last_week=("epiweek_end", "max"))
        .sort_values("site_weeks", ascending=False)
    )
    out["tables"]["target_coverage"] = _table(per_target, "target_coverage")
    out["per_target_coverage"] = per_target.to_dict("records")

    if reports.get("qc"):
        out["figures"]["qc_waterfall"] = F.plot_qc_waterfall(reports["qc"])
    out["figures"]["target_coverage"] = F.plot_target_coverage(region_week)

    # Multi-pathogen co-behaviour: do the respiratory targets move together?
    wide = (
        region_week.pivot_table(index=["region_code", "epiweek_end"], columns="target",
                                values="log10_ratio_pmmov_z")
    )
    corr = wide.corr(method="spearman", min_periods=40)
    out["tables"]["pathogen_correlation"] = _table(corr.reset_index(), "pathogen_correlation")
    out["pathogen_correlation"] = corr.round(3).to_dict()

    out["back_calculation"] = _back_calculation_demo(config)
    out["governance"] = _governance(site_week, region_week, config)
    return out


def _back_calculation_demo(config: AnalysisConfig) -> dict[str, Any]:
    """Worked non-communicable-disease back-calculation, with its own limits attached.

    No metformin measurements were obtainable in this environment, so the input
    concentration is a stated scenario value, not a measurement. What the
    calculation demonstrates is the *method* and the size of its uncertainty —
    which is the finding: even with a literature-backed excretion fraction, the
    95% interval on treated prevalence spans more than a factor of three.
    """
    catalog = default_catalog()
    params = parameters_from_catalog("metformin", catalog, defined_daily_dose_mg=2000.0)

    scenario = {
        "influent_concentration_ng_per_L": 12_000.0,
        "flow_L_per_day": 50e6,
        "population_served": 250_000,
        "note": (
            "Scenario inputs, not measurements. Flow and population are typical of a "
            "medium municipal plant; the concentration is within the range reported for "
            "metformin in municipal influent. Substitute measured values to obtain an estimate."
        ),
    }
    point = back_calculate(
        scenario["influent_concentration_ng_per_L"], scenario["flow_L_per_day"],
        scenario["population_served"], params,
    )
    mc = back_calculate_mc(
        scenario["influent_concentration_ng_per_L"], scenario["flow_L_per_day"],
        scenario["population_served"], params, seed=config.seed,
    )

    refused = []
    for bid in ("cortisol_cortisone", "isoprostane_8_iso_pgf2a", "atorvastatin_ohmetabolites",
                "capecitabine_5fu", "antihypertensive_panel"):
        try:
            parameters_from_catalog(bid, catalog, defined_daily_dose_mg=1.0)
            refused.append({"biomarker_id": bid, "status": "parameters_available"})
        except Exception as exc:
            refused.append({"biomarker_id": bid, "status": "refused",
                            "reason": str(exc).split(". ")[0]})

    return {
        "scenario": scenario,
        "parameters": {
            "excretion_fraction": params.excretion_fraction,
            "bioavailability": params.bioavailability,
            "correction_factor": params.correction_factor,
            "defined_daily_dose_mg": params.defined_daily_dose_mg,
            "source": params.source,
        },
        "point_estimate": {k: (float(v) if np.isscalar(v) or getattr(v, "ndim", 1) == 0 else float(v))
                           for k, v in point.items()},
        "monte_carlo": mc,
        "markers_without_transferable_parameters": refused,
    }


def _governance(site_week: pd.DataFrame, region_week: pd.DataFrame,
                config: AnalysisConfig) -> dict[str, Any]:
    _, site_report = apply_publication_policy(site_week, config=config, level="site")
    _, region_report = apply_publication_policy(region_week, config=config, level="region")
    return {"statement": governance_statement(config),
            "site_level": site_report, "region_level": region_report}


# ---------------------------------------------------------------------------
# Objective 2
# ---------------------------------------------------------------------------

def objective_two(config: AnalysisConfig) -> dict[str, Any]:
    region_week = pd.read_parquet(INTERIM_DIR / "wbe_region_week.parquet")
    health_week = pd.read_parquet(INTERIM_DIR / "health_region_week.parquet")

    panel, join_report = build_analysis_panel(region_week, health_week, target=PRIMARY_TARGET,
                                              config=config)
    lag_df, lag_report = lag_correlations(panel)
    coverage = coverage_table(panel)

    out: dict[str, Any] = {
        "join": join_report, "lag": lag_report,
        "tables": {
            "panel_coverage": _table(coverage, "panel_coverage"),
            "lag_correlations": _table(lag_df, "lag_correlations"),
        },
        "figures": {
            "lag_correlation": F.plot_lag_correlation(lag_report["pooled_by_lag"]),
            "series": F.plot_series_examples(panel),
        },
    }

    experiments = {}
    for mode in ("delta", "level"):
        res = run_experiment(panel, config=config, target_mode=mode, label=PRIMARY_TARGET)
        experiments[mode] = {
            "summary": res["summary"], "optimism": res["optimism"],
            "comparisons": res["comparisons"], "conformal_coverage": res["conformal_coverage"],
            "paths": res["paths"],
        }
    out["experiments"] = experiments
    out["figures"]["model_skill"] = F.plot_model_skill(experiments["delta"]["summary"])
    out["figures"]["optimism"] = F.plot_validation_optimism(
        pd.concat([experiments["delta"]["optimism"].assign(target_mode="delta"),
                   experiments["level"]["optimism"].assign(target_mode="level")], ignore_index=True)
    )
    out["_panel"] = panel
    return out


# ---------------------------------------------------------------------------
# Objective 3
# ---------------------------------------------------------------------------

def objective_three(panel: pd.DataFrame, config: AnalysisConfig) -> dict[str, Any]:
    events, lead_report = lead_time_analysis(panel, config=config)

    labels = surge_labels(panel, horizon=2, growth_threshold=0.5)
    features, _ = build_features(panel, max_lag=config.max_lag_weeks, horizons=(1,),
                                 target_mode="delta")
    features = features.merge(labels[["region_code", "epiweek_end", "surge"]],
                              on=["region_code", "epiweek_end"], how="left")

    splitter = RollingOriginSplit(n_splits=config.n_cv_splits, test_weeks=13,
                                  gap_weeks=config.cv_gap_weeks, min_train_weeks=52)
    summaries, curves, predictions = [], [], {}
    for block, opts in R.FEATURE_BLOCKS.items():
        cols = feature_columns(features, **{"use_wbe": opts["use_wbe"], "use_ar": opts["use_ar"]})
        frame = features.dropna(subset=cols + ["surge", "wbe_lag0"])
        if len(frame) < 200:
            continue
        X = frame[cols]
        y = frame["surge"].astype(int)
        meta = frame[["region_code", "epiweek_end"]].reset_index(drop=True)
        preds, summary, info = evaluate_surge_classification(
            X, y, meta, splitter=splitter, estimators=classifier_zoo(config.seed)
        )
        if preds.empty:
            continue
        summary.insert(0, "block", block)
        summaries.append(summary)
        predictions[block] = preds
        curve = pd.DataFrame(info["decision_curves"]).assign(block=block)
        curves.append(curve)

    classification = pd.concat(summaries, ignore_index=True) if summaries else pd.DataFrame()
    curve_df = pd.concat(curves, ignore_index=True) if curves else pd.DataFrame()

    best_row = classification.sort_values("auprc", ascending=False).iloc[0] if len(classification) else None
    ops = pd.DataFrame()
    best_curve = pd.DataFrame()
    if best_row is not None:
        ops = operating_points(predictions[best_row["block"]], estimator=best_row["estimator"],
                               thresholds=(0.1, 0.15, 0.2, 0.3, 0.4))
        best_curve = curve_df[(curve_df["block"] == best_row["block"]) &
                              (curve_df["estimator"] == best_row["estimator"])]

    out: dict[str, Any] = {
        "lead_time": lead_report,
        "classification": classification.to_dict("records"),
        "best_alert_model": None if best_row is None else {
            "block": best_row["block"], "estimator": best_row["estimator"],
            "auroc": float(best_row["auroc"]), "auprc": float(best_row["auprc"]),
            "prevalence": float(best_row["prevalence"]),
            "auprc_lift_over_prevalence": float(best_row["auprc"] / best_row["prevalence"]),
        },
        "operating_points": ops.to_dict("records"),
        "net_benefit_positive_range": _net_benefit_range(best_curve),
        "tables": {
            "alert_events": _table(events, "alert_events"),
            "surge_classification": _table(classification, "surge_classification"),
            "operating_points": _table(ops, "alert_operating_points"),
            "decision_curves": _table(curve_df, "decision_curves"),
        },
        "figures": {},
    }
    if len(classification) and len(best_curve):
        out["figures"]["alerts"] = F.plot_alert_performance(classification, best_curve)
    return out


def _net_benefit_range(curve: pd.DataFrame) -> dict[str, Any]:
    if curve.empty:
        return {}
    positive = curve[curve["benefit_over_best_default"] > 0]
    return {
        "n_thresholds_tested": int(len(curve)),
        "n_thresholds_with_positive_net_benefit": int(len(positive)),
        "threshold_range": [float(positive["threshold"].min()), float(positive["threshold"].max())]
            if len(positive) else None,
        "max_benefit_over_best_default": float(curve["benefit_over_best_default"].max()),
    }


# ---------------------------------------------------------------------------
# Sensitivity
# ---------------------------------------------------------------------------

def sensitivity_analyses(panel: pd.DataFrame, config: AnalysisConfig) -> dict[str, Any]:
    features, _ = build_features(panel, max_lag=config.max_lag_weeks, horizons=(1,),
                                 target_mode="delta")
    X, y, meta = prepare_supervised(features, horizon=1, use_wbe=True, use_ar=True)
    splitter = RollingOriginSplit(n_splits=config.n_cv_splits, test_weeks=13,
                                  gap_weeks=config.cv_gap_weeks, min_train_weeks=52)
    factory = R.model_zoo(config.seed)["ridge"]

    permutation = S.permutation_importance_oof(
        X, y, meta, estimator_factory=factory, splitter=splitter, n_repeats=10, seed=config.seed
    )
    perturbation = S.input_perturbation(
        X, y, meta, estimator_factory=factory, splitter=splitter
    )
    measurement = S.measurement_uncertainty_mc(
        X, y, meta, estimator_factory=factory, splitter=splitter, n_draws=60, seed=config.seed
    )
    spec = _specification_curve(panel, config, splitter, factory)

    return {
        "permutation_importance": permutation.to_dict("records"),
        "input_perturbation": perturbation.to_dict("records"),
        "measurement_uncertainty": measurement,
        "specification_curve": spec.to_dict("records"),
        "tables": {
            "permutation_importance": _table(permutation, "sensitivity_permutation"),
            "input_perturbation": _table(perturbation, "sensitivity_perturbation"),
            "specification_curve": _table(spec, "sensitivity_specification"),
        },
        "figures": {
            "sensitivity": F.plot_sensitivity(permutation, perturbation),
            "specification": F.plot_specification_curve(spec),
        },
    }


def _specification_curve(panel, config, splitter, factory) -> pd.DataFrame:
    """Re-run the headline model under each defensible analysis choice."""
    region_week = pd.read_parquet(INTERIM_DIR / "wbe_region_week.parquet")
    health_week = pd.read_parquet(INTERIM_DIR / "health_region_week.parquet")

    variants: dict[str, pd.DataFrame] = {
        f"headline (causal z, clip +/-{config.signal_clip:g})": panel,
    }

    # The leakage comparison: identical pipeline, retrospective standardisation.
    retro, _ = build_analysis_panel(
        region_week, health_week, target=PRIMARY_TARGET, config=config,
        metric=f"{config.primary_metric}_z",
    )
    variants["retrospective z-score (leaks future data)"] = retro

    # How much the winsorisation limit matters, reported rather than assumed.
    for clip in (None, 10.0, 5.0):
        alt, _ = build_analysis_panel(region_week, health_week, target=PRIMARY_TARGET,
                                      config=config, clip=clip)
        label = "causal z, unclipped" if clip is None else f"causal z, clip +/-{clip:g}"
        variants[label] = alt

    strict, _ = build_analysis_panel(region_week, health_week, target=PRIMARY_TARGET,
                                     config=config, min_weeks_per_region=90)
    variants["counties with >=90 weeks only"] = strict

    variants["pre-Omicron only (to 2021-11)"] = panel[panel["epiweek_end"] < "2021-12-01"]
    variants["Omicron era only (2021-12 on)"] = panel[panel["epiweek_end"] >= "2021-12-01"]
    variants["region-weeks with >=2 sites"] = panel[panel["n_sites"] >= 2]

    rows = []
    for name, variant in variants.items():
        if variant is None or len(variant) < 200:
            rows.append({"specification": name, "n": int(len(variant) if variant is not None else 0),
                         "rmse": np.nan, "r2": np.nan, "spearman": np.nan,
                         "note": "insufficient rows"})
            continue
        try:
            feats, _ = build_features(variant, max_lag=config.max_lag_weeks, horizons=(1,),
                                      target_mode="delta")
            Xv, yv, mv = prepare_supervised(feats, horizon=1, use_wbe=True, use_ar=True)
            dates = mv["epiweek_end"].reset_index(drop=True)
            variant_splitter, settings = adaptive_splitter(int(dates.nunique()), splitter)
            if variant_splitter is None:
                rows.append({"specification": name, "n": int(len(Xv)), "rmse": np.nan,
                             "r2": np.nan, "spearman": np.nan,
                             "note": settings.get("reason", "no valid split")})
                continue
            preds, trues = [], []
            for tr, te in variant_splitter.split(dates):
                model = factory()
                model.fit(Xv.iloc[tr], yv.iloc[tr])
                preds.append(np.asarray(model.predict(Xv.iloc[te]), dtype=float))
                trues.append(np.asarray(yv.iloc[te], dtype=float))
            from omics_wbe.modeling.validation import regression_metrics
            metrics = regression_metrics(np.concatenate(trues), np.concatenate(preds))
            note = (
                f"reduced split: {settings['min_train_weeks']}wk train / "
                f"{settings['test_weeks']}wk test - not directly comparable to the headline"
                if settings.get("reduced") else ""
            )
            rows.append({"specification": name, **metrics, "note": note})
        except ValueError as exc:
            rows.append({"specification": name, "n": int(len(variant)), "rmse": np.nan,
                         "r2": np.nan, "spearman": np.nan, "note": str(exc)[:90]})
    return pd.DataFrame(rows).sort_values("rmse").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Second programme: Queensland
# ---------------------------------------------------------------------------

def queensland_analysis(config: AnalysisConfig) -> dict[str, Any]:
    path = INTERIM_DIR / "qld_site_week.parquet"
    if not path.exists():
        return {"available": False}
    weekly = pd.read_parquet(path)

    community = weekly[~weekly["is_subcatchment"]]
    bins = [0, 10_000, 50_000, 150_000, np.inf]
    labels = ["<10k", "10-50k", "50-150k", ">150k"]
    community = community.assign(
        size_band=pd.cut(community["population_served"], bins=bins, labels=labels)
    )
    by_band = community.groupby("size_band", observed=True, as_index=False).agg(
        sites=("site_id", "nunique"), site_weeks=("detect_fraction", "size"),
        mean_detect_fraction=("detect_fraction", "mean"),
    )
    return {
        "available": True,
        "n_sites": int(weekly["site_id"].nunique()),
        "n_subcatchment_sites": int(weekly.loc[weekly["is_subcatchment"], "site_id"].nunique()),
        "detection_by_catchment_size": by_band.to_dict("records"),
        "tables": {"qld_detection_by_size": _table(by_band, "qld_detection_by_size")},
        "figures": {"qld_detection": F.plot_urban_rural_detection(community)},
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_study(config: AnalysisConfig = DEFAULT_CONFIG, *, force: bool = False) -> dict[str, Any]:
    ensure_dirs()
    warnings.filterwarnings("ignore", category=FutureWarning)

    stage_one = run_stage_one(config, force=force)
    obj1 = objective_one(stage_one, config)
    obj2 = objective_two(config)
    panel = obj2.pop("_panel")
    obj3 = objective_three(panel, config)
    sens = sensitivity_analyses(panel, config)
    qld = queensland_analysis(config)

    results = {
        "config": config.to_dict(),
        "objective_1_detection": obj1,
        "objective_2_integration_prediction": obj2,
        "objective_3_public_health_value": obj3,
        "sensitivity": sens,
        "second_programme_queensland": qld,
    }

    serialisable = _to_serialisable(results)
    path = RESULTS_DIR / "study_results.json"
    path.write_text(json.dumps(serialisable, indent=2, default=str))

    manifest = RunManifest("05_study", config.to_dict())
    manifest.add_output("study_results", path)
    for section in (obj1, obj2, obj3, sens, qld):
        for label, fig in (section.get("figures") or {}).items():
            manifest.add_output(f"figure_{label}", fig)
        for label, tab in (section.get("tables") or {}).items():
            manifest.add_output(f"table_{label}", tab)
    manifest.add_metric("headline", headline_findings(results))
    manifest.write()

    results["_serialisable"] = serialisable
    return results


def _to_serialisable(obj: Any) -> Any:
    if isinstance(obj, pd.DataFrame):
        return obj.to_dict("records")
    if isinstance(obj, pd.Series):
        return obj.to_dict()
    if isinstance(obj, dict):
        return {str(k): _to_serialisable(v) for k, v in obj.items() if not str(k).startswith("_")}
    if isinstance(obj, (list, tuple)):
        return [_to_serialisable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return str(obj)
    return obj


def headline_findings(results: dict[str, Any]) -> dict[str, Any]:
    """The numbers the report leads with, extracted once so they cannot drift."""
    obj1 = results["objective_1_detection"]
    obj2 = results["objective_2_integration_prediction"]
    obj3 = results["objective_3_public_health_value"]

    delta = obj2["experiments"]["delta"]["summary"]
    if isinstance(delta, list):
        delta = pd.DataFrame(delta)
    h1 = delta[delta["horizon"] == 1]
    skill_col = next((c for c in h1.columns if c.startswith("skill_vs_")), None)

    def best(block):
        sel = h1[(h1["block"] == block) & (~h1["estimator"].str.startswith("baseline_"))]
        return sel.sort_values("rmse").iloc[0] if len(sel) else None

    out: dict[str, Any] = {
        "n_measurements_ingested": obj1["ingest"].get("rows_read"),
        "n_measurements_retained": obj1["qc"].get("n_pass"),
        "qc_pass_rate": obj1["qc"].get("pass_rate"),
        "n_biomarkers_in_catalog": obj1["catalog_summary"]["n_biomarkers"],
        "n_targets_measured": len(obj1.get("per_target_coverage", [])),
        "optimal_lead_weeks": obj2["lag"].get("best_lag_median_rho"),
        "peak_spearman": obj2["lag"].get("best_lag_value"),
        "n_counties_modelled": obj2["join"].get("regions_retained"),
    }
    for block in ("wbe", "ar", "wbe+ar"):
        row = best(block)
        if row is not None:
            out[f"h1_{block}_best_estimator"] = row["estimator"]
            out[f"h1_{block}_rmse"] = float(row["rmse"])
            out[f"h1_{block}_spearman"] = float(row["spearman"])
            if skill_col:
                out[f"h1_{block}_skill"] = float(row[skill_col])
    if obj3.get("best_alert_model"):
        out["alert"] = obj3["best_alert_model"]
    out["net_benefit"] = obj3.get("net_benefit_positive_range")
    out["median_lead_weeks_alarm"] = obj3["lead_time"]["summary"].get("median_lead_weeks")
    return out
