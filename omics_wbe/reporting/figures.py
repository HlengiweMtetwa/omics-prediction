"""Figures for the technical report.

Matplotlib only, Agg backend, no seaborn: the figures must render identically in
CI and on a workstation with no display. Every figure returns its path so the
report can embed it and the manifest can hash it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from omics_wbe.config import FIGURES_DIR

PALETTE = {
    "wbe": "#1b6ca8", "clinical": "#c1440e", "wbe_ar": "#2e7d32",
    "baseline": "#7a7a7a", "accent": "#8e44ad", "muted": "#b0b0b0",
}
plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 130, "font.size": 9,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "figure.autolayout": True,
})


def _save(fig, name: str) -> str:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURES_DIR / name
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return str(path)


def plot_qc_waterfall(qc_report: dict[str, Any], name: str = "fig01_qc_waterfall.png") -> str:
    """How many measurements each QC rule removed."""
    rules = [r for r in qc_report["rules"] if r["severity"] == "fail" and r["n_violations"] > 0]
    rules.sort(key=lambda r: r["n_violations"], reverse=True)
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    labels = [f"{r['code']}\n{r['description'][:34]}" for r in rules]
    ax.bar(labels, [r["n_violations"] for r in rules], color=PALETTE["clinical"])
    ax.set_ylabel("measurements failing")
    ax.set_title(
        f"QC exclusions ({qc_report['n_pass']:,} of {qc_report['rows_in']:,} retained, "
        f"{qc_report['pass_rate']:.1%})"
    )
    ax.tick_params(axis="x", labelsize=6.5)
    return _save(fig, name)


def plot_target_coverage(region_week: pd.DataFrame, name: str = "fig02_target_coverage.png") -> str:
    """Region-weeks available per biomarker, over time."""
    fig, ax = plt.subplots(figsize=(7.6, 3.6))
    counts = (
        region_week.groupby([pd.Grouper(key="epiweek_end", freq="QE"), "target"])
        .size().unstack(fill_value=0)
    )
    order = counts.sum().sort_values(ascending=False).index
    bottom = np.zeros(len(counts))
    cmap = plt.get_cmap("tab10")
    for i, target in enumerate(order):
        ax.bar(counts.index, counts[target], bottom=bottom, width=70,
               label=target, color=cmap(i % 10))
        bottom += counts[target].to_numpy()
    ax.set_ylabel("region-weeks")
    ax.set_title("Multi-pathogen surveillance coverage by quarter")
    ax.legend(fontsize=6.2, ncol=3, loc="upper left")
    return _save(fig, name)


def plot_lag_correlation(pooled_by_lag: list[dict], name: str = "fig03_lag_correlation.png") -> str:
    """Wastewater-versus-cases correlation at each lead time."""
    df = pd.DataFrame(pooled_by_lag)
    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    ax.plot(df["lag_weeks"], df["median_rho"], "o-", color=PALETTE["wbe"], label="median across counties")
    ax.plot(df["lag_weeks"], df["mean_rho"], "s--", color=PALETTE["muted"], label="mean")
    best = df.loc[df["median_rho"].idxmax()]
    ax.axvline(best["lag_weeks"], color=PALETTE["clinical"], ls=":",
               label=f"peak at {int(best['lag_weeks'])} weeks")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel("wastewater lead (weeks) — positive means wastewater first")
    ax.set_ylabel("Spearman ρ with case rate")
    ax.set_title("Wastewater signal leads reported cases")
    ax.legend(fontsize=7)
    return _save(fig, name)


def plot_series_examples(
    panel: pd.DataFrame, regions: list[str] | None = None, name: str = "fig04_series.png"
) -> str:
    """Wastewater signal against case rate for the best-covered counties."""
    if regions is None:
        regions = (
            panel.groupby("region_code").size().sort_values(ascending=False).head(4).index.tolist()
        )
    fig, axes = plt.subplots(len(regions), 1, figsize=(7.6, 2.0 * len(regions)), sharex=True)
    axes = np.atleast_1d(axes)
    for ax, region in zip(axes, regions):
        g = panel[panel["region_code"] == region].sort_values("epiweek_end")
        label = g["region_name"].iloc[0] if "region_name" in g and len(g) else region
        ax.plot(g["epiweek_end"], g["wbe_signal"], color=PALETTE["wbe"], lw=1.3, label="wastewater (z)")
        ax2 = ax.twinx()
        ax2.plot(g["epiweek_end"], g["case_rate_per_100k"], color=PALETTE["clinical"],
                 lw=1.3, alpha=0.85, label="cases /100k")
        ax2.grid(False)
        ax.set_ylabel("WW z", color=PALETTE["wbe"], fontsize=8)
        ax2.set_ylabel("cases/100k", color=PALETTE["clinical"], fontsize=8)
        ax.set_title(f"{label} ({region})", fontsize=8.5, loc="left")
    axes[-1].set_xlabel("epidemiological week")
    fig.suptitle("Wastewater signal and reported case rate", y=1.001, fontsize=10)
    return _save(fig, name)


def plot_model_skill(summary: pd.DataFrame, name: str = "fig05_model_skill.png") -> str:
    """Forecast skill by feature block and horizon."""
    skill_col = next((c for c in summary.columns if c.startswith("skill_vs_")), None)
    if skill_col is None:
        raise ValueError("summary has no skill column")
    best = (
        summary[~summary["estimator"].str.startswith("baseline_")]
        .sort_values(skill_col, ascending=False)
        .groupby(["horizon", "block"], as_index=False).first()
    )
    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    blocks = ["wbe", "ar", "wbe+ar"]
    colours = [PALETTE["wbe"], PALETTE["clinical"], PALETTE["wbe_ar"]]
    horizons = sorted(best["horizon"].unique())
    width = 0.26
    for i, (block, colour) in enumerate(zip(blocks, colours)):
        vals = [
            best.loc[(best["horizon"] == h) & (best["block"] == block), skill_col].max()
            for h in horizons
        ]
        ax.bar(np.arange(len(horizons)) + (i - 1) * width, vals, width, label=block, color=colour)
    ax.set_xticks(np.arange(len(horizons)))
    ax.set_xticklabels([f"+{h} wk" for h in horizons])
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel(skill_col.replace("skill_vs_", "skill vs "))
    ax.set_title("Forecast skill by feature block (best estimator per cell)")
    ax.legend(fontsize=7.5)
    return _save(fig, name)


def plot_validation_optimism(optimism: pd.DataFrame, name: str = "fig06_optimism.png") -> str:
    """What random k-fold reports versus what rolling-origin reports."""
    df = optimism[~optimism["estimator"].str.startswith("baseline_")]
    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    ax.scatter(df["rmse_rolling_origin"], df["rmse_random_kfold"],
               c=[PALETTE["wbe"] if b == "wbe" else PALETTE["clinical"] if b == "ar"
                  else PALETTE["wbe_ar"] for b in df["block"]], s=34)
    lo = float(min(df["rmse_rolling_origin"].min(), df["rmse_random_kfold"].min()))
    hi = float(max(df["rmse_rolling_origin"].max(), df["rmse_random_kfold"].max()))
    ax.plot([lo, hi], [lo, hi], "k--", lw=0.9, label="equal (no optimism)")
    ax.set_xlabel("RMSE — rolling-origin CV (honest)")
    ax.set_ylabel("RMSE — random k-fold")
    ax.set_title("Random k-fold understates error on autocorrelated panels")
    ax.legend(fontsize=7.5)
    return _save(fig, name)


def plot_alert_performance(
    classification_summary: pd.DataFrame, decision_curve_df: pd.DataFrame,
    name: str = "fig07_alerts.png"
) -> str:
    """Surge-warning discrimination and net benefit side by side."""
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.4))

    piv = classification_summary.pivot_table(index="block", columns="estimator", values="auprc")
    piv.plot(kind="bar", ax=axes[0], width=0.78, colormap="viridis", legend=True)
    prevalence = float(classification_summary["prevalence"].median())
    axes[0].axhline(prevalence, color="k", ls="--", lw=0.9, label=f"prevalence {prevalence:.3f}")
    axes[0].set_ylabel("AUPRC")
    axes[0].set_title("Surge warning: precision-recall AUC")
    axes[0].legend(fontsize=6.5)
    axes[0].tick_params(axis="x", rotation=0)

    dc = decision_curve_df
    axes[1].plot(dc["threshold"], dc["net_benefit_model"], color=PALETTE["wbe"], label="model")
    axes[1].plot(dc["threshold"], dc["net_benefit_alert_all"], color=PALETTE["muted"],
                 ls="--", label="alert always")
    axes[1].axhline(0, color="k", lw=0.8, label="alert never")
    axes[1].set_ylim(min(-0.05, dc["net_benefit_model"].min() - 0.01),
                     dc["net_benefit_model"].max() + 0.02)
    axes[1].set_xlabel("decision threshold probability")
    axes[1].set_ylabel("net benefit")
    axes[1].set_title("Decision-curve analysis")
    axes[1].legend(fontsize=7)
    return _save(fig, name)


def plot_sensitivity(
    permutation: pd.DataFrame, perturbation: pd.DataFrame, name: str = "fig08_sensitivity.png"
) -> str:
    """Feature importance and input-perturbation response."""
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 3.6))

    top = permutation.head(10).iloc[::-1]
    colours = [PALETTE["wbe"] if f.startswith("wbe_") else PALETTE["clinical"] for f in top["feature"]]
    axes[0].barh(top["feature"], top["rmse_increase"], color=colours)
    axes[0].set_xlabel("RMSE increase when permuted")
    axes[0].set_title("Out-of-fold permutation importance")
    axes[0].tick_params(axis="y", labelsize=7)

    axes[1].plot(perturbation["shift"], perturbation["mean_prediction_change"],
                 "o-", color=PALETTE["accent"])
    axes[1].axhline(0, color="k", lw=0.8)
    axes[1].axvline(0, color="k", lw=0.8)
    axes[1].set_xlabel("shift applied to wastewater inputs (robust SD units)")
    axes[1].set_ylabel("mean change in predicted Δlog case rate")
    axes[1].set_title("Input perturbation response")
    return _save(fig, name)


def plot_specification_curve(spec: pd.DataFrame, name: str = "fig09_specification.png") -> str:
    """Headline metric under each defensible analysis specification."""
    df = spec.dropna(subset=["rmse"]).sort_values("rmse")
    fig, ax = plt.subplots(figsize=(6.6, 0.42 * len(df) + 1.6))
    ax.barh(df["specification"], df["rmse"], color=PALETTE["wbe"])
    ax.invert_yaxis()
    ax.set_xlabel("rolling-origin RMSE (Δlog case rate)")
    ax.set_title("Specification curve: does the result depend on an analysis choice?")
    ax.tick_params(axis="y", labelsize=7.5)
    for i, (_, row) in enumerate(df.iterrows()):
        ax.text(row["rmse"], i, f"  ρ={row['spearman']:.2f}", va="center", fontsize=6.8)
    return _save(fig, name)


def plot_urban_rural_detection(qld_weekly: pd.DataFrame, name: str = "fig10_qld_detection.png") -> str:
    """Detection frequency by catchment size in the Queensland programme."""
    df = qld_weekly.dropna(subset=["population_served"]).copy()
    bins = [0, 10_000, 50_000, 150_000, np.inf]
    labels = ["<10k\n(small/rural)", "10-50k", "50-150k", ">150k\n(large urban)"]
    df["size_band"] = pd.cut(df["population_served"], bins=bins, labels=labels)
    grouped = df.groupby("size_band", observed=True).agg(
        detect_rate=("detect_fraction", "mean"),
        n_site_weeks=("detect_fraction", "size"),
        n_sites=("site_id", "nunique"),
    ).reset_index()

    fig, ax = plt.subplots(figsize=(6.0, 3.4))
    ax.bar(grouped["size_band"].astype(str), grouped["detect_rate"], color=PALETTE["wbe"])
    for i, row in grouped.iterrows():
        ax.text(i, row["detect_rate"], f"  n={int(row['n_site_weeks'])}\n  {int(row['n_sites'])} sites",
                ha="center", va="bottom", fontsize=6.6)
    ax.set_ylabel("mean weekly detection fraction")
    ax.set_title("SARS-CoV-2 detection frequency by catchment size (Queensland)")
    ax.set_ylim(0, min(1.0, grouped["detect_rate"].max() * 1.45))
    return _save(fig, name)
