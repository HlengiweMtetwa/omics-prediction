"""Tests for the operational surveillance view.

The properties under test are the ones that decide whether a dashboard is safe
to put in front of a health department: governance cannot be bypassed, status is
computed causally, and silence is never rendered as reassurance.
"""

import json

import numpy as np
import pandas as pd
import pytest

from omics_wbe.config import AnalysisConfig, DEFAULT_CONFIG
from omics_wbe.surveillance.dashboard import (
    STATUS_DESCRIPTIONS, STATUS_ORDER, build_snapshot, catalog_view,
    model_performance_card, pathogen_activity, target_timeseries,
)

METRIC = f"{DEFAULT_CONFIG.primary_metric}_{DEFAULT_CONFIG.signal_variant}"


def _region_week(
    n_weeks=60, regions=("06001", "06002"), targets=("sars_cov_2",),
    population=100_000.0, signal=None, end="2023-06-03", seed=0,
):
    rng = np.random.default_rng(seed)
    weeks = pd.date_range(end=pd.Timestamp(end), periods=n_weeks, freq="W-SAT")
    rows = []
    for region in regions:
        for target in targets:
            values = rng.normal(0, 1, n_weeks) if signal is None else np.asarray(signal, dtype=float)
            rows.append(pd.DataFrame({
                "region_code": region, "target": target, "epiweek_end": weeks,
                METRIC: values, "n_sites": 2, "n_samples": 6,
                "detect_fraction": 1.0, "population_covered": population,
            }))
    return pd.concat(rows, ignore_index=True)


# --- staleness -------------------------------------------------------------

def test_stale_catchment_is_unknown_not_normal():
    df = _region_week(n_weeks=40)
    as_of = df["epiweek_end"].max() + pd.Timedelta(weeks=6)
    snapshot = build_snapshot(df, as_of=as_of, staleness_weeks=3)
    assert set(snapshot.statuses["status"]) == {"no_recent_data"}
    assert (snapshot.statuses["signal"].isna()).all()


def test_staleness_window_is_respected_at_its_boundary():
    df = _region_week(n_weeks=40)
    last = df["epiweek_end"].max()
    inside = build_snapshot(df, as_of=last + pd.Timedelta(weeks=3), staleness_weeks=3)
    outside = build_snapshot(df, as_of=last + pd.Timedelta(weeks=4), staleness_weeks=3)
    assert "no_recent_data" not in set(inside.statuses["status"])
    assert set(outside.statuses["status"]) == {"no_recent_data"}


def test_weeks_since_last_report_is_recorded():
    df = _region_week(n_weeks=40)
    as_of = df["epiweek_end"].max() + pd.Timedelta(weeks=5)
    snapshot = build_snapshot(df, as_of=as_of, staleness_weeks=3)
    assert (snapshot.statuses["weeks_since_last_report"] == 5).all()


# --- status classification -------------------------------------------------

def test_short_series_reports_insufficient_history():
    df = _region_week(n_weeks=6)
    snapshot = build_snapshot(df, min_history=12)
    assert set(snapshot.statuses["status"]) == {"insufficient_history"}


def test_flat_series_is_normal():
    df = _region_week(n_weeks=40, signal=np.zeros(40))
    snapshot = build_snapshot(df, min_history=12)
    assert set(snapshot.statuses["status"]) == {"normal"}


def test_rising_excursion_raises_an_alert():
    values = np.r_[np.zeros(40), np.linspace(0, 10, 10)]
    df = _region_week(n_weeks=50, signal=values)
    snapshot = build_snapshot(df, min_history=12)
    assert set(snapshot.statuses["status"]) == {"alert"}
    assert (snapshot.statuses["trend_4wk"] > 0).all()


def test_falling_excursion_is_a_watch_not_an_alert():
    """A signal that is high but declining does not warrant escalation."""
    values = np.r_[np.zeros(30), np.linspace(0, 10, 10), np.linspace(10, 6, 10)]
    df = _region_week(n_weeks=50, signal=values)
    snapshot = build_snapshot(df, min_history=12)
    assert "alert" not in set(snapshot.statuses["status"])
    assert set(snapshot.statuses["status"]) == {"watch"}


