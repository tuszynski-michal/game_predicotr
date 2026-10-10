---
title: Bound and accelerate model-quality loading
status: done
last_updated: 2026-10-07
---

# TASK-0898 — Bound and accelerate model-quality loading

## Status

`done`

## Goal

Read the unchanged quality/cohort report without per-cell source decoding or
PNG round trips, and recover visibly from stalled requests.

## Context

Mumie quality has remained loading for over two minutes. Read-only queries
selected 28,320 candidates across 1,117 sources (0.469 s exclusion counts,
2.156 s candidate query). Each descriptor currently loads a complete JPEG
and encodes then decodes a PNG. The UI waits for independent pending preview.

## Dependencies / entry conditions

- MAIN branch v1.1-vision-lab-hybrid-geometry, HEAD v1.7.240 / 0a38e082079898831b32e3274db6bb3929867f76.
- User requested diagnosis/fix. Preserve pre-existing receipt changes.
- No unresolved product choice: identical report, eligibility and manifest
  are required. A 45-second request limit is an explicit UI recovery assumption.

## Recommended execution

gpt-6.1-sol / high, as assigned in the plan. Review the parity and source
integrity paths before commit; escalate any proposed eligibility/API change.
No delegation is authorized by this task.

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/architecture/API_CONTRACT.md
- ai_docs/delivery/MODEL_QUALITY_LOADING_FIX_PLAN_20261007.md

## Scope

- Execution-scoped image renderer; grouped source loading, RGB descriptors.
- Preserve SQL caps/order, protected checks, freeze and source validation.
- Abort/timeout/retry and independently loaded pending reinference preview.
- Regression/parity tests, limited real-data read, docs and one commit.

## Out of scope

Training, activation, real-data mutation, migrations, cleanup, deployment,
service restarts, push/merge, alternate summary API or background queues.

## Acceptance criteria

- [x] Each descriptor source is decoded once per group, with at most seven
  execution-scoped frames and no PNG serialization for descriptors.
- [x] Exact descriptors, ordered candidates and deterministic manifests match.
- [x] Protected-source checks, drift rejection, missing-asset accounting and
  fresh-process/freeze validation remain effective.
- [x] Quality does not await pending preview; reads end within 45 seconds
  with a visible retryable error. Late responses cannot update another game.
- [x] Focused tests, lint, scoped types and build pass; actual limitations recorded.

## Technical notes

Reuse the canonical loader and full provenance renderer. Group row indices
by source checksum, render in workers, sort results back by index before
domain selection. Source/frame memory expires at the end of a group; keep
existing protected-source attestation against the same atomic byte/RGB frame.
Read-only render-spec loading may precede the attestation, but no cell pixels
are rendered before its source passes the protection gate. The PNG consumer keeps its
default behavior and gets parity coverage. No generated API change is needed.
For UI use a bounded abortable read helper and independent pending loading;
refresh cancels earlier reads, and unmount/game change invalidates callbacks.

## Expected files

- services/api/src/game_predictor_api/application/virtual_cell_previews.py — renderer
- services/api/src/game_predictor_api/storage/symbol_cell_training_source_repository.py — inventory/descriptors
- services/api/tests/test_symbol_cell_training_source_repository.py
- services/api/tests/test_virtual_cell_previews.py
- apps/admin/src/features/model-quality/model-quality-actions.ts — bounded reads
- apps/admin/src/features/model-quality/model-quality-workspace.tsx — refresh
- apps/admin/test/model-quality-actions.test.mjs
- Proposed apps/admin/test-interactions/model-quality-loading.test.mjs
- services/worker/src/game_predictor_worker/images/normalization.py — atomic byte/RGB loader
- services/worker/tests/test_image_normalization.py
- services/worker/tests/test_mumie_pilot_feedback.py — equivalent shared-frame protection gate
- Relevant architecture/API guide, CURRENT_STATE and this task/plan

## Test cases

