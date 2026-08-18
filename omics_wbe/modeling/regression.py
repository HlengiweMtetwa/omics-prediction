"""Nowcast and forecast models, evaluated under both validation protocols.

The scientific question is not "can a model predict case rates" — persistence
does that well — but "does the wastewater signal add anything to what routine
clinical surveillance already provides". Three feature blocks are therefore run
through an identical loop on identical rows:

``wbe``      wastewater only. Answers: could this stand in for case reporting?
``ar``       autoregressive clinical only. The incumbent.
``wbe+ar``   both. Its margin over ``ar`` is the incremental value of wastewater.

Prediction intervals come from *split conformal* calibration rather than from a
model's own variance estimate, because conformal coverage holds without
assuming the residuals are Gaussian, which these are not.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from omics_wbe.config import DEFAULT_CONFIG, AnalysisConfig
from omics_wbe.modeling.baselines import (
    BASELINE_REQUIREMENTS, BASELINES, BASELINES_BY_TARGET_MODE, DEFAULT_SKILL_BASELINE,
)
from omics_wbe.modeling.validation import (
    RollingOriginSplit, paired_bootstrap_delta, regression_metrics, skill_score,
)

FEATURE_BLOCKS: dict[str, dict[str, bool]] = {
    "wbe": {"use_wbe": True, "use_ar": False},
    "ar": {"use_wbe": False, "use_ar": True},
    "wbe+ar": {"use_wbe": True, "use_ar": True},
}


def model_zoo(seed: int = DEFAULT_CONFIG.seed) -> dict[str, Callable[[], Any]]:
    """Estimators spanning a linear, a bagged and a boosted learner.

    Ridge is scaled because its penalty is scale-dependent; the tree models are
    not, because they are invariant to monotone feature transforms and scaling
    them only obscures the feature values in any inspection of the fitted model.
    """
    return {
        "ridge": lambda: Pipeline([
            ("scale", StandardScaler()),
            ("model", RidgeCV(alphas=np.logspace(-3, 3, 25))),
        ]),
        "random_forest": lambda: RandomForestRegressor(
            n_estimators=400, min_samples_leaf=3, max_features="sqrt",
            random_state=seed, n_jobs=-1,
        ),
        "gradient_boosting": lambda: GradientBoostingRegressor(
            n_estimators=300, learning_rate=0.05, max_depth=3,
            subsample=0.8, random_state=seed,
        ),
    }


def _fit_predict(estimator, X_train, y_train, X_test) -> np.ndarray:
    estimator.fit(X_train, y_train)
    return np.asarray(estimator.predict(X_test), dtype=float)


def evaluate_rolling_origin(
    X: pd.DataFrame,
    y: pd.Series,
    meta: pd.DataFrame,
    *,
    splitter: RollingOriginSplit,
    estimators: dict[str, Callable[[], Any]],
    include_baselines: bool = True,
    target_mode: str = "delta",
    date_col: str = "epiweek_end",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fit every estimator on every fold. Returns out-of-fold predictions.

    Predictions are returned rather than only summary metrics so that skill,
    calibration, alerting and the paired bootstrap are all computed from the
    same out-of-fold values, not from separate re-runs.
    """
    dates = meta[date_col].reset_index(drop=True)
    X = X.reset_index(drop=True)
    y = pd.Series(np.asarray(y, dtype=float))

    candidates = dict(estimators)
    skipped_baselines = []
    if include_baselines:
        for name in BASELINES_BY_TARGET_MODE.get(target_mode, ("mean",)):
            needed = BASELINE_REQUIREMENTS.get(name, ())
            if any(col not in X.columns for col in needed):
                # e.g. a wastewater-only block has no clinical history, so a
                # persistence baseline cannot be built for it.
                skipped_baselines.append(name)
                continue
            candidates[f"baseline_{name}"] = BASELINES[name]

    records = []
    fold_info = []
    for fold, (train_idx, test_idx) in enumerate(splitter.split(dates)):
        X_tr, y_tr = X.iloc[train_idx], y.iloc[train_idx]
        X_te, y_te = X.iloc[test_idx], y.iloc[test_idx]
        fold_info.append({
            "fold": fold, "n_train": int(len(train_idx)), "n_test": int(len(test_idx)),
            "train_end": str(dates.iloc[train_idx].max().date()),
            "test_start": str(dates.iloc[test_idx].min().date()),
            "test_end": str(dates.iloc[test_idx].max().date()),
        })
        for name, factory in candidates.items():
            pred = _fit_predict(factory(), X_tr, y_tr, X_te)
            block = meta.iloc[test_idx].reset_index(drop=True)
            records.append(pd.DataFrame({
                "fold": fold, "estimator": name,
                "region_code": block["region_code"].values,
                date_col: block[date_col].values,
                "y_true": y_te.values, "y_pred": pred,
                "case_rate": block["case_rate"].values,
            }))

    predictions = pd.concat(records, ignore_index=True) if records else pd.DataFrame()
    return predictions, {
        "folds": fold_info, "n_folds": len(fold_info), "target_mode": target_mode,
        "estimators": sorted(candidates), "baselines_skipped": skipped_baselines,
    }


