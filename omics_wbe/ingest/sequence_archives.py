"""Connectors for the sequence archives named in the proposal: NCBI, ENA, DDBJ.

Scope note, stated plainly
--------------------------
These archives hold *sequencing runs* — wastewater metagenomes and amplicon
libraries — not the quantified, date-and-catchment-stamped biomarker
concentrations the predictive models consume. Turning a run accession into a
biomarker concentration requires read-level processing (QC, host depletion,
taxonomic or reference-based quantification), which is a compute-bound
bioinformatics pipeline, not a data-mining step.

So this module does the part that is honestly a mining problem: it builds the
archive queries that implement the proposal's selection criteria, executes them
against the public APIs, and returns a harmonised *run inventory* with the
metadata needed to decide what to process. :func:`plan_quantification` then maps
that inventory onto the read-processing steps required to reach the canonical
measurement schema, so the gap between "records found" and "measurements usable
in the model" is explicit rather than glossed over.

The environment this was developed in blocks outbound access to
``eutils.ncbi.nlm.nih.gov`` and ``www.ebi.ac.uk``. :func:`check_connectivity`
reports that state rather than letting a caller mistake a network denial for an
empty archive.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

import pandas as pd

NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ENA_PORTAL = "https://www.ebi.ac.uk/ena/portal/api"
DDBJ_SEARCH = "https://ddbj.nig.ac.jp/search"

USER_AGENT = "omics-wbe/1.0 (wastewater-based epidemiology research pipeline)"


class ArchiveUnavailable(RuntimeError):
    """Raised when an archive cannot be reached.

    Deliberately distinct from an empty result: "the network refused us" and
    "the archive holds no matching runs" are different scientific facts and must
    never be reported as the same thing.
    """


# ---------------------------------------------------------------------------
# Selection criteria -> executable queries
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ArchiveQuery:
    """The proposal's "specific selection criteria", made executable.

    Every field maps to a stated criterion, so the query string published in the
    methods section is generated from the same object the pipeline ran.
    """

    organism_terms: tuple[str, ...] = ("wastewater metagenome", "sewage metagenome")
    library_strategies: tuple[str, ...] = ("WGS", "AMPLICON", "RNA-Seq")
    library_sources: tuple[str, ...] = ("METAGENOMIC", "METATRANSCRIPTOMIC", "VIRAL RNA")
    platforms: tuple[str, ...] = ("ILLUMINA", "OXFORD_NANOPORE")
    date_from: str | None = "2020-01-01"
    date_to: str | None = None
    countries: tuple[str, ...] = ()
    min_read_count: int | None = 100_000
    #: Runs without a collection date or geographic origin cannot be placed on a
    #: time series or a catchment, so they are excluded at query time.
    require_collection_date: bool = True
    require_geo_location: bool = True

    def to_entrez(self) -> str:
        """NCBI SRA Entrez query string."""
        parts = ["(" + " OR ".join(f'"{o}"[Organism]' for o in self.organism_terms) + ")"]
        if self.library_strategies:
            parts.append("(" + " OR ".join(f'"{s}"[Strategy]' for s in self.library_strategies) + ")")
        if self.library_sources:
            parts.append("(" + " OR ".join(f'"{s}"[Source]' for s in self.library_sources) + ")")
        if self.platforms:
            parts.append("(" + " OR ".join(f'"{p}"[Platform]' for p in self.platforms) + ")")
        if self.date_from or self.date_to:
            lo = (self.date_from or "1900/01/01").replace("-", "/")
            hi = (self.date_to or "3000/01/01").replace("-", "/")
            parts.append(f'("{lo}"[PDAT] : "{hi}"[PDAT])')
        return " AND ".join(parts)

    def to_ena(self) -> str:
        """ENA portal ``query`` expression."""
        parts = ["(" + " OR ".join(f'library_source="{s}"' for s in self.library_sources) + ")"]
        if self.library_strategies:
            parts.append("(" + " OR ".join(f'library_strategy="{s}"' for s in self.library_strategies) + ")")
        parts.append("(" + " OR ".join(f'scientific_name="{o}"' for o in self.organism_terms) + ")")
        if self.date_from:
            parts.append(f'collection_date>={self.date_from}')
        if self.date_to:
            parts.append(f'collection_date<={self.date_to}')
        if self.countries:
            parts.append("(" + " OR ".join(f'country="{c}"' for c in self.countries) + ")")
        if self.require_collection_date:
            parts.append('collection_date!=""')
        if self.require_geo_location:
            parts.append('country!=""')
        return " AND ".join(parts)

    def describe(self) -> dict[str, Any]:
        return {
            "criteria": {k: (list(v) if isinstance(v, tuple) else v) for k, v in self.__dict__.items()},
            "ncbi_sra_entrez_query": self.to_entrez(),
            "ena_portal_query": self.to_ena(),
        }


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

def _get(url: str, timeout: float = 30.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        raise ArchiveUnavailable(f"{url.split('?')[0]}: {exc}") from exc


def check_connectivity(timeout: float = 15.0) -> dict[str, str]:
    """Probe each archive. Returns ``{archive: "ok" | "unavailable: <reason>"}``."""
    probes = {
        "ncbi": f"{NCBI_EUTILS}/einfo.fcgi?retmode=json",
        "ena": f"{ENA_PORTAL}/searchFields?result=read_run&format=json",
        "ddbj": DDBJ_SEARCH,
    }
    out = {}
    for name, url in probes.items():
        try:
            _get(url, timeout=timeout)
            out[name] = "ok"
        except ArchiveUnavailable as exc:
            out[name] = f"unavailable: {exc}"
    return out


# ---------------------------------------------------------------------------
# Archive searches
# ---------------------------------------------------------------------------

def search_sra(query: ArchiveQuery, *, retmax: int = 500, api_key: str | None = None,
               timeout: float = 30.0) -> dict[str, Any]:
    """NCBI SRA esearch. Returns accession ids plus the total hit count."""
    params = {
        "db": "sra", "term": query.to_entrez(), "retmode": "json",
        "retmax": str(retmax), "usehistory": "y",
    }
    if api_key:
        params["api_key"] = api_key
    payload = json.loads(_get(f"{NCBI_EUTILS}/esearch.fcgi?{urllib.parse.urlencode(params)}", timeout))
    result = payload.get("esearchresult", {})
    return {
        "archive": "ncbi_sra",
        "query": query.to_entrez(),
        "total_found": int(result.get("count", 0)),
        "returned": len(result.get("idlist", [])),
        "ids": result.get("idlist", []),
        "webenv": result.get("webenv"),
        "query_key": result.get("querykey"),
    }


ENA_FIELDS = (
    "run_accession,study_accession,sample_accession,scientific_name,library_strategy,"
    "library_source,instrument_platform,collection_date,country,location,read_count,"
    "base_count,first_public,study_title,sample_title"
)


def search_ena(query: ArchiveQuery, *, limit: int = 1000, timeout: float = 60.0) -> pd.DataFrame:
    """ENA portal search. Returns one row per sequencing run."""
    params = {
        "result": "read_run", "query": query.to_ena(),
        "fields": ENA_FIELDS, "format": "tsv", "limit": str(limit),
    }
    raw = _get(f"{ENA_PORTAL}/search?{urllib.parse.urlencode(params)}", timeout)
    if not raw.strip():
        return pd.DataFrame(columns=ENA_FIELDS.split(","))
    from io import BytesIO
    return pd.read_csv(BytesIO(raw), sep="\t")


def build_run_inventory(query: ArchiveQuery, *, limit: int = 1000,
                        timeout: float = 60.0) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Harmonised inventory of wastewater sequencing runs across archives.

    ENA mirrors SRA and DDBJ under the INSDC agreement, so ENA is the primary
    source of structured run metadata and SRA is queried for its hit count as a
    cross-check that the two query translations select comparable sets.
    """
    report: dict[str, Any] = {"query": query.describe(), "archives": {}}

    try:
        ena = search_ena(query, limit=limit, timeout=timeout)
        report["archives"]["ena"] = {"status": "ok", "runs": int(len(ena))}
    except ArchiveUnavailable as exc:
        report["archives"]["ena"] = {"status": "unavailable", "reason": str(exc)}
        ena = pd.DataFrame()

    try:
        sra = search_sra(query, timeout=timeout)
        report["archives"]["ncbi_sra"] = {"status": "ok", "total_found": sra["total_found"]}
    except ArchiveUnavailable as exc:
        report["archives"]["ncbi_sra"] = {"status": "unavailable", "reason": str(exc)}

    report["archives"]["ddbj"] = {
        "status": "covered_via_ena",
        "note": "DDBJ records are mirrored into ENA under the INSDC agreement; querying ENA covers them.",
    }

    if ena.empty:
        return pd.DataFrame(columns=[
            "run_accession", "study_accession", "sample_accession", "collection_date",
            "country", "library_strategy", "instrument_platform", "read_count",
        ]), report

    inv = ena.copy()
    inv["collection_date"] = pd.to_datetime(inv.get("collection_date"), errors="coerce")
    if query.min_read_count is not None and "read_count" in inv:
        before = len(inv)
        inv = inv[pd.to_numeric(inv["read_count"], errors="coerce").fillna(0) >= query.min_read_count]
        report["runs_below_min_read_count"] = int(before - len(inv))
    if query.require_collection_date:
        before = len(inv)
        inv = inv[inv["collection_date"].notna()]
        report["runs_without_collection_date"] = int(before - len(inv))

    report["runs_retained"] = int(len(inv))
    report["countries"] = inv["country"].value_counts().head(20).to_dict() if "country" in inv else {}
    return inv.reset_index(drop=True), report


