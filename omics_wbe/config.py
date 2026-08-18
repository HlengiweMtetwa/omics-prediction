"""Central configuration: paths, canonical schemas, analysis constants.

Every path is derived from ``PROJECT_ROOT`` so the package behaves the same
whether it is imported from the repository root, from a test, or from a
Snakemake rule executing in a different working directory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.environ.get("OMICS_WBE_DATA_DIR", PROJECT_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
RESULTS_DIR = Path(os.environ.get("OMICS_WBE_RESULTS_DIR", PROJECT_ROOT / "results" / "wbe"))
FIGURES_DIR = RESULTS_DIR / "figures"
TABLES_DIR = RESULTS_DIR / "tables"
REPORTS_DIR = RESULTS_DIR / "reports"

#: Single seed for every stochastic step in the project. Recorded in run manifests.
RANDOM_SEED = 20240501


def ensure_dirs() -> None:
    """Create every output directory. Safe to call repeatedly."""
    for d in (RAW_DIR, INTERIM_DIR, PROCESSED_DIR, RESULTS_DIR, FIGURES_DIR, TABLES_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# Canonical schemas
# --------------------------------------------------------------------------
# Every ingest connector, whatever the upstream format, emits one of these two
# frames. Adding a new surveillance programme means writing a connector, not
# touching anything downstream of it.

#: One row = one measurement of one target in one wastewater sample.
WBE_MEASUREMENT_COLUMNS = [
    "sample_id",            # str  - unique within source
    "source",               # str  - provenance tag, e.g. "nwss_ca"
    "site_id",              # str  - sewershed / treatment plant identifier
    "site_name",            # str
    "region_code",          # str  - county FIPS or equivalent admin unit
    "collect_date",         # datetime64[ns]
    "target",               # str  - biomarker_id from the catalogue
    "gene_target",          # str  - assay-level target (n1, InfA1, ...)
    "matrix",               # str  - raw wastewater | primary sludge | post grit removal
    "concentration",        # float - as reported
    "unit",                 # str  - copies/L wastewater | copies/g dry sludge
    "below_lod",            # bool
    "lod",                  # float - limit of detection in `unit`, may be NaN
    "normaliser_conc",      # float - PMMoV (or other faecal marker) in same unit
    "normaliser_target",    # str
    "recovery_pct",         # float - process recovery control, percent
    "inhibition_detected",  # bool
    "ntc_amplified",        # bool
    "flow_rate",            # float - MGD, may be NaN
    "population_served",    # float
    "quality_flag",         # str - upstream free-text flag
    "exclude_upstream",     # bool - upstream told us not to analyse this row
]

#: One row = one region-day of routine clinical surveillance.
HEALTH_RECORD_COLUMNS = [
    "source",
    "region_code",
    "region_name",
    "date",
    "indicator",            # str - e.g. "covid_cases"
    "count",                # float - raw daily count
    "count_avg7",           # float - 7-day rolling average
    "rate_avg7_per_100k",   # float
]


@dataclass(frozen=True)
class AnalysisConfig:
    """Knobs for the analysis. Serialised into every run manifest."""

    # --- QC gating -------------------------------------------------------
    recovery_min_pct: float = 5.0
    recovery_max_pct: float = 200.0
    #: Below-LOD values are substituted with lod / sqrt(2) (Hornung & Reed 1990).
    censored_substitution: str = "lod_over_sqrt2"

    # --- normalisation ---------------------------------------------------
    #: Primary metric is target/faecal-marker ratio; it is dimensionless and so
    #: comparable across the liquid and solid matrices NWSS mixes together.
    primary_metric: str = "log10_ratio_pmmov"
    #: Model features use the *causal* (expanding-window) standardisation.
    #: The retrospective variant standardises each sample partly by measurements
    #: taken years later, which no forecaster could have had.
    signal_variant: str = "zc"
    #: Winsorisation limit on the standardised signal, in robust SD units.
    #: A robust z-score of a series containing an epidemic excursion is heavily
    #: tailed - the post-Omicron collapse reaches -27 here - and a penalised
    #: linear model is destroyed by those tails while a tree model is untouched.
    #: 3 is the conventional control-chart limit. The specification curve reports
    #: performance across this choice rather than resting on it.
    signal_clip: float = 3.0

    # --- temporal aggregation -------------------------------------------
    #: Epidemiological week ending Saturday, matching US MMWR convention.
    week_anchor: str = "W-SAT"
    min_samples_per_site_week: int = 1

    # --- governance ------------------------------------------------------
    #: Sewersheds smaller than this are suppressed from any published output.
    min_population_served: int = 3000
    #: A region-week must aggregate at least this many distinct sites to publish.
    min_sites_per_region_week: int = 1

    # --- modelling -------------------------------------------------------
    max_lag_weeks: int = 4
    forecast_horizons: tuple = (0, 1, 2)
    n_cv_splits: int = 5
    #: Weeks of gap between train and test in rolling-origin CV, to stop a
    #: 4-week lag feature seeing its own future target.
    cv_gap_weeks: int = 4
    conformal_alpha: float = 0.2  # -> 80% prediction interval

    # --- alerting --------------------------------------------------------
    ewma_lambda: float = 0.3
    alert_sigma: float = 2.0
    #: Clinical "surge" threshold, cases per 100k per day (7-day average).
    surge_threshold_per_100k: float = 20.0

    seed: int = RANDOM_SEED
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        out = {}
        for k, v in self.__dict__.items():
            out[k] = list(v) if isinstance(v, tuple) else v
        return out


DEFAULT_CONFIG = AnalysisConfig()
