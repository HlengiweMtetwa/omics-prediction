"""Tests for the validation protocol, feature causality and baselines.

The tests that matter most here are the leakage tests. A leaky pipeline still
produces plausible numbers, so leakage has to be caught by construction rather
than by noticing that a result looks too good.
"""

import numpy as np
import pandas as pd
import pytest

from omics_wbe.features.build import build_features, feature_columns, prepare_supervised
from omics_wbe.modeling.baselines import (
    BASELINE_REQUIREMENTS, BASELINES, BASELINES_BY_TARGET_MODE, NoChangeBaseline,
    PersistenceBaseline,
)
from omics_wbe.modeling.validation import (
    RollingOriginSplit, paired_bootstrap_delta, regression_metrics, skill_score,
)


def _panel(n_regions=4, n_weeks=140, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    weeks = pd.date_range("2021-01-02", periods=n_weeks, freq="W-SAT")
    for r in range(n_regions):
        signal = np.cumsum(rng.normal(0, 0.3, n_weeks))
        rate = np.clip(20 + 8 * np.roll(signal, 2) + rng.normal(0, 2, n_weeks), 0.1, None)
        rows.append(pd.DataFrame({
            "region_code": f"0600{r}", "region_name": f"County {r}",
            "epiweek_end": weeks, "wbe_signal": signal,
            "case_rate_per_100k": rate, "log_case_rate": np.log1p(rate),
            "n_sites": 2, "detect_fraction": 1.0, "population_covered": 100_000,
        }))
    return pd.concat(rows, ignore_index=True)


# --- rolling-origin splits -------------------------------------------------

def test_every_training_row_precedes_every_test_row():
    panel = _panel()
    dates = panel["epiweek_end"]
    splitter = RollingOriginSplit(n_splits=4, test_weeks=10, gap_weeks=4, min_train_weeks=52)
    for train_idx, test_idx in splitter.split(dates):
        assert dates.iloc[train_idx].max() < dates.iloc[test_idx].min()


def test_gap_is_at_least_the_requested_length():
    panel = _panel()
    dates = pd.to_datetime(panel["epiweek_end"])
    splitter = RollingOriginSplit(n_splits=4, test_weeks=10, gap_weeks=4, min_train_weeks=52)
    for train_idx, test_idx in splitter.split(dates):
        gap_days = (dates.iloc[test_idx].min() - dates.iloc[train_idx].max()).days
        assert gap_days >= 4 * 7, f"gap of {gap_days} days is shorter than 4 weeks"


def test_training_set_grows_across_folds():
    panel = _panel()
    sizes = [len(tr) for tr, _ in
             RollingOriginSplit(n_splits=4, test_weeks=10, gap_weeks=4,
                                min_train_weeks=52).split(panel["epiweek_end"])]
    assert sizes == sorted(sizes)


def test_split_refuses_a_series_too_short_for_its_settings():
    short = _panel(n_weeks=40)["epiweek_end"]
    with pytest.raises(ValueError, match="at least"):
        list(RollingOriginSplit(min_train_weeks=52, gap_weeks=4, test_weeks=13).split(short))


def test_all_regions_of_a_test_week_go_to_the_same_fold():
    """Splitting by date, not by row, keeps a panel week intact."""
    panel = _panel()
    splitter = RollingOriginSplit(n_splits=3, test_weeks=10, gap_weeks=4, min_train_weeks=52)
    for _, test_idx in splitter.split(panel["epiweek_end"]):
        block = panel.iloc[test_idx]
        for _, week in block.groupby("epiweek_end"):
            assert len(week) == panel["region_code"].nunique()


# --- feature causality -----------------------------------------------------

def test_no_ar_lag0_feature_exists():
    features, _ = build_features(_panel())
    assert "ar_lag0" not in features.columns
    assert not any(c.endswith("lag0") and c.startswith("ar_") for c in features.columns)


def test_lag_features_equal_the_shifted_signal():
    panel = _panel(n_regions=1)
    features, _ = build_features(panel, max_lag=3)
    merged = features.sort_values("epiweek_end").reset_index(drop=True)
    original = panel.sort_values("epiweek_end")["wbe_signal"].reset_index(drop=True)
    np.testing.assert_allclose(merged["wbe_lag0"].to_numpy(), original.to_numpy())
    np.testing.assert_allclose(merged["wbe_lag2"].to_numpy()[2:], original.to_numpy()[:-2])


def test_features_do_not_change_when_future_weeks_are_appended():
    """The decisive leakage test for feature construction."""
    full = _panel(n_weeks=140)
    truncated = full[full["epiweek_end"] < full["epiweek_end"].max() - pd.Timedelta(weeks=20)]

    f_full, _ = build_features(full, horizons=(1,))
    f_trunc, _ = build_features(truncated, horizons=(1,))

    cols = feature_columns(f_full)
    key = ["region_code", "epiweek_end"]
    merged = f_trunc[key + cols].merge(f_full[key + cols], on=key, suffixes=("_t", "_f"))
    for col in cols:
        np.testing.assert_allclose(
            merged[f"{col}_t"].to_numpy(), merged[f"{col}_f"].to_numpy(),
            equal_nan=True, err_msg=f"{col} changed when future data was appended",
        )


def test_missing_weeks_do_not_silently_change_what_a_lag_means():
    panel = _panel(n_regions=1, n_weeks=100)
    gapped = panel.drop(panel.index[40:45])
    features, _ = build_features(gapped, max_lag=2)
    gap_rows = features[features["wbe_lag2"].isna() & features["wbe_lag0"].notna()]
    assert len(gap_rows) > 0, "a gap must produce missing lags, not silently shifted ones"


def test_all_feature_blocks_score_identical_rows():
    features, _ = build_features(_panel(), horizons=(1,))
    shapes = {}
    for name, opts in {"wbe": (True, False), "ar": (False, True), "both": (True, True)}.items():
        X, y, meta = prepare_supervised(features, horizon=1, use_wbe=opts[0], use_ar=opts[1])
        shapes[name] = (len(X), tuple(meta["epiweek_end"].astype(str)))
    assert shapes["wbe"][0] == shapes["ar"][0] == shapes["both"][0]
    assert shapes["wbe"][1] == shapes["ar"][1] == shapes["both"][1]


def test_delta_target_is_the_change_from_the_last_observable_week():
    panel = _panel(n_regions=1)
    features, _ = build_features(panel, horizons=(1,), target_mode="delta")
    row = features.dropna(subset=["y_h1", "y_level_h1", "ar_lag1"]).iloc[0]
    assert row["y_h1"] == pytest.approx(row["y_level_h1"] - row["ar_lag1"])


def test_level_target_is_the_raw_future_value():
    features, _ = build_features(_panel(n_regions=1), horizons=(1,), target_mode="level")
    row = features.dropna(subset=["y_h1", "y_level_h1"]).iloc[0]
    assert row["y_h1"] == pytest.approx(row["y_level_h1"])


def test_unknown_target_mode_is_rejected():
    with pytest.raises(ValueError, match="unknown target_mode"):
        build_features(_panel(), target_mode="whatever")


# --- baselines -------------------------------------------------------------

def test_baseline_selection_matches_the_target_mode():
    assert "persistence" in BASELINES_BY_TARGET_MODE["level"]
    assert "persistence" not in BASELINES_BY_TARGET_MODE["delta"]
    assert "nochange" in BASELINES_BY_TARGET_MODE["delta"]


def test_every_declared_baseline_exists_and_declares_its_requirements():
    for mode, names in BASELINES_BY_TARGET_MODE.items():
        for name in names:
            assert name in BASELINES, f"{mode} references unknown baseline {name}"
            assert name in BASELINE_REQUIREMENTS


def test_persistence_returns_the_last_observed_value():
    X = pd.DataFrame({"ar_lag1": [1.0, 2.0, 3.0]})
    np.testing.assert_allclose(PersistenceBaseline().fit(X, [0, 0, 0]).predict(X), [1.0, 2.0, 3.0])


def test_nochange_predicts_zero_and_needs_no_clinical_history():
    X = pd.DataFrame({"wbe_lag0": [1.0, 2.0]})
    np.testing.assert_allclose(NoChangeBaseline().fit(X).predict(X), [0.0, 0.0])
    assert BASELINE_REQUIREMENTS["nochange"] == ()


# --- metrics ---------------------------------------------------------------

def test_skill_score_signs():
    assert skill_score(0.5, 1.0) == pytest.approx(0.5)
    assert skill_score(1.0, 1.0) == pytest.approx(0.0)
    assert skill_score(2.0, 1.0) == pytest.approx(-1.0)


def test_perfect_prediction_metrics():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    m = regression_metrics(y, y)
    assert m["rmse"] == pytest.approx(0.0)
    assert m["r2"] == pytest.approx(1.0)
    assert m["bias"] == pytest.approx(0.0)


def test_metrics_ignore_non_finite_pairs():
    y = np.array([1.0, 2.0, np.nan, 4.0])
    p = np.array([1.0, 2.0, 3.0, np.inf])
    assert regression_metrics(y, p)["n"] == 2


def test_paired_bootstrap_detects_a_better_model():
    rng = np.random.default_rng(0)
    y = rng.normal(size=400)
    good = y + rng.normal(0, 0.1, 400)
    bad = y + rng.normal(0, 1.0, 400)
    out = paired_bootstrap_delta(y, good, bad, n_boot=400, seed=1)
    assert out["delta_rmse"] < 0
    assert out["ci95_high"] < 0
    assert out["p_a_better"] > 0.95


def test_paired_bootstrap_is_symmetric_in_sign():
    rng = np.random.default_rng(2)
    y = rng.normal(size=300)
    a = y + rng.normal(0, 0.2, 300)
    b = y + rng.normal(0, 0.6, 300)
    forward = paired_bootstrap_delta(y, a, b, n_boot=300, seed=5)
    reverse = paired_bootstrap_delta(y, b, a, n_boot=300, seed=5)
    assert forward["delta_rmse"] == pytest.approx(-reverse["delta_rmse"])
