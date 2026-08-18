"""Objective 3: does the wastewater signal produce *actionable* warnings?

A model with a good RMSE is not the same as a surveillance system that helps.
What a health department acts on is an alert, so this module evaluates alerts
directly:

* **EWMA control-chart alarms** on the wastewater signal, and the same rule on
  the clinical series, so the two are detected by identical logic and any lead
  time is a property of the data rather than of two differently-tuned detectors.
* **Lead time** between a wastewater alarm and the corresponding clinical alarm,
  reported as a distribution — the mean lead time of a surveillance system says
  much less than the fraction of events it caught early *at all*.
* **Alarm precision and recall** against clinically-defined surge events, with
  an explicit matching window.
* **Decision-curve net benefit**, which converts precision and recall into the
  quantity a public health decision actually turns on: whether acting on the
  alert is worth its cost at the threshold probability the decision-maker holds.

Every detector here runs causally: the control limits at week *t* are estimated
from weeks strictly before *t*.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from omics_wbe.config import AnalysisConfig, DEFAULT_CONFIG


def ewma_alarms(
    series: pd.Series,
    *,
    lam: float = 0.3,
    sigma_multiple: float = 2.0,
    burn_in: int = 8,
) -> pd.DataFrame:
    """Causal EWMA control chart. Returns statistic, limit and alarm per week.

    The control limit at each week uses the expanding mean and SD of *prior*
    observations only, so an alarm is something the system could genuinely have
    raised at the time.
    """
    s = pd.to_numeric(series, errors="coerce")
    ewma = s.ewm(alpha=lam, adjust=False).mean()

    past = s.shift(1)
    mu = past.expanding(min_periods=burn_in).mean()
    sd = past.expanding(min_periods=burn_in).std()
    # SD of the EWMA statistic under independence.
    ewma_sd = sd * np.sqrt(lam / (2 - lam))
    upper = mu + sigma_multiple * ewma_sd

    return pd.DataFrame({
        "value": s, "ewma": ewma, "centre": mu, "upper_limit": upper,
        "alarm": (ewma > upper).fillna(False),
    })


def _alarm_onsets(alarm: pd.Series) -> list[int]:
    """Positions where an alarm turns on. A run of alarm weeks is one event."""
    a = alarm.fillna(False).astype(bool).to_numpy()
    return list(np.flatnonzero(a & ~np.r_[False, a[:-1]]))


def lead_time_analysis(
    panel: pd.DataFrame,
    *,
    signal_col: str = "wbe_signal",
    clinical_col: str = "case_rate_per_100k",
    group_col: str = "region_code",
    date_col: str = "epiweek_end",
    config: AnalysisConfig = DEFAULT_CONFIG,
    match_window_weeks: int = 6,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Match wastewater alarms to clinical alarms and measure the gap.

    A wastewater alarm is matched to the first clinical alarm within
    ``match_window_weeks`` after it. Positive lead time means wastewater alarmed
    first. Unmatched wastewater alarms are counted as false alarms rather than
    dropped, because a system that alarms constantly would otherwise appear to
    have an excellent lead time.
    """
    rows = []
    per_region = []

    for region, group in panel.groupby(group_col):
        g = group.sort_values(date_col).set_index(date_col)
        full = pd.date_range(g.index.min(), g.index.max(), freq="W-SAT")
        g = g.reindex(full)

        wbe = ewma_alarms(g[signal_col], lam=config.ewma_lambda, sigma_multiple=config.alert_sigma)
        clin = ewma_alarms(g[clinical_col], lam=config.ewma_lambda, sigma_multiple=config.alert_sigma)

        wbe_onsets = _alarm_onsets(wbe["alarm"])
        clin_onsets = _alarm_onsets(clin["alarm"])
        if not clin_onsets:
            continue

        matched = 0
        for w in wbe_onsets:
            future = [c for c in clin_onsets if 0 <= c - w <= match_window_weeks]
            if future:
                lead = future[0] - w
                matched += 1
                rows.append({group_col: region, "wbe_alarm_week": full[w],
                             "clinical_alarm_week": full[future[0]], "lead_weeks": int(lead)})
            else:
                rows.append({group_col: region, "wbe_alarm_week": full[w],
                             "clinical_alarm_week": pd.NaT, "lead_weeks": np.nan})

        # A clinical event is "detected" if any wastewater alarm precedes it
        # within the window.
        detected = sum(
            1 for c in clin_onsets
            if any(0 <= c - w <= match_window_weeks for w in wbe_onsets)
        )
        per_region.append({
            group_col: region,
            "n_wbe_alarms": len(wbe_onsets),
            "n_clinical_events": len(clin_onsets),
            "n_matched": matched,
            "n_clinical_detected": detected,
            "precision": matched / len(wbe_onsets) if wbe_onsets else np.nan,
            "sensitivity": detected / len(clin_onsets) if clin_onsets else np.nan,
            "weeks_observed": int(len(full)),
        })

    events = pd.DataFrame(rows)
    regions = pd.DataFrame(per_region)
    leads = events["lead_weeks"].dropna() if len(events) else pd.Series(dtype=float)

    report: dict[str, Any] = {
        "match_window_weeks": match_window_weeks,
        "ewma_lambda": config.ewma_lambda,
        "alert_sigma": config.alert_sigma,
        "n_regions": int(len(regions)),
        "n_wbe_alarms": int(regions["n_wbe_alarms"].sum()) if len(regions) else 0,
        "n_clinical_events": int(regions["n_clinical_events"].sum()) if len(regions) else 0,
        "pooled_precision": float(regions["n_matched"].sum() / regions["n_wbe_alarms"].sum())
            if len(regions) and regions["n_wbe_alarms"].sum() else float("nan"),
        "pooled_sensitivity": float(regions["n_clinical_detected"].sum() / regions["n_clinical_events"].sum())
            if len(regions) and regions["n_clinical_events"].sum() else float("nan"),
    }
    if len(leads):
        report.update({
            "median_lead_weeks": float(leads.median()),
            "mean_lead_weeks": float(leads.mean()),
            "iqr_lead_weeks": [float(leads.quantile(0.25)), float(leads.quantile(0.75))],
            "pct_lead_ge_1_week": float((leads >= 1).mean()),
            "pct_simultaneous": float((leads == 0).mean()),
        })
    return events, {"summary": report, "per_region": regions.to_dict("records")}


