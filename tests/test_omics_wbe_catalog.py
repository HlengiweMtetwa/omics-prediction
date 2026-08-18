"""Tests for the biomarker catalogue and its refusal behaviour."""

import json

import pytest

from omics_wbe.biomarkers.catalog import (
    EVIDENCE_TIERS, BiomarkerCatalog, CatalogError, default_catalog,
)


def test_catalog_loads_and_validates():
    catalog = default_catalog()
    assert len(catalog) >= 30
    summary = catalog.summary()
    assert summary["n_biomarkers"] == len(catalog)
    assert summary["n_unique_references"] >= 20


def test_every_entry_has_a_citable_reference():
    for bm in default_catalog():
        assert bm["references"], f"{bm.id} has no reference"
        for ref in bm["references"]:
            assert ref.get("pmid") or ref.get("doi"), f"{bm.id} reference lacks PMID and DOI"


def test_catalog_spans_all_three_omics_layers_and_both_disease_classes():
    catalog = default_catalog()
    layers = {bm["omics_layer"] for bm in catalog}
    assert {"genomics", "proteomics", "metabolomics"} <= layers
    classes = {bm["disease_class"] for bm in catalog}
    assert {"communicable", "non_communicable", "amr", "exposure"} <= classes


def test_gene_target_resolution_is_case_and_separator_insensitive():
    catalog = default_catalog()
    assert catalog.resolve_gene_target("n1") == "sars_cov_2"
    assert catalog.resolve_gene_target("N1") == "sars_cov_2"
    assert catalog.resolve_gene_target(" InfB ") == "influenza_b"
    assert catalog.resolve_gene_target("RSV-A and RSV-B combined") == "rsv"


def test_unknown_gene_target_returns_none_rather_than_guessing():
    assert default_catalog().resolve_gene_target("totally_unknown_assay") is None
    assert default_catalog().resolve_gene_target(None) is None


def test_prospective_markers_are_never_inference_ready():
    catalog = default_catalog()
    for bm in catalog:
        if bm["evidence_tier"] == "prospective":
            assert not catalog.inference_ready(bm.id), f"{bm.id} is prospective but marked usable"


def test_select_filters_by_tier_floor():
    catalog = default_catalog()
    established = catalog.select(min_tier="established")
    assert all(bm["evidence_tier"] == "established" for bm in established)
    assert len(catalog.select(min_tier="prospective")) >= len(established)


def test_normalisers_excluded_from_selection_by_default():
    catalog = default_catalog()
    assert all(not bm.is_normaliser for bm in catalog.select())
    assert any(bm.is_normaliser for bm in catalog.select(include_normalisers=True))


def test_duplicate_biomarker_id_is_rejected():
    payload = json.loads((BiomarkerCatalog.load().__class__ and __import__(
        "omics_wbe.biomarkers.catalog", fromlist=["CATALOG_PATH"]).CATALOG_PATH).read_text())
    payload["biomarkers"].append(dict(payload["biomarkers"][0]))
    with pytest.raises(CatalogError, match="duplicate biomarker_id"):
        BiomarkerCatalog(payload)


def test_entry_without_reference_is_rejected():
    from omics_wbe.biomarkers.catalog import CATALOG_PATH
    payload = json.loads(CATALOG_PATH.read_text())
    payload["biomarkers"][0] = {**payload["biomarkers"][0], "references": []}
    with pytest.raises(CatalogError, match="at least one reference"):
        BiomarkerCatalog(payload)


def test_unknown_evidence_tier_is_rejected():
    from omics_wbe.biomarkers.catalog import CATALOG_PATH
    payload = json.loads(CATALOG_PATH.read_text())
    payload["biomarkers"][0] = {**payload["biomarkers"][0], "evidence_tier": "definitely"}
    with pytest.raises(CatalogError, match="unknown evidence_tier"):
        BiomarkerCatalog(payload)


def test_evidence_tiers_are_ordered_weakest_first():
    assert EVIDENCE_TIERS.index("prospective") < EVIDENCE_TIERS.index("established")
