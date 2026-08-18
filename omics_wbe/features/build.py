"""Feature construction for the predictive models.

Everything here is *causal by construction*: a feature for week ``t`` uses only
data timestamped at or before ``t``. That is enforced two ways — series are
reindexed onto a complete weekly calendar before any shift, so a missing week
never silently changes what a lag means, and every rolling statistic is
computed on already-lagged values.

Feature blocks are separated because the scientific question is not "how well
can we predict cases" but "what does wastewater add to what clinical
surveillance already knows". Answering that needs the wastewater block and the
autoregressive block to be switchable independently.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

WBE_PREFIX = "wbe_"
AR_PREFIX = "ar_"


def _complete_weekly(group: pd.DataFrame, date_col: str) -> pd.DataFrame:
    g = group.set_index(date_col).sort_index()
    full = pd.date_range(g.index.min(), g.index.max(), freq="W-SAT")
    return g.reindex(full).rename_axis(date_col)


def build_features(
    panel: pd.DataFrame,
    *,
    signal_col: str = "wbe_signal",
    target_col: str = "log_case_rate",
    group_col: str = "region_code",
    date_col: str = "epiweek_end",
    max_lag: int = 4,
    horizons: tuple[int, ...] = (0, 1, 2),
    target_mode: str = "level",
    region_z_min_periods: int = 8,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build lagged wastewater and autoregressive features plus horizon targets.

    Returns a long frame with one row per region-week and columns:

    * ``wbe_lag0..N``       - the wastewater signal at t, t-1, ... t-N
    * ``wbe_roll3_mean``    - 3-week mean of the signal up to and including t
    * ``wbe_delta1``        - week-on-week change in the signal
    * ``wbe_slope3``        - least-squares slope over the last 3 weeks
    * ``wbe_missing_frac``  - fraction of the lag window that was unobserved
    * ``ar_lag1..N``        - log case rate at t-1, ... t-N (never t)
    * ``y_h{h}``            - log case rate at t+h, the prediction targets

    ``ar_lag0`` deliberately does not exist. The clinical value at week ``t`` is
    the thing being predicted at horizon 0; including it would produce a model
    that reports its own input back with an R² near 1.
    """
    if target_mode not in {"level", "delta", "region_z"}:
        raise ValueError(
            f"unknown target_mode {target_mode!r}; expected one of level, delta, region_z"
        )

    frames = []
    for region, group in panel.groupby(group_col):
        g = _complete_weekly(group[[date_col, signal_col, target_col, "case_rate_per_100k"]], date_col)
        out = pd.DataFrame(index=g.index)
        out[group_col] = region

        signal = g[signal_col]
        for lag in range(0, max_lag + 1):
            out[f"{WBE_PREFIX}lag{lag}"] = signal.shift(lag)

        out[f"{WBE_PREFIX}roll3_mean"] = signal.rolling(3, min_periods=2).mean()
        out[f"{WBE_PREFIX}roll3_std"] = signal.rolling(3, min_periods=2).std()
        out[f"{WBE_PREFIX}delta1"] = signal.diff(1)
        out[f"{WBE_PREFIX}delta2"] = signal.diff(2)
        out[f"{WBE_PREFIX}slope3"] = signal.rolling(3, min_periods=3).apply(_slope, raw=True)
        out[f"{WBE_PREFIX}missing_frac"] = (
            signal.isna().rolling(max_lag + 1, min_periods=1).mean()
        )

        clinical = g[target_col]
        for lag in range(1, max_lag + 1):
            out[f"{AR_PREFIX}lag{lag}"] = clinical.shift(lag)
        out[f"{AR_PREFIX}delta1"] = clinical.shift(1) - clinical.shift(2)
        out[f"{AR_PREFIX}roll3_mean"] = clinical.shift(1).rolling(3, min_periods=2).mean()

        # Every target mode is anchored on t-1, the last value observable when a
        # forecast for t+h is issued.
        anchor = clinical.shift(1)
        past_mean = anchor.expanding(min_periods=region_z_min_periods).mean()
        past_sd = anchor.expanding(min_periods=region_z_min_periods).std().replace(0, np.nan)

        for h in horizons:
            future = clinical.shift(-h)
            out[f"y_level_h{h}"] = future
            if target_mode == "level":
                out[f"y_h{h}"] = future
            elif target_mode == "delta":
                out[f"y_h{h}"] = future - anchor
            else:
                out[f"y_h{h}"] = (future - past_mean) / past_sd
            out[f"case_rate_h{h}"] = g["case_rate_per_100k"].shift(-h)

        out["case_rate"] = g["case_rate_per_100k"]
        frames.append(out.reset_index())

    features = pd.concat(frames, ignore_index=True).sort_values([date_col, group_col]).reset_index(drop=True)

    report = {
        "rows": int(len(features)),
        "regions": int(features[group_col].nunique()),
        "target_mode": target_mode,
        "max_lag": max_lag,
        "horizons": list(horizons),
        "wbe_feature_columns": [c for c in features.columns if c.startswith(WBE_PREFIX)],
        "ar_feature_columns": [c for c in features.columns if c.startswith(AR_PREFIX)],
        "date_min": str(features[date_col].min().date()),
        "date_max": str(features[date_col].max().date()),
    }
    return features, report


def _slope(window: np.ndarray) -> float:
    if np.isnan(window).any():
        return np.nan
    x = np.arange(len(window), dtype=float)
    return float(np.polyfit(x, window, 1)[0])


def feature_columns(features: pd.DataFrame, *, use_wbe: bool = True, use_ar: bool = True) -> list[str]:
    cols = []
    if use_wbe:
        cols += sorted(c for c in features.columns if c.startswith(WBE_PREFIX))
    if use_ar:
        cols += sorted(c for c in features.columns if c.startswith(AR_PREFIX))
    return cols


def prepare_supervised(
    features: pd.DataFrame,
    *,
    horizon: int = 1,
    use_wbe: bool = True,
    use_ar: bool = True,
    date_col: str = "epiweek_end",
    group_col: str = "region_code",
    required_signal: str = "wbe_lag0",
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Assemble ``(X, y, meta)`` for one horizon and feature-block combination.

    Rows are kept only where the target and the current wastewater observation
    both exist, *including for the autoregressive-only model*. Letting the
    AR-only baseline train on weeks the wastewater model cannot see would make
    the comparison between them meaningless — they must be scored on identical
    rows.
    """
    y_col = f"y_h{horizon}"
    cols = feature_columns(features, use_wbe=use_wbe, use_ar=use_ar)
    needed = [c for c in (y_col, required_signal) if c in features.columns]

    frame = features.dropna(subset=needed)
    # Remaining feature NaNs come from short leading windows; drop rather than
    # impute, so no model is scored on a value that was invented for it.
    frame = frame.dropna(subset=cols)

    meta_cols = [group_col, date_col, "case_rate", f"case_rate_h{horizon}"]
    if f"y_level_h{horizon}" in frame.columns:
        meta_cols.append(f"y_level_h{horizon}")
    if "ar_lag1" in frame.columns:
        meta_cols.append("ar_lag1")
    meta = frame[meta_cols].copy()
    return frame[cols].copy(), frame[y_col].copy(), meta.reset_index(drop=True)
