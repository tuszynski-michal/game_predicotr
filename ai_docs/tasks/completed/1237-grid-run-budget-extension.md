---
title: Scoped grid training budget extension and checkpoint recovery
status: done
last_updated: 2026-11-17
---

# TASK-1237 — Scoped grid training budget extension and checkpoint recovery

## Status

`done`

## Goal

Resume the existing stopped training with its verified step-575 checkpoint and an
explicitly approved four-hour cumulative ceiling, without renewing consumption.

## Context

Operator explicitly accepted controlled cancellation, a 2 -> 4 hour limit for this
same run and checkpoint-safe resume, after the 30–60 minute test/audit cost warning.
The run already stopped naturally with RUN_BUDGET_EXHAUSTED, so no cancellation is
needed. Run c489f65f-8272-412b-aaf1-f86bac000856, parent 42f30e0e-9707-4cf9-aaf6-10482f6e9d60,
game 246a1f54-eee8-49d5-b11a-0fde70e5eecd, cohort 19a52a6c-99ea-56ba-b713-c918338db415.
Budget: 7200/7200 seconds, 1200 reserved/8000 steps, two attempts. An immutable
checkpoint 32df4540... exists at step 575, but the stored pointer is null.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/process/CROSS_AUDIT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Owner-only operator CLI: read-only preview, then explicit preview-SHA apply.
- Only stopped, unleased, non-content single-game runs of the approved preset.
- Raise this existing per-run ceiling from 7200 to 14400; preserve all consumption,
  inputs, plan, recipe, seed, state metadata, status, errors and job counters.
- Recover an explicitly selected content-addressed checkpoint only after checksum,
  complete binding and RNG/optimizer validation using the existing loader.
- Transactional row lock/CAS and idempotent lost-response replay; audit history.
- Unit/real PostgreSQL checks, scoped quality, independent Claude review before
  commit/application, then the existing parent resume API; no new run or activation.

## Out of scope

Global budget/preset changes, training/quality policy changes, API/UI/schema changes,
activation, cancellation of another run, modification or deletion of artifacts.

## Acceptance criteria

- [x] Preview is read-only and fails closed on active/foreign/drifted/corrupt state.
- [x] Apply changes only the approved budget ceiling, pointer and audit history;
  stale previews fail and a lost-response replay cannot grant a second extension.
- [x] Checkpoint binding/bytes are verified and consumption remains 7200 s/1200 steps.
- [x] Targeted unit/PostgreSQL/lint/types/docs/maps and Claude review pass.
- [x] The original parent/child resume with 14400 seconds and checkpoint step 575.

## Technical notes

Use existing RunBudget envelope and its canonical digest, leaving the global v2
ceiling unchanged. This is the operator-approved data override for one run, not a
new optimization policy. Apply locks the job and compares input/state hashes; an
active lease or concurrent resume blocks mutation. Existing API resume performs
the ordinary currentness/admission checks. Do not reset time, steps or attempts.

## Expected files

Proposed: worker `training_core/run_budget_extension.py`, operator
`scripts/extend_grid_training_run.py`, focused unit and PostgreSQL tests.
Existing: generated code maps, architecture paragraph, current-state pointer.

## Test cases

Stopped-run extension/recovery; active lease rejection; foreign input, content
experiment, consumed-state drift, wrong checkpoint/older pointer rejection;
tampered preview rejection; idempotent replay after lost response/resume;
real transactional update and stale concurrent state on a disposable database.

## Outcome

Commit: v1.7.656 (hash dopisuje kolejny commit).

Implementation prepared in a separate worktree from main 498ccebf. No other
task/branch work is included. Implementation commit v1.7.655:
5e82a06a4e66ca3e500ceecb2924ebf6f9437054. No cancellation was necessary.

### Changed

- Pure grant builder preserves all state except max_seconds, checkpoint pointer
  and an explicit grant history entry. Existing RunBudget digest/format is retained.
- Owner CLI validates the sealed spec, manifest, complete TrainingPlan binding,
  checkpoint SHA/structure/RNG/optimizer, early-stop state and training exposure.
- Apply checks an exact preview SHA, inactive lease, settled charge and unchanged
  input/state under FOR UPDATE. Replay of the same applied grant is read-only,
  including after the ordinary resume changes status and consumed work.
- No API/schema/global ceiling changes or artifact mutation. No new training ID.

### Verification results

- 14 unit regressions PASS (8.78 s); includes a valid checksum with foreign run
  binding, corrupt bytes, active state, drift, tampered preview, preserved metadata
  and replay after resume. Existing with_current_limits retains the four-hour data
  ceiling after a new worker loads it.
- Dedicated disposable PostgreSQL test PASS (18.15 s): another transaction changes
  state between the first read and FOR UPDATE; the operator update rejects it and
  preserves that concurrent change. A successful apply modifies one existing row,
  leaves status/inputs intact, and lost-response replay adds no second grant.
- Strict scoped mypy with silent imports PASS (2 source files). Scoped lint/format,
  regenerated maps/code-map:check and docs/window checks PASS.
- Actual checkpoint read on CPU passed checksum and full binding/state validation
  at step 575. Read-only CLI preview SHA:
  `8eed026132ba1f7a14d154bc0cfa968892d25bc1a615f04f178848785da75ef8`.
  It retains 7200 used seconds, 1200 reserved steps, two attempts and the 1200-step
  plan; target ceiling is 14400 seconds. Operator evidence is in
  `.runtime/task1237-preview.json` and `.runtime/task1237-before.json`.
- Unit artifact fixtures use an owned short --basetemp under .runtime to avoid the
  desktop runtime's long default Windows temporary path. No production path altered.
- Claude round 1 PASS, 0 open P0/P1; report and SHA-verified receipt in
  `ai_docs/quality/TASK-1237_AUDIT_claude-opus-5-5.md`. Both P2 observations were
  corrected in the permitted correction round: the PostgreSQL replay assertion now
  rereads the database and checks unchanged updated_at, and checkpoint binding uses
  manifest gameId and preset mode exactly like the training child. The fixture now
  includes the production manifest gameId field. Focused tests were rerun; no paid
  audit retry was needed. Original report/receipt remain unchanged as audit evidence.

### Operational verification

The approved preview was applied once. Fresh database read confirmed exact
afterState, unchanged inputs/status and 7200 consumed seconds/1200 reserved steps/
two attempts. Evidence: root .runtime/task1237-after-apply.json. Ordinary parent
resume at 00:21:10 UTC returned the same learningId/runId/cohortId/commandKey.
At 00:23:49 UTC attempt 3 entered training with sealed resume.step=575 and 7200
remaining seconds. New consumption/reservations accrue normally. No new run,
schema migration, service restart or activation was required for this data override.
At 00:32:08 UTC the new process progressed to step 580/1200 from checkpoint 575,
with no error; the complete restart/resume acceptance criterion is verified.
Evidence: root .runtime/task1237-observations.jsonl and task1237-latest.json.

### Not completed

- The actual candidate's training/evaluation remains the enclosing TASK-1230 scope;
  this helper does not claim candidate readiness or activation.
- Integration of this helper branch to main is pending result acceptance; production
  data override already succeeded using the reviewed, committed operator tool.
