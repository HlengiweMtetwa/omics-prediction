# SOP 01 — Systematic Data Mining and Acquisition

**Version** 1.0 · **Scope** All external data entering the omics-WBE platform
**Owner** Principal Investigator · **Review cycle** Annual, or on any change to a source's licence

---

## 1. Purpose

The proposal commits to "systematic data mining of wastewater samples sequences
from available databases ... [with] specific selection criteria". This SOP makes
those criteria executable and auditable: no dataset enters analysis without a
registry entry, a licence, a citation and a recorded set of selection criteria.

## 2. Principle

**A source that is not in the registry does not exist to the pipeline.**
`omics_wbe/ingest/sources.py` is the single register. Adding a dataset means
adding a `DataSource` record, not adding a file path to an analysis script.

## 3. Procedure

### 3.1 Register the source

Create a `DataSource` with, at minimum:

| Field | Requirement |
|---|---|
| `key` | Short stable identifier used in the `source` column of every row it produces |
| `title`, `publisher` | As the data provider states them |
| `licence` | Verbatim from the provider. If it cannot be determined, the source is **not** registered |
| `citation` | The form required by the provider |
| `landing_page` | Where a reader can independently obtain the data |
| `selection_criteria` | One string per criterion, phrased so a reviewer can check compliance |
| `spatial_scope`, `temporal_scope` | The real coverage, not the intended coverage |
| `notes` | Known biases and limitations — this field is not optional |

### 3.2 Verify availability

```bash
python -m omics_wbe.cli check-sources
```

Missing files must be resolved before any analysis. The command prints the
selection criteria alongside availability so the criteria are reviewed at the
point of use, not only at registration.

### 3.3 Record provenance

Every stage writes a manifest containing the SHA-256 of each input and output.
Verify at any time:

```bash
python -m omics_wbe.cli verify
```

A `DRIFT` result means a file changed since the result was produced. **Any
published number whose manifest reports drift is withdrawn until re-run.**

### 3.4 Sequence archives (NCBI SRA / ENA / DDBJ)

`omics_wbe/ingest/sequence_archives.py` builds and executes the archive queries.

```bash
python -m omics_wbe.cli archives            # show the queries and probe connectivity
python -m omics_wbe.cli archives --search   # execute (requires outbound network access)
```

Selection criteria are encoded in `ArchiveQuery`; `describe()` emits the exact
Entrez and ENA query strings for the methods section.

**Critical distinction.** Archive records are *sequencing runs*, not quantified
biomarker concentrations. A run accession becomes a usable measurement only
after the steps enumerated by `plan_quantification()` — download, read QC, host
depletion, taxonomic or reference-based quantification, AMR profiling and
harmonisation. Absolute units additionally require a quantitative internal
standard spiked into the sequencing run. A run inventory must never be
presented as a measurement dataset.

DDBJ is covered by querying ENA: the three archives mirror each other under the
INSDC agreement.

### 3.5 Distinguish "unavailable" from "empty"

`ArchiveUnavailable` is raised for a network or authorisation failure and is
never converted into an empty result. "The archive holds no matching runs" and
"we could not reach the archive" are different scientific facts and must be
reported differently.

## 4. Acceptance criteria

- [ ] Source registered with licence, citation and selection criteria
- [ ] `check-sources` reports `OK`
- [ ] Connector emits the canonical schema and an ingest report counting every dropped row
- [ ] Unmapped assay targets are **counted and reported**, never silently dropped
- [ ] Manifest written and `verify` clean
- [ ] Known biases recorded in `notes` and carried into the report's limitations section

## 5. Records

`results/wbe/manifests/*.manifest.json` — retained for the life of the project
plus the retention period required by the funder.
