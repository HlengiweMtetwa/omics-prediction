"""CDC NWSS connector: raw submissions -> canonical WBE measurement frame.

NWSS is a federated submission format, so the same column can mean different
things between laboratories. Everything that needs local knowledge to interpret
is resolved here and nowhere else; downstream modules only ever see the
canonical schema in :data:`omics_wbe.config.WBE_MEASUREMENT_COLUMNS`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from omics_wbe.biomarkers.catalog import BiomarkerCatalog, default_catalog
from omics_wbe.config import WBE_MEASUREMENT_COLUMNS

#: NWSS free-text booleans. Anything outside this map becomes NA, never False -
#: "we do not know whether inhibition was detected" is not "no inhibition".
_YES = {"yes", "y", "true", "1"}
_NO = {"no", "n", "false", "0"}

#: Unit strings seen in submissions, folded to canonical spellings.
_UNIT_CANONICAL = {
    "copies/l wastewater": "copies/L wastewater",
    "copies/L wastewater": "copies/L wastewater",
    "copies/g dry sludge": "copies/g dry sludge",
    "log10 copies/L wastewater": "log10 copies/L wastewater",
}

_MATRIX_CANONICAL = {
    "raw wastewater": "raw wastewater",
    "post grit removal": "post grit removal",
    "primary sludge": "primary sludge",
}

_USECOLS = [
    "wwtp_name", "facility_name", "county_names", "reporting_jurisdiction", "population_served",
    "sample_id", "sample_collect_date", "sample_matrix", "sample_location", "flow_rate",
    "pcr_target", "pcr_gene_target", "pcr_target_units", "pcr_target_avg_conc",
    "pcr_target_below_lod", "lod_sewage", "hum_frac_mic_conc", "hum_frac_mic_unit",
    "hum_frac_target_mic", "rec_eff_percent", "inhibition_detect", "ntc_amplify",
    "quality_flag", "qc_ignore", "analysis_ignore", "dashboard_ignore", "major_lab_method",
]


def _tri_bool(series: pd.Series) -> pd.Series:
    """Yes/no free text -> nullable boolean, with unknown staying unknown."""
    s = series.astype("string").str.strip().str.lower()
    out = pd.Series(pd.NA, index=series.index, dtype="boolean")
    out[s.isin(_YES)] = True
    out[s.isin(_NO)] = False
    return out


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _canonical_units(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip()
    return s.map(lambda v: _UNIT_CANONICAL.get(v, _UNIT_CANONICAL.get(str(v).lower(), pd.NA)))


def _canonical_matrix(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip().str.lower()
    return s.map(lambda v: _MATRIX_CANONICAL.get(v, pd.NA))


def _primary_county(series: pd.Series) -> pd.Series:
    """A sewershed may span counties; the first listed FIPS is the reporting county.

    Recorded rather than silently assumed - :func:`load_nwss` returns the count
    of multi-county sewersheds in its report so the assumption is visible.
    """
    return (
        series.astype("string")
        .str.split(",").str[0]
        .str.strip()
        .str.zfill(5)
        .replace({"<NA>": pd.NA, "nan": pd.NA, "00nan": pd.NA})
    )


def load_nwss(
    path: str | Path,
    catalog: BiomarkerCatalog | None = None,
    *,
    include_upstream: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Read an NWSS export and return ``(canonical_frame, ingest_report)``.

    The report is not decoration: it records how many rows were dropped and why,
    which assay targets failed to resolve against the catalogue, and how many
    sewersheds span multiple counties. Those numbers go straight into the run
    manifest and the methods section.
    """
    catalog = catalog or default_catalog()
    raw = pd.read_csv(path, usecols=lambda c: c in _USECOLS, low_memory=False)
    report: dict[str, Any] = {"rows_read": int(len(raw))}

    df = pd.DataFrame(index=raw.index)
    df["source"] = "nwss_ca"
    df["sample_id"] = raw["sample_id"].astype("string")
    df["site_name"] = raw["wwtp_name"].astype("string").fillna(raw["facility_name"].astype("string"))
    # sample_location distinguishes the plant influent from upstream manholes in
    # the same sewershed; they are different catchments and must not be pooled.
    location = raw["sample_location"].astype("string").str.strip().str.lower()
    df["site_id"] = (
        df["site_name"].fillna("unknown")
        + "|" + location.fillna("unknown")
        + "|" + raw["sample_matrix"].astype("string").fillna("unknown")
    )
    df["region_code"] = _primary_county(raw["county_names"])
    df["collect_date"] = pd.to_datetime(raw["sample_collect_date"], errors="coerce")
    df["gene_target"] = raw["pcr_gene_target"].astype("string")
    df["target"] = df["gene_target"].map(catalog.resolve_gene_target).astype("string")
    df["matrix"] = _canonical_matrix(raw["sample_matrix"])
    df["concentration"] = _numeric(raw["pcr_target_avg_conc"])
    df["unit"] = _canonical_units(raw["pcr_target_units"])
    df["below_lod"] = _tri_bool(raw["pcr_target_below_lod"])
    df["lod"] = _numeric(raw["lod_sewage"])
    df["normaliser_conc"] = _numeric(raw["hum_frac_mic_conc"])
    df["normaliser_target"] = (
        raw["hum_frac_target_mic"].astype("string").str.strip().str.lower()
        .map(lambda v: "pmmov" if isinstance(v, str) and "pepper mild mottle" in v else pd.NA)
    )
    df["recovery_pct"] = _numeric(raw["rec_eff_percent"])
    df["inhibition_detected"] = _tri_bool(raw["inhibition_detect"])
    df["ntc_amplified"] = _tri_bool(raw["ntc_amplify"])
    df["flow_rate"] = _numeric(raw["flow_rate"])
    df["population_served"] = _numeric(raw["population_served"])
    df["quality_flag"] = raw["quality_flag"].astype("string")
    df["lab_method"] = raw["major_lab_method"].astype("string")
    df["sample_location_kind"] = location

    # The submitting laboratory's own exclusion flags. Honoured, not second-guessed.
    ignore = pd.concat(
        [_tri_bool(raw[c]).fillna(False) for c in ("qc_ignore", "analysis_ignore")], axis=1
    ).any(axis=1)
    df["exclude_upstream"] = ignore

    # ---- filtering, each step counted --------------------------------------
    report["unmapped_gene_targets"] = (
        df.loc[df["target"].isna(), "gene_target"].value_counts().head(20).to_dict()
    )
    report["rows_unmapped_target"] = int(df["target"].isna().sum())
    report["rows_flagged_by_submitter"] = int(df["exclude_upstream"].sum())
    report["rows_missing_concentration"] = int(df["concentration"].isna().sum())
    report["rows_missing_date"] = int(df["collect_date"].isna().sum())
    report["rows_unknown_units"] = int(df["unit"].isna().sum())
    report["multi_county_sewershed_rows"] = int(
        raw["county_names"].astype("string").str.contains(",", na=False).sum()
    )

    keep = (
        df["target"].notna()
        & df["collect_date"].notna()
        & df["concentration"].notna()
        & df["unit"].notna()
        & df["region_code"].notna()
        & ~df["exclude_upstream"]
    )
    if not include_upstream:
        upstream = df["sample_location_kind"].eq("upstream").fillna(False)
        report["rows_upstream_excluded"] = int((keep & upstream).sum())
        keep &= ~upstream

    df = df.loc[keep].copy()

    # log10-reported concentrations are converted so one column means one thing.
    is_log = df["unit"].eq("log10 copies/L wastewater")
    report["rows_delogged"] = int(is_log.sum())
    df.loc[is_log, "concentration"] = np.power(10.0, df.loc[is_log, "concentration"])
    df.loc[is_log, "unit"] = "copies/L wastewater"

    df = df.sort_values(["site_id", "target", "collect_date"]).reset_index(drop=True)

    report["rows_kept"] = int(len(df))
    report["n_sites"] = int(df["site_id"].nunique())
    report["n_regions"] = int(df["region_code"].nunique())
    report["targets"] = df["target"].value_counts().to_dict()
    report["units"] = df["unit"].value_counts().to_dict()
    report["matrices"] = df["matrix"].value_counts(dropna=False).to_dict()
    report["date_min"] = str(df["collect_date"].min().date()) if len(df) else None
    report["date_max"] = str(df["collect_date"].max().date()) if len(df) else None

    return _order_columns(df), report


def _order_columns(df: pd.DataFrame) -> pd.DataFrame:
    extras = [c for c in df.columns if c not in WBE_MEASUREMENT_COLUMNS]
    ordered = [c for c in WBE_MEASUREMENT_COLUMNS if c in df.columns] + extras
    return df[ordered]
