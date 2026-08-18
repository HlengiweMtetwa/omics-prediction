# Two-Year Work Plan, Budget and Impact Metrics

Maps the proposal's timeline and budget onto what has been built, what remains,
and how impact will be measured.

---

## 1. Status against the proposal's work plan

Legend: **[done]** implemented and executed here · **[partial]** implemented,
awaiting data or approval · **[pending]** not started

### Year 1

| Quarter | Proposal activity | Status | Evidence |
|---|---|---|---|
| Q1 | Project infrastructure, software, database access | **[done]** | `omics_wbe/` package, `requirements.txt`, `workflow/Snakefile` |
| Q1 | Literature review to refine approach | **[done]** | 24 peer-reviewed references in `catalog.json`, retrieved via PubMed |
| Q1 | Partnerships with treatment facilities and health departments | **[pending]** | Institutional activity, not a code deliverable |
| Q1 | Train postgraduates on omics and data integration | **[partial]** | SOPs 01–03 are the training materials |
| Q2 | Protocols for extracting/processing omics data | **[done]** | SOP 02; `harmonise`, `qc`, `normalize` modules |
| Q2 | Baseline measures and calibration | **[done]** | QC acceptance windows, recovery-scale inference, cohort LOD estimation |
| Q2 | Initial omics analyses; integrate with health records | **[done]** | 137,711 measurements ingested, 97,960 passing QC → region-week panel joined to county case records |
| Q3 | Initial predictive models | **[done]** | `omics_wbe/modeling/`, rolling-origin validated |
| Q3 | Scale up sampling and omics data production | **[partial]** | Data mining executed; primary sampling is institutional |
| Q4 | Model refinement, statistical validation | **[done]** | Conformal intervals, paired bootstrap, specification curve |
| Q4 | First-year evaluation and progress report | **[done]** | `results/wbe/reports/technical_report.html` |

### Year 2

| Quarter | Proposal activity | Status | Notes |
|---|---|---|---|
| Q1 | Advanced model development | **[done]** | Three feature blocks × three estimators × three horizons × two target modes |
| Q1 | Workshops with public health officials; conference presentations | **[pending]** | Policy brief drafted (`docs/POLICY_BRIEF.md`) |
| Q2 | Full-scale omics analyses | **[partial]** | Complete for PCR-target data; sequence-level processing requires the archive pipeline in SOP 01 §3.4 |
| Q2 | Model optimisation, advanced statistics | **[done]** | Calibration, decision-curve analysis, sensitivity suite |
| Q3 | Pilot testing with partner health departments | **[pending]** | Operating-point table (`alert_operating_points.csv`) is the input a partner needs to choose a threshold |
| Q3 | Refinement from pilot feedback | **[pending]** | Depends on the pilot |
| Q4 | Final evaluation and reporting | **[partial]** | Technical report auto-generates; final report follows the pilot |
| Q4 | Publish in peer-reviewed journals | **[partial]** | Three manuscript outlines in `docs/MANUSCRIPTS.md` |

## 2. What is genuinely blocked, and by what

| Blocker | Affects | Resolution |
|---|---|---|
| No outbound access to NCBI/ENA/DDBJ in this environment | Sequence-level omics mining | Run `python -m omics_wbe.cli archives --search` from a networked environment; connectors are implemented and tested |
| No non-communicable-disease measurements obtainable | Empirical NCD arm | Engine, catalogue and refusal gate are implemented; supply LC-MS/MS data through the same schema |
| Case data available only for COVID-19, California | Quantitative validation of influenza, RSV, norovirus, mpox, *C. auris*, *Legionella* | Obtain matched notifiable-disease data; the pipeline is pathogen-agnostic |
| Institutional partnerships, ethics approval | Primary sampling, pilot deployment | Institutional process; `docs/ETHICS_AND_GOVERNANCE.md` is the submission draft |

## 3. Budget

As proposed (ZAR):

| Item | Year 1 | Year 2 | Total |
|---|---|---|---|
| Postdoctoral researcher salary | 400,000 | — | 400,000 |
| Software and bioinformatics tools | 100,000 | 100,000 | 200,000 |
| Travel and conferences | 60,000 | 60,000 | 120,000 |
| Open-access publication (3 papers @ 40,000) | — | 120,000 | 120,000 |
| **Total** | | | **840,000** |

### Note on the software line

The proposal budgets R200,000 over two years for "licences for specialised
software". **The platform delivered here uses no licensed software.** Every
dependency is open source (Python, pandas, scikit-learn, SciPy, matplotlib,
Snakemake), consistent with the proposal's own open-science commitment.

MaxQuant (proteomics) and MetaboAnalyst (metabolomics), named in the proposal,
are free for academic use; commercial LC-MS/MS vendor software is not, and would
be the genuine call on this line if the non-communicable-disease arm proceeds to
laboratory measurement.

This is a note for the funder's attention, not a request to reallocate: the
decision is the PI's. Should reallocation be considered, LC-MS/MS analytical
costs and local excretion-parameter calibration are the two expenditures that
would most directly unblock the NCD arm — which §2 identifies as the
project's principal empirical gap.

## 4. Impact measurement

The proposal commits to "specific metrics to evaluate the impact of the research
outcomes". Baselines below are the values measured in this analysis.

### 4.1 Forecast accuracy

| Metric | Baseline (measured here) | Target |
|---|---|---|
| Skill vs no-change, 1-week horizon, wbe+ar | 0.222 | ≥ 0.30 |
| Incremental RMSE gain over clinical-only | conclusive only at +2 wk | CI excludes zero at every horizon |
| Conformal interval coverage (nominal 80%) | 0.77–0.80 | Within 0.78–0.82 |

### 4.2 Early warning

| Metric | Baseline | Target |
|---|---|---|
| Surge-warning AUPRC (best block) | 0.337 | ≥ 0.40 |
| AUPRC lift over base rate | 3.3× | ≥ 4× sustained |
| AUPRC advantage over clinical-only | 2.4× | Sustained ≥ 2× |
| Median alarm lead time | 1.0 weeks | ≥ 2 weeks |
| Thresholds with positive net benefit | 23 / 30 | ≥ 25 / 30 |

### 4.3 Methodological adoption

- SOPs 01–03 adopted by ≥ 1 external surveillance programme
- Biomarker catalogue cited or reused externally
- Rolling-origin validation adopted in ≥ 1 subsequent WBE publication

### 4.4 Public health uptake

- Number of partner health departments receiving routine outputs
- Documented instances where a wastewater alert preceded a clinical response
- Operating threshold formally adopted by a partner

### 4.5 Capacity building

- Postgraduates trained on the SOPs
- Peer-reviewed publications (target: 3, per budget)
- Ethics guidelines adopted institutionally

### 4.6 Long-term monitoring

The proposal commits to long-term impact monitoring. Concretely: retain every
run manifest, re-run the specification curve annually against accumulated data,
and re-evaluate whether the wastewater signal's incremental value over clinical
surveillance grows, holds, or decays as clinical ascertainment changes. That
last question is the one this study can least answer from three years of a
single pandemic.
