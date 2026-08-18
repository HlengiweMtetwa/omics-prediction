# SOP 02 — Quality Control, Harmonisation and Normalisation

**Version** 1.0 · **Scope** All wastewater measurements before analysis
**Owner** Laboratory Lead and Data Lead jointly

---

## 1. Purpose

Standardised, reproducible treatment of wastewater measurements from the point
of ingest to the point of modelling, as required by the proposal's
"Standardisation and Calibration" commitment.

## 2. Mandatory order of operations

The order is not a convenience. Running QC before harmonisation fails
approximately **82% of a real NWSS extract** for reasons that are submission
conventions, not data quality.

```
ingest → harmonise → QC → filter → collapse replicates → substitute censored
       → compute metrics → standardise → aggregate to site-week → aggregate to region-week
```

## 3. Harmonisation (`omics_wbe.normalize.harmonise`)

### 3.1 Recovery scale

Contributing laboratories report process recovery as either a **ratio** or a
**percent**. Scale is inferred per `(source, lab_method, matrix)` group from that
group's median, and groups smaller than 30 rows are left unrescaled rather than
rescaled from a handful of points.

- A sentinel value of `-1` means "recovery control not performed" and becomes
  missing, never a numeric value.
- The inferred scale is recorded per row in `recovery_scale`.

### 3.2 Censoring inference

A non-positive concentration with an unpopulated below-LOD flag is a non-detect
whose flag was never set. Censoring is inferred and marked in
`censoring_inferred`, so the sensitivity analysis can re-run without inferred
censoring.

A non-positive concentration *explicitly* flagged as **not** below LOD is a
genuine contradiction and fails QC rule QC005.

## 4. QC rules (`omics_wbe.qc.checks`)

| Code | Severity | Check |
|---|---|---|
| QC001 | fail | No-template control amplified |
| QC002 | fail | PCR inhibition detected |
| QC003 | fail | Process recovery outside the acceptance window |
| QC004 | fail | Negative reported concentration |
| QC005 | fail | Non-positive concentration explicitly flagged as not below LOD |
| QC006 | fail | Non-positive faecal normaliser concentration |
| QC008 | fail | Non-positive population served |
| QC007 | warn | Analytical replicate present (collapsed, not discarded) |
| QC010 | warn | No process recovery control reported |
| QC011 | warn | Below-LOD flag inconsistent with reported concentration |
| QC012 | warn | Faecal normaliser not measured |
| QC013 | warn | Robust outlier within a site × target series |

`fail` excludes; `warn` retains and flags. Re-running with
`apply_qc_filter(..., drop_warnings=True)` is the QC sensitivity analysis and
must be reported whenever a conclusion is close to a decision boundary.

**The acceptance window (`recovery_min_pct`, `recovery_max_pct`) is
configuration, not a constant.** Set it from the laboratory's own validation
data, and record the value used in the run manifest.

## 5. Censored data

Non-detects are substituted at **LOD / √2** (Hornung & Reed 1990). Where no LOD
was submitted, a cohort LOD is estimated as the 1st percentile of detected values
in the same `(target, unit, matrix)` group, and the route used is recorded per
row in `lod_route`.

A censored value with no LOD by either route keeps a NaN concentration. It is
never assigned a number: a non-detect with no detection limit carries no
quantitative information whatsoever.

**Report the censoring fraction per target.** Above roughly 60–70% censoring,
quantitative modelling of that target is not supportable; the detect-fraction
gate in `standardise_within_site` enforces a floor automatically.

## 6. Normalisation

| Metric | Definition | Use |
|---|---|---|
| `log10_conc` | log₁₀ of the imputed concentration | Within one matrix only |
| `log10_ratio_pmmov` | log₁₀(target / faecal marker) | **Primary.** Dimensionless, so comparable across matrices |
| `log10_load_per_100k` | log₁₀(concentration × flow / population) | Absolute load. Requires liquid matrix and a reported flow |
| `*_z` | Robust within-site z-score (whole series) | Description only — **leaks future data, never a model feature** |
| `*_zc` | Robust within-site z-score (expanding, causal) | **Model features.** Uses only each sample's own past |

Median and MAD are used throughout rather than mean and SD: an epidemic wave is
a genuine excursion, and an SD the wave itself inflated shrinks exactly the
signal being measured.

## 7. Replicates

Collapsed on the log scale (geometric mean of detected replicates). One
confirmed detection among non-detects is a detection. The maximum LOD across
replicates is retained as the conservative choice, and the between-replicate
log₁₀ SD is kept as a per-sample measurement-uncertainty estimate.

## 8. Aggregation

- **Site-week** — median of the weekly metric. Epidemiological week ends Saturday (MMWR).
- **Region-week** — mean across sewersheds weighted by served population.

## 9. Acceptance criteria

- [ ] Harmonisation ran before QC
- [ ] QC pass rate and per-rule violation counts recorded in the manifest
- [ ] Censoring fraction reported per target
- [ ] Causal (`_zc`) features used for every model; retrospective (`_z`) used only for description
- [ ] Manifest written and `verify` clean
