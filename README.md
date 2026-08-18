# Omics-Based Wastewater Surveillance Platform

Research execution platform for **"Omics Approaches to Predictive Prevention
Tools for Disease Surveillance Through Wastewater-Based Epidemiology"**
(Hlengiwe Nombuso Mtetwa, Ph.D. — Department of Community Health Studies,
Durban University of Technology).

The `omics_wbe/` package implements and executes the proposal's three research
objectives against **real surveillance data**, and generates its projected
outputs. It is independent of the synthetic demo pipeline documented further
down this file.

## What was actually run

| | |
|---|---|
| Wastewater measurements ingested | 137,711 (US CDC NWSS, California, Mar 2020 – Jan 2024) |
| Measurements passing QC | 97,960 (84.3%) |
| Biomarker targets measured | 11 (SARS-CoV-2 + 2 variant markers, influenza A/B, RSV, norovirus GII, mpox, *C. auris*, *Legionella*) |
| Counties modelled | 17, joined to NYT county COVID-19 case records |
| Signal used for modelling | causal (expanding-window) standardisation, winsorised at ±3 robust SD |
| Biomarkers catalogued | 36, across genomics / proteomics / metabolomics, 24 peer-reviewed references |
| Tests | `pytest tests/ -q` |

**No data in this section is synthetic.** Raw inputs are not redistributed —
see [`docs/DATA_ACQUISITION.md`](docs/DATA_ACQUISITION.md) for retrieval and
checksums.

## Headline findings

1. **Wastewater leads reported cases by ~3 weeks** (peak median Spearman
   ρ = 0.57 across 17 counties; per-county optimum most often 2 weeks).
2. **It predicts change, not level.** A within-site standardised signal has no
   information about a county's absolute case rate — the standardisation removed
   exactly that — and level models on it fail (R² < 0). Re-framed onto the
   change in log case rate, the same signal is genuinely predictive.
3. **Its distinct value is early warning.** For two-week-ahead surge detection,
   models carrying the wastewater block reach AUPRC 0.34 against a 0.103 base
   rate (3.3× lift) versus **0.138 for clinical autoregression alone** — a 2.4×
   advantage. For forecasting *magnitude* the incremental value is smaller and
   only conclusive at the 2-week horizon (95% interval excludes zero at +2 wk;
   at +0 and +1 wk the point estimate favours wastewater but the interval still
   contains zero).
4. **Positive decision-curve net benefit** at 23 of 30 thresholds tested
   (0.06–0.60), which is the concrete sense in which the signal is *actionable*.
5. **The validation protocol matters more than the model.** Random k-fold
   cross-validation — as specified in the original proposal — understates error
   on this panel and inflates R² by up to 0.56.

Full technical report: `results/wbe/reports/technical_report.html`
(regenerated from `study_results.json`, so its prose cannot drift from its numbers).

## Quick start

```bash
pip install -r requirements.txt
python -m omics_wbe.cli check-sources   # confirm raw inputs are present
python -m omics_wbe.cli run --force     # full pipeline + study + report (~6 min)
python -m omics_wbe.cli verify          # re-hash every manifest input/output
```

Other commands:

```bash
python -m omics_wbe.cli catalog --class non_communicable --min-tier emerging
python -m omics_wbe.cli archives        # show NCBI/ENA queries, probe connectivity
python -m omics_wbe.cli stage-one       # build analysis panels only
```

## Architecture

```
omics_wbe/
  config.py            canonical schemas, paths, AnalysisConfig (every knob, one place)
  provenance.py        SHA-256 manifests, drift verification
  biomarkers/          evidence-tiered catalogue (36 markers, 24 references)
  ingest/              sources registry + NWSS / NYT / QLD / sequence-archive connectors
  normalize/           harmonisation, censoring, PMMoV ratio, standardisation, back-calculation
  qc/                  12-rule QC engine (fail vs warn, every violation counted)
  integrate/           region x epiweek alignment, lag/lead correlation
  features/            causal lag construction, three switchable feature blocks
  modeling/            rolling-origin validation, baselines, regression, classification, sensitivity
  surveillance/        EWMA alarms, lead time, surge labels, decision-curve analysis
  governance/          catchment suppression, sensitive-setting screening
  reporting/           figures and the auto-generated technical report
  pipeline.py          stage 1: raw -> analysis panels (cached, manifested)
  study.py             stage 2: all three objectives -> results bundle
  cli.py               command-line entry point
```

