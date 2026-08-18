"""Baselines every model must beat to be worth anything.

A forecast of next week's case rate that is not better than "same as last week"
is not a forecast. These are implemented with the scikit-learn estimator
interface so they run through the identical validation loop as the real models,
on identical rows — the only way the comparison means anything.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin


class PersistenceBaseline(BaseEstimator, RegressorMixin):
    """Predict the most recent observed clinical value (``ar_lag1``).

    The standard reference for short-horizon epidemic forecasting, and a
    demanding one: weekly case rates are strongly autocorrelated.
    """

    def __init__(self, column: str = "ar_lag1"):
        self.column = column

    def fit(self, X, y=None):
        self.fallback_ = float(np.nanmean(np.asarray(y, dtype=float))) if y is not None else 0.0
        return self

    def predict(self, X):
        if isinstance(X, pd.DataFrame) and self.column in X.columns:
            return np.asarray(X[self.column], dtype=float)
        raise ValueError(f"PersistenceBaseline needs the {self.column!r} column")


class DriftBaseline(BaseEstimator, RegressorMixin):
    """Last value plus its most recent week-on-week change: a linear extrapolation."""

    def __init__(self, level_column: str = "ar_lag1", delta_column: str = "ar_delta1", damping: float = 1.0):
        self.level_column = level_column
        self.delta_column = delta_column
        self.damping = damping

    def fit(self, X, y=None):
        return self

    def predict(self, X):
        level = np.asarray(X[self.level_column], dtype=float)
        delta = np.asarray(X[self.delta_column], dtype=float)
        return level + self.damping * np.nan_to_num(delta)


class MeanBaseline(BaseEstimator, RegressorMixin):
    """Training-set mean. The floor: any model below this has negative skill."""

    def fit(self, X, y):
        self.mean_ = float(np.nanmean(np.asarray(y, dtype=float)))
        return self

    def predict(self, X):
        return np.full(len(X), self.mean_, dtype=float)


class NoChangeBaseline(BaseEstimator, RegressorMixin):
    """Predict zero change.

    The correct reference for a ``delta`` target, and the only baseline that
    needs no clinical history — so it is the one baseline a wastewater-only
    model can actually be scored against.
    """

    def fit(self, X, y=None):
        return self

    def predict(self, X):
        return np.zeros(len(X), dtype=float)


class MomentumBaseline(BaseEstimator, RegressorMixin):
    """Predict that this week's change repeats. The ``delta`` analogue of drift."""

    def __init__(self, column: str = "ar_delta1"):
        self.column = column

    def fit(self, X, y=None):
        return self

    def predict(self, X):
        return np.nan_to_num(np.asarray(X[self.column], dtype=float))


BASELINES = {
    "persistence": PersistenceBaseline,
    "drift": DriftBaseline,
    "mean": MeanBaseline,
    "nochange": NoChangeBaseline,
    "momentum": MomentumBaseline,
}

#: Which baselines are meaningful for which target. A persistence baseline
#: scored against a *change* target predicts a level where a difference is
#: expected, and produces a meaningless RMSE of ~3 with R^2 of -133. Gating them
#: here keeps nonsense numbers out of the results tables entirely.
BASELINES_BY_TARGET_MODE: dict[str, tuple[str, ...]] = {
    "level": ("persistence", "drift", "mean"),
    "delta": ("nochange", "momentum", "mean"),
    "region_z": ("nochange", "mean"),
}

#: Columns a baseline needs present in X before it can be run at all.
BASELINE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "persistence": ("ar_lag1",),
    "drift": ("ar_lag1", "ar_delta1"),
    "momentum": ("ar_delta1",),
    "nochange": (),
    "mean": (),
}

#: The reference each target mode's skill score is computed against.
DEFAULT_SKILL_BASELINE: dict[str, str] = {
    "level": "baseline_persistence",
    "delta": "baseline_nochange",
    "region_z": "baseline_nochange",
}
