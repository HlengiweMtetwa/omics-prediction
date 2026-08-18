# SOP 03 — Predictive Modelling and Validation

**Version** 1.0 · **Scope** Every model whose output is reported or deployed
**Owner** Data Lead

---

## 1. Purpose

To ensure reported model performance is what the model would actually deliver in
operation.

## 2. The validation rule

> **Random k-fold cross-validation must not be used to report performance on
> wastewater surveillance panels.**

The original proposal specifies k-fold. On a panel of overlapping weekly time
series with lagged features and autocorrelated targets, a random fold puts week
*t−1* of a county in training and week *t* in test — the model is scored on a
week it has effectively already seen.

Measured on this project's own data, random k-fold reduces reported RMSE by
roughly 10% and inflates R² by up to 0.56 for the wastewater-only level model,
relative to rolling-origin validation.

**Required protocol:** `RollingOriginSplit` — train on the past, discard a gap at
least as long as the longest feature lag, test on the future. Random k-fold may
be reported *alongside* rolling-origin solely to quantify its optimism.

## 3. Feature construction

- Every feature is causal by construction: series are reindexed onto a complete
  weekly calendar before any shift, so a missing week never silently changes
  what a lag means.
- `ar_lag0` must never exist. The clinical value at week *t* is the horizon-0
  target.
- Rows with missing features are dropped, never imputed. No model is scored on a
  value invented for it.

## 4. Mandatory comparisons

Every reported model runs on **identical rows** against:

1. `wbe` — wastewater features only
2. `ar` — clinical autoregressive features only
3. `wbe+ar` — both

and against the baselines appropriate to the target:

| Target mode | Baselines |
|---|---|
| `level` | persistence, drift, mean |
| `delta` | no-change, momentum, mean |
| `region_z` | no-change, mean |

**A baseline that does not match the target mode is not reported.** A persistence
baseline scored against a change target predicts a level where a difference is
expected and yields a meaningless R² of −133.

The claim "wastewater adds value" requires `wbe+ar` to beat `ar` under a
**paired bootstrap on shared rows** with a confidence interval excluding zero.

## 5. Choosing the target

A within-site standardised signal has had its level information removed by
construction. Asking it to predict an absolute case rate is asking for something
its input cannot supply, and it fails (R² < 0).

- Use `delta` (change in log case rate) for a standardised signal.
- Use `level` only with an absolute, recovery-corrected, flow-normalised load.

## 6. Uncertainty

Prediction intervals come from **split conformal** calibration on earlier folds,
not from a model's own variance estimate: conformal coverage holds without
assuming Gaussian residuals, which these are not. Report empirical against
nominal coverage.

## 7. Classification and alerting

- Probabilities from tree ensembles must be **calibrated** (isotonic, fitted
  inside the training fold only). An uncalibrated random forest here reached
  AUROC 0.86 while scoring worse than the base rate on Brier.
- Report AUPRC **against prevalence**, not AUROC alone — surge events are rare.
- Report a **decision curve**. A model that never beats "alert always" or "alert
  never" at any plausible threshold is not actionable regardless of its AUROC.
- Publish operating points (precision, recall, alerts per 100 region-weeks) so a
  health department can choose a threshold against its own capacity.

## 8. Sensitivity

Every reported result carries:

1. Out-of-fold permutation importance
2. Input perturbation over a plausible measurement-error range
3. Monte-Carlo propagation of analytical noise
4. A **specification curve** re-running the headline model under every
   defensible analysis choice

## 9. Acceptance criteria

- [ ] Rolling-origin CV with a gap ≥ the longest feature lag
- [ ] All three feature blocks scored on identical rows
- [ ] Target-appropriate baselines only
- [ ] Paired bootstrap supports any incremental-value claim
- [ ] Conformal coverage reported
- [ ] Specification curve reported
- [ ] Seed and library versions in the manifest
