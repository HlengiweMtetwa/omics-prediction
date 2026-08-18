"""The modelling experiment: every horizon x feature block x estimator.

Answers three questions in one pass, from one set of out-of-fold predictions:

1. Does the wastewater signal carry usable information about community case
   burden? (``wbe`` block versus the mean baseline.)
2. Does it add anything to routine clinical surveillance? (``wbe+ar`` versus
   ``ar``, paired bootstrap on shared rows.)
3. How much does the proposal's stated random k-fold protocol overstate
   performance on these data? (rolling-origin versus random k-fold.)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from omics_wbe.config import DEFAULT_CONFIG, AnalysisConfig, RESULTS_DIR, TABLES_DIR, ensure_dirs
from omics_wbe.features.build import build_features, prepare_supervised
from omics_wbe.modeling import regression as R
from omics_wbe.modeling.validation import RollingOriginSplit
from omics_wbe.provenance import RunManifest


def run_experiment(
    panel: pd.DataFrame,
    *,
    config: AnalysisConfig = DEFAULT_CONFIG,
    horizons: tuple[int, ...] | None = None,
    primary_estimator: str = "ridge",
    signal_col: str = "wbe_signal",
    label: str = "sars_cov_2",
    target_mode: str = "delta",
) -> dict[str, Any]:
    ensure_dirs()
    horizons = horizons or tuple(config.forecast_horizons)
    features, feature_report = build_features(
        panel, signal_col=signal_col, max_lag=config.max_lag_weeks, horizons=horizons,
        target_mode=target_mode,
    )
    splitter = RollingOriginSplit(
        n_splits=config.n_cv_splits, test_weeks=13,
        gap_weeks=config.cv_gap_weeks, min_train_weeks=52,
    )
    zoo = R.model_zoo(config.seed)

    summaries: list[dict[str, Any]] = []
    kfold_rows: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    all_predictions: list[pd.DataFrame] = []
    fold_reports: dict[str, Any] = {}

    for horizon in horizons:
        preds_by_block: dict[str, pd.DataFrame] = {}
        for block, opts in R.FEATURE_BLOCKS.items():
            X, y, meta = prepare_supervised(features, horizon=horizon, **opts)
            if len(X) < 100:
                continue
            preds, info = R.evaluate_rolling_origin(
                X, y, meta, splitter=splitter, estimators=zoo, target_mode=target_mode
            )
            preds_by_block[block] = preds
            fold_reports[f"h{horizon}_{block}"] = info

            summary = R.summarise_predictions(preds, target_mode=target_mode)
            summary.insert(0, "block", block)
            summary.insert(0, "horizon", horizon)
            summaries.append(summary)

            kf = R.evaluate_random_kfold(X, y, estimators=zoo, n_splits=config.n_cv_splits, seed=config.seed)
            kf.insert(0, "block", block)
            kf.insert(0, "horizon", horizon)
            kfold_rows.append(kf)

            preds = preds.assign(horizon=horizon, block=block)
            all_predictions.append(preds)

            intervals, cov = R.conformal_intervals(
                preds, alpha=config.conformal_alpha, estimator=primary_estimator
            )
            cov.update({"horizon": horizon, "block": block, "estimator": primary_estimator})
            coverage.append(cov)

        if {"ar", "wbe+ar"} <= preds_by_block.keys():
            cmp = R.compare_blocks(preds_by_block, estimator=primary_estimator,
                                   reference="ar", challenger="wbe+ar")
            cmp["horizon"] = horizon
            comparisons.append(cmp)
        if {"wbe", "ar"} <= preds_by_block.keys():
            cmp2 = R.compare_blocks(preds_by_block, estimator=primary_estimator,
                                    reference="ar", challenger="wbe")
            cmp2["horizon"] = horizon
            comparisons.append(cmp2)

    summary_df = pd.concat(summaries, ignore_index=True) if summaries else pd.DataFrame()
    kfold_df = pd.concat(kfold_rows, ignore_index=True) if kfold_rows else pd.DataFrame()
    predictions_df = pd.concat(all_predictions, ignore_index=True) if all_predictions else pd.DataFrame()

    optimism = _optimism_table(summary_df, kfold_df)

    paths = _write_outputs(f"{label}_{target_mode}", summary_df, kfold_df, optimism,
                           predictions_df, comparisons, coverage)

    manifest = RunManifest(f"04_model_experiment_{label}_{target_mode}", config.to_dict())
    for name, path in paths.items():
        manifest.add_output(name, path)
    manifest.add_metric("features", feature_report)
    manifest.add_metric("folds", fold_reports)
    manifest.add_metric("block_comparisons", comparisons)
    manifest.add_metric("conformal_coverage", coverage)
    manifest.note(
        "Rolling-origin CV is the reported protocol. Random k-fold results are included only to "
        "quantify the optimism it introduces on autocorrelated panel data."
    )
    manifest_path = manifest.write()

    return {
        "summary": summary_df,
        "kfold": kfold_df,
        "optimism": optimism,
        "predictions": predictions_df,
        "comparisons": comparisons,
        "conformal_coverage": coverage,
        "target_mode": target_mode,
        "feature_report": feature_report,
        "fold_reports": fold_reports,
        "paths": {**paths, "manifest": str(manifest_path)},
    }


def _optimism_table(rolling: pd.DataFrame, kfold: pd.DataFrame) -> pd.DataFrame:
    """RMSE under each protocol, and the ratio between them."""
    if rolling.empty or kfold.empty:
        return pd.DataFrame()
    keys = ["horizon", "block", "estimator"]
    merged = rolling[keys + ["rmse", "r2"]].merge(
        kfold[keys + ["rmse", "r2"]], on=keys, suffixes=("_rolling_origin", "_random_kfold")
    )
    merged["rmse_ratio_kfold_over_rolling"] = merged["rmse_random_kfold"] / merged["rmse_rolling_origin"]
    merged["r2_inflation_kfold_minus_rolling"] = merged["r2_random_kfold"] - merged["r2_rolling_origin"]
    return merged.sort_values(keys).reset_index(drop=True)


def _write_outputs(label, summary, kfold, optimism, predictions, comparisons, coverage) -> dict[str, str]:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for name, frame in (
        ("model_summary", summary), ("model_kfold", kfold),
        ("model_optimism", optimism), ("model_predictions", predictions),
    ):
        if frame is None or frame.empty:
            continue
        path = TABLES_DIR / f"{label}_{name}.csv"
        frame.to_csv(path, index=False)
        paths[name] = str(path)

    extra = RESULTS_DIR / f"{label}_model_diagnostics.json"
    extra.write_text(json.dumps(
        {"block_comparisons": comparisons, "conformal_coverage": coverage}, indent=2, default=str
    ))
    paths["diagnostics"] = str(extra)
    return paths
