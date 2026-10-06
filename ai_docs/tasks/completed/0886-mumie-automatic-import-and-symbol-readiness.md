# TASK-0886 — automatic Mumie imports and recoverable symbol readiness

## Status

done

## Goal

Import complete neural lattices directly into bulk symbol verification and
recover the Mumie projection without individual geometry approvals.

## Context

The user requested a complete MAIN solution analogous to the V1.1 workflow.
The compulsory neural manual branch and an orphan rebuilding projection are
confirmed causes, not a need for more manual training labels.

## Dependencies / entry conditions

MAIN v1.7.227, schema 0145, existing qualified Mumie neural/symbol snapshots.
Current request authorizes deployment and non-destructive recovery through
existing APIs. Historical human corrections and unrelated dirty metadata must
remain protected. No blocking business question.

## Recommended execution

gpt-6.1-sol / high. Own implementation and separate self-review, no delegation.
Reassess before changing sequence, source identity or human-truth contracts.

## Relevant docs

- AGENTS.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/DECISION_LOG.md (D-522, D-523)
- ai_docs/requirements/ADMIN_APP.md
- ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/architecture/API_CONTRACT.md
- ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/delivery/MUMIE_AUTOMATIC_IMPORT_RECOVERY_20261006.md

## Scope

Versioned optional neural execution policy, exact-node automatic virtual crops,
per-slot deferrals, projection readiness/recovery, existing managed reprocess,
human-owner protection, API generated contract, tests and MAIN recovery.
Final backfill also repairs unavailable historical counts using existing
bounded count reconstruction and durable cursors. Ready current counts are
unchanged. This is required by live acceptance, not a new UI/API workflow.

## Out of scope

777 changes, destructive operations, new training/promotion, Super logic,
full database backup and population benchmarks.

## Acceptance criteria

- [x] Full bound neural slots produce fifteen current pending symbol cells.
- [x] Missing/partial slots preserve sequence and alone require correction.
- [x] Actual 24-node geometry is rendered; legacy policy remains reproducible.
- [x] Reprocess preserves current human geometry/labels and is retry-safe.
- [x] Empty initial projection is safely ready; orphan backfill is recoverable.
- [x] UI exposes useful state and recovery without perpetual false preparation.
- [x] Mumie image-bearing selections support bulk approval; legacy and outside selections keep their safeguards.
- [x] Existing Mumie import/projection recovered through supported APIs.
- [x] Focused regression, contract, type/lint checks and scoped live proof pass.

## Technical notes

Follow the execution plan. Automatic means usable prediction, not human truth.
Use source-bounded transactions and existing job/checkpoint infrastructure.
New policy participates in pipeline identity; never reinterpret old receipts.
No new endpoint or database schema. Persist diagnostics for uncalibrated grids.

## Expected files

Existing: application/jobs.py and schemas/jobs.py; worker neural_pending_geometry,
production_workflow and pipeline_store; common geometry gate, job repository,
lateral_reprocess_protection and symbol review storage; Admin
symbol-review-workspace; OpenAPI/generated client; scoped tests and operator docs.

## Test cases

Complete four lattices plus missing middle → sixty cells and one deferred slot;
exact internal nodes; no policy → old all-deferred behavior; cold retry;
human owner preserved; empty ready vs historical rebuilding; orphan backfill
button/automatic start, active reuse and failed retry.

## Verification

Run targeted pytest/API PostgreSQL and Admin interaction tests through the
existing bounded runner (120 seconds per finite step). Run scoped Ruff,
format, types and generated contract checks. Use controlled service restarts
and bounded polling, then existing Mumie-only endpoints. Record actual results.

## Risks / open questions

Structural validity does not prove recognition accuracy. Human corrections
remain the training truth. No open question requiring user intervention.

## Outcome

Implemented neural-auto-crop-v1 with exact 24-node virtual rendering, strict
source/sequence binding, sparse short-page ordering, individual deferrals and
protected human owners. Managed reprocess validates neural manifest schema5/v13
and retries the same job. Old unreviewed pending records are superseded with
history retained. API/OpenAPI/generated SDK agree; no migration or new endpoint.

Empty games initialize ready only after proving no history. Orphan preparation
starts once, reuses a durable job and exposes explicit retry. Late responses
from a previous game cannot disable or overwrite the current preparation.
Backfill finishes unavailable historical counters using durable bounded batches;
ready current counts remain untouched. Mumie-profile bulk approval now uses
the existing operation; outside and legacy safeguards retain their defaults.

MAIN recovery: 100 original photos retained,99 bound sources,891 current boards,
13,365 cells. Reprocess af474e46-28bc-404d-af1c-07aeb05a165c processed99/99,
199/199 steps,zero failures; HTTP retry preserved the job. Initial backfill
faa3c87b-e823-4107-aa3e-17f643718938 completed; final historical counts repair
13aabb68-aa50-42b7-9176-81552ca9b651 completed with no error. Projection and
counts ready,revision174,40 approved/13,325 pending. Human snapshot44 geometries
and2 cell decisions preserved exactly;847 unreviewed pending superseded.
Both games' model activations preserved. One unbound ending source remains
explicit correction without invented geometry or sequence.

Verification: focused108 API/worker,21 managed evidence/protection and15 lateral
scoped tests passed (overlapping suites). Final actual isolated PostgreSQL2
passed/0skip, including HTTP symbol feedback without geometry approval and
historical count batches on fresh sessions. Separate manual HTTP regression1
passed. Count/handler12,Admin interactions9 and SDK requests78 passed. Scoped
Ruff/format,Admin ESLint/types,SDK types,strict owned-source mypy and generated
contract checks passed. Admin production build passed. Live UI confirms2000
page size,423 Mumia pending crop previews,exact counts and enabled bulk approval
on selection,with no production label guessed or submitted by inspection.

Known unrelated baseline failures remain: frozen-page bulk unreadable badge
expectation and incomplete lateral public-browser JobResponse fixture. Proven
on HEAD; no test was weakened. Full repository checks/physical Android/OS reboot
are not claimed. Torch/Torchvision graph skipped by the scoped mypy config.
No cleanup,777 operations,new training/promotion,Super mechanics,push or
population benchmark. Prior dirty metadata and unrelated files preserved.

All nine criteria and the accepted plan were reviewed separately; no open
scoped P0–P2. Quality report:
ai_docs/quality/MUMIE_AUTOMATIC_IMPORT_RECOVERY_20261006.md.
Operator guide describes existing crops,bulk corrections and500→2000-photo
uploads without retraining after each upload. MAIN remains
v1.1-vision-lab-hybrid-geometry. Completion version: v1.7.228; hash recorded
after the scoped commit.
