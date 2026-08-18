# Ethical Guidelines for Omics-Based Wastewater Surveillance

**Version** 1.0
**Status** Draft for submission to the Institutional Research Ethics Committee (IREC)

> This document is a projected output of the research proposal ("Development of
> ethical guidelines for the use of omics data in WBE, addressing issues related
> to privacy, consent, and data security"). It is a proposal to an ethics
> committee, not a substitute for its approval.

---

## 1. The premise this document rejects

Wastewater surveillance is routinely described as inherently anonymous. **It is
not.** Anonymity is a property of the *catchment*, not of the method.

A sewershed serving 500,000 people reveals nothing about any individual. An
upstream manhole serving one building, one prison wing, one student residence or
one workplace can report on a group small enough to be identified — and the
smaller and more socially marked the group, the greater the potential for harm
from a published result.

Everything below follows from taking that seriously.

## 2. Principles

### 2.1 Group privacy is the operative concern

Individual privacy is protected almost automatically; **group privacy is not**.
The realistic harm from wastewater surveillance is not identification of a
person but stigmatisation of a place: a neighbourhood, an institution, a migrant
community, an informal settlement. Governance must be designed for that harm.

### 2.2 Consent cannot be individual, so accountability must be collective

No individual consent can be obtained for a sewer sample, and none should be
fabricated. Legitimacy comes instead from:

- a public mandate for the surveillance programme, granted by an accountable
  body;
- transparency about what is measured, at what spatial resolution, and for what
  purpose;
- a route by which a monitored community can contest the programme;
- community engagement **before** monitoring begins in any sub-catchment.

### 2.3 Proportionality of spatial resolution

Sampling resolution must be the coarsest that answers the public health
question. Finer resolution requires a specific, documented justification and
prior ethics approval — not a general programme authorisation.

### 2.4 Surveillance must not be enforcement

Wastewater data must not be used to target individuals or households for
sanction, immigration action, or criminal investigation. Drug-consumption
biomarkers make this a live risk, and the prohibition must be a condition of
data sharing, in writing, with any partner agency.

## 3. Controls implemented in the pipeline

These are mechanical, in `omics_wbe.governance.ethics`, not matters of
individual judgement at publication time.

| Control | Implementation | Default |
|---|---|---|
| Minimum catchment population | `suppress_small_catchments` | 3,000 people |
| Unknown population | Treated as failing the floor | Suppressed |
| Minimum sites per region-week | `suppress_sparse_region_weeks` | 1 |
| Institutional settings | `flag_sensitive_sites` | Withheld pending IREC review |
| Upstream sub-catchments | Pattern-matched and flagged | Withheld pending IREC review |
| Human sequence reads | Removed at host-depletion step | Mandatory before any sharing |

**The thresholds are configuration, not constants.** The IREC sets them; the
pipeline executes that decision and records it in the run manifest.

Pattern matching on site names is a *prompt for review*, never a clearance: an
unmatched name is not evidence that a catchment is a general community.

## 4. Data protection

- No individual-level data are collected, processed or stored at any stage.
- Where sequencing data are processed, **human reads are removed before any
  onward sharing** — a privacy control, not only a bioinformatics convenience.
- Raw data are held under access control; only aggregated, suppression-screened
  outputs are released.
- Compliance targets: South Africa's Protection of Personal Information Act
  (POPIA) and, for any data received from EU partners, the GDPR. Even where
  wastewater data fall outside "personal information" as defined, the group-privacy
  controls above apply as a matter of programme policy.

## 5. Non-communicable disease and stigmatising biomarkers

Metabolite and pharmaceutical markers carry stigma risk that pathogen markers do
not. A published statement that a named community has elevated antidepressant,
antiretroviral or illicit-drug residues can cause direct harm.

Additional requirements for any non-communicable-disease or lifestyle marker:

1. Reporting at the **coarsest** spatial unit that answers the question, and
   never at sub-catchment level without specific approval.
2. Explicit statement that a prescribed-drug marker estimates **treated**
   prevalence — undiagnosed and non-pharmacologically managed disease is
   invisible to it, and reporting it as "prevalence" is a factual error with
   discriminatory consequences.
3. No back-calculated prevalence published from an excretion parameter that has
   not been locally calibrated. This is enforced in code:
   `parameters_from_catalog` raises `ParameterUnavailable` for any marker whose
   catalogue entry records `requires_local_calibration`.
4. Uncertainty published **with** every estimate. In this project's worked
   example the 95% interval spans a factor of more than three from parameter
   uncertainty alone.

## 6. Communication

- Never publish a wastewater signal as a case count. It is not one.
- Always publish the uncertainty interval alongside the estimate.
- Always state the ascertainment caveat when comparing to clinical data:
  divergence between wastewater and case counts may reflect changed testing
  behaviour rather than changed transmission.
- Where a result could stigmatise a community, the communication plan is
  reviewed with that community's representatives **before** release.

## 7. Review and audit

| Trigger | Action |
|---|---|
| New sampling site | Ethics screening before first sample |
| Any sub-catchment sampling | Full IREC review, community engagement |
| New biomarker class | Ethics review, especially for stigmatising markers |
| Data-sharing request | Review against §4 and the enforcement prohibition in §2.4 |
| Annual | Full review of thresholds, controls and this document |

## 8. Open questions for the committee

Stated openly because they are not resolved by this document:

1. What is the appropriate minimum catchment population for the South African
   context, where informal settlements may share small sanitation infrastructure?
2. Who holds the mandate to authorise sub-catchment sampling, and what
   community-consultation standard applies?
3. What is the retention period for raw sequence data, given that human reads
   are removed but re-identification research advances?
4. Under what circumstances, if any, may wastewater data be shared with agencies
   whose function is enforcement rather than health?
