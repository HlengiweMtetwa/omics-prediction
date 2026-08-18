"""Quality-control rule engine for wastewater measurements.

The proposal commits to "regular quality control checks throughout the data
mining and analytical phases". This module makes those checks a declared,
versioned, testable list rather than ad-hoc filtering scattered through an
analysis script.

Two severities:

``fail``
    The measurement cannot be interpreted. Excluded from analysis.
``warn``
    The measurement is usable but carries a caveat. Retained and flagged, so
    a sensitivity analysis can re-run without warned rows and show whether any
    conclusion depended on them.

Every rule reports how many rows it caught. A QC step that silently drops rows
is indistinguishable from a bug.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

from omics_wbe.config import AnalysisConfig, DEFAULT_CONFIG


@dataclass(frozen=True)
class QCRule:
    code: str
    severity: str            # "fail" | "warn"
    description: str
    rationale: str
    #: Returns a boolean Series that is True where the rule is VIOLATED.
    predicate: Callable[[pd.DataFrame, AnalysisConfig], pd.Series]

    def evaluate(self, df: pd.DataFrame, config: AnalysisConfig) -> pd.Series:
        violated = self.predicate(df, config)
        return pd.Series(violated, index=df.index).fillna(False).astype(bool)


def _f(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _bool(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df:
        return pd.Series(False, index=df.index)
    return df[column].astype("boolean").fillna(False).astype(bool)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def _ntc_amplified(df, cfg):
    return _bool(df, "ntc_amplified")


def _inhibition(df, cfg):
    return _bool(df, "inhibition_detected")


def _recovery_out_of_range(df, cfg):
    rec = _f(df.get("recovery_pct", pd.Series(np.nan, index=df.index)))
    return rec.notna() & ((rec < cfg.recovery_min_pct) | (rec > cfg.recovery_max_pct))


def _recovery_missing(df, cfg):
    return _f(df.get("recovery_pct", pd.Series(np.nan, index=df.index))).isna()


def _negative_concentration(df, cfg):
    return _f(df["concentration"]) < 0


def _zero_not_flagged(df, cfg):
    """A non-positive concentration explicitly flagged as NOT below LOD.

    A genuine contradiction between two submitted fields. An *unset* flag on a
    zero concentration is not a contradiction, it is an unpopulated flag, and is
    resolved upstream by :func:`omics_wbe.normalize.harmonise.infer_censoring`.
    Running this rule on unharmonised data will therefore fire on tens of
    thousands of ordinary non-detects.
    """
    conc = _f(df["concentration"])
    below = df.get("below_lod", pd.Series(pd.NA, index=df.index)).astype("boolean")
    return conc.le(0).fillna(False) & (below == False)  # noqa: E712 - elementwise


def _lod_flag_inconsistent(df, cfg):
    """Flagged below-LOD while reporting a concentration above the stated LOD.

    Common in federated submissions where the reported LOD is an assay-level
    constant and the flag is set per-run. Warn rather than fail: the censoring
    step trusts the flag, and this records how often the two disagree.
    """
    conc, lod = _f(df["concentration"]), _f(df.get("lod", pd.Series(np.nan, index=df.index)))
    below = df.get("below_lod", pd.Series(pd.NA, index=df.index)).astype("boolean").fillna(False)
    return below.astype(bool) & lod.notna() & (conc > lod)


def _normaliser_missing(df, cfg):
    return _f(df.get("normaliser_conc", pd.Series(np.nan, index=df.index))).isna()


def _normaliser_nonpositive(df, cfg):
    n = _f(df.get("normaliser_conc", pd.Series(np.nan, index=df.index)))
    return n.notna() & (n <= 0)


def _analytical_replicate(df, cfg):
    """More than one measurement of the same target in the same sample.

    In these submissions that is an analytical replicate (the same gene target
    assayed twice) or a multi-gene assay (n1 and n2 both quantifying
    SARS-CoV-2) - not a data error. Dropping the extra rows would discard real
    measurement-uncertainty information, so this is a warning and the rows are
    collapsed on the log scale by
    :func:`omics_wbe.normalize.wastewater.collapse_replicates`.
    """
    keys = [k for k in ("source", "sample_id", "target") if k in df]
    if len(keys) < 2:
        return pd.Series(False, index=df.index)
    return df.duplicated(keys, keep=False) & df["sample_id"].notna()


def _robust_outlier(df, cfg):
    """|modified z| > 5 within a site x target series, on log10 concentration.

    Median/MAD rather than mean/SD: an outlier detector that uses the mean is
    dragged by the very points it is meant to find. Requires at least 10
    observations in the group, otherwise the MAD is not estimable.
    """
    conc = _f(df["concentration"])
    logc = np.log10(conc.where(conc > 0))
    if "site_id" not in df or "target" not in df:
        return pd.Series(False, index=df.index)
    grp = logc.groupby([df["site_id"], df["target"]])
    med = grp.transform("median")
    mad = grp.transform(lambda s: (s - s.median()).abs().median())
    n = grp.transform("count")
    scaled = 0.6745 * (logc - med) / mad.replace(0, np.nan)
    return (n >= 10) & scaled.abs().gt(5)


def _implausible_population(df, cfg):
    pop = _f(df.get("population_served", pd.Series(np.nan, index=df.index)))
    return pop.notna() & (pop <= 0)


RULES: tuple[QCRule, ...] = (
    QCRule("QC001", "fail", "No-template control amplified",
           "A contaminated run cannot distinguish target from carry-over.", _ntc_amplified),
    QCRule("QC002", "fail", "PCR inhibition detected",
           "Inhibition biases quantification downward by an unknown factor.", _inhibition),
    QCRule("QC003", "fail", "Process recovery outside acceptable range",
           "Recovery outside the acceptance window means the extraction did not behave as characterised.",
           _recovery_out_of_range),
    QCRule("QC004", "fail", "Negative reported concentration",
           "Physically impossible; indicates a reporting or unit error.", _negative_concentration),
    QCRule("QC005", "fail", "Non-positive concentration explicitly flagged as NOT below LOD",
           "The concentration and censoring fields contradict each other. Requires harmonised input.",
           _zero_not_flagged),
    QCRule("QC006", "fail", "Non-positive faecal normaliser concentration",
           "A zero or negative normaliser makes the normalised ratio undefined.", _normaliser_nonpositive),

    QCRule("QC008", "fail", "Non-positive population served",
           "Per-capita normalisation and governance suppression both need a real denominator.",
           _implausible_population),
    QCRule("QC007", "warn", "Analytical replicate present for this sample and target",
           "Replicates carry measurement uncertainty and are collapsed on the log scale, not discarded.",
           _analytical_replicate),
    QCRule("QC010", "warn", "No process recovery control reported",
           "Recovery-uncorrected values are comparable within a laboratory but not between laboratories.",
           _recovery_missing),
    QCRule("QC011", "warn", "Below-LOD flag inconsistent with reported concentration",
           "Records how often the submitted flag and the submitted LOD disagree.", _lod_flag_inconsistent),
    QCRule("QC012", "warn", "Faecal normaliser not measured",
           "Row can only be used on the unnormalised metric.", _normaliser_missing),
    QCRule("QC013", "warn", "Robust outlier within site and target series",
           "Flags probable transcription or dilution-event artefacts without deleting real extremes.",
           _robust_outlier),
)


def run_qc(
    df: pd.DataFrame,
    config: AnalysisConfig = DEFAULT_CONFIG,
    rules: tuple[QCRule, ...] = RULES,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply every rule. Returns ``(annotated_frame, qc_report)``.

    The frame gains one boolean column per rule code plus ``qc_pass`` and
    ``qc_warn``. Nothing is dropped here — filtering is the caller's decision,
    made visibly, via :func:`apply_qc_filter`.
    """
    out = df.copy()
    report: dict[str, Any] = {"rows_in": int(len(df)), "rules": []}

    fail = pd.Series(False, index=out.index)
    warn = pd.Series(False, index=out.index)
    for rule in rules:
        violated = rule.evaluate(out, config)
        out[rule.code] = violated
        if rule.severity == "fail":
            fail |= violated
        else:
            warn |= violated
        report["rules"].append({
            "code": rule.code, "severity": rule.severity, "description": rule.description,
            "n_violations": int(violated.sum()),
            "pct_violations": round(100.0 * violated.mean(), 4) if len(out) else 0.0,
        })

    out["qc_pass"] = ~fail
    out["qc_warn"] = warn
    report["n_fail"] = int(fail.sum())
    report["n_warn_only"] = int((warn & ~fail).sum())
    report["n_pass"] = int((~fail).sum())
    report["pass_rate"] = round(float((~fail).mean()), 4) if len(out) else 0.0
    if "target" in out:
        report["pass_rate_by_target"] = (
            out.groupby("target")["qc_pass"].mean().round(4).to_dict()
        )
    return out, report


def apply_qc_filter(df: pd.DataFrame, *, drop_warnings: bool = False) -> pd.DataFrame:
    """Keep QC-passing rows. ``drop_warnings=True`` powers the QC sensitivity run."""
    keep = df["qc_pass"]
    if drop_warnings:
        keep = keep & ~df["qc_warn"]
    return df.loc[keep].copy()


def qc_rule_table() -> pd.DataFrame:
    """The rule set as a table, for the SOP annex."""
    return pd.DataFrame([
        {"code": r.code, "severity": r.severity, "check": r.description, "rationale": r.rationale}
        for r in RULES
    ])
