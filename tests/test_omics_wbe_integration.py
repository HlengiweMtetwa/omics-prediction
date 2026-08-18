"""End-to-end tests over the real analysis panels.

These skip cleanly when the panels have not been built, so the suite runs on a
fresh clone without the raw data. When the panels *are* present they assert the
properties that the whole study rests on.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from omics_wbe.config import DEFAULT_CONFIG, INTERIM_DIR, RESULTS_DIR
from omics_wbe.integrate.align import build_analysis_panel, lag_correlations

REGION_WEEK = INTERIM_DIR / "wbe_region_week.parquet"
HEALTH_WEEK = INTERIM_DIR / "health_region_week.parquet"

needs_panels = pytest.mark.skipif(
    not (REGION_WEEK.exists() and HEALTH_WEEK.exists()),
    reason="analysis panels not built; run `python -m omics_wbe.cli stage-one`",
)


@pytest.fixture(scope="module")
def panels():
    return pd.read_parquet(REGION_WEEK), pd.read_parquet(HEALTH_WEEK)


@needs_panels
def test_panel_carries_both_standardisation_variants(panels):
    region_week, _ = panels
    assert "log10_ratio_pmmov_z" in region_week.columns
    assert "log10_ratio_pmmov_zc" in region_week.columns


@needs_panels
def test_headline_panel_uses_the_causal_variant(panels):
    _, report = build_analysis_panel(*panels, target="sars_cov_2")
    assert report["signal_metric"].endswith("_zc"), "headline features must not leak future data"


@needs_panels
def test_signal_is_winsorised_at_the_configured_limit(panels):
    panel, report = build_analysis_panel(*panels, target="sars_cov_2")
    limit = DEFAULT_CONFIG.signal_clip
    assert panel["wbe_signal"].abs().max() <= limit + 1e-9
    assert report["signal_clip"] == pytest.approx(limit)


@needs_panels
def test_join_is_one_to_one_on_region_and_week(panels):
    panel, _ = build_analysis_panel(*panels, target="sars_cov_2")
    assert not panel.duplicated(["region_code", "epiweek_end"]).any()


@needs_panels
def test_wastewater_leads_reported_cases(panels):
    """The study's central empirical claim, asserted rather than described."""
    panel, _ = build_analysis_panel(*panels, target="sars_cov_2")
    _, report = lag_correlations(panel)
    assert report["best_lag_median_rho"] >= 1, "expected wastewater to lead by at least a week"
    assert report["best_lag_value"] > 0.4, "expected a moderate positive correlation at the best lag"


@needs_panels
def test_every_modelled_county_has_enough_history_to_validate(panels):
    panel, report = build_analysis_panel(*panels, target="sars_cov_2")
    weeks = panel.groupby("region_code")["epiweek_end"].nunique()
    assert (weeks >= 52).all()
    assert report["regions_retained"] == len(weeks)


@needs_panels
def test_multiple_pathogens_are_present_in_the_panel(panels):
    region_week, _ = panels
    targets = set(region_week["target"])
    assert {"sars_cov_2", "influenza_a", "rsv", "norovirus_gii"} <= targets


@needs_panels
def test_nearly_fully_censored_targets_are_excluded_from_the_panel(panels):
    """C. auris is 98% non-detect; its z-scores are artefacts, not signal."""
    region_week, _ = panels
    assert "candida_auris" not in set(region_week["target"])


@pytest.mark.skipif(
    not (RESULTS_DIR / "study_results.json").exists(),
    reason="study not run; run `python -m omics_wbe.cli run`",
)
def test_study_results_expose_every_objective():
    results = json.loads((RESULTS_DIR / "study_results.json").read_text())
    for key in ("objective_1_detection", "objective_2_integration_prediction",
                "objective_3_public_health_value", "sensitivity"):
        assert key in results, f"{key} missing from study results"


@pytest.mark.skipif(
    not (RESULTS_DIR / "study_results.json").exists(), reason="study not run"
)
def test_headline_findings_are_fully_populated():
    """A cached stage-one run once silently emptied these; they are load-bearing."""
    from omics_wbe.study import headline_findings

    results = json.loads((RESULTS_DIR / "study_results.json").read_text())
    headline = headline_findings(results)
    for key in ("n_measurements_ingested", "n_measurements_retained", "qc_pass_rate",
                "n_biomarkers_in_catalog", "optimal_lead_weeks", "n_counties_modelled"):
        assert headline.get(key) is not None, f"{key} is None - stage reports did not reach the report"


@pytest.mark.skipif(
    not (RESULTS_DIR / "manifests").exists(), reason="no manifests; run the pipeline"
)
def test_every_manifest_verifies_clean():
    from omics_wbe.provenance import verify_manifest

    for path in sorted((RESULTS_DIR / "manifests").glob("*.manifest.json")):
        report = verify_manifest(path)
        assert not report["changed"], f"{path.name} inputs/outputs changed: {report['changed']}"
