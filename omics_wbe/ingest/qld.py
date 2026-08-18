"""Queensland connector: qualitative detect / non-detect surveillance.

A second surveillance programme with a genuinely different upstream schema.
It publishes no concentrations, so it cannot enter the quantitative model; it
enters the canonical frame with ``concentration`` as ``NaN`` and the result
carried in ``detected``. Downstream code that needs a concentration therefore
excludes these rows by construction rather than by a hand-maintained filter.

It supports the urban/rural detection-frequency comparison the proposal calls
for, which the California data cannot: NWSS carries no urban/rural label.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import pandas as pd

_RESULT_MAP = {"detect": True, "detected": True, "non-detect": False, "not detected": False, "nondetect": False}


def load_qld(paths: Iterable[str | Path]) -> tuple[pd.DataFrame, dict[str, Any]]:
    frames: list[pd.DataFrame] = []
    report: dict[str, Any] = {"files": []}
    blank_rows = 0
    for path in paths:
        chunk = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
        chunk.columns = [c.strip().lstrip("﻿") for c in chunk.columns]
        # Several published quarters are padded to ~900k all-empty rows by the
        # spreadsheet they were exported from. Dropping them here keeps the
        # "unparseable" count in the report meaning what it says.
        blank = chunk.isna().all(axis=1)
        blank_rows += int(blank.sum())
        chunk = chunk[~blank]
        report["files"].append({
            "path": str(Path(path).name), "rows": int(len(chunk)), "blank_padding_rows": int(blank.sum()),
        })
        frames.append(chunk)

    raw = pd.concat(frames, ignore_index=True)
    report["blank_padding_rows_dropped"] = blank_rows
    report["rows_read"] = int(len(raw))

    result = raw["Result"].astype("string").str.strip().str.lower()
    report["unmapped_results"] = (
        result[~result.isin(_RESULT_MAP)].value_counts().head(10).to_dict()
    )

    df = pd.DataFrame({
        "source": "qld_wbe",
        "site_name": raw["Site"].astype("string").str.strip(),
        "collect_date": pd.to_datetime(raw["Sampling date"], dayfirst=True, errors="coerce"),
        "target": "sars_cov_2",
        "detected": result.map(_RESULT_MAP).astype("boolean"),
        "population_served": pd.to_numeric(raw["Site population"], errors="coerce"),
        "concentration": pd.NA,
        "unit": pd.NA,
    })
    df["site_id"] = df["site_name"]
    # "Upstream Location X" points are sub-catchment manholes, not plant influent.
    df["is_subcatchment"] = df["site_name"].str.contains("Upstream Location", case=False, na=False)

    keep = df["collect_date"].notna() & df["detected"].notna() & df["site_name"].notna()
    report["rows_dropped_unparseable"] = int((~keep).sum())
    df = df[keep].sort_values(["site_id", "collect_date"]).reset_index(drop=True)

    report["rows_kept"] = int(len(df))
    report["n_sites"] = int(df["site_id"].nunique())
    report["n_subcatchment_sites"] = int(df.loc[df["is_subcatchment"], "site_id"].nunique())
    report["detection_rate"] = float(df["detected"].mean())
    report["date_min"] = str(df["collect_date"].min().date()) if len(df) else None
    report["date_max"] = str(df["collect_date"].max().date()) if len(df) else None
    return df, report
