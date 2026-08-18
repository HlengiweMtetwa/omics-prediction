"""Sensitivity analysis: which inputs and which analysis choices drive the result.

The proposal asks for "sensitivity analyses ... to determine how different
inputs affect the outcomes of the models". Three distinct things go under that
heading and they answer different questions, so all three are here:

**Feature sensitivity** (:func:`permutation_importance_oof`) — which features the
fitted model actually relies on, measured on held-out folds. Measured on
training data it would mostly report which features the model overfitted.

**Input sensitivity** (:func:`input_perturbation`, :func:`measurement_uncertainty_mc`)
— how much the prediction moves when the wastewater measurement is wrong by a
plausible amount. This is the question a laboratory cares about: is it worth
halving analytical variability?

**Specification sensitivity** (:func:`specification_curve`) — how much the
conclusion moves when defensible analysis choices are made differently. This is
the largest and least often reported source of uncertainty, and the one a
reviewer is entitled to ask about.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd

from omics_wbe.config import DEFAULT_CONFIG
from omics_wbe.modeling.validation import RollingOriginSplit, regression_metrics


def permutation_importance_oof(
    X: pd.DataFrame,
    y: pd.Series,
    meta: pd.DataFrame,
    *,
    estimator_factory: Callable[[], Any],
    splitter: RollingOriginSplit,
    n_repeats: int = 10,
    seed: int = DEFAULT_CONFIG.seed,
    date_col: str = "epiweek_end",
) -> pd.DataFrame:
    """Permutation importance computed on each fold's *test* rows.

    Importance is the increase in RMSE when one feature is shuffled. Permuting
    within the test block preserves the fold's own difficulty, so importances
    are comparable across folds.
    """
    rng = np.random.default_rng(seed)
    dates = meta[date_col].reset_index(drop=True)
    X = X.reset_index(drop=True)
    y = pd.Series(np.asarray(y, dtype=float))

    records = []
    for fold, (train_idx, test_idx) in enumerate(splitter.split(dates)):
        model = estimator_factory()
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        X_te, y_te = X.iloc[test_idx], y.iloc[test_idx]
        base_rmse = regression_metrics(y_te, model.predict(X_te))["rmse"]

        for column in X.columns:
            deltas = []
            for _ in range(n_repeats):
                shuffled = X_te.copy()
                shuffled[column] = rng.permutation(shuffled[column].to_numpy())
                deltas.append(regression_metrics(y_te, model.predict(shuffled))["rmse"] - base_rmse)
            records.append({
                "fold": fold, "feature": column,
                "rmse_increase_mean": float(np.mean(deltas)),
                "rmse_increase_sd": float(np.std(deltas, ddof=1)) if n_repeats > 1 else 0.0,
                "base_rmse": base_rmse,
            })

    df = pd.DataFrame(records)
    return (
        df.groupby("feature", as_index=False)
        .agg(rmse_increase=("rmse_increase_mean", "mean"),
             rmse_increase_sd=("rmse_increase_mean", "std"),
             relative_increase=("rmse_increase_mean", "mean"))
        .assign(relative_increase=lambda d: d["rmse_increase"] / df["base_rmse"].mean())
        .sort_values("rmse_increase", ascending=False)
        .reset_index(drop=True)
    )


def input_perturbation(
    X: pd.DataFrame,
    y: pd.Series,
    meta: pd.DataFrame,
    *,
    estimator_factory: Callable[[], Any],
    splitter: RollingOriginSplit,
    columns: list[str] | None = None,
    shifts: tuple[float, ...] = (-1.0, -0.5, -0.25, 0.25, 0.5, 1.0),
    date_col: str = "epiweek_end",
) -> pd.DataFrame:
    """One-at-a-time perturbation of the wastewater inputs.

    Shifts are additive in units of the standardised signal (so ``0.5`` is half
    a robust SD of that site's own history), because the primary metric is a
    z-score and a percentage change of a z-score is not interpretable.

    The model is *not* refitted: the question is how a deployed model responds
    to a mis-measured input, not how it would have been trained on different data.
    """
    columns = columns or [c for c in X.columns if c.startswith("wbe_")]
    dates = meta[date_col].reset_index(drop=True)
    X = X.reset_index(drop=True)
    y = pd.Series(np.asarray(y, dtype=float))

    rows = []
    for fold, (train_idx, test_idx) in enumerate(splitter.split(dates)):
        model = estimator_factory()
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        X_te, y_te = X.iloc[test_idx], y.iloc[test_idx]
        base_pred = np.asarray(model.predict(X_te), dtype=float)
        base_rmse = regression_metrics(y_te, base_pred)["rmse"]

        for shift in shifts:
            shifted = X_te.copy()
            for column in columns:
                shifted[column] = shifted[column] + shift
            pred = np.asarray(model.predict(shifted), dtype=float)
            rows.append({
                "fold": fold, "shift": shift,
                "mean_prediction_change": float(np.mean(pred - base_pred)),
                "mean_abs_prediction_change": float(np.mean(np.abs(pred - base_pred))),
                "rmse": regression_metrics(y_te, pred)["rmse"],
                "rmse_change": regression_metrics(y_te, pred)["rmse"] - base_rmse,
            })

    return (
        pd.DataFrame(rows)
        .groupby("shift", as_index=False)
        .agg(mean_prediction_change=("mean_prediction_change", "mean"),
             mean_abs_prediction_change=("mean_abs_prediction_change", "mean"),
             mean_rmse=("rmse", "mean"),
             mean_rmse_change=("rmse_change", "mean"))
        .sort_values("shift")
        .reset_index(drop=True)
    )


def measurement_uncertainty_mc(
    X: pd.DataFrame,
    y: pd.Series,
    meta: pd.DataFrame,
    *,
    estimator_factory: Callable[[], Any],
    splitter: RollingOriginSplit,
    noise_sd: float = 0.3,
    n_draws: int = 200,
    seed: int = DEFAULT_CONFIG.seed,
    date_col: str = "epiweek_end",
) -> dict[str, Any]:
    """Propagate analytical measurement noise into prediction error.

    Gaussian noise of ``noise_sd`` (in standardised-signal units) is added to
    every wastewater feature of every test row, ``n_draws`` times, and the model
    is scored on each draw. The spread of the resulting RMSE inflation is the
    part of forecast error attributable to analytical variability alone.

    Inflation is computed **per fold, against that fold's own baseline**, and
    only then pooled. Folds differ substantially in difficulty here, so pooling
    raw RMSEs across folds and comparing their median to the mean of the fold
    baselines mixes two different distributions — and produced the nonsensical
    result that adding noise *improved* accuracy by 17%.
    """
    rng = np.random.default_rng(seed)
    dates = meta[date_col].reset_index(drop=True)
    X = X.reset_index(drop=True)
    y = pd.Series(np.asarray(y, dtype=float))
    wbe_cols = [c for c in X.columns if c.startswith("wbe_")]

    per_fold: list[dict[str, Any]] = []
    inflations: list[float] = []
    relative: list[float] = []

    for fold, (train_idx, test_idx) in enumerate(splitter.split(dates)):
        model = estimator_factory()
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        X_te, y_te = X.iloc[test_idx], y.iloc[test_idx]
        base = regression_metrics(y_te, model.predict(X_te))["rmse"]

        fold_draws = np.empty(n_draws)
        for i in range(n_draws):
            noisy = X_te.copy()
            noise = rng.normal(0.0, noise_sd, size=(len(noisy), len(wbe_cols)))
            noisy[wbe_cols] = noisy[wbe_cols].to_numpy() + noise
            fold_draws[i] = regression_metrics(y_te, model.predict(noisy))["rmse"]

        inflations.extend((fold_draws - base).tolist())
        relative.extend(((fold_draws - base) / base).tolist())
        per_fold.append({
            "fold": fold, "baseline_rmse": base,
            "perturbed_rmse_median": float(np.median(fold_draws)),
            "median_inflation": float(np.median(fold_draws) - base),
        })

    inflation = np.asarray(inflations, dtype=float)
    rel = np.asarray(relative, dtype=float)
    baseline_mean = float(np.mean([f["baseline_rmse"] for f in per_fold]))
    return {
        "noise_sd_standardised_units": noise_sd,
        "n_draws_per_fold": n_draws,
        "n_folds": len(per_fold),
        "baseline_rmse_mean_across_folds": baseline_mean,
        "median_rmse_inflation": float(np.median(inflation)),
        "rmse_inflation_ci95": [float(np.percentile(inflation, 2.5)),
                                float(np.percentile(inflation, 97.5))],
        "median_relative_inflation": float(np.median(rel)),
        "relative_inflation_ci95": [float(np.percentile(rel, 2.5)),
                                    float(np.percentile(rel, 97.5))],
        "fraction_of_draws_worse_than_baseline": float(np.mean(inflation > 0)),
        "per_fold": per_fold,
    }


def adaptive_splitter(
    n_weeks: int, base: RollingOriginSplit
) -> tuple[RollingOriginSplit | None, dict[str, Any]]:
    """A splitter that fits ``n_weeks`` of history, or ``None`` if none can.

    Era-restricted specifications (pre-Omicron, Omicron-only) are genuinely
    shorter than the full panel and cannot support 52 training weeks plus a
    13-week test block. Rather than reporting them as NaN with no explanation,
    the split settings are shrunk to fit and the settings actually used are
    returned, so the reader can see that such a row is not directly comparable
    to the headline.
    """
    for min_train, test_weeks in (
        (base.min_train_weeks, base.test_weeks), (40, 13), (30, 10), (24, 8), (20, 6)
    ):
        if n_weeks >= min_train + base.gap_weeks + test_weeks:
            splitter = RollingOriginSplit(
                n_splits=base.n_splits, test_weeks=test_weeks,
                gap_weeks=base.gap_weeks, min_train_weeks=min_train,
            )
            settings = {
                "min_train_weeks": min_train, "test_weeks": test_weeks,
                "gap_weeks": base.gap_weeks,
                "reduced": min_train != base.min_train_weeks or test_weeks != base.test_weeks,
            }
            return splitter, settings
    return None, {"reduced": True, "reason": f"only {n_weeks} distinct weeks available"}


def specification_curve(
    panel_variants: dict[str, pd.DataFrame],
    *,
    build_features_fn: Callable,
    prepare_fn: Callable,
    estimator_factory: Callable[[], Any],
    splitter: RollingOriginSplit,
    horizon: int = 1,
    target_mode: str = "delta",
    use_wbe: bool = True,
    use_ar: bool = True,
) -> pd.DataFrame:
    """Re-run the headline model under each defensible analysis specification.

    ``panel_variants`` maps a specification name to the panel it produces, e.g.
    a panel built with retrospective standardisation versus causal, or with QC
    warnings retained versus dropped. If the headline conclusion survives every
    variant it is robust; if it does not, the reader is entitled to know which
    choice it depended on.
    """
    rows = []
    for name, panel in panel_variants.items():
        features, _ = build_features_fn(panel, horizons=(horizon,), target_mode=target_mode)
        X, y, meta = prepare_fn(features, horizon=horizon, use_wbe=use_wbe, use_ar=use_ar)
        if len(X) < 100:
            rows.append({"specification": name, "n": int(len(X)), "rmse": np.nan,
                         "r2": np.nan, "spearman": np.nan, "note": "insufficient rows"})
            continue

        preds, trues = [], []
        for train_idx, test_idx in splitter.split(meta["epiweek_end"].reset_index(drop=True)):
            model = estimator_factory()
            model.fit(X.iloc[train_idx], y.iloc[train_idx])
            preds.append(np.asarray(model.predict(X.iloc[test_idx]), dtype=float))
            trues.append(np.asarray(y.iloc[test_idx], dtype=float))

        metrics = regression_metrics(np.concatenate(trues), np.concatenate(preds))
        rows.append({"specification": name, **metrics, "note": ""})

    return pd.DataFrame(rows).sort_values("rmse").reset_index(drop=True)
