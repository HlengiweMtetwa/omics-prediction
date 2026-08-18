"""Public health record connector: routine clinical surveillance series.

Objective 2 requires integrating wastewater signals with public health records.
The NYT county series stands in for the notifiable-disease register a health
department would supply: same shape (region x date x indicator x count), same
biases, same joins.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from omics_wbe.config import HEALTH_RECORD_COLUMNS

_GEOID = re.compile(r"^USA-(\d{5})$")


def _fips_from_geoid(series: pd.Series) -> pd.Series:
    return series.astype("string").str.extract(_GEOID, expand=False)


def load_nyt_counties(
    paths: Iterable[str | Path],
    *,
    state: str | None = "California",
    indicator: str = "covid_cases",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Read NYT rolling-average county files into the canonical health frame.

    ``cases_avg_per_100k`` is the analysis target rather than the raw daily
    ``cases``: daily counts carry a strong weekday reporting cycle and negative
    values where a health department reconciles a backlog, neither of which is
    epidemiological signal.
    """
    frames = []
    report: dict[str, Any] = {"files": []}
    for path in paths:
        chunk = pd.read_csv(path, usecols=["date", "geoid", "county", "state", "cases", "cases_avg", "cases_avg_per_100k"])
        report["files"].append({"path": str(path), "rows": int(len(chunk))})
        frames.append(chunk)

    raw = pd.concat(frames, ignore_index=True)
    report["rows_read"] = int(len(raw))

    if state is not None:
        raw = raw[raw["state"] == state]
        report["rows_after_state_filter"] = int(len(raw))

    fips = _fips_from_geoid(raw["geoid"])
    report["rows_unresolvable_geoid"] = int(fips.isna().sum())
    raw = raw[fips.notna()].copy()
    raw["region_code"] = fips[fips.notna()]

    df = pd.DataFrame({
        "source": "nyt_counties",
        "region_code": raw["region_code"].astype("string"),
        "region_name": raw["county"].astype("string"),
        "date": pd.to_datetime(raw["date"], errors="coerce"),
        "indicator": indicator,
        "count": pd.to_numeric(raw["cases"], errors="coerce"),
        "count_avg7": pd.to_numeric(raw["cases_avg"], errors="coerce"),
        "rate_avg7_per_100k": pd.to_numeric(raw["cases_avg_per_100k"], errors="coerce"),
    })

    df = df[df["date"].notna()]
    # Duplicate region-days would silently double-weight a county in the join.
    dupes = df.duplicated(["region_code", "date", "indicator"], keep="first")
    report["duplicate_region_days_dropped"] = int(dupes.sum())
    df = df[~dupes]

    df = df.sort_values(["region_code", "date"]).reset_index(drop=True)
    report["rows_kept"] = int(len(df))
    report["n_regions"] = int(df["region_code"].nunique())
    report["date_min"] = str(df["date"].min().date()) if len(df) else None
    report["date_max"] = str(df["date"].max().date()) if len(df) else None
    report["negative_daily_counts"] = int((df["count"] < 0).sum())
    report["missing_rate_avg7"] = int(df["rate_avg7_per_100k"].isna().sum())

    return df[HEALTH_RECORD_COLUMNS], report
