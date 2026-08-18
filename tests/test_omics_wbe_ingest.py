"""Tests for ingest connectors, the source registry and provenance."""

import json
from pathlib import Path

import pandas as pd
import pytest

from omics_wbe.config import WBE_MEASUREMENT_COLUMNS
from omics_wbe.ingest.health_records import load_nyt_counties
from omics_wbe.ingest.nwss import load_nwss
from omics_wbe.ingest.qld import load_qld
from omics_wbe.ingest.sequence_archives import (
    ArchiveQuery, ArchiveUnavailable, plan_quantification,
)
from omics_wbe.ingest.sources import REGISTRY, availability_report, get_source
from omics_wbe.provenance import RunManifest, sha256_file, verify_manifest


# --- source registry -------------------------------------------------------

def test_every_source_declares_licence_citation_and_criteria():
    for key, source in REGISTRY.items():
        assert source.licence, f"{key} has no licence"
        assert source.citation, f"{key} has no citation"
        assert source.selection_criteria, f"{key} has no selection criteria"
        assert source.landing_page.startswith("http"), f"{key} has no landing page"
        assert source.notes, f"{key} records no known limitations"


def test_unknown_source_key_raises():
    with pytest.raises(KeyError, match="unknown data source"):
        get_source("not_a_source")


def test_availability_report_covers_the_whole_registry(tmp_path):
    report = availability_report(tmp_path)
    assert set(report) == set(REGISTRY)
    assert all(not r["available"] for r in report.values())


# --- NWSS connector --------------------------------------------------------

def _nwss_csv(tmp_path: Path) -> Path:
    rows = []
    for i in range(8):
        rows.append({
            "wwtp_name": "PlantA", "facility_name": "Plant A", "county_names": "06001",
            "reporting_jurisdiction": "CA", "population_served": 50_000,
            "sample_id": f"S{i}", "sample_collect_date": f"2022-01-0{i + 1}",
            "sample_matrix": "raw wastewater", "sample_location": "wwtp", "flow_rate": 10.0,
            "pcr_target": "sars-cov-2", "pcr_gene_target": "n1",
            "pcr_target_units": "copies/L wastewater", "pcr_target_avg_conc": 1e5 + i,
            "pcr_target_below_lod": "no", "lod_sewage": 1000.0,
            "hum_frac_mic_conc": 1e8, "hum_frac_mic_unit": "copies/L",
            "hum_frac_target_mic": "pepper mild mottle virus", "rec_eff_percent": 70.0,
            "inhibition_detect": "no", "ntc_amplify": "no", "quality_flag": "",
            "qc_ignore": "no", "analysis_ignore": "no", "dashboard_ignore": "no",
            "major_lab_method": "1", "major_lab_method_desc": "",
        })
    # An unmapped assay target, an upstream sample, and a log10-reported value.
    rows.append({**rows[0], "sample_id": "SX", "pcr_gene_target": "not_a_real_target"})
    rows.append({**rows[0], "sample_id": "SU", "sample_location": "upstream"})
    rows.append({**rows[0], "sample_id": "SL", "pcr_target_avg_conc": 5.0,
                 "pcr_target_units": "log10 copies/L wastewater"})
    rows.append({**rows[0], "sample_id": "SI", "qc_ignore": "yes"})

    path = tmp_path / "nwss.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_nwss_emits_the_canonical_schema(tmp_path):
    df, _ = load_nwss(_nwss_csv(tmp_path))
    for column in WBE_MEASUREMENT_COLUMNS:
        if column == "exclude_upstream":
            continue
        assert column in df.columns, f"canonical column {column} missing"


def test_nwss_maps_assay_targets_to_catalogue_biomarkers(tmp_path):
    df, _ = load_nwss(_nwss_csv(tmp_path))
    assert set(df["target"]) == {"sars_cov_2"}


def test_nwss_counts_unmapped_targets_rather_than_dropping_them_silently(tmp_path):
    _, report = load_nwss(_nwss_csv(tmp_path))
    assert report["rows_unmapped_target"] == 1
    assert "not_a_real_target" in report["unmapped_gene_targets"]


def test_nwss_honours_submitter_exclusion_flags(tmp_path):
    df, report = load_nwss(_nwss_csv(tmp_path))
    assert report["rows_flagged_by_submitter"] == 1
    assert "SI" not in set(df["sample_id"])