def plan_quantification(inventory: pd.DataFrame) -> list[dict[str, Any]]:
    """The processing steps between a run inventory and canonical measurements.

    Returned as data rather than prose so the gap is auditable: nothing in this
    repository converts a run accession into a biomarker concentration, and this
    is the list of what would have to run first.
    """
    n = int(len(inventory))
    return [
        {"step": "download", "tool": "fasterq-dump / ENA FTP", "runs": n,
         "produces": "raw FASTQ", "note": "Bandwidth- and storage-bound; not attempted in this environment."},
        {"step": "read_qc", "tool": "fastp / FastQC + MultiQC", "runs": n,
         "produces": "trimmed reads + QC report",
         "note": "Adapter and quality trimming; runs failing QC thresholds are excluded here, not later."},
        {"step": "host_depletion", "tool": "bowtie2 vs GRCh38", "runs": n,
         "produces": "non-host reads",
         "note": "Also a privacy control: human reads are removed before any downstream sharing."},
        {"step": "taxonomic_profiling", "tool": "Kraken2 + Bracken", "runs": n,
         "produces": "per-taxon relative abundance",
         "note": "Relative abundance, not concentration - it cannot be back-calculated to copies/L without a spiked internal standard."},
        {"step": "target_quantification", "tool": "reference mapping vs catalogue targets (samtools/bedtools)",
         "runs": n, "produces": "per-target read counts",
         "note": "Requires a quantitative internal standard in the sequencing run to reach absolute units."},
        {"step": "amr_profiling", "tool": "CARD/RGI or AMRFinderPlus", "runs": n,
         "produces": "ARG hits per sample",
         "note": "Maps onto the catalogue's amr disease_class entries."},
        {"step": "harmonisation", "tool": "omics_wbe.ingest (new connector)", "runs": n,
         "produces": "canonical WBE measurement rows",
         "note": "Only reached once a target is expressed in an absolute unit with a stated LOD."},
    ]
