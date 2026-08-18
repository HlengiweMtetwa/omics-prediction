"""Tests for harmonisation, QC and normalisation.

Fixtures reproduce the specific NWSS conventions that broke a naive
implementation: recovery reported as a ratio in one submission group and as a
percent in another, and non-detects reported as a zero concentration with the
below-LOD flag never populated.
"""

import numpy as np
import pandas as pd
import pytest

from omics_wbe.config import AnalysisConfig
from omics_wbe.normalize import wastewater as W
from omics_wbe.normalize.harmonise import harmonise, harmonise_recovery, infer_censoring
from omics_wbe.qc.checks import RULES, apply_qc_filter, qc_rule_table, run_qc


def _frame(n=60, **overrides):
    # Drawn from a fixed-length pool and sliced, so _frame(60) and _frame(80)
    # share their first 60 values. Re-seeding per length would make the two
    # frames incomparable and quietly break the leakage tests below.
    pool = np.random.default_rng(0)
    conc_pool = pool.lognormal(11, 0.5, 500)
    norm_pool = pool.lognormal(16, 0.2, 500)
    rec_pool = pool.normal(80, 8, 500)
    df = pd.DataFrame({
        "source": "test", "site_id": "siteA", "site_name": "Site A", "region_code": "06001",
        "sample_id": [f"s{i}" for i in range(n)],
        "collect_date": pd.date_range("2022-01-01", periods=n, freq="D"),
        "target": "sars_cov_2", "gene_target": "n1", "matrix": "raw wastewater",
        "concentration": conc_pool[:n],
        "unit": "copies/L wastewater", "below_lod": pd.Series([False] * n, dtype="boolean"),
        "lod": 1000.0, "normaliser_conc": norm_pool[:n], "normaliser_target": "pmmov",
        "recovery_pct": rec_pool[:n], "inhibition_detected": False, "ntc_amplified": False,
        "flow_rate": 10.0, "population_served": 50_000.0, "quality_flag": pd.NA,
        "lab_method": "1.0", "exclude_upstream": False,
    })
    for key, value in overrides.items():
        df[key] = value
    return df


# --- harmonisation ---------------------------------------------------------

def test_ratio_scale_recovery_is_rescaled_to_percent():
    df = _frame(60, recovery_pct=np.full(60, 1.2), matrix="primary sludge")
    out, report = harmonise_recovery(df)
    assert report["groups"][0]["inferred_scale"] == "ratio"
    assert out["recovery_pct"].median() == pytest.approx(120.0)


def test_percent_scale_recovery_is_left_alone():
    df = _frame(60, recovery_pct=np.full(60, 65.0))
    out, report = harmonise_recovery(df)
    assert report["groups"][0]["inferred_scale"] == "percent"
    assert out["recovery_pct"].median() == pytest.approx(65.0)


def test_mixed_groups_are_rescaled_independently():
    ratio = _frame(60, recovery_pct=np.full(60, 1.2), matrix="primary sludge")
    percent = _frame(60, recovery_pct=np.full(60, 65.0), matrix="raw wastewater")
    out, _ = harmonise_recovery(pd.concat([ratio, percent], ignore_index=True))
    by_matrix = out.groupby("matrix")["recovery_pct"].median()
    assert by_matrix["primary sludge"] == pytest.approx(120.0)
    assert by_matrix["raw wastewater"] == pytest.approx(65.0)


def test_recovery_sentinel_becomes_missing_not_a_value():
    df = _frame(40, recovery_pct=np.r_[np.full(20, -1.0), np.full(20, 70.0)])
    out, report = harmonise_recovery(df)
    assert report["recovery_sentinel_rows"] == 20
    assert out["recovery_pct"].isna().sum() == 20
    assert (out["recovery_pct"].dropna() > 0).all()


def test_small_group_is_not_rescaled_from_its_own_median():
    df = _frame(5, recovery_pct=np.full(5, 1.2))
    out, report = harmonise_recovery(df)
    assert report["groups"][0]["inferred_scale"] == "percent_assumed_small_group"
    assert out["recovery_pct"].median() == pytest.approx(1.2)


def test_zero_concentration_with_unset_flag_is_inferred_as_censored():
    df = _frame(10)
    df.loc[:4, "concentration"] = 0.0
    df["below_lod"] = pd.Series([pd.NA] * 10, dtype="boolean")
    out, report = infer_censoring(df)
    assert report["rows_censoring_inferred"] == 5
    assert out.loc[:4, "below_lod"].all()
    assert out.loc[:4, "censoring_inferred"].all()
    assert not out.loc[5:, "censoring_inferred"].any()