def test_nwss_excludes_upstream_sampling_points_by_default(tmp_path):
    df, report = load_nwss(_nwss_csv(tmp_path))
    assert report["rows_upstream_excluded"] == 1
    assert "SU" not in set(df["sample_id"])
    included, _ = load_nwss(_nwss_csv(tmp_path), include_upstream=True)
    assert "SU" in set(included["sample_id"])


def test_nwss_converts_log10_reported_concentrations(tmp_path):
    df, report = load_nwss(_nwss_csv(tmp_path))
    assert report["rows_delogged"] == 1
    row = df[df["sample_id"] == "SL"].iloc[0]
    assert row["concentration"] == pytest.approx(1e5)
    assert row["unit"] == "copies/L wastewater"


def test_nwss_separates_sampling_points_within_a_sewershed(tmp_path):
    df, _ = load_nwss(_nwss_csv(tmp_path), include_upstream=True)
    assert df[df["sample_id"] == "SU"]["site_id"].iloc[0] != df[df["sample_id"] == "S0"]["site_id"].iloc[0]


def test_nwss_zero_pads_county_fips(tmp_path):
    df, _ = load_nwss(_nwss_csv(tmp_path))
    assert (df["region_code"].str.len() == 5).all()


# --- health records --------------------------------------------------------

def _nyt_csv(tmp_path: Path) -> Path:
    rows = []
    for i in range(6):
        rows.append({"date": f"2022-01-0{i + 1}", "geoid": "USA-06001", "county": "Alameda",
                     "state": "California", "cases": 10 + i, "cases_avg": 11.0,
                     "cases_avg_per_100k": 0.7})
    rows.append({"date": "2022-01-01", "geoid": "USA-36061", "county": "New York",
                 "state": "New York", "cases": 5, "cases_avg": 5.0, "cases_avg_per_100k": 0.3})
    rows.append({"date": "2022-01-01", "geoid": "USA-06999", "county": "Unknown",
                 "state": "California", "cases": 1, "cases_avg": 1.0, "cases_avg_per_100k": 0.1})
    rows.append({"date": "2022-01-01", "geoid": "unparseable", "county": "X",
                 "state": "California", "cases": 1, "cases_avg": 1.0, "cases_avg_per_100k": 0.1})
    path = tmp_path / "nyt.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_health_records_filter_to_the_requested_state(tmp_path):
    df, report = load_nyt_counties([_nyt_csv(tmp_path)], state="California")
    assert "36061" not in set(df["region_code"])
    assert report["rows_after_state_filter"] == 8


def test_health_records_drop_unresolvable_geoids(tmp_path):
    _, report = load_nyt_counties([_nyt_csv(tmp_path)])
    assert report["rows_unresolvable_geoid"] == 1


def test_health_records_deduplicate_region_days(tmp_path):
    path = _nyt_csv(tmp_path)
    df, report = load_nyt_counties([path, path])
    assert report["duplicate_region_days_dropped"] > 0
    assert not df.duplicated(["region_code", "date", "indicator"]).any()


# --- Queensland ------------------------------------------------------------

def test_qld_separates_blank_padding_from_parse_failures(tmp_path):
    rows = [{"Sampling date": "22/07/2020", "Site": "Coombabah", "Result": "Non-detect",
             "Site population": 238437}]
    rows += [{"Sampling date": None, "Site": None, "Result": None, "Site population": None}] * 50
    rows += [{"Sampling date": "bad-date", "Site": "X", "Result": "Detect", "Site population": 1}]
    path = tmp_path / "qld.csv"
    pd.DataFrame(rows).to_csv(path, index=False)

    df, report = load_qld([path])
    assert report["blank_padding_rows_dropped"] == 50
    assert report["rows_dropped_unparseable"] == 1
    assert report["rows_kept"] == 1
    assert bool(df["detected"].iloc[0]) is False


def test_qld_parses_day_first_dates(tmp_path):
    path = tmp_path / "qld.csv"
    pd.DataFrame([{"Sampling date": "07/12/2021", "Site": "S", "Result": "Detect",
                   "Site population": 5000}]).to_csv(path, index=False)
    df, _ = load_qld([path])
    assert df["collect_date"].iloc[0] == pd.Timestamp("2021-12-07")


