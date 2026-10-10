---
title: Fast model quality overview and independent grid controls
status: done
last_updated: 2026-10-07
---

# TASK-0899 — Fast model quality overview and independent grid controls

## Status

`done`

## Goal

Open model quality using metadata only, keep grid controls available
independently, and prepare an exact cohort only on explicit training intent.

## Context

The user rejects TASK-0898's 45-second timeout. Full source attestation at
page entry still takes tens of seconds and gates grid mounting. This is a
workflow defect, not a reason to increase the timeout.

## Dependencies / entry conditions

- MAIN v1.1-vision-lab-hybrid-geometry; HEAD v1.7.241 / 3cabf8f2a7d64c92f2d8a642cba93c1afe2d64fe.
- User authorized the root fix; compatible API extension announced.
- Preserve pre-existing receipt changes, .claude and v7-output.
- Assumption: metadata counts are logical approvals, never training eligibility.
  Record D-529; no domain decision or schema change.

## Recommended execution

gpt-6.1-sol / high. Match the plan; inspect both response modes and frozen
source safeguards before commit. No delegation. Escalate any proposed
eligibility, geometry, production-data or deployment change.

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/process/DECISION_LOG.md (D-529)
- ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/architecture/API_CONTRACT.md
- ai_docs/delivery/MODEL_QUALITY_OVERVIEW_FIX_PLAN_20261007.md
- ai_docs/tasks/completed/0898-model-quality-loading.md

## Scope

- Compatible view=overview, SQL-only metadata and generated API client.
- Explicit checksum-bound training preview; retain exact freeze validation.
- Independent grid rendering; remove UI timeout, retain cancellation/retry.
- Focused regressions, read-only real-data verification, docs and one commit.

## Out of scope

Production mutation, migration, training, activation, cleanup, deployment,
restart, merge/push and changes to manual grid geometry.

## Acceptance criteria

- [x] Overview never reads originals, render manifests or protected photographs.
- [x] Counts describe approvals of current board owners and active real symbols;
      they are labelled separately from selected training samples.
- [x] Default GET, exact preview, protected sources and stale-freeze guards remain.
- [x] Opening/retrying overview does not prepare a dataset or start training.
- [x] Training preview must complete before confirmation; wrong-game/late
      responses cannot be applied.
- [x] Grid section remains mounted while symbol overview/preview loads or fails.
- [x] No arbitrary 45-second timeout; cancellation still settles hanging reads.
- [x] OpenAPI, client wrapper, request tests and rendered UI tests pass.
- [x] Fresh-process bounded read-only measurement, docs, DoD and versioned commit.

## Technical notes

Use two explicit response schemas on the existing endpoint. Overview excludes
manifest checksum, sample delta and canFreeze; those exist only in the full
response after pixel attestation. Metadata approval counts include logical
labels whose current pixels may later be excluded. SQL groups per active
symbol and uses the fast-document canonical review owner. Latest cohort reads
one metadata record, not its sample checksums.

All requests retain game identity checks and AbortSignal. Preparing a cohort
has a separate controller and busy state; changing game/unmount aborts it.
A failed overview or preview is a local symbol error, not a grid dependency.
Freeze uses only the full preview checksum and existing server revalidation.

## Expected files

Existing: services/api/src/game_predictor_api/{api,application,domain,schemas}/verified_training_cohorts.py;
storage/symbol_cell_training_source_repository.py and verified_training_cohort_repository.py;
packages/admin-api-client/src/index.ts, generated files and openapi/openapi.json;
apps/admin/src/features/model-quality/model-quality-actions.ts and model-quality-workspace.tsx;
associated API/client/Admin unit and interaction tests; relevant requirements,
architecture, decision log and CURRENT_STATE.md.
New: this task and MODEL_QUALITY_OVERVIEW_FIX_PLAN_20261007.md.

## Test cases

- Overview uses metadata only even when artifact reads raise.
- Counts/zero classes, absent game, latest metadata and per-game query binding.
- Default full request unchanged; overview returns no fake checksum/readiness.
- Entry requests overview, training click requests full exactly once.
- Hanging overview/pending/full preview leaves grid mounted; cancellation
  rejects without a timer; old-game responses are ignored.
- Preview failure cannot freeze; success confirms exact checksum; empty/active
  heavy report remains disabled.
- Existing freeze/activation/renderer/protected-source regressions.

## Verification

Use artifacts/grid-v3-deployment-20261004/run_step.py with --timeout 120,
absolute --cwd MAIN (Admin for tsconfig), and explicit executable/file paths.
Run changed pytest modules first, then Admin/client node tests and rendered
tsx tests, scoped ruff/eslint/mypy/tsc, OpenAPI export/client drift and known
Admin build. No load tests or synthetic large datasets. Read-only real-data
GET uses statement/lock/connect limits and rollback; report measured elapsed
time and counts, not an invented performance claim.

## Risks / open questions

Grid location clarification remains unanswered. This task repairs independently
reproduced mounting and loading in the quality screen; it does not change manual
grid geometry. The running API's existing reload picked up the overview and was
verified by HTTP and generated-client reads; no restart was performed.

The test browser showed the independently mounted grid section, but its requests
failed without HTTP responses, including game catalog and RSC requests. A complete
live UI walkthrough could not be confirmed. Direct runtime HTTP, generated-client
reads, CORS/preflight and rendered component interactions passed. Do not treat
these checks as evidence that every live browser network failure is resolved.

## Outcome

Completed the accepted plan without extending data or geometry behavior.

- Added an explicit metadata-only response to the existing endpoint through
  `view=overview`. SQL counts current-owner logical approvals of active real
  symbols; labels distinguish them from pixel-attested training samples.
  Latest cohort reads metadata only. OpenAPI and the generated client agree.
- Page entry and retry request overview. Exact source attestation is requested
  only by "Ulepsz rozpoznawanie". Confirmation uses the exact report's manifest;
  freeze, protected-source and stale-source checks retain their contracts.
- Removed the arbitrary 45-second read timeout, retained cancellation and
  wrong-game/late-response guards. Grid controls remain mounted across symbol
  loading, error, retry and exact preparation.
- Python regressions 64/64, Admin helpers/contracts 17/17, rendered interactions
  8/8 and API-client requests 76/76 passed. Scoped Python/Admin/client lint,
  format and type checks passed; OpenAPI/client drift checks passed. An isolated
  Admin build passed in 31.7 s without replacing the live build directory.
- A fresh-process read-only FastAPI overview returned HTTP 200 in 0.922 s:
  29201 logical approvals, 6146 boards, 1384 sources; zero image reads. Running
  API HTTP returned 200 in 0.937 s. Actual generated-client metadata reads were
  below 0.5 s each. The previous full report took 39.843 s; this changes page
  entry work, not the duration or eligibility of exact training preparation.
- Evidence: `artifacts/model-quality-overview-20261007/verification.json` and
  `artifacts/grid-v3-deployment-20261004/0899-*.json`. Verification compared
  every acceptance criterion with the implementation and accepted plan.
- No production writes, migration, training, activation, cleanup, manual restart,
  deployment, push or merge. Existing runtime reload was observed, not initiated.
  Complete live browser verification remains limited as described above.
- Completion v1.7.242; 5916b6ec39c1be062f2602d658dbf73bfdc2a608.
