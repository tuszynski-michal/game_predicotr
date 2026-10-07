---
title: TASK-0928 — resume image imports at the configured hard reserve
status: in_progress
last_updated: 2026-10-07
---

# TASK-0928 — resume image imports at the configured hard reserve

## Status

`in_progress`

## Goal

Resume storage-paused image imports at the same configured hard reserve as
normal processing, without an unrelated GC target or a tight retry loop.

## Context

Mumie import `092ff7a4-e652-4273-9c0a-a30e38ebd8cc`, folder
`50320 - 76554 cut`, is repeatedly claimed with `waiting_for_storage`.
Fresh read-only diagnostics show 50.23 GiB free on C:, 535/2915 processed
sources, 2380 still at discovery, no file errors, and attemptCount advancing
548 to 552 without source progress. The active worker has a healthy lease.
`ProductionImageImportWorkflow` uses hard reserve during normal processing
but the GC target (80 GiB) for a storage-paused job. Its defaults and the
CLI fallback also still contain the older 30 GiB reserve.

## Dependencies / entry conditions

- Main branch `v1.1-vision-lab-hybrid-geometry`, inspected HEAD v1.7.250.
- User requests implementation and separately authorizes restarting only
  worker general after tests. API/Admin remain user-controlled and untouched.
- Management work reserves TASK-0921–0927 and has pre-existing dirty files;
  this independent fix uses TASK-0928 and preserves those changes.

## Recommended execution

Standalone bounded bug fix by the current agent. No implementation plan,
model switch or delegation applies. Escalate if a schema change or changes
to GC deletion eligibility become necessary; neither is intended.

## Relevant docs