def test_submitter_censoring_flag_is_not_marked_as_inferred():
    df = _frame(10)
    df.loc[:2, "concentration"] = 0.0
    df.loc[:2, "below_lod"] = True
    out, report = infer_censoring(df)
    assert report["rows_censored_by_submitter"] == 3
    assert report["rows_censoring_inferred"] == 0
    assert not out["censoring_inferred"].any()


# --- QC --------------------------------------------------------------------

def test_qc_flags_but_never_drops():
    df, _ = harmonise(_frame(40))
    out, report = run_qc(df)
    assert len(out) == len(df)
    assert report["rows_in"] == 40
    assert {"qc_pass", "qc_warn"} <= set(out.columns)


def test_ntc_amplification_fails_the_measurement():
    df, _ = harmonise(_frame(40, ntc_amplified=True))
    out, report = run_qc(df)
    assert report["n_pass"] == 0
    assert out["QC001"].all()


def test_recovery_outside_window_fails():
    cfg = AnalysisConfig(recovery_min_pct=50, recovery_max_pct=150)
    df, _ = harmonise(_frame(40, recovery_pct=np.full(40, 500.0)))
    _, report = run_qc(df, cfg)
    assert report["n_pass"] == 0


def test_analytical_replicates_are_a_warning_not_a_failure():
    # Same sample ids and dates twice: analytical replicates.
    df = pd.concat([_frame(5), _frame(5)], ignore_index=True)
    df, _ = harmonise(df)
    out, report = run_qc(df)
    assert out["QC007"].all()
    assert report["n_pass"] == len(df), "replicates must not be excluded"


def test_unharmonised_zeroes_do_not_mass_fail_after_harmonisation():
    df = _frame(50)
    df.loc[:29, "concentration"] = 0.0
    df["below_lod"] = pd.Series([pd.NA] * 50, dtype="boolean")
    harmonised, _ = harmonise(df)
    _, report = run_qc(harmonised)
    assert report["n_pass"] == 50


def test_every_rule_has_a_unique_code_and_valid_severity():
    codes = [r.code for r in RULES]
    assert len(codes) == len(set(codes))
    assert all(r.severity in {"fail", "warn"} for r in RULES)
    assert len(qc_rule_table()) == len(RULES)


# --- normalisation ---------------------------------------------------------

def test_replicates_collapse_to_a_geometric_mean():
    df = _frame(2)
    df["sample_id"] = "same"
    df["collect_date"] = pd.Timestamp("2022-01-01")
    df["concentration"] = [100.0, 10_000.0]
    df, _ = harmonise(df)
    out, report = W.collapse_replicates(df)
    assert len(out) == 1
    assert out["concentration"].iloc[0] == pytest.approx(1000.0)  # geometric, not 5050
    assert report["samples_with_replicates"] == 1


def test_one_detect_among_non_detects_is_a_detect():
    df = _frame(2)
    df["sample_id"] = "same"
    df["collect_date"] = pd.Timestamp("2022-01-01")
    df["concentration"] = [0.0, 5000.0]
    df["below_lod"] = pd.Series([True, False], dtype="boolean")
    df, _ = harmonise(df)
    out, _ = W.collapse_replicates(df)
    assert not bool(out["below_lod"].iloc[0])
    assert out["concentration"].iloc[0] == pytest.approx(5000.0)


def test_all_non_detect_replicates_stay_a_non_detect():
    df = _frame(2)
    df["sample_id"] = "same"
    df["collect_date"] = pd.Timestamp("2022-01-01")
    df["concentration"] = 0.0
    df["below_lod"] = pd.Series([True, True], dtype="boolean")
    df, _ = harmonise(df)
    out, _ = W.collapse_replicates(df)
    assert bool(out["below_lod"].iloc[0])


def test_censored_values_are_substituted_at_lod_over_sqrt2():
    df = _frame(30)
    df.loc[:9, "concentration"] = 0.0
    df.loc[:9, "below_lod"] = True
    df, _ = harmonise(df)
    collapsed, _ = W.collapse_replicates(df)
    out, report = W.substitute_censored(collapsed)
    substituted = out.loc[out["censored"], "concentration_imputed"]
    assert substituted.iloc[0] == pytest.approx(1000.0 / np.sqrt(2))
    assert report["n_censored"] == 10


