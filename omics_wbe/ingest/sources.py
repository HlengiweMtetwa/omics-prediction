"""Registry of the external data sources this project mines.

The proposal's methodology is "systematic data mining ... [with] specific
selection criteria". Those criteria live here as executable metadata rather
than as prose in a report, so the acquisition step is auditable: every source
records its provenance, licence, citation, expected local path and the
selection criteria applied to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omics_wbe.config import RAW_DIR


@dataclass(frozen=True)
class DataSource:
    key: str
    title: str
    publisher: str
    kind: str                      # "wbe_measurements" | "health_records"
    licence: str
    landing_page: str
    citation: str
    files: tuple[str, ...]         # paths relative to RAW_DIR
    selection_criteria: tuple[str, ...]
    spatial_scope: str
    temporal_scope: str
    notes: tuple[str, ...] = field(default_factory=tuple)

    def paths(self, raw_dir: Path | None = None) -> list[Path]:
        base = Path(raw_dir) if raw_dir else RAW_DIR
        return [base / f for f in self.files]

    def available(self, raw_dir: Path | None = None) -> bool:
        return all(p.exists() for p in self.paths(raw_dir))

    def missing(self, raw_dir: Path | None = None) -> list[Path]:
        return [p for p in self.paths(raw_dir) if not p.exists()]

    def to_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        for k in ("files", "selection_criteria", "notes"):
            d[k] = list(d[k])
        return d


NWSS_CA = DataSource(
    key="nwss_ca",
    title="CDC National Wastewater Surveillance System (NWSS) public dataset - California submissions",
    publisher="US CDC / California Department of Public Health and contributing laboratories",
    kind="wbe_measurements",
    licence="Public domain (US Government work), redistributed CC0 by the Kaggle mirror",
    landing_page="https://www.kaggle.com/datasets/yashusinghal/master-covid-public-dataset",
    citation=(
        "US Centers for Disease Control and Prevention. National Wastewater Surveillance System "
        "(NWSS) public dataset. Accessed via the 'Covid-19 Public Master Dataset' Kaggle mirror."
    ),
    files=("nwss/master-covid-public.csv",),
    selection_criteria=(
        "Sewershed-level (wwtp or upstream) samples only; no institution-specific sampling points.",
        "Rows must carry a quantitative pcr_target_avg_conc and an interpretable pcr_target_units value.",
        "Assay targets must resolve to a biomarker in the project catalogue; unmapped targets are counted and reported, never silently dropped.",
        "Rows the submitting laboratory flagged for exclusion (qc_ignore / analysis_ignore) are removed before analysis.",
        "Sewersheds serving fewer than the governance minimum population are suppressed from published outputs.",
    ),
    spatial_scope="43 California county groupings (FIPS-coded), sewershed resolution",
    temporal_scope="2020-03-18 to 2024-01-17",
    notes=(
        "Multi-pathogen: SARS-CoV-2, influenza A/B, RSV, norovirus GII, mpox (hMPXV) and SARS-CoV-2 variant markers.",
        "Mixed matrices (raw wastewater, post grit removal, primary sludge) with incompatible units - see omics_wbe.normalize.",
        "county_names holds FIPS codes and may list several counties for a shared sewershed.",
    ),
)

NYT_US_COUNTIES = DataSource(
    key="nyt_counties",
    title="New York Times COVID-19 US county-level case and death series (rolling averages)",
    publisher="The New York Times",
    kind="health_records",
    licence="CC BY-NC 4.0 (NYT data licence: non-commercial use with attribution)",
    landing_page="https://github.com/nytimes/covid-19-data",
    citation=(
        "The New York Times. Coronavirus (Covid-19) Data in the United States. "
        "https://github.com/nytimes/covid-19-data (rolling-averages series)."
    ),
    files=(
        "nyt/us-counties-2020.csv",
        "nyt/us-counties-2021.csv",
        "nyt/us-counties-2022.csv",
        "nyt/us-counties-2023.csv",
    ),
    selection_criteria=(
        "California counties only, to match the NWSS submissions available.",
        "Rows with a resolvable 5-digit FIPS geoid; 'Unknown' county rows are excluded.",
        "The 7-day rolling average per 100k is the analysis target - raw daily counts carry weekday reporting artefacts.",
    ),
    spatial_scope="US counties (analysis restricted to California)",
    temporal_scope="2020-01-21 to 2023-03-23",
    notes=(
        "Reported cases are a biased proxy for infection: test-seeking behaviour and test availability changed "
        "substantially across the study period. This is the central limitation of any wastewater-versus-cases model.",
        "Negative daily counts occur where a health department revised a backlog; the rolling average absorbs them.",
    ),
)

QLD_WBE = DataSource(
    key="qld_wbe",
    title="Queensland wastewater surveillance for SARS-CoV-2 (detect / non-detect)",
    publisher="Queensland Health / Queensland Government open data",
    kind="wbe_measurements",
    licence="CC BY-SA 4.0",
    landing_page="https://www.kaggle.com/datasets/joebeachcapital/qld-wastewater-surveillance-sars-cov-2-covid19",
    citation=(
        "Queensland Government. Queensland wastewater surveillance for SARS-CoV-2, 2020-2022. "
        "Queensland open data portal."
    ),
    files=(
        "qld/queensland-wastewater-surveillance-for-sars-cov-2-in-2020v1.1(1).csv",
        "qld/queensland-wastewater-surveillance-for-sars-cov-2-q1-2021.csv",
        "qld/queensland-wastewater-surveillance-for-sars-cov-2-q2-2021.csv",
        "qld/queensland-wastewater-surveillance-for-sars-cov-2-q3-2021.csv",
        "qld/queensland-wastewater-surveillance-for-sars-cov-2-q4-2021.csv",
        "qld/queensland-wastewater-surveillance-for-sars-cov-2-q1-2022.csv",
        "qld/queensland-wastewater-surveillance-for-sars-cov-2-q2-2022.csv",
        "qld/queensland-wastewater-surveillance-for-sars-cov-2-q3-2022.csv",
    ),
    selection_criteria=(
        "Named sewershed sites with a recorded serviced population.",
        "Qualitative Detect / Non-detect results only - retained as a second, independent programme for "
        "detection-level (presence/absence) methods, not for quantitative modelling.",
    ),
    spatial_scope="Queensland, Australia - urban and regional sewersheds",
    temporal_scope="2020-07-22 to 2022-09",
    notes=(
        "No concentrations are published, so this source cannot enter the quantitative model. It exercises the "
        "connector abstraction against a genuinely different upstream schema and supports the urban/rural "
        "detection-frequency comparison the proposal calls for.",
    ),
)

#: Sequence archives named in the proposal. Their connectors are implemented in
#: :mod:`omics_wbe.ingest.sequence_archives`, but no records are mined here -
#: see that module's docstring for why.
SEQUENCE_ARCHIVES = ("ncbi_sra", "ena", "ddbj")

REGISTRY: dict[str, DataSource] = {s.key: s for s in (NWSS_CA, NYT_US_COUNTIES, QLD_WBE)}


def get_source(key: str) -> DataSource:
    try:
        return REGISTRY[key]
    except KeyError:
        raise KeyError(f"unknown data source {key!r}; known: {sorted(REGISTRY)}") from None


def availability_report(raw_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """What is on disk right now. Used by the CLI to fail early and clearly."""
    return {
        key: {
            "available": src.available(raw_dir),
            "missing": [str(p) for p in src.missing(raw_dir)],
            "licence": src.licence,
        }
        for key, src in REGISTRY.items()
    }
