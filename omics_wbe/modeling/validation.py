"""Validation protocol: rolling-origin CV, and what random k-fold costs.

The proposal specifies k-fold cross-validation. For a panel of overlapping
weekly time series that is the wrong protocol, and quantifiably so: with lagged
features and autocorrelated targets, a random fold puts week *t-1* of a county
in the training set and week *t* in the test set, so the model is scored on a
week it has effectively already seen.

Rather than silently substituting a different protocol, this module implements
both, and the analysis reports both. The gap between them is the *optimism* of
random k-fold on these data — a result worth publishing in its own right, since
it is the difference between a model that looks deployable and one that is.

:class:`RollingOriginSplit` is the honest protocol: train on the past, leave a
gap at least as long as the longest feature lag, test on the future.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class RollingOriginSplit:
    """Expanding-window splits over a shared date axis in a panel.

    Parameters
    ----------
    n_splits:
        Number of successive test blocks.
    test_weeks:
        Length of each test block, in weeks.
    gap_weeks:
        Weeks discarded between the end of training and the start of testing.
        Must be at least the longest feature lag: without it, a training row at
        the boundary contains lagged values drawn from the test period.
    min_train_weeks:
        The first split will not be produced until this much history exists.
    """

    n_splits: int = 5
    test_weeks: int = 13
    gap_weeks: int = 4
    min_train_weeks: int = 52

    def split(self, dates: pd.Series) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        dates = pd.to_datetime(pd.Series(dates).reset_index(drop=True))
        unique = np.sort(dates.unique())
        n_weeks = len(unique)

        needed = self.min_train_weeks + self.gap_weeks + self.test_weeks
        if n_weeks < needed:
            raise ValueError(
                f"need at least {needed} distinct weeks for these split settings, got {n_weeks}"
            )

        last_start = n_weeks - self.test_weeks
        first_start = self.min_train_weeks + self.gap_weeks
        if self.n_splits == 1:
            starts = [last_start]
        else:
            starts = np.unique(np.linspace(first_start, last_start, self.n_splits).astype(int))

        for start in starts:
            test_weeks = unique[start:start + self.test_weeks]
            train_cutoff = unique[start - self.gap_weeks - 1]
            train_idx = np.flatnonzero(dates.values <= train_cutoff)
            test_idx = np.flatnonzero(np.isin(dates.values, test_weeks))
            if len(train_idx) == 0 or len(test_idx) == 0:
                continue
            yield train_idx, test_idx

    def describe(self, dates: pd.Series) -> list[dict[str, Any]]:
        dates = pd.to_datetime(pd.Series(dates).reset_index(drop=True))
        out = []
        for i, (tr, te) in enumerate(self.split(dates)):
            out.append({
                "fold": i,
                "n_train": int(len(tr)), "n_test": int(len(te)),
                "train_end": str(dates.iloc[tr].max().date()),
                "test_start": str(dates.iloc[te].min().date()),
                "test_end": str(dates.iloc[te].max().date()),
            })
        return out


def regression_metrics(y_true, y_pred) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    ok = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true, y_pred = y_true[ok], y_pred[ok]
    if len(y_true) < 2:
        return {"n": int(len(y_true)), "rmse": float("nan"), "mae": float("nan"),
                "r2": float("nan"), "spearman": float("nan"), "bias": float("nan")}

    resid = y_pred - y_true
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    rho = stats.spearmanr(y_true, y_pred).statistic if np.std(y_pred) > 0 else np.nan
    return {
        "n": int(len(y_true)),
        "rmse": float(np.sqrt(np.mean(resid ** 2))),
        "mae": float(np.mean(np.abs(resid))),
        "r2": float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan"),
        "spearman": float(rho) if rho == rho else float("nan"),
        "bias": float(np.mean(resid)),
    }


def skill_score(model_rmse: float, baseline_rmse: float) -> float:
    """Fractional RMSE reduction against a baseline. 0 = no better; 1 = perfect.

    Negative means the model is worse than the baseline, which is the outcome
    that matters most and the one an R² reported on its own will hide.
    """
    if not np.isfinite(baseline_rmse) or baseline_rmse <= 0:
        return float("nan")
    return float(1.0 - model_rmse / baseline_rmse)


def paired_bootstrap_delta(
    y_true, pred_a, pred_b, *, n_boot: int = 2000, seed: int = 20240501
) -> dict[str, float]:
    """Bootstrap CI for the RMSE difference between two models on the same rows.

    Paired, because both models are evaluated on identical test rows; an
    unpaired comparison would attribute shared fold-difficulty variation to the
    models.
    """
    y_true = np.asarray(y_true, dtype=float)
    a = np.asarray(pred_a, dtype=float)
    b = np.asarray(pred_b, dtype=float)
    ok = np.isfinite(y_true) & np.isfinite(a) & np.isfinite(b)
    y_true, a, b = y_true[ok], a[ok], b[ok]

    rng = np.random.default_rng(seed)
    n = len(y_true)
    if n < 10:
        return {"delta_rmse": float("nan"), "ci95_low": float("nan"), "ci95_high": float("nan"),
                "p_a_better": float("nan")}

    def rmse(t, p):
        return float(np.sqrt(np.mean((p - t) ** 2)))

    observed = rmse(y_true, a) - rmse(y_true, b)
    deltas = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        deltas[i] = rmse(y_true[idx], a[idx]) - rmse(y_true[idx], b[idx])
    return {
        "delta_rmse": observed,
        "ci95_low": float(np.percentile(deltas, 2.5)),
        "ci95_high": float(np.percentile(deltas, 97.5)),
        "p_a_better": float(np.mean(deltas < 0)),
    }