def test_pmmov_ratio_is_dimensionless_and_matrix_independent():
    df = _frame(20, concentration=np.full(20, 1e5), normaliser_conc=np.full(20, 1e8))
    df, _ = harmonise(df)
    collapsed, _ = W.collapse_replicates(df)
    imputed, _ = W.substitute_censored(collapsed)
    out, _ = W.compute_metrics(imputed)
    assert out["ratio_pmmov"].iloc[0] == pytest.approx(1e-3)
    assert out["log10_ratio_pmmov"].iloc[0] == pytest.approx(-3.0)


def test_standardisation_excludes_nearly_all_censored_series():
    df = _frame(40)
    df["concentration"] = 0.0
    df["below_lod"] = True
    df, _ = harmonise(df)
    collapsed, _ = W.collapse_replicates(df)
    imputed, _ = W.substitute_censored(collapsed)
    metrics, _ = W.compute_metrics(imputed)
    out, report = W.standardise_within_site(metrics)
    assert report["n_series_below_min_detect_fraction"] == 1
    assert out["log10_ratio_pmmov_z"].isna().all()


def test_causal_standardisation_uses_only_the_past():
    df = _frame(60)
    df, _ = harmonise(df)
    collapsed, _ = W.collapse_replicates(df)
    imputed, _ = W.substitute_censored(collapsed)
    metrics, _ = W.compute_metrics(imputed)
    out, _ = W.standardise_within_site_causal(metrics, min_window=20)
    ordered = out.sort_values("collect_date")
    # The first min_window observations have no prior history to standardise against.
    assert ordered["log10_ratio_pmmov_zc"].head(20).isna().all()
    assert ordered["log10_ratio_pmmov_zc"].tail(10).notna().any()


def test_causal_standardisation_is_unaffected_by_appending_future_data():
    base = _frame(60)
    extended = _frame(80)
    results = []
    for df in (base, extended):
        h, _ = harmonise(df)
        collapsed, _ = W.collapse_replicates(h)
        imputed, _ = W.substitute_censored(collapsed)
        metrics, _ = W.compute_metrics(imputed)
        out, _ = W.standardise_within_site_causal(metrics, min_window=20)
        results.append(out.sort_values("collect_date")["log10_ratio_pmmov_zc"].head(60).to_numpy())
    np.testing.assert_allclose(results[0], results[1], equal_nan=True)


def test_retrospective_standardisation_does_change_with_future_data():
    """The contrast that motivates the causal variant existing at all."""
    base, extended = _frame(60), _frame(80)
    results = []
    for df in (base, extended):
        h, _ = harmonise(df)
        collapsed, _ = W.collapse_replicates(h)
        imputed, _ = W.substitute_censored(collapsed)
        metrics, _ = W.compute_metrics(imputed)
        out, _ = W.standardise_within_site(metrics, min_observations=10)
        results.append(out.sort_values("collect_date")["log10_ratio_pmmov_z"].head(60).to_numpy())
    assert not np.allclose(results[0], results[1], equal_nan=True)


def test_epiweek_anchors_on_saturday():
    dates = pd.Series(pd.to_datetime(["2022-01-02", "2022-01-05", "2022-01-08"]))
    weeks = W.to_epiweek(dates)
    assert str(weeks.iloc[0].date()) == "2022-01-08"
    assert str(weeks.iloc[1].date()) == "2022-01-08"
    assert str(weeks.iloc[2].date()) == "2022-01-08"


def test_region_aggregation_is_population_weighted():
    site_weeks = pd.DataFrame({
        "source": "t", "site_id": ["big", "small"], "target": "sars_cov_2",
        "epiweek_end": pd.to_datetime(["2022-01-08", "2022-01-08"]),
        "log10_ratio_pmmov_z": [1.0, 5.0],
        "population_served": [900_000.0, 100_000.0],
        "region_code": "06001", "n_samples": [1, 1], "detect_fraction": [1.0, 1.0],
    })
    out, _ = W.aggregate_region_week(site_weeks, metric="log10_ratio_pmmov_z")
    assert out["log10_ratio_pmmov_z"].iloc[0] == pytest.approx(0.9 * 1.0 + 0.1 * 5.0)