Adding a surveillance programme means writing one connector that emits
`WBE_MEASUREMENT_COLUMNS`. Nothing downstream changes.

## Design decisions that carry the science

These were forced by the data, and each is a place a naive implementation
silently produces wrong answers.

**Harmonise before QC.** Contributing laboratories report process recovery as a
*ratio* in some submission groups and a *percent* in others, and report
non-detects as a zero concentration with the below-LOD flag unset. Running QC on
unharmonised input fails **82%** of a real NWSS extract for reasons that are
conventions, not data quality. After harmonisation the pass rate is 84%.

**Causal features, not retrospective ones.** Whole-series z-scores standardise a
March 2021 sample partly by measurements taken in 2023. All model features use
the expanding-window variant; the retrospective version is reported only as the
optimism comparison.

**Rolling-origin validation with a gap.** Random k-fold puts week *t−1* of a
county in training and week *t* in test. Both protocols are run; only
rolling-origin is reported as performance.

**Target-appropriate baselines.** A persistence baseline scored against a
*change* target predicts a level where a difference is expected, producing a
meaningless R² of −133. Baselines are gated by target mode.

**Winsorised signal.** A robust z-score of a series containing an epidemic
excursion is heavily tailed — the post-Omicron collapse reaches −27 here. Ridge
on the unclipped signal reaches R² of −4.5; gradient boosting on the identical
input is unaffected. The signal is clipped at ±3 robust SD and the specification
curve reports performance across that choice.

**Calibrated alert probabilities.** An uncalibrated random forest discriminated
at AUROC 0.86 while scoring *worse than the base rate* on Brier, which would
have made the decision curve meaningless.

**Refuse to guess excretion parameters.** Of 36 catalogued biomarkers, exactly
one has a transferable literature excretion fraction. `parameters_from_catalog`
raises `ParameterUnavailable` for the rest, so a prevalence figure can never be
produced from a parameter nobody measured. That refusal is the deliverable, not
an obstacle to it.

**Evidence tiers.** Every catalogue entry is `established`, `emerging` or
`prospective`. `inference_ready()` refuses prospective markers for published
claims; they exist to fix the schema and record the open question.

## What is *not* done, and why

Stated plainly rather than buried in a limitations paragraph.

| Gap | Reason |
|---|---|
| **No sequence-level omics processed** | Outbound access to NCBI/ENA/DDBJ is blocked in this environment. Connectors are implemented and tested; `plan_quantification()` enumerates the read-processing steps needed to turn a run accession into a measurement. Genomic depth here is assay-level PCR targets, not metagenomes. |
| **No non-communicable-disease measurements** | No metformin or metabolite data were obtainable. The catalogue, mass-balance engine, Monte-Carlo uncertainty propagation and refusal gate are implemented and tested; the NCD arm is methodological, not empirical. |
| **Only SARS-CoV-2 validated quantitatively** | Matched case data existed only for COVID-19 in California. The other ten targets are characterised descriptively. The pipeline is pathogen-agnostic. |
| **Reported cases are a biased comparator** | Clinical ascertainment changed enormously across 2020–2023. This analysis cannot separate a change in transmission from a change in testing. |
| **Snakemake workflow not executed** | `workflow/Snakefile` wraps the same CLI commands, but Snakemake could not be installed here (a transitive dependency fails to build). The CLI is the verified path. |

## Documentation

| Document | Contents |
|---|---|
| [`docs/SOP_01_data_acquisition_and_mining.md`](docs/SOP_01_data_acquisition_and_mining.md) | Systematic data mining, selection criteria, provenance |
| [`docs/SOP_02_qc_and_normalisation.md`](docs/SOP_02_qc_and_normalisation.md) | Harmonisation, QC rules, censoring, normalisation |
| [`docs/SOP_03_modelling_and_validation.md`](docs/SOP_03_modelling_and_validation.md) | Validation protocol, baselines, calibration, sensitivity |
| [`docs/ETHICS_AND_GOVERNANCE.md`](docs/ETHICS_AND_GOVERNANCE.md) | Ethics guidelines (IREC submission draft) — group privacy, not individual privacy, is the operative concern |
| [`docs/POLICY_BRIEF.md`](docs/POLICY_BRIEF.md) | What wastewater surveillance can and cannot tell a health department |
| [`docs/WORK_PLAN_AND_BUDGET.md`](docs/WORK_PLAN_AND_BUDGET.md) | Status against the proposal timeline, budget, impact metrics |
| [`docs/MANUSCRIPTS.md`](docs/MANUSCRIPTS.md) | Three manuscript outlines built from produced results |
| [`docs/DATA_ACQUISITION.md`](docs/DATA_ACQUISITION.md) | How to obtain the raw inputs, with checksums |

