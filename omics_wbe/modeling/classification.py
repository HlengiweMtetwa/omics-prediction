"""Surge early-warning as a classification problem.

Regression on case rates answers "how many", but a health department acts on
"is this about to grow". That is a classification question, and it is evaluated
differently: discrimination (AUROC), performance in the rare-positive regime
that matters (AUPRC against prevalence), calibration (Brier), and finally
whether acting on the output beats acting on nothing or acting always
(decision-curve net benefit).

The same rolling-origin protocol as the regression models, with probabilities
produced strictly out-of-fold, so calibration and net benefit are measured on
predictions the model had not seen the answer to.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegressionCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from omics_wbe.config import DEFAULT_CONFIG
from omics_wbe.modeling.validation import RollingOriginSplit
from omics_wbe.surveillance.alerts import alarm_metrics, decision_curve


def classifier_zoo(seed: int = DEFAULT_CONFIG.seed, *, calibrate: bool = True) -> dict[str, Callable[[], Any]]:
    """Classifiers, calibrated by default.

    Tree ensembles rank well but their scores are not probabilities: a random
    forest that discriminates at AUROC 0.86 here still scored *worse than the
    base rate* on Brier, because its output clusters away from the true event
    frequency. Both quantities the decision curve needs — a probability
    threshold and a net benefit — are meaningless on an uncalibrated score, so
    each tree model is wrapped in an isotonic calibration fitted by
    cross-validation *inside the training fold only*. The calibrator never sees
    the test block.

    Logistic regression is left uncalibrated; it optimises log-loss directly and
    is already close to calibrated.
    """
    def wrap(factory: Callable[[], Any]) -> Callable[[], Any]:
        if not calibrate:
            return factory
        return lambda: CalibratedClassifierCV(factory(), method="isotonic", cv=3)

    return {
        "logistic": lambda: Pipeline([
            ("scale", StandardScaler()),
            ("model", LogisticRegressionCV(Cs=10, cv=3, max_iter=2000, scoring="neg_log_loss")),
        ]),
        "random_forest": wrap(lambda: RandomForestClassifier(
            n_estimators=400, min_samples_leaf=5, max_features="sqrt",
            random_state=seed, n_jobs=-1, class_weight="balanced_subsample",
        )),
        "gradient_boosting": wrap(lambda: GradientBoostingClassifier(
            n_estimators=250, learning_rate=0.05, max_depth=3, subsample=0.8, random_state=seed,
        )),
    }


def evaluate_surge_classification(
    X: pd.DataFrame,
    y: pd.Series,
    meta: pd.DataFrame,
    *,
    splitter: RollingOriginSplit,
    estimators: dict[str, Callable[[], Any]] | None = None,
    date_col: str = "epiweek_end",
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Out-of-fold surge probabilities, per-estimator metrics and decision curves."""
    estimators = estimators or classifier_zoo()
    dates = meta[date_col].reset_index(drop=True)
    X = X.reset_index(drop=True)
    y = pd.Series(np.asarray(y, dtype=int)).reset_index(drop=True)

    records, folds = [], []
    for fold, (train_idx, test_idx) in enumerate(splitter.split(dates)):
        y_tr = y.iloc[train_idx]
        folds.append({
            "fold": fold, "n_train": int(len(train_idx)), "n_test": int(len(test_idx)),
            "train_positive_rate": float(y_tr.mean()),
            "test_positive_rate": float(y.iloc[test_idx].mean()),
        })
        if y_tr.nunique() < 2:
            continue  # a fold with one class cannot train a classifier
        for name, factory in estimators.items():
            model = factory()
            model.fit(X.iloc[train_idx], y_tr)
            prob = model.predict_proba(X.iloc[test_idx])[:, 1]
            block = meta.iloc[test_idx].reset_index(drop=True)
            records.append(pd.DataFrame({
                "fold": fold, "estimator": name,
                "region_code": block["region_code"].values,
                date_col: block[date_col].values,
                "y_true": y.iloc[test_idx].values, "y_prob": prob,
            }))

    predictions = pd.concat(records, ignore_index=True) if records else pd.DataFrame()
    if predictions.empty:
        return predictions, pd.DataFrame(), {"folds": folds, "note": "no fold could be trained"}

    summary = pd.DataFrame([
        {"estimator": name, **alarm_metrics(g["y_true"], g["y_prob"])}
        for name, g in predictions.groupby("estimator")
    ]).sort_values("auprc", ascending=False).reset_index(drop=True)

    curves = []
    for name, g in predictions.groupby("estimator"):
        curve = decision_curve(g["y_true"], g["y_prob"])
        curve.insert(0, "estimator", name)
        curves.append(curve)
    curves_df = pd.concat(curves, ignore_index=True)

    return predictions, summary, {
        "folds": folds,
        "decision_curves": curves_df.to_dict("records"),
        "best_by_auprc": summary.iloc[0]["estimator"],
    }


def operating_points(
    predictions: pd.DataFrame, *, estimator: str, thresholds: tuple[float, ...] = (0.2, 0.3, 0.4, 0.5)
) -> pd.DataFrame:
    """Confusion-matrix quantities at candidate alert thresholds.

    What a health department needs in order to choose a threshold: how many
    alerts per 100 region-weeks, what fraction are real, and what fraction of
    real surges are caught.
    """
    g = predictions[predictions["estimator"] == estimator]
    rows = []
    for t in thresholds:
        alert = g["y_prob"] >= t
        tp = int(((alert) & (g["y_true"] == 1)).sum())
        fp = int(((alert) & (g["y_true"] == 0)).sum())
        fn = int(((~alert) & (g["y_true"] == 1)).sum())
        tn = int(((~alert) & (g["y_true"] == 0)).sum())
        rows.append({
            "threshold": t, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / (tp + fp) if tp + fp else np.nan,
            "recall": tp / (tp + fn) if tp + fn else np.nan,
            "specificity": tn / (tn + fp) if tn + fp else np.nan,
            "alerts_per_100_region_weeks": 100.0 * (tp + fp) / len(g) if len(g) else np.nan,
        })
    return pd.DataFrame(rows)