def surge_labels(
    panel: pd.DataFrame,
    *,
    clinical_col: str = "case_rate_per_100k",
    group_col: str = "region_code",
    date_col: str = "epiweek_end",
    horizon: int = 2,
    growth_threshold: float = 0.5,
) -> pd.DataFrame:
    """Label the weeks a health department would want warning of.

    A surge is defined *relatively*: the log case rate rises by more than
    ``growth_threshold`` between week ``t`` and week ``t + horizon``. An
    absolute threshold would make the label mostly a function of which county
    it is, and of how much testing was available that year — neither of which is
    what an early-warning system is being asked to detect.

    ``growth_threshold=0.5`` on the log1p scale is roughly a 65% rise in the
    weekly case rate over the horizon.
    """
    out = []
    for region, group in panel.groupby(group_col):
        g = group.sort_values(date_col).set_index(date_col)
        full = pd.date_range(g.index.min(), g.index.max(), freq="W-SAT")
        g = g.reindex(full)
        log_rate = np.log1p(g[clinical_col].clip(lower=0))
        growth = log_rate.shift(-horizon) - log_rate
        out.append(pd.DataFrame({
            group_col: region, date_col: full,
            "surge": (growth > growth_threshold),
            "growth": growth,
        }))
    labels = pd.concat(out, ignore_index=True)
    labels["surge"] = labels["surge"].where(labels["growth"].notna())
    return labels


def alarm_metrics(y_true: pd.Series, y_score: pd.Series) -> dict[str, float]:
    """Discrimination and calibration for a surge-warning score."""
    from sklearn.metrics import (
        average_precision_score, brier_score_loss, roc_auc_score,
    )

    mask = pd.notna(y_true) & pd.notna(y_score)
    yt = np.asarray(y_true[mask], dtype=float)
    ys = np.asarray(y_score[mask], dtype=float)
    if len(np.unique(yt)) < 2:
        return {"n": int(len(yt)), "prevalence": float(yt.mean()) if len(yt) else float("nan"),
                "auroc": float("nan"), "auprc": float("nan"), "brier": float("nan")}
    out = {
        "n": int(len(yt)),
        "prevalence": float(yt.mean()),
        "auroc": float(roc_auc_score(yt, ys)),
        "auprc": float(average_precision_score(yt, ys)),
    }
    if 0.0 <= ys.min() and ys.max() <= 1.0:
        out["brier"] = float(brier_score_loss(yt, ys))
        out["brier_skill_vs_prevalence"] = float(
            1 - out["brier"] / brier_score_loss(yt, np.full_like(ys, yt.mean()))
        )
    return out


def decision_curve(
    y_true: pd.Series, y_prob: pd.Series, thresholds: np.ndarray | None = None
) -> pd.DataFrame:
    """Net benefit across threshold probabilities (Vickery decision-curve analysis).

    Net benefit at threshold ``p`` is::

        TP/n - FP/n * (p / (1 - p))

    which weights a false alarm by the odds at which the decision-maker would
    be indifferent. Compared against "alert always" and "alert never", it says
    whether acting on the model is better than either blanket policy — the
    question that decides whether a surveillance signal changes practice.
    """
    mask = pd.notna(y_true) & pd.notna(y_prob)
    yt = np.asarray(y_true[mask], dtype=float)
    yp = np.asarray(y_prob[mask], dtype=float)
    n = len(yt)
    if n == 0:
        return pd.DataFrame()

    thresholds = np.linspace(0.02, 0.6, 30) if thresholds is None else thresholds
    prevalence = yt.mean()
    rows = []
    for p in thresholds:
        alert = yp >= p
        tp = float(np.sum(alert & (yt == 1)))
        fp = float(np.sum(alert & (yt == 0)))
        odds = p / (1 - p)
        rows.append({
            "threshold": float(p),
            "net_benefit_model": tp / n - (fp / n) * odds,
            "net_benefit_alert_all": prevalence - (1 - prevalence) * odds,
            "net_benefit_alert_none": 0.0,
            "alert_rate": float(alert.mean()),
        })
    df = pd.DataFrame(rows)
    df["benefit_over_best_default"] = df["net_benefit_model"] - df[
        ["net_benefit_alert_all", "net_benefit_alert_none"]
    ].max(axis=1)
    return df