## Reproducibility

Every stage writes a manifest to `results/wbe/manifests/` recording input and
output SHA-256 hashes, full configuration, random seed and library versions.
`python -m omics_wbe.cli verify` re-hashes everything and reports drift. Any
published number whose manifest reports drift should be withdrawn until re-run.

---

# Appendix — Synthetic Demo Pipeline and Platform Application

Everything below predates the `omics_wbe/` platform above and is
independent of it. The demo pipeline's data is **synthetic**; the
registry, auth, API and Streamlit layers are real infrastructure.

## The demo pipeline

A small, end-to-end demonstration pipeline showing how genomic, protein,
metabolite and metadata features could be merged and fed into a classifier,
with a Streamlit dashboard for viewing results.

**This is a methodology demonstration, not a validated surveillance tool.**
All input data (`collect_data.py`) is randomly generated — it does not come
from real wastewater samples, NCBI, UniProt, or MetaboLights. The trained
model has no genuine predictive signal against the synthetic label; do not
treat its output as an environmental disease signal, a risk score, or a
public-health finding.

## Pipeline

```
collect_data.py      -> data/*.csv               (synthetic genomic/protein/metabolite/metadata)
prepare_dataset.py   -> data/structured_dataset.csv (merged, scaled, one-hot encoded)
train_model.py        -> models/random_forest_model.pkl, results/*.png, results/evaluation_metrics.txt
streamlit_dashboard.py -> interactive viewer over the trained model + results
```

Run individually:

```bash
pip install -r requirements.txt
python collect_data.py
python prepare_dataset.py
python train_model.py
streamlit run streamlit_dashboard.py
```

Or via Snakemake:

```bash
snakemake --cores 1
```

## Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Known limitations

- Data is synthetic (`numpy.random`-generated); there is no true relationship
  between features and the `disease_present` label, so classification
  metrics are not meaningful as performance indicators.
- No leakage-prevention, cross-validation, calibration, or uncertainty
  quantification is implemented — this is a single train/test split with
  default hyperparameters.
- No provenance tracking beyond the upload/job records themselves, no
  evidence hierarchy, and no API layer exists yet.
- Pipeline jobs run the *synthetic demo* pipeline only (collect_data ->
  prepare_dataset -> train_model) - no real bioinformatics tool (FastQC,
  Kraken2, CARD/RGI, etc.) is wired in, and a job does not yet consume a
  specific uploaded file; it always regenerates its own synthetic data.
- Jobs run via a Python `threading.Thread` per submission, not a real task
  queue (Celery/RQ) - adequate for a single-process prototype with a handful
  of concurrent users, not for production load or multi-worker deployment.
- Uploaded files, job outputs and generated reports are stored on local disk
  (`instance/uploads/`, `instance/jobs/`, `instance/reports/`), not object
  storage — fine for a single-process prototype, not for production.
- Reports are HTML only (no PDF/CSV export yet), and cover registry + job
  state, not the Environmental Evidence Hierarchy / decision-intelligence
  content described in the design document — that engine doesn't exist yet.
- `data/` is git-ignored and regenerated by `collect_data.py`; the committed
  `models/random_forest_model.pkl` and `results/` outputs reflect the most
  recent pipeline run and will go stale if the code changes without
  re-running the pipeline.
- The API (`api/`) only covers auth and projects so far - sites, samples,
  uploads, jobs, reports and models are only reachable through the
  Streamlit UI for now. No rate limiting is implemented despite
  `ACCOUNT_LOCKOUT_*` existing at the auth-service level.

## Persistence and authentication (`ai_wasteguard/`)

A database-backed foundation for projects/sites/sampling events/samples and
canonical authentication, independent of the demo scripts above.

- **Models**: `User`, `Project`, `Site`, `SamplingEvent`, `Sample`
  (`ai_wasteguard/models.py`), with cascading relationships.
