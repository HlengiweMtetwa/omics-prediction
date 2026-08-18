# Policy Brief — What Wastewater Surveillance Can and Cannot Tell a Health Department

**Audience** Public health decision-makers and surveillance programme managers
**Evidence base** 116,237 wastewater measurements (US NWSS, California,
March 2020 – January 2024) across 11 pathogen targets, linked to county-level
reported COVID-19 cases across 17 counties
**Full results** `results/wbe/reports/technical_report.html`

---

## The short version

Wastewater surveillance is a **good early-warning system and a poor
case-counting system**. Programmes that buy it for the first purpose get value;
programmes that buy it expecting the second will be disappointed, and the
disappointment will be blamed on the laboratory rather than on the
misunderstanding.

## Four findings

### 1. The signal leads reported cases by one to three weeks

Pooled median Spearman correlation between the wastewater signal and reported
case rates peaks at a **three-week wastewater lead** (ρ = 0.57), though the most
common per-county optimum is **two weeks** (9 of 17 counties). Eleven of
seventeen counties exceeded ρ = 0.5 at their best lag; per-county optima ranged
from 1 to 6 weeks.

**Implication:** the lead time is real but *county-specific*. A programme should
estimate its own lead per catchment rather than adopting a national figure.

### 2. It tells you the direction of change, not the number of cases

A standardised wastewater signal carries no information about a county's
absolute case rate — the standardisation that makes different sampling matrices
comparable removes exactly that information. Models asked to predict absolute
case rates from it failed outright (R² below zero).

Re-framed to predict *change*, the same signal works.

**Implication:** never publish a wastewater signal as a case count or a
converted "estimated infections" figure. Report it as a trend and a risk level.
If a programme needs absolute burden, it must fund flow measurement and
recovery-corrected absolute quantification — a substantially more expensive
laboratory configuration.

### 3. Its distinct value is early warning, not forecasting magnitude

| Task | Wastewater alone | Clinical data alone | Both |
|---|---|---|---|
| Forecast next week's change (skill vs no-change) | 0.18 | 0.19 | **0.22** |
| Warn of a surge two weeks out (AUPRC, base rate 0.10) | 0.32 | 0.14 | **0.34** |

For magnitude forecasting the three are close, and the improvement from adding
wastewater is only statistically conclusive at the two-week horizon.

For *surge warning* — will transmission rise sharply in the next fortnight —
the gap is decisive: **any model carrying the wastewater signal roughly
doubles the AUPRC of clinical autoregression alone** (0.32–0.34 versus 0.14),
against a 0.10 base rate.

**Implication:** commission wastewater surveillance as an early-warning trigger
feeding an escalation protocol, not as an input to case-number estimates.

### 4. Acting on the alert beats both blanket policies

Decision-curve analysis shows positive net benefit over both "always alert" and
"never alert" at 23 of 30 thresholds tested, spanning 0.06 to 0.60 — the whole
plausible range for a health department's tolerance of a false alarm.

Choose an operating threshold against available response capacity:

| Alert threshold | Precision | Recall | Alerts per 100 county-weeks |
|---|---|---|---|
| 0.10 | 19% | 73% | 40 |
| 0.15 | 28% | 61% | 22 |
| 0.20 | 36% | 43% | 12 |
| 0.30 | 50% | 20% | 4 |
| 0.40 | 59% | 10% | 2 |

**Implication:** for a low-cost response (a communication, heightened testing),
choose a low threshold and accept the false-alarm rate. For a costly response,
choose a high one and accept missing most surges. There is no threshold at which
this signal is both highly precise and highly sensitive, and a programme should
be told so before it is procured.

## Two things a programme must not do

**Do not compare wastewater against case counts and conclude the laboratory is
wrong.** Clinical ascertainment changed enormously across 2020–2023.
Divergence between the two series frequently means testing behaviour changed,
not that the assay drifted.

**Do not sample below the community level without an ethics mandate.** Wastewater
surveillance is not inherently anonymous. A sewershed serving 500,000 people
reveals nothing about anyone; a manhole serving one building can stigmatise a
identifiable group. Sub-catchment sampling requires prior ethics review and
community engagement, and wastewater data must never be routed to enforcement
agencies. See `docs/ETHICS_AND_GOVERNANCE.md`.

## Multi-pathogen capability

The same infrastructure carried influenza A and B, RSV, norovirus GII, mpox,
*Candida auris* and *Legionella pneumophila* alongside SARS-CoV-2. The marginal
cost of an additional target on an existing programme is far below the cost of
standing one up.

Two caveats. Only SARS-CoV-2 could be validated against clinical outcomes here,
because matched case data were unavailable for the others. And not every target
supports quantitative use: *C. auris* was 98% non-detect, so it functions as a
presence/absence alert for healthcare-associated risk, not as a prevalence
measure.

## Note on non-communicable disease

Extending wastewater surveillance to chronic disease is technically real and
implemented in this platform, but it is **not yet ready for routine reporting**.
Of the metabolite and pharmaceutical markers catalogued, only one has a
transferable literature excretion parameter. For a worked example using it, the
95% uncertainty interval on estimated treated prevalence spanned more than a
factor of three — from parameter uncertainty alone.

Prescribed-drug markers also measure *treated* prevalence: people who are
undiagnosed, or managed without medication, are invisible. Reporting such a
figure as "diabetes prevalence" would be a factual error with discriminatory
consequences for exactly the underserved communities the method is often
proposed to help.

**Recommendation:** fund local excretion-parameter calibration before
commissioning any non-communicable-disease wastewater reporting.

## Seeing it

The operational view — status per catchment, pathogen activity, trend, and the
measured performance a threshold choice should rest on — runs as:

```bash
streamlit run pages/7_Wastewater_Surveillance.py
```

It applies the publication-governance controls before rendering anything, and
labels itself a retrospective research extract rather than implying a live feed.

## Recommended actions

1. **Commission for early warning.** Define the escalation protocol before the
   first sample; a signal with no attached decision changes nothing.
2. **Estimate your own lead time per catchment.** Do not import a published figure.
3. **Choose an operating threshold against response capacity**, using the table
   above, and revisit it as capacity changes.
4. **Report trends and risk levels, never case-equivalent numbers.**
5. **Add pathogens to an existing programme** rather than standing up separate ones.
6. **Obtain an ethics mandate before any sub-catchment sampling.**
7. **Validate against your own clinical data annually.** The relationship between
   wastewater and reported cases depends on ascertainment, which changes.
