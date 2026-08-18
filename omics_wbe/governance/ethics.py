"""Data governance controls for wastewater surveillance outputs.

Wastewater surveillance is often described as inherently anonymous. It is not.
Anonymity is a property of the *catchment*, not of the method: a sewershed
serving a whole city reveals nothing about any individual, while an upstream
manhole serving one building, one prison wing or one student residence can
report on a group small enough to be identified — and the smaller and more
socially marked the group, the more a published result can stigmatise it.

This module makes that a mechanical control rather than a matter of individual
judgement at publication time:

* :func:`suppress_small_catchments` removes results for catchments below a
  population floor.
* :func:`suppress_sparse_region_weeks` removes region-weeks resting on too few
  sites or samples to be a community-level statement.
* :func:`flag_sensitive_sites` marks institutional catchments (correctional,
  educational, healthcare, workplace) for the additional review such settings
  require, since a population floor alone does not make a prison sewer line an
  acceptable publication.
* :func:`apply_publication_policy` runs all of them and returns a record of what
  was withheld, which belongs in the release documentation.

The defaults implement a *k*-anonymity-style floor. They are a starting point
for a research ethics committee to set, not a substitute for one, and they are
deliberately parameters rather than constants so the governing body's decision
is what the code executes.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from omics_wbe.config import AnalysisConfig, DEFAULT_CONFIG

#: Catchment-name patterns that indicate an institutional rather than a
#: community population. Matching is a prompt for review, never an automatic
#: clearance: an unmatched name is not evidence that a catchment is general.
#: Stems are suffixed with ``\w*`` deliberately. A pattern of ``\bcorrection\b``
#: does not match "Correctional Facility" - the single most common naming for
#: exactly the setting this is meant to catch - because the word boundary falls
#: after "correctional", not after "correction". Non-capturing groups avoid
#: pandas warning that the groups look like an extraction request.
SENSITIVE_SITE_PATTERNS: dict[str, str] = {
    "correctional": r"\b(?:prison\w*|correction\w*|jail\w*|detention|penitentiar\w*|remand|carceral)\b",
    "educational": r"\b(?:school\w*|universit\w*|college\w*|campus\w*|dormitor\w*|residence hall\w*|student\w*)\b",
    "healthcare": r"\b(?:hospital\w*|clinic\w*|medical cent\w*|nursing home\w*|care home\w*|hospice\w*)\b",
    "workplace": r"\b(?:factor(?:y|ies)|abattoir\w*|mine site|barrack\w*|labou?r camp\w*|plant site)\b",
    "upstream_subcatchment": r"\b(?:upstream|manhole\w*|sub-?catchment\w*|location [a-z])\b",
}


def flag_sensitive_sites(
    df: pd.DataFrame, *, name_col: str = "site_name", patterns: dict[str, str] | None = None
) -> pd.DataFrame:
    """Add ``sensitive_setting`` and ``sensitive_category`` columns."""
    patterns = patterns or SENSITIVE_SITE_PATTERNS
    names = df.get(name_col, pd.Series("", index=df.index)).astype("string").fillna("")
    category = pd.Series(pd.NA, index=df.index, dtype="string")
    for label, pattern in patterns.items():
        hit = names.str.contains(pattern, case=False, regex=True, na=False)
        category = category.mask(hit & category.isna(), label)
    out = df.copy()
    out["sensitive_category"] = category
    out["sensitive_setting"] = category.notna()
    return out


def suppress_small_catchments(
    df: pd.DataFrame,
    *,
    population_col: str = "population_served",
    min_population: int | None = None,
    config: AnalysisConfig = DEFAULT_CONFIG,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Withhold results for catchments below the population floor.

    Rows with an *unknown* population are suppressed too. An unverified
    denominator cannot demonstrate that the floor is met, and the failure mode
    of assuming it does is publishing a result about a group too small to be
    anonymous.
    """
    floor = min_population if min_population is not None else config.min_population_served
    pop = pd.to_numeric(df.get(population_col), errors="coerce")
    keep = pop.notna() & (pop >= floor)

    report = {
        "min_population_served": int(floor),
        "rows_in": int(len(df)),
        "rows_suppressed_small": int(((pop.notna()) & (pop < floor)).sum()),
        "rows_suppressed_unknown_population": int(pop.isna().sum()),
        "rows_retained": int(keep.sum()),
    }
    if "site_id" in df.columns:
        report["sites_suppressed"] = int(df.loc[~keep, "site_id"].nunique())
    return df.loc[keep].copy(), report


def suppress_sparse_region_weeks(
    df: pd.DataFrame,
    *,
    min_sites: int | None = None,
    min_samples: int = 1,
    config: AnalysisConfig = DEFAULT_CONFIG,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Withhold region-weeks resting on too little observation to publish."""
    floor = min_sites if min_sites is not None else config.min_sites_per_region_week
    sites = pd.to_numeric(df.get("n_sites", 1), errors="coerce").fillna(0)
    samples = pd.to_numeric(df.get("n_samples", 1), errors="coerce").fillna(0)
    keep = (sites >= floor) & (samples >= min_samples)
    return df.loc[keep].copy(), {
        "min_sites_per_region_week": int(floor),
        "min_samples_per_region_week": int(min_samples),
        "rows_in": int(len(df)),
        "rows_suppressed": int((~keep).sum()),
        "rows_retained": int(keep.sum()),
    }


def apply_publication_policy(
    df: pd.DataFrame,
    *,
    config: AnalysisConfig = DEFAULT_CONFIG,
    require_sensitive_review: bool = True,
    level: str = "site",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Run every suppression rule and return the release record.

    ``require_sensitive_review=True`` withholds institutional catchments pending
    explicit approval, rather than releasing them and relying on someone to
    notice afterwards.
    """
    report: dict[str, Any] = {"level": level, "rows_in": int(len(df))}
    out = df

    if level == "site":
        out = flag_sensitive_sites(out)
        report["sensitive_sites_flagged"] = (
            out.loc[out["sensitive_setting"], "sensitive_category"].value_counts().to_dict()
        )
        if require_sensitive_review:
            withheld = int(out["sensitive_setting"].sum())
            out = out.loc[~out["sensitive_setting"]].copy()
            report["rows_withheld_pending_sensitive_review"] = withheld
        out, report["small_catchment"] = suppress_small_catchments(out, config=config)
    else:
        out, report["sparse_region_week"] = suppress_sparse_region_weeks(out, config=config)

    report["rows_released"] = int(len(out))
    report["suppression_rate"] = (
        round(1 - len(out) / len(df), 4) if len(df) else 0.0
    )
    return out, report


def governance_statement(config: AnalysisConfig = DEFAULT_CONFIG) -> str:
    """The policy in prose, for inclusion in a data release or ethics annex."""
    return (
        "Publication policy in force for this analysis:\n"
        f"  * Sewersheds serving fewer than {config.min_population_served:,} people are suppressed "
        "from all released outputs, and catchments with no verified served population are treated "
        "as failing that floor rather than as meeting it.\n"
        f"  * A region-week must aggregate at least {config.min_sites_per_region_week} monitored "
        "site(s) to be released.\n"
        "  * Catchments identifiable as correctional, educational, healthcare or workplace settings, "
        "and upstream sub-catchment sampling points, are withheld pending explicit review by the "
        "governing research ethics committee.\n"
        "  * No individual-level data are collected, processed or stored at any stage. Where "
        "sequencing data are processed, human reads are removed before any onward sharing.\n"
        "  * These thresholds are configuration, not constants: the governing ethics committee sets "
        "them and the pipeline executes that decision."
    )
