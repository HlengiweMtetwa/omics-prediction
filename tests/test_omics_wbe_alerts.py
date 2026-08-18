"""Tests for the early-warning and decision-support layer."""

import numpy as np
import pandas as pd
import pytest

from omics_wbe.surveillance.alerts import (
    alarm_metrics, decision_curve, ewma_alarms, lead_time_analysis, surge_labels,
)


def _panel_with_a_wave(lead_weeks=2, n_weeks=120):
    weeks = pd.date_range("2021-01-02", periods=n_weeks, freq="W-SAT")
    base = np.full(n_weeks, 1.0)
    wave = np.zeros(n_weeks)
    wave[60:75] = np.linspace(0, 8, 15)
    signal = base + np.roll(wave, -lead_weeks)
    cases = 5 + 10 * wave
    return pd.DataFrame({
        "region_code": "06001", "region_name": "Test",
        "epiweek_end": weeks, "wbe_signal": signal,
        "case_rate_per_100k": cases, "log_case_rate": np.log1p(cases),
        "n_sites": 1, "detect_fraction": 1.0, "population_covered": 100_000,
    })


def test_ewma_control_limits_use_only_prior_observations():
    s = pd.Series(np.r_[np.ones(30), np.full(30, 99.0)])
    chart = ewma_alarms(s, burn_in=8)
    # The limit at the first excursion cannot already reflect the excursion.
    assert chart["upper_limit"].iloc[30] < 99.0


def test_no_alarm_on_a_flat_series():
    chart = ewma_alarms(pd.Series(np.full(60, 5.0)), burn_in=8)
    assert not chart["alarm"].any()


def test_alarm_fires_on_a_real_excursion():
    rng = np.random.default_rng(0)
    s = pd.Series(np.r_[rng.normal(0, 1, 60), rng.normal(8, 1, 20)])
    assert ewma_alarms(s, burn_in=10)["alarm"].iloc[60:].any()


def test_lead_time_is_positive_when_wastewater_leads():
    events, report = lead_time_analysis(_panel_with_a_wave(lead_weeks=2))
    leads = events["lead_weeks"].dropna()
    assert len(leads) > 0
    assert leads.max() >= 1
    assert report["summary"]["n_clinical_events"] >= 1


def test_unmatched_alarms_are_counted_as_false_alarms_not_dropped():
    panel = _panel_with_a_wave()
    panel.loc[10:14, "wbe_signal"] = 40.0  # a spike with no clinical counterpart
    events, report = lead_time_analysis(panel)
    assert events["lead_weeks"].isna().any()
    assert report["summary"]["pooled_precision"] < 1.0


def test_surge_labels_are_relative_to_each_region():
    labels = surge_labels(_panel_with_a_wave(), horizon=2, growth_threshold=0.5)
    assert labels["surge"].sum() > 0
    assert labels["surge"].mean() < 0.5, "a surge label that fires most weeks is not a surge label"


def test_surge_label_definition_matches_the_stated_growth():
    panel = _panel_with_a_wave()
    labels = surge_labels(panel, horizon=2, growth_threshold=0.5)
    merged = panel.merge(labels, on=["region_code", "epiweek_end"])
    log_rate = np.log1p(merged["case_rate_per_100k"])
    expected = log_rate.shift(-2) - log_rate
    np.testing.assert_allclose(
        merged["growth"].to_numpy(), expected.to_numpy(), equal_nan=True, rtol=1e-9
    )


def test_alarm_metrics_on_a_perfect_and_a_useless_score():
    y = pd.Series([0, 0, 1, 1, 0, 1, 0, 0, 1, 1])
    perfect = pd.Series([0.0, 0.1, 0.9, 0.95, 0.05, 0.99, 0.02, 0.03, 0.91, 0.98])
    assert alarm_metrics(y, perfect)["auroc"] == pytest.approx(1.0)
    constant = pd.Series(np.full(10, 0.5))
    assert alarm_metrics(y, constant)["auroc"] == pytest.approx(0.5)


def test_alarm_metrics_handle_a_single_class():
    out = alarm_metrics(pd.Series([0, 0, 0]), pd.Series([0.1, 0.2, 0.3]))
    assert np.isnan(out["auroc"])


def test_decision_curve_alert_all_equals_prevalence_at_zero_threshold():
    y = pd.Series([0, 1] * 50)
    p = pd.Series(np.linspace(0, 1, 100))
    curve = decision_curve(y, p, thresholds=np.array([1e-6]))
    assert curve["net_benefit_alert_all"].iloc[0] == pytest.approx(0.5, abs=1e-3)


def test_decision_curve_rewards_a_perfect_classifier():
    y = pd.Series([0] * 80 + [1] * 20)
    p = pd.Series([0.01] * 80 + [0.99] * 20)
    curve = decision_curve(y, p)
    assert (curve["benefit_over_best_default"] >= -1e-9).all()
    assert curve["benefit_over_best_default"].max() > 0


def test_decision_curve_penalises_a_useless_classifier():
    rng = np.random.default_rng(0)
    y = pd.Series(rng.integers(0, 2, 400))
    p = pd.Series(rng.random(400))
    curve = decision_curve(y, p)
    assert curve["benefit_over_best_default"].max() < 0.05