Shared-source rows in interleaved SQL order -> one decode/group, same order;
RGB/PNG descriptors -> exact equality; fresh renderer -> same manifest;
missing or changed source/crop -> existing exclusion/conflict semantics;
protected aliases -> excluded/fail closed; stuck quality/pending -> bounded
failure and unaffected independent report; unmount/new game/retry -> no late state.

## Verification

Use the existing artifacts/grid-v3-deployment-20261004/run_step.py with
explicit <=120 s timeout from absolute MAIN/Admin paths. Python pytest
focused renderer/source/cohort tests; Node --import tsx --test focused Admin
actions/interactions/contracts; Ruff format/check, scoped mypy, Prettier,
ESLint, TypeScript noEmit and Next build. Read-only real-data checks set
transaction READ ONLY, 10 s SQL timeout and 2 s lock timeout.

## Risks / open questions

Full candidate selection still depends on cohort size within existing caps.
Read-only validation may still be too slow on unusually large originals;
report measurements honestly. The running API has no reload; deployment
requires a separately authorized controlled restart.

## Outcome

### Changed

- Grouped the existing SQL pool by managed source path/checksum. Up to seven
  execution-scoped frames serve protection and cell rendering, with original
  row order restored. RGB descriptors avoid PNG serialization. The canonical
  loader hashes and decodes the same bytes; its unreadable-source error remains.
- Added 45-second abortable reads, retry, late-response protection, independent
  pending-preview loading and a disabled reinference action until its count loads.
- Preserved API types, exact cohort selection, eligibility, checksum/protection
  checks, geometry, human labels and model activation. No new disk cache.

### Verification results

- Focused Python 50/50 PASS; broader renderer/cohort/reference/worker regressions
  104/104 PASS (19.19 s). Last changed-branch regressions 28/28 PASS, including
  unreadable-source compatibility. Existing Starlette deprecation warning only.
- Admin actions/contracts 14/14 PASS; rendered UI interactions 4/4 PASS. Cases
  include lost responses, timeout/retry, unmount, game change/late responses,
  independently stalled pending counts and unavailable reinference action.
- Ruff format/lint, Prettier, ESLint and TypeScript PASS. Scoped mypy on six
  source/protocol/domain modules PASS (6.91 s). An earlier skipped-import run
  lacked the crop-asset domain type; rerun included the actual dependency.
- Admin production build PASS (18.17 s), without restarting services.
- Two fresh-process real-data reads, in transaction READ ONLY with bounded SQL,
  selected 6303 samples / 3074 boards / 813 sources. Service preview: 32.610 s;
  actual FastAPI GET handler: HTTP 200 in 39.843 s. Exact same manifest checksum:
  138a43d3290d0fcc983d57cccfeb1aabcd41647edb08b6d1182bdd18cd11c7c8.
  Earlier intermediate implementations took 84.031 and 51.907 s, explaining
  why source attestation and rendering must share a frame. No quality threshold
  or validation was weakened to obtain the result.
- Evidence: artifacts/model-quality-loading-20261007/verification.json and
  bounded command receipts in artifacts/grid-v3-deployment-20261004/0898-*.json.

### Not completed

- No production writes, migrations, cleanup, training, activation, deployment,
  restart, push or merge. Running processes still need a controlled deployment.
- This remains an exact pixel-verified cohort report, rather than a cheap count.
  The observed 33–40 seconds is not an instant-load guarantee on future data or
  under heavier concurrent work. A separate lightweight-summary design would
  require an explicit compatible API extension, outside this fix.

### Documentation updates

Requirements, architecture, API contract narrative, plan and CURRENT_STATE.
All five acceptance criteria and Definition of Done checked; no task blocker.

### Recommended next task

Authorized controlled API/Admin deployment, then verify the panel in the main
application. No automatic deployment was performed under AGENTS.md.

Completion version: v1.7.241. Commit: 3cabf8f2a7d64c92f2d8a642cba93c1afe2d64fe.
