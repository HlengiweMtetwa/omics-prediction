"""Harmonisation of federated submission conventions.

NWSS is a *submission* format: contributing laboratories report the same
quantity under different conventions. Two of those conventions, discovered by
profiling the California submissions, would each silently destroy most of the
dataset if taken at face value:

**Recovery scale.** The dominant laboratory method reports process recovery as a
*ratio* (median 1.28) while others report a *percent* (median 51-75). Reading
the ratio group as percent makes 81% of the dataset look like it failed a
recovery acceptance window; reading the percent group as a ratio makes every
recovery look like 5000%. The scale is therefore inferred per submission group
and recorded, not assumed globally.

**Censoring flag.** 37,963 rows report a concentration of exactly zero with the
``pcr_target_below_lod`` flag left empty. Zero is not a measurement — it is a
non-detect whose flag was never populated. Treating an unset flag as "not
censored" would send every one of those rows to a QC failure; treating a zero
concentration as a real value would put a hard zero into a log transform.
Censoring is therefore *inferred* and the inference is marked, so the
sensitivity analysis can re-run without inferred censoring and show whether any
conclusion depended on it.

Both corrections are reported, never silent. The report goes into the manifest
and the methods section.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

#: Sentinel used by some submitters for "recovery control not performed".
RECOVERY_SENTINELS = (-1.0,)

#: A group whose median recovery is below this is reporting a ratio, not a
#: percent. The gap between the two populations is roughly two orders of
#: magnitude, so the threshold is not near any real boundary.
RATIO_MEDIAN_THRESHOLD = 5.0

#: Minimum group size before the scale is inferred from that group's own median.
MIN_GROUP_FOR_SCALE_INFERENCE = 30


def harmonise_recovery(
    df: pd.DataFrame,
    group_cols: tuple[str, ...] = ("source", "lab_method", "matrix"),
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Put every ``recovery_pct`` on a percent scale. Returns ``(frame, report)``.

    Groups too small to infer a scale from are left on the global scale and
    counted, rather than being rescaled on the strength of a handful of points.
    """
    out = df.copy()
    rec = pd.to_numeric(out["recovery_pct"], errors="coerce")

    sentinel = rec.isin(RECOVERY_SENTINELS)
    rec = rec.mask(sentinel)
    report: dict[str, Any] = {
        "recovery_sentinel_rows": int(sentinel.sum()),
        "groups": [],
    }

    present = [c for c in group_cols if c in out.columns]
    if not present:
        out["recovery_pct"] = rec
        out["recovery_scale"] = "unknown"
        return out, report

    keys = out[present].astype("string").fillna("NA").agg("|".join, axis=1)
    scale = pd.Series("percent", index=out.index, dtype="object")

    for key, idx in keys.groupby(keys).groups.items():
        vals = rec.loc[idx].dropna()
        if len(vals) < MIN_GROUP_FOR_SCALE_INFERENCE:
            inferred, median = "percent_assumed_small_group", float(vals.median()) if len(vals) else float("nan")
        elif float(vals.median()) < RATIO_MEDIAN_THRESHOLD:
            inferred, median = "ratio", float(vals.median())
        else:
            inferred, median = "percent", float(vals.median())
        scale.loc[idx] = inferred
        if inferred == "ratio":
            rec.loc[idx] = rec.loc[idx] * 100.0
        report["groups"].append({
            "group": key, "n": int(len(idx)), "n_with_recovery": int(len(vals)),
            "median_as_reported": round(median, 4) if median == median else None,
            "inferred_scale": inferred,
        })

    out["recovery_pct"] = rec
    out["recovery_scale"] = scale
    report["rows_rescaled_from_ratio"] = int((scale == "ratio").sum())
    report["recovery_median_after"] = float(rec.median()) if rec.notna().any() else None
    return out, report


def infer_censoring(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fill in unset below-LOD flags from non-positive concentrations.

    Adds ``censoring_inferred`` (bool) so every downstream step, and the
    sensitivity analysis, can see which censoring came from the submitter and
    which came from us.
    """
    out = df.copy()
    conc = pd.to_numeric(out["concentration"], errors="coerce")
    flag = out["below_lod"].astype("boolean") if "below_lod" in out else pd.Series(pd.NA, index=out.index, dtype="boolean")

    nonpositive = conc.le(0).fillna(False)
    inferred = nonpositive & flag.isna()
    contradiction = nonpositive & (flag == False)  # noqa: E712 - elementwise comparison

    out["below_lod"] = flag.copy()
    out.loc[inferred, "below_lod"] = True
    out["censoring_inferred"] = inferred

    report = {
        "rows_nonpositive_concentration": int(nonpositive.sum()),
        "rows_censoring_inferred": int(inferred.sum()),
        "rows_flag_contradicts_zero": int(contradiction.sum()),
        "rows_censored_by_submitter": int((flag == True).sum()),  # noqa: E712
        "rows_censoring_flag_still_missing": int(out["below_lod"].isna().sum()),
    }
    return out, report


def harmonise(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Run every harmonisation step in order. Returns ``(frame, combined_report)``."""
    out, rec_report = harmonise_recovery(df)
    out, cen_report = infer_censoring(out)
    return out, {"recovery": rec_report, "censoring": cen_report}