def test_percentile_is_within_the_catchments_own_history():
    values = np.r_[np.zeros(40), np.linspace(0, 6, 10)]
    df = _region_week(n_weeks=50, signal=values)
    snapshot = build_snapshot(df, min_history=12)
    assert (snapshot.statuses["percentile_in_own_history"] > 0.9).all()


def test_a_past_deep_excursion_does_not_desensitise_the_alarm():
    """Regression: the control chart must be robust to one catastrophic dip.

    An EWMA limit built from an expanding standard deviation is permanently
    widened by a single extreme value, so a catchment that once collapsed would
    stop alarming afterwards. San Francisco's post-Omicron signal reaches -10
    robust SD in the real panel, so this is not hypothetical. The chart input is
    winsorised to prevent it.
    """
    # A rise to 2.5 robust SD is deliberately moderate: with the historic dip
    # left unclipped it inflates the control limit past the excursion and the
    # alert is missed entirely. This test fails if the winsorisation is removed.
    rising = np.r_[np.zeros(40), np.linspace(0, 2.5, 20)]
    with_dip = rising.copy()
    with_dip[20] = -30.0

    clean_status = build_snapshot(_region_week(n_weeks=60, signal=rising), min_history=12)
    dipped_status = build_snapshot(_region_week(n_weeks=60, signal=with_dip), min_history=12)

    assert set(clean_status.statuses["status"]) == {"alert"}
    assert set(dipped_status.statuses["status"]) == {"alert"}, (
        "a historic collapse must not suppress a present alert"
    )


def test_displayed_signal_is_not_winsorised():
    """The control chart is clipped; what a human reads is not."""
    values = np.r_[np.zeros(40), np.full(19, 0.0), [-30.0]]
    df = _region_week(n_weeks=60, signal=values)
    snapshot = build_snapshot(df, min_history=12)
    assert snapshot.statuses["signal"].iloc[0] == pytest.approx(-30.0)


# --- causality -------------------------------------------------------------

def test_status_at_a_past_week_ignores_later_data():
    """The decisive test: a dashboard must not be back-filled with hindsight."""
    values = np.r_[np.zeros(40), np.linspace(0, 20, 10)]
    full = _region_week(n_weeks=50, signal=values)
    cutoff = full["epiweek_end"].iloc[39]

    from_full = build_snapshot(full, as_of=cutoff, min_history=12)
    truncated = full[full["epiweek_end"] <= cutoff]
    from_truncated = build_snapshot(truncated, as_of=cutoff, min_history=12)

    pd.testing.assert_frame_equal(
        from_full.statuses.reset_index(drop=True),
        from_truncated.statuses.reset_index(drop=True),
    )
    assert set(from_full.statuses["status"]) == {"normal"}, "the later surge must be invisible"


def test_as_of_defaults_to_the_latest_week_in_the_data():
    df = _region_week(n_weeks=30)
    assert build_snapshot(df).as_of == df["epiweek_end"].max()


# --- governance ------------------------------------------------------------

def test_governance_is_applied_before_anything_is_shown():
    df = _region_week(n_weeks=40)
    df.loc[df["region_code"] == "06002", "n_sites"] = 0
    strict = AnalysisConfig(min_sites_per_region_week=2)
    snapshot = build_snapshot(df, config=strict)
    assert set(snapshot.statuses["region_code"]) == {"06001"}
    assert snapshot.suppression["applied"] is True
    assert snapshot.suppression["sparse_region_week"]["rows_suppressed"] > 0


def test_governance_can_be_disabled_only_explicitly():
    df = _region_week(n_weeks=40)
    df.loc[df["region_code"] == "06002", "n_sites"] = 0
    strict = AnalysisConfig(min_sites_per_region_week=2)
    snapshot = build_snapshot(df, config=strict, apply_governance=False)
    assert set(snapshot.statuses["region_code"]) == {"06001", "06002"}
    assert snapshot.suppression["applied"] is False


# --- snapshot surface ------------------------------------------------------