- **Database**: SQLAlchemy, defaulting to a local SQLite file at
  `instance/app.db`. Set `DATABASE_URL` (e.g.
  `postgresql+psycopg2://user:pass@host/db`) to use PostgreSQL instead — no
  code changes required either way (see `.env.example`).
- **Migrations**: Alembic, `migrations/`. Schema changes go through
  migrations, not `create_all` in application code.
- **Auth**: `ai_wasteguard/auth.py` — Argon2 password hashing, email
  normalization, duplicate-registration rejection, enumeration-safe login
  errors, and lockout after repeated failed attempts.
- **Uploads**: `ai_wasteguard/uploads.py` — extension allow-listing
  (tabular + sequence formats), SHA-256 checksumming, chunked disk writes
  (never loads a whole file into memory), and storage keys generated
  server-side (`uuid4()`, never derived from the client filename) so a
  crafted filename like `../../etc/passwd.csv` cannot escape the upload
  directory - it's stored safely and only the basename is kept as a label.
- **RBAC**: `ai_wasteguard/permissions.py` — one policy (role -> allowed
  action sets) that both the UI and service layer consult; roles are
  self-selectable at registration except Administrator. `Viewer`/`Student`/
  `PublicHealthOfficial` get read-only access to the registry pages;
  `Researcher`/`LaboratoryScientist`/`Administrator` can create records,
  per role differences.
- **Audit log**: `ai_wasteguard/audit.py` — every registration, login
  attempt (success, wrong password, unknown email, disabled/locked
  account), registry mutation, upload, job submission/outcome, and
  permission denial is recorded as an immutable `AuditLog` row with actor,
  action, resource, and timestamp.
- **Pipeline jobs**: `ai_wasteguard/jobs.py` — submits the synthetic demo
  pipeline as real subprocesses (`collect_data.py` -> `prepare_dataset.py`
  -> `train_model.py`) against an isolated `instance/jobs/<job_id>/`
  directory per run. Status reflects actual subprocess exit codes - a
  failing step marks the job FAILED with the real stderr in its log,
  it is never assumed to have succeeded.
- **Reports**: `ai_wasteguard/reports.py` — generates an HTML project
  summary (sites, samples, uploads, job history, and any completed job's
  evaluation metrics), writes it to disk, and records a SHA-256 content
  hash in the `Report` row. All user-supplied text (project title,
  description, filenames) is HTML-escaped before being embedded.
- **Model registry**: `ai_wasteguard/model_registry.py` — turns a
  *completed* job's artefact into a tracked `MLModel` row (algorithm,
  target variable, metrics, artefact path, standard intended-use/
  prohibited-use text). Registration is rejected for any job that isn't
  COMPLETED or whose artefact is missing - never silently accepted. New
  models start in `draft`; only `Administrator` can `approve` one
  (`permissions.CAN_APPROVE_MODELS`).
- **Administrator bootstrap**: `ai_wasteguard/admin.py` +
  `scripts/create_admin.py`. Administrator is deliberately excluded from
  self-registration, but nothing else in the app could ever grant it -
  which meant the model-approval feature above was functionally
  unreachable in a real deployment. `python scripts/create_admin.py
  user@example.com` promotes an *already-registered* user, is meant to be
  run from a trusted environment (not exposed through the web app), and
  records an audit event with `actor_user_id=None` (an out-of-band
  operator action, not attributed to the promoted user as if they did it
  themselves).
- **Dashboard**: `ai_wasteguard/dashboard.py` — aggregates active
  projects/sites/samples, a pipeline job status breakdown (queued/running/
  completed/failed), approved models, and recent audit activity, scoped
  to the logged-in user's own data (verified isolation: another user's
  projects never contribute to your counts). Rendered on `Home.py` after
  login. Pure read aggregation - no new tables.

Session note: `ai_wasteguard/db.py`'s `SessionLocal` is configured with
`expire_on_commit=False`. Every service in this layer follows the pattern
`with get_session() as s: obj = do_something(s, ...)` and then reads
attributes off `obj` after the block exits (the session is closed by then);
with the SQLAlchemy default (`expire_on_commit=True`) that raises
`DetachedInstanceError`. This was an actual bug caught during manual
browser verification of the uploads and reports pages (the page didn't
crash loudly in a way the first pass of testing caught - see
`tests/test_db.py` for the regression test) - not a hypothetical.

Setup:

