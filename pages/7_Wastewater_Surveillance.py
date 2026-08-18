"""Operational wastewater surveillance dashboard.

Presentation only. Every number comes from `omics_wbe.surveillance.dashboard`,
which is tested without a Streamlit runtime — the same layering the rest of this
application follows.

Deliberately not behind the registry login: this page shows only
governance-screened, aggregate surveillance outputs, which is exactly the
material a public health programme is meant to be able to publish. Nothing here
touches the registry database or any individual-level record.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from omics_wbe.config import DEFAULT_CONFIG
from omics_wbe.surveillance.dashboard import (
    STATUS_DESCRIPTIONS, build_snapshot, catalog_view, load_region_week,
    model_performance_card, pathogen_activity, target_timeseries,
)

st.set_page_config(page_title="Wastewater Surveillance", layout="wide")
st.title("Wastewater surveillance")

STATUS_BADGE = {
    "alert": "🔴 alert", "watch": "🟠 watch", "normal": "🟢 normal",
    "no_recent_data": "⚪ no recent data", "insufficient_history": "⚫ too little history",
}


@st.cache_data(show_spinner="Loading surveillance panel…")
def _load():
    return load_region_week()


region_week = _load()
if region_week is None:
    st.error(
        "No analysis panel found. Build it first:\n\n"
        "```bash\npython -m omics_wbe.cli check-sources\npython -m omics_wbe.cli run --force\n```"
    )
    st.stop()

# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------
weeks = sorted(pd.to_datetime(region_week["epiweek_end"]).unique())
with st.sidebar:
    st.header("View")
    as_of = st.select_slider(
        "Reporting week", options=weeks, value=weeks[-1],
        format_func=lambda d: pd.Timestamp(d).date().isoformat(),
        help="Rewind to reconstruct the view the system would have shown then. "
             "Status is computed causally, so no later data leaks in.",
    )
    staleness = st.slider("Staleness window (weeks)", 1, 8, 3,
                          help="Beyond this, a catchment is reported as unknown, not normal.")
    apply_governance = st.checkbox(
        "Apply publication governance", value=True,
        help="Suppresses catchments below the population floor and sparse region-weeks. "
             "Disable only for internal review.",
    )

snapshot = build_snapshot(
    region_week, as_of=as_of, staleness_weeks=staleness, apply_governance=apply_governance
)

if not snapshot.is_live:
    st.warning(
        f"**Retrospective research extract — not a live feed.** The latest week in this "
        f"dataset is **{snapshot.as_of.date()}**. Nothing on this page reflects current "
        "conditions anywhere.",
        icon="⚠️",
    )

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
counts = snapshot.status_counts()
cols = st.columns(5)
for col, key in zip(cols, ("alert", "watch", "normal", "no_recent_data", "insufficient_history")):
    col.metric(STATUS_BADGE[key], counts[key])

st.caption(" · ".join(f"**{STATUS_BADGE[k]}** {v}" for k, v in STATUS_DESCRIPTIONS.items()))

attention = snapshot.needing_attention()
st.subheader(f"Needs attention ({len(attention)} catchment-target pairs)")
if attention.empty:
    st.success("No catchment is above its control limit this week.")
else:
    display = attention.assign(status=attention["status"].map(STATUS_BADGE))
    st.dataframe(
        display[[
            "status", "target", "region_code", "signal", "trend_4wk",
            "percentile_in_own_history", "n_sites", "population_covered",
        ]].rename(columns={
            "region_code": "county (FIPS)", "signal": "signal (robust z)",
            "trend_4wk": "4-week change", "percentile_in_own_history": "percentile of own history",
            "n_sites": "sites", "population_covered": "population",
        }),
        width="stretch", hide_index=True,
    )
    st.caption(
        "The signal is a within-catchment standardised ratio to a faecal marker. It is **not** "
        "a case count and must never be reported as one."
    )

# ---------------------------------------------------------------------------
# Pathogens
# ---------------------------------------------------------------------------
st.subheader("Pathogen activity")
activity = pathogen_activity(region_week, as_of=as_of, weeks=8)
if activity.empty:
    st.info("No pathogen reported in the last 8 weeks.")
else:
    left, right = st.columns([2, 3])
    with left:
        st.dataframe(
            activity.rename(columns={
                "target": "pathogen",
                "percentile_of_own_history": "percentile of own history",
                "n_regions_reporting": "counties reporting",
                "mean_detect_fraction": "detection rate",
            })[["pathogen", "percentile of own history", "counties reporting", "detection rate"]],
            width="stretch", hide_index=True,
        )
        st.caption(
            "Each pathogen is scored against **its own** history. Comparing raw values between "
            "pathogens would be meaningless — different shedding rates, assays and detection limits."
        )
    with right:
        fig, ax = plt.subplots(figsize=(6, 0.4 * len(activity) + 1.2))
        ax.barh(activity["target"], activity["percentile_of_own_history"], color="#1b6ca8")
        ax.axvline(0.9, color="#c1440e", ls="--", lw=1, label="90th percentile")
        ax.set_xlim(0, 1)
        ax.set_xlabel("percentile of that pathogen's own history")
        ax.legend(fontsize=7, loc="lower right")
        ax.invert_yaxis()
        st.pyplot(fig, width="stretch")
        plt.close(fig)

# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------
st.subheader("Trend")
target = st.selectbox("Pathogen", snapshot.targets,
                      index=snapshot.targets.index("sars_cov_2") if "sars_cov_2" in snapshot.targets else 0)
# Default to the best-*covered* counties, not whichever happen to be alerting.
# Alerting catchments are often single-site series with sparse history, which
# makes for a chart that shows spikes on an empty axis rather than a trend.
coverage_rank = (
    region_week[region_week["target"] == target]
    .groupby("region_code")["epiweek_end"].nunique().sort_values(ascending=False)
)
available = sorted(coverage_rank.index)
default = list(coverage_rank.head(5).index)
regions = st.multiselect(
    "Counties (FIPS)", available, default=default,
    help="Defaults to the five counties with the longest reporting history for this pathogen.",
)

if regions:
    wide = target_timeseries(region_week, target=target, regions=regions)
    wide = wide[wide.index <= pd.Timestamp(as_of)]
    fig, ax = plt.subplots(figsize=(11, 3.6))
    for column in wide.columns:
        ax.plot(wide.index, wide[column], lw=1.4, label=column)
    ax.axhline(0, color="k", lw=0.7)
    ax.set_ylabel("signal (robust z)")
    ax.set_xlabel("epidemiological week")
    ax.legend(fontsize=7, ncol=min(len(regions), 6))
    ax.grid(alpha=0.25)
    st.pyplot(fig, width="stretch")
    plt.close(fig)
else:
    st.info("Select at least one county.")

# ---------------------------------------------------------------------------
# How much to trust this
# ---------------------------------------------------------------------------
st.subheader("How much to trust this")
card = model_performance_card()
if not card.get("available"):
    st.info(card.get("reason", "Model performance not available."))
else:
    a, b, c, d = st.columns(4)
    a.metric("Lead over reported cases", f"{card['lead_weeks']} wk" if card.get("lead_weeks") else "—",
             help=f"Peak median Spearman ρ = {card.get('lead_correlation', float('nan')):.2f}")
    b.metric("Surge-warning AUPRC",
             f"{card['surge_auprc']:.3f}" if card.get("surge_auprc") else "—",
             help=f"Base rate {card.get('surge_base_rate', float('nan')):.3f}")
    if card.get("clinical_only_auprc"):
        c.metric("vs clinical data alone", f"{card['clinical_only_auprc']:.3f}",
                 delta=f"{card['surge_auprc'] - card['clinical_only_auprc']:+.3f}")
    d.metric("Median alarm lead",
             f"{card['median_alarm_lead_weeks']} wk" if card.get("median_alarm_lead_weeks") else "—")

    if card.get("operating_points"):
        st.markdown("**Choose an alert threshold against your response capacity**")
        ops = pd.DataFrame(card["operating_points"])
        st.dataframe(
            ops[["threshold", "precision", "recall", "specificity", "alerts_per_100_region_weeks"]]
            .rename(columns={"alerts_per_100_region_weeks": "alerts per 100 county-weeks"}).round(3),
            width="stretch", hide_index=True,
        )

    st.error("**Limits of this signal**\n\n" + "\n".join(f"- {c}" for c in card["caveats"]), icon="🛑")

# ---------------------------------------------------------------------------
# Programme + governance
# ---------------------------------------------------------------------------
with st.expander("Programme coverage and governance"):
    a, b, c = st.columns(3)
    a.metric("Counties", snapshot.coverage["n_regions"])
    b.metric("Pathogens", snapshot.coverage["n_targets"])
    population = snapshot.coverage.get("population_covered")
    c.metric("Population covered", f"{population:,.0f}" if population else "—")

    st.json(snapshot.suppression)
    st.caption(
        "Suppression is applied before anything reaches this page. A catchment below the "
        "population floor cannot be displayed by disabling a filter here."
    )

with st.expander("Biomarker catalogue"):
    catalogue = catalog_view()
    tier = st.multiselect("Evidence tier", sorted(catalogue["evidence_tier"].unique()),
                          default=["established", "emerging"])
    view = catalogue[catalogue["evidence_tier"].isin(tier)] if tier else catalogue
    st.dataframe(
        view[["biomarker_id", "name", "omics_layer", "disease_class", "evidence_tier",
              "usable_for_inference", "assay", "caveats"]],
        width="stretch", hide_index=True,
    )
    st.caption(
        "`usable_for_inference` is false for prospective markers. They are listed because the "
        "open question is part of the scientific record, not because they support a claim."
    )