def test_qld_flags_upstream_subcatchments(tmp_path):
    path = tmp_path / "qld.csv"
    pd.DataFrame([
        {"Sampling date": "01/07/2021", "Site": "Luggage Point Upstream Location A",
         "Result": "Detect", "Site population": 14950},
        {"Sampling date": "01/07/2021", "Site": "Luggage Point", "Result": "Detect",
         "Site population": 500000},
    ]).to_csv(path, index=False)
    df, report = load_qld([path])
    assert report["n_subcatchment_sites"] == 1
    assert df.set_index("site_name")["is_subcatchment"]["Luggage Point"] == False  # noqa: E712


# --- sequence archives -----------------------------------------------------

def test_archive_query_encodes_its_selection_criteria():
    described = ArchiveQuery().describe()
    assert "wastewater metagenome" in described["ncbi_sra_entrez_query"]
    assert "METAGENOMIC" in described["ena_portal_query"]
    assert described["criteria"]["require_collection_date"] is True


def test_archive_query_requires_geolocation_and_date_in_the_ena_expression():
    ena = ArchiveQuery().to_ena()
    assert 'collection_date!=""' in ena
    assert 'country!=""' in ena


def test_unreachable_archive_raises_rather_than_returning_empty():
    query = ArchiveQuery()
    from omics_wbe.ingest import sequence_archives as sa
    original = sa._get
    sa._get = lambda url, timeout=30.0: (_ for _ in ()).throw(ArchiveUnavailable("blocked"))
    try:
        with pytest.raises(ArchiveUnavailable):
            sa.search_ena(query)
    finally:
        sa._get = original


def test_run_inventory_reports_unavailability_without_claiming_an_empty_archive():
    from omics_wbe.ingest import sequence_archives as sa
    original = sa._get
    sa._get = lambda url, timeout=30.0: (_ for _ in ()).throw(ArchiveUnavailable("blocked"))
    try:
        inventory, report = sa.build_run_inventory(ArchiveQuery())
    finally:
        sa._get = original
    assert inventory.empty
    assert report["archives"]["ena"]["status"] == "unavailable"
    assert report["archives"]["ncbi_sra"]["status"] == "unavailable"
    assert "runs_retained" not in report


def test_quantification_plan_names_every_step_to_a_measurement():
    steps = [s["step"] for s in plan_quantification(pd.DataFrame(index=range(3)))]
    assert "host_depletion" in steps
    assert "target_quantification" in steps
    assert steps[-1] == "harmonisation"


# --- provenance ------------------------------------------------------------

def test_manifest_records_and_verifies_hashes(tmp_path):
    target = tmp_path / "data.csv"
    target.write_text("a,b\n1,2\n")
    manifest = RunManifest("test_stage", {"seed": 1}).add_input("data", target).add_metric("n", 1)
    path = manifest.write(tmp_path)

    assert verify_manifest(path) == {"ok": ["inputs.data"], "changed": [], "missing": []}


def test_manifest_detects_a_changed_input(tmp_path):
    target = tmp_path / "data.csv"
    target.write_text("a,b\n1,2\n")
    path = RunManifest("test_stage", {}).add_input("data", target).write(tmp_path)
    target.write_text("a,b\n9,9\n")
    assert verify_manifest(path)["changed"] == ["inputs.data"]


def test_manifest_detects_a_missing_input(tmp_path):
    target = tmp_path / "data.csv"
    target.write_text("x")
    path = RunManifest("test_stage", {}).add_input("data", target).write(tmp_path)
    target.unlink()
    assert verify_manifest(path)["missing"] == ["inputs.data"]


def test_manifest_records_seed_and_library_versions(tmp_path):
    path = RunManifest("test_stage", {"seed": 42}).write(tmp_path)
    payload = json.loads(path.read_text())
    assert payload["config"]["seed"] == 42
    assert "numpy" in payload["libraries"]
    assert "python" in payload["libraries"]


def test_hashing_a_file_is_stable(tmp_path):
    target = tmp_path / "x.bin"
    target.write_bytes(b"hello world")
    assert sha256_file(target) == sha256_file(target)