```bash
pip install -r requirements.txt
alembic upgrade head        # creates instance/app.db and applies schema
pytest tests/test_auth.py tests/test_models.py tests/test_registry.py tests/test_uploads.py tests/test_audit_and_permissions.py tests/test_jobs.py tests/test_reports.py tests/test_db.py tests/test_model_registry.py tests/test_admin.py tests/test_dashboard.py tests/test_tokens.py -v
```

## API (`api/`)

A FastAPI backend over the *same* `ai_wasteguard` services the Streamlit
app uses - not a reimplementation. This is the concrete proof of the
platform's layering promise ("presentation layers call services, not the
ORM directly"): register a user or create a project through the API, and
it shows up identically in the Streamlit app's registry pages and audit
log, and vice versa, because both go through `ai_wasteguard.auth` /
`ai_wasteguard.registry`.

- Auth is **stateless JWT**, independent of Streamlit's session-based
  `app_state.py` - `POST /api/v1/auth/register`, `POST /api/v1/auth/login`
  (returns a bearer token), `GET /api/v1/auth/me`.
- `GET/POST /api/v1/projects`, `GET /api/v1/projects/{id}` - the same
  RBAC as the UI (`permissions.CAN_CREATE_PROJECT`), and requesting a
  project you don't own returns 404, not 403 - deliberately, so the API
  doesn't confirm a project id exists to someone who can't see it (same
  principle as the enumeration-safe login error).
- Unhandled exceptions never reach the client as a stack trace - a
  global handler logs and returns a generic 500.
- CORS is closed by default; set `CORS_ALLOWED_ORIGINS` to open it to
  specific browser origins.
- `API_SECRET_KEY` signs access tokens - **must** be overridden via env
  var before any real deployment; the checked-in default is intentionally
  labeled insecure.

Run it:

```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn api.main:app --reload
# interactive docs at http://127.0.0.1:8000/docs
```

Verified with real HTTP requests (curl against a running `uvicorn`
process, not just FastAPI's in-process TestClient) covering the full
register → login → authenticated create/list/get flow, all the negative
cases (duplicate email, wrong password, missing/invalid token, a Viewer
role rejected from creating a project, a non-owner requesting someone
else's project id), and confirmed via the `audit_log` table that API-driven
actions are indistinguishable from UI-driven ones.

```bash
pytest tests/test_api.py -v
```

## Registry + upload + pipelines + reports + models app (`Home.py`)

A separate Streamlit app (independent of `streamlit_dashboard.py`) exposing
the persistence layer above through a UI: registration/login, project → site
→ sampling event → sample registration, file upload against a specific
sample, pipeline job submission/history, report generation, and model
registration/approval per project - each scoped to the logged-in user.

```bash
pip install -r requirements.txt
alembic upgrade head
streamlit run Home.py
```

Pages call `ai_wasteguard.registry`/`ai_wasteguard.auth`/`ai_wasteguard.uploads`/
`ai_wasteguard.jobs`/`ai_wasteguard.reports`/`ai_wasteguard.model_registry`
rather than querying the database or filesystem directly (`app_state.py` is
the thin Streamlit-session glue). Verified end-to-end in a real headless
browser (Playwright): register → log in → create project → create site →
create sampling event → create sample → upload a file → see it listed, with
the on-disk checksum independently confirmed against the DB record; submit a
pipeline job → watch it move to `completed` → see real evaluation metrics
rendered from the job's own output directory; register a model from that
job → see it listed as `draft` with the real metrics attached, with no
"Approve" button visible to that (self-registered, non-admin) account →
promote the account to Administrator with a real invocation of
`scripts/create_admin.py` as a subprocess against the live database → log
back in and confirm the role change took effect, the "Approve" button is
now present, clicking it updates the status badge to `approved` and the
button disappears. Also verified that a self-registered `Viewer` account
cannot see or use the "create project" form, while a `Researcher` account
can — confirming the permission policy is actually enforced end-to-end
across a role change, not just defined.

## Bootstrapping the first Administrator

1. Register normally through the app (any self-registerable role - the
   role picker doesn't matter, it will be overwritten).
2. From a trusted environment with access to the deployment's database:
   `python scripts/create_admin.py <their-email>`.
3. They log out and back in (role is read at login time) to pick up the
   new role.

## Roadmap

Longer-term plans for this project (real data integration, feature
engineering, explainability, decision support, production architecture,
etc.) are substantial and proceed incrementally, with each stage tested and
reviewed before the next begins, rather than as a single large rewrite.