def summarise_predictions(
    predictions: pd.DataFrame, *, baseline: str | None = None, target_mode: str = "delta"
) -> pd.DataFrame:
    """Per-estimator metrics plus skill against the target mode's own baseline."""
    baseline = baseline or DEFAULT_SKILL_BASELINE.get(target_mode, "baseline_mean")
    if baseline not in set(predictions["estimator"]):
        baseline = "baseline_mean"
    rows = []
    base = predictions[predictions["estimator"] == baseline]
    base_rmse = regression_metrics(base["y_true"], base["y_pred"])["rmse"] if len(base) else np.nan

    for name, group in predictions.groupby("estimator"):
        metrics = regression_metrics(group["y_true"], group["y_pred"])
        metrics["estimator"] = name
        metrics["skill_vs_" + baseline.replace("baseline_", "")] = skill_score(metrics["rmse"], base_rmse)
        rows.append(metrics)

    return (
        pd.DataFrame(rows)
        .set_index("estimator")
        .sort_values("rmse")
        .reset_index()
    )


def evaluate_random_kfold(
    X: pd.DataFrame, y: pd.Series, *, estimators: dict[str, Callable[[], Any]],
    n_splits: int = 5, seed: int = DEFAULT_CONFIG.seed,
) -> pd.DataFrame:
    """The protocol the proposal specifies, run so its optimism can be measured.

    Random k-fold over an autocorrelated panel lets a model train on week t-1
    and test on week t for the same county. The resulting metrics are reported
    beside the rolling-origin metrics, never instead of them.
    """
    from sklearn.model_selection import KFold

    kf = KFold(n_splits=n_splits, shuffle=True, random_state=seed)
    X = X.reset_index(drop=True)
    y = pd.Series(np.asarray(y, dtype=float))

    rows = []
    for name, factory in estimators.items():
        preds = np.full(len(X), np.nan)
        for train_idx, test_idx in kf.split(X):
            preds[test_idx] = _fit_predict(factory(), X.iloc[train_idx], y.iloc[train_idx], X.iloc[test_idx])
        metrics = regression_metrics(y, preds)
        metrics["estimator"] = name
        rows.append(metrics)
    return pd.DataFrame(rows).set_index("estimator").reset_index()


def conformal_intervals(
    predictions: pd.DataFrame, *, alpha: float = 0.2, estimator: str | None = None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Split-conformal prediction intervals calibrated on earlier folds.

    Fold *k*'s interval width comes from the absolute residuals of folds
    ``< k``, so the calibration set always precedes the prediction in time. The
    first fold has no prior calibration data and is excluded from the coverage
    figure rather than being given an interval derived from its own residuals.
    """
    df = predictions if estimator is None else predictions[predictions["estimator"] == estimator]
    df = df.sort_values(["fold"]).reset_index(drop=True)

    out = []
    for fold in sorted(df["fold"].unique()):
        calibration = df[df["fold"] < fold]
        current = df[df["fold"] == fold].copy()
        if len(calibration) < 20:
            current["lower"] = np.nan
            current["upper"] = np.nan
            current["calibrated"] = False
        else:
            residuals = np.abs(calibration["y_true"] - calibration["y_pred"])
            n = len(residuals)
            level = min(1.0, np.ceil((n + 1) * (1 - alpha)) / n)
            q = float(np.quantile(residuals, level))
            current["lower"] = current["y_pred"] - q
            current["upper"] = current["y_pred"] + q
            current["calibrated"] = True
        out.append(current)

    result = pd.concat(out, ignore_index=True)
    covered = result[result["calibrated"]]
    inside = ((covered["y_true"] >= covered["lower"]) & (covered["y_true"] <= covered["upper"]))
    report = {
        "alpha": alpha,
        "nominal_coverage": 1 - alpha,
        "empirical_coverage": float(inside.mean()) if len(covered) else float("nan"),
        "n_calibrated": int(len(covered)),
        "median_interval_width": float((covered["upper"] - covered["lower"]).median()) if len(covered) else float("nan"),
    }
    return result, report


def compare_blocks(
    predictions_by_block: dict[str, pd.DataFrame], *, estimator: str,
    reference: str = "ar", challenger: str = "wbe+ar",
    date_col: str = "epiweek_end",
) -> dict[str, Any]:
    """Paired comparison of two feature blocks, on the rows they share.

    Joined on region and week rather than assumed row-aligned: the two blocks
    are built from the same supervised frame, but relying on that silently is
    how a paired test ends up comparing different weeks.
    """
    ref = predictions_by_block[reference]
    cha = predictions_by_block[challenger]
    ref = ref[ref["estimator"] == estimator][["region_code", date_col, "y_true", "y_pred"]]
    cha = cha[cha["estimator"] == estimator][["region_code", date_col, "y_pred"]]

    merged = ref.merge(cha, on=["region_code", date_col], suffixes=("_ref", "_cha"))
    boot = paired_bootstrap_delta(merged["y_true"], merged["y_pred_cha"], merged["y_pred_ref"])
    return {
        "estimator": estimator, "reference": reference, "challenger": challenger,
        "n_paired_rows": int(len(merged)),
        "rmse_reference": regression_metrics(merged["y_true"], merged["y_pred_ref"])["rmse"],
        "rmse_challenger": regression_metrics(merged["y_true"], merged["y_pred_cha"])["rmse"],
        **boot,
    }
