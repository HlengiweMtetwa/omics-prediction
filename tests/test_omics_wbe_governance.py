"""Tests for the publication-governance controls."""

import numpy as np
import pandas as pd
import pytest

from omics_wbe.config import AnalysisConfig
from omics_wbe.governance.ethics import (
    apply_publication_policy, flag_sensitive_sites, governance_statement,
    suppress_small_catchments, suppress_sparse_region_weeks,
)


def _sites():
    return pd.DataFrame({
        "site_id": ["a", "b", "c", "d", "e", "f"],
        "site_name": [
            "Metro Central WWTP", "Riverside Correctional Facility",
            "State University Campus Residence", "Tiny Hamlet WWTP",
            "General Hospital Outfall", "Luggage Point Upstream Location I",
        ],
        "population_served": [500_000.0, 40_000.0, 12_000.0, 800.0, 20_000.0, np.nan],
        "n_sites": 3, "n_samples": 5,
    })


def test_small_catchments_are_suppressed():
    out, report = suppress_small_catchments(_sites(), min_population=3000)
    assert "d" not in set(out["site_id"])
    assert report["rows_suppressed_small"] == 1


def test_unknown_population_is_suppressed_not_assumed_adequate():
    out, report = suppress_small_catchments(_sites(), min_population=3000)
    assert "f" not in set(out["site_id"])
    assert report["rows_suppressed_unknown_population"] == 1


def test_institutional_settings_are_flagged_by_category():
    flagged = flag_sensitive_sites(_sites())
    by_site = dict(zip(flagged["site_id"], flagged["sensitive_category"]))
    assert by_site["b"] == "correctional"
    assert by_site["c"] == "educational"
    assert by_site["e"] == "healthcare"
    assert by_site["f"] == "upstream_subcatchment"
    assert pd.isna(by_site["a"])


def test_flagging_is_case_insensitive():
    df = pd.DataFrame({"site_name": ["RIVERSIDE PRISON", "county jail intake"],
                       "population_served": [50_000.0, 50_000.0]})
    assert flag_sensitive_sites(df)["sensitive_setting"].all()


def test_sensitive_sites_are_withheld_by_default():
    out, report = apply_publication_policy(_sites(), level="site")
    assert set(out["site_id"]) == {"a"}
    assert report["rows_withheld_pending_sensitive_review"] == 4
    assert report["sensitive_sites_flagged"]["correctional"] == 1


def test_sensitive_review_can_be_waived_explicitly():
    out, _ = apply_publication_policy(_sites(), level="site", require_sensitive_review=False)
    # b, c and e clear the population floor once the sensitive hold is lifted.
    assert set(out["site_id"]) == {"a", "b", "c", "e"}


def test_sparse_region_weeks_are_suppressed():
    df = pd.DataFrame({"region_code": ["1", "2"], "n_sites": [3, 1], "n_samples": [10, 2]})
    out, report = suppress_sparse_region_weeks(df, min_sites=2)
    assert list(out["region_code"]) == ["1"]
    assert report["rows_suppressed"] == 1


def test_thresholds_come_from_configuration():
    strict = AnalysisConfig(min_population_served=100_000)
    out, report = apply_publication_policy(_sites(), config=strict, level="site")
    assert report["small_catchment"]["min_population_served"] == 100_000
    assert len(out) == 1


def test_governance_statement_reflects_the_configured_thresholds():
    text = governance_statement(AnalysisConfig(min_population_served=7500))
    assert "7,500" in text
    assert "ethics committee" in text.lower()


def test_policy_is_a_pure_filter_and_never_mutates_input():
    sites = _sites()
    before = sites.copy()
    apply_publication_policy(sites, level="site")
    pd.testing.assert_frame_equal(sites, before)