def test_snapshot_never_claims_to_be_live():
    assert build_snapshot(_region_week()).is_live is False


def test_status_counts_cover_every_defined_status():
    counts = build_snapshot(_region_week(n_weeks=40)).status_counts()
    assert set(counts) == set(STATUS_ORDER)
    assert all(isinstance(v, int) for v in counts.values())


def test_every_status_has_a_description_for_the_reader():
    assert set(STATUS_DESCRIPTIONS) == set(STATUS_ORDER)


def test_needing_attention_selects_only_actionable_statuses():
    values = np.r_[np.zeros(40), np.linspace(0, 10, 10)]
    snapshot = build_snapshot(_region_week(n_weeks=50, signal=values), min_history=12)
    assert set(snapshot.needing_attention()["status"]) <= {"alert", "watch"}


def test_statuses_are_sorted_worst_first():
    values_alert = np.r_[np.zeros(40), np.linspace(0, 10, 10)]
    alerting = _region_week(n_weeks=50, signal=values_alert, regions=("06001",))
    calm = _region_week(n_weeks=50, signal=np.zeros(50), regions=("06002",))
    snapshot = build_snapshot(pd.concat([alerting, calm], ignore_index=True), min_history=12)
    ranks = [STATUS_ORDER.index(s) for s in snapshot.statuses["status"]]
    assert ranks == sorted(ranks)


def test_population_covered_is_not_double_counted_across_weeks():
    df = _region_week(n_weeks=40, regions=("06001", "06002"), population=100_000.0)
    snapshot = build_snapshot(df)
    assert snapshot.coverage["population_covered"] == pytest.approx(200_000.0)


# --- supporting views ------------------------------------------------------

def test_target_timeseries_is_week_by_region():
    df = _region_week(n_weeks=30, regions=("06001", "06002"))
    wide = target_timeseries(df, target="sars_cov_2")
    assert list(wide.columns) == ["06001", "06002"]
    assert wide.index.is_monotonic_increasing


def test_pathogen_activity_compares_each_target_to_its_own_history():
    """Raw cross-pathogen comparison is meaningless; percentiles are the fix."""
    rising = _region_week(n_weeks=50, targets=("influenza_a",),
                          signal=np.r_[np.zeros(40), np.linspace(0, 5, 10)])
    flat = _region_week(n_weeks=50, targets=("rsv",), signal=np.full(50, 100.0))
    activity = pathogen_activity(pd.concat([rising, flat], ignore_index=True), weeks=8)
    by_target = activity.set_index("target")["percentile_of_own_history"]
    assert by_target["influenza_a"] > by_target["rsv"], (
        "a rising target must outrank a flat one regardless of absolute magnitude"
    )


def test_catalog_view_marks_prospective_markers_as_unusable():
    view = catalog_view()
    prospective = view[view["evidence_tier"] == "prospective"]
    assert len(prospective) > 0
    assert not prospective["usable_for_inference"].any()


def test_model_performance_card_reports_absence_rather_than_guessing(tmp_path):
    card = model_performance_card(tmp_path / "missing.json")
    assert card["available"] is False
    assert "run" in card["reason"]


def test_model_performance_card_always_carries_caveats(tmp_path):
    path = tmp_path / "study_results.json"
    path.write_text(json.dumps({
        "objective_2_integration_prediction": {"lag": {"best_lag_median_rho": 2, "best_lag_value": 0.5}},
        "objective_3_public_health_value": {
            "classification": [
                {"block": "wbe", "estimator": "logistic", "auprc": 0.3, "auroc": 0.8, "prevalence": 0.1},
                {"block": "ar", "estimator": "logistic", "auprc": 0.1, "auroc": 0.6, "prevalence": 0.1},
            ],
            "lead_time": {"summary": {"median_lead_weeks": 1.0}},
        },
    }))
    card = model_performance_card(path)
    assert card["available"] is True
    assert card["surge_auprc"] == pytest.approx(0.3)
    assert card["clinical_only_auprc"] == pytest.approx(0.1)
    assert any("case number" in c for c in card["caveats"])