- `AGENTS.md` — lifecycle authorization, dirty worktree, test and commit rules
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md` — resume and image-storage capacity
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md` — worker lease and capacity policy
- `ai_docs/architecture/API_CONTRACT.md` — storage-paused pipeline
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md` — worker operations/storage guard
- `ai_docs/process/DECISION_LOG.md` — D-530, D-534

## Scope

- Use only the configured hard reserve for source copying and pipeline
  continuation/resumption; remove the unrelated resume target argument.
- Align worker defaults/fallbacks with the shared five-GiB retention default.
- Sleep for the existing positive polling interval after storage deferral,
  preserving durable requeue, checkpoint and lease fencing semantics.
- Regression tests for boundaries, overrides, resumed durable jobs, restart,
  no duplicate completed source work and finite polling.
- Update docs and verify the authorized general-worker restart and actual
  progress of the existing job with bounded normal reads.

## Out of scope

API/Admin lifecycle, GC execution/eligibility/threshold changes, removing
data, starting a new import, manual checkpoint/status mutation, migrations,
OpenAPI shape changes, new queue infrastructure, benchmark, push or merge.

## Acceptance criteria

- [x] Waiting and normal imports both allow exactly the configured reserve,
  default 5 GiB, and block below it, irrespective of GC target 80 GiB.
- [x] Configured overrides reach the worker; direct default construction
  does not silently retain the old 30 GiB reserve.
- [x] Saved storage-wait state resumes in a newly constructed workflow;
  completed source work, identity, counts and checkpoint are preserved.
- [x] Storage-deferral polling waits between attempts; normal completed
  work does not get an added artificial delay.
- [x] Focused tests, scoped lint/format/type checks and relevant regressions
  pass; unrelated pre-existing failures are reported separately.
- [ ] Only the explicitly authorized general worker is restarted, one live
  instance is verified, and the same existing import shows actual progress.
- [x] Docs and Outcome are updated and this fix has a separate versioned
  main-branch commit, excluding pre-existing changes.

## Technical notes

D-534 makes the configured hard reserve authoritative for in-flight import
resumption. Admission still retains its conservative artifact estimate;
warning, GC trigger and GC target remain unchanged. Storage wait remains a
durable `created` job with `waiting_for_storage` stage; no new status or
persisted fields are needed. Add the existing polling delay to the storage
deferral result instead of performing unbounded immediate reclaims.

## Expected files

- `services/worker/src/game_predictor_worker/images/production_workflow.py`
  — constructor defaults and `_has_pipeline_capacity`
- `services/worker/src/game_predictor_worker/cli.py` — import composition
- `services/worker/src/game_predictor_worker/jobs/runtime.py` — `run_forever`
- New `services/worker/tests/test_image_import_storage_resume.py`
- Relevant existing worker composition/runtime test files if needed
- Requirements/architecture/API narrative/operator guide listed above
- `ai_docs/process/DECISION_LOG.md`, `CURRENT_STATE.md` and this task

## Test cases

- Normal and waiting states: 5 GiB minus one byte blocks; exactly 5, 5 plus
  one byte, 50.23 GiB and 80 GiB pass.
- Explicit larger reserve and invalid negative reserve retain protection.
- Fresh workflow and worker recover a persisted storage-wait checkpoint,
  with no new job, unchanged source identities and no repeated settled work.
- Polling sleeps after storage wait/no job but not successful processing;
  tests replace sleep and stop after a finite number of iterations.
- CLI default and override configure only the hard reserve, not GC target.

## Verification

Run the new focused pytest module first, scoped Ruff and strict mypy next,
then relevant worker/ingestion/runtime/CLI/capacity tests. Use fresh test
processes with an explicit maximum 120-second timeout per step. Perform no
load test or large synthetic fixture. After successful verification restart
only the named general lane using the existing process manager, verify the
old process has ended and one new worker heartbeat is ready, and compare
bounded reads of this existing job/source counters. Do not await the entire
import or change its status/checkpoint directly.

## Risks / open questions

- The running general worker has no code reload; its separate restart is
  explicitly authorized. API/Admin lifecycle is not authorized.
- No promise of zero future capacity failures: less than the hard reserve
  must still pause safely; a bounded polling delay prevents a tight loop.
- Pre-restart read-only check at 19:22:52 UTC found database revision
  `0146_symbol_review_import_filter_index`, while current code requires
  `0147_merge_v7_main`. Do not stop the healthy existing general process
  until the V7 schema is migrated. That migration and API/Admin lifecycle
  are not included in the separate general-restart approval.
- Uncommitted management migration `0148_management_points_machines` belongs
  to another task. A V7-only upgrade must target `0147_merge_v7_main`, not
  blindly upgrade to `head` while that unrelated work is in progress.

## Outcome

Repository implementation is verified; live rollout remains pending the
existing V7 migration blocker. Keep this task `in_progress` until the same
existing import demonstrably advances after the authorized general restart.

Changes:

- Worker constructor and CLI fallback use the shared five-GiB hard-reserve
  default. Explicit reserve overrides remain effective. Invalid non-positive
  direct-constructor reserves are rejected before storage creation.
- Source-copy and normal/paused pipeline checks share one threshold. Removed
  the GC resume-target argument; warning, GC and admission policies remain
  unchanged. The polling loop sleeps after durable storage deferral.
- Requirements, architecture, API narrative and operator guide document
  D-534. No schema or HTTP shape was changed by this fix.

Verification:

- Loading the original HEAD versions in a test-only process reproduces both
  new targeted regressions: paused-reserve equality incorrectly blocks and
  storage-deferral polling does not sleep. Both pass on the fixed code.
- Fresh-process focused pytest: **24 PASS**.
- Relevant worker workflow/orchestration/source-ingestion/runtime plus new
  regressions: **119 PASS** in 11.09 seconds. Windows sandbox blocked strict
  path resolution/hardlinks in the first attempt; an unsandboxed test-only
  rerun with short `.runtime/t928a` temporary paths passed. No production
  import data or service process was modified by tests.
- API capacity/config/retention regressions: **71 PASS**.
- Scoped strict mypy: **PASS**, four changed Python files; imported code
  followed silently and third-party ML imports skipped, retaining strict
  checks on the changed implementation and new tests.
- Scoped Ruff lint and format check: **PASS**, four changed Python files.
- Existing `test_worker_cli.py`: four fixture failures and two passes.
  Loading the HEAD version of CLI in a separate test process reproduces all
  four failures: missing `grid_shadow_enabled` / V7 settings in its old
  `SimpleNamespace` fixture. These unrelated fixture failures are preserved;
  the new configured/default-capacity CLI composition tests pass.
- Read-only live check: same job remains at **535/2915** sources, zero file
  failures, 2380 discovery sources, general heartbeat healthy. Free space
  **50.14 GiB**, configured reserve 5 GiB. General process remains the original
  managed PID 6984 / Python child 19496; no restart, API/Admin operation,
  manual job mutation, data cleanup, migration, push or merge was performed.

Remaining acceptance/Definition of Done: safely apply the already-existing
V7 migration under separately authorized operations/user-managed services,
then restart only general with its seven-thread budget and confirm one live
instance plus actual source progress for this same job. Do not claim live
repair complete on the basis of unit tests or a healthy heartbeat alone.
