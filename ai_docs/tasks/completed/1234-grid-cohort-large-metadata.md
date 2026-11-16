---
title: Large grid cohort metadata compatibility
status: done
last_updated: 2026-11-16
---

# TASK-1234 — Large grid cohort metadata compatibility

## Status

`done`

## Goal

Read the preserved 20.20 MiB manifest consistently during freeze and training,
then enable resuming the existing TASK-1230 workflow without replacing its data.

## Context

Parent `42f30e0e-9707-4cf9-aaf6-10482f6e9d60` failed during freeze with
`GRID_COHORT_METADATA_TOO_LARGE`; cohort `19a52a6c-99ea-56ba-b713-c918338db415`
is ready_to_freeze. The published manifest is 21,181,768 bytes, SHA-256
`d2c9c9c552fcaf3ff89c5acb6803ab9f6061ad67c962b487bddd4a35d4f22620`.
Both the API reader and the training snapshot reader currently enforce 16 MiB,
while the publisher has no matching bound.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/CROSS_AUDIT.md`

## Scope

- Use a shared 64 MiB JSON metadata resource bound in publisher and both readers.
- Verify SHA-256 against the exact bounded bytes subsequently decoded by the API.
- Reject oversized metadata before immutable publication; preserve existing hashes.
- Preserve source/page/index checks, split evidence, currentness and quality gates.
- Verify the preserved manifest read-only and regression behavior on isolated storage.
- Resume only the existing parent, after reviewed deployment and fresh worker code.

## Expected files

- Existing: domain/grid_training_cohorts.py metadata constants;
  storage/grid_training_cohort_artifacts.py publisher/reader;
  worker images/grid_cohort_dataset.py snapshot reader.
- Existing: API cohort-core and worker snapshot tests, architecture, code maps.

## Acceptance criteria

- [x] Previously published manifests above 16 MiB are read by API and training.
- [x] Publication and readers agree at the new bound; oversized input fails closed.
- [x] Corruption, unsafe paths, stale human/source evidence still fail closed.
  Existing currentness checks are unchanged; incomplete E2E coverage is recorded as P2-2.
- [x] Lost-response replay and a fresh process reuse identical immutable artifacts.
- [x] Required independent Claude review has a valid result before commit.
- [x] Same-parent operational resume is verified, or its concrete blocker recorded.

## Verification

Targeted API cohort-core and worker dataset pytest, scoped ruff/mypy,
code-map and docs checks; all finite commands bounded to 120 seconds.
Read-only live artifact proof uses a copy in temporary storage and a fresh process.
Claude CLI review uses the repository runner, with no authentication changes.

## Risks / open questions

- 64 MiB is a bounded memory resource budget, not a photo selection cap. Larger
  future metadata is rejected before publication, rather than leaving unreadable data.
- API and worker processes need the reviewed code before resuming; service control
  belongs to the operator. Activation and new workflows are outside this repair.

## Outcome

Commit: v1.7.649 / `a79b12aba25192a02276d670f31d85f0278505ed`.

Implementation is isolated in `codex/grid-cohort-large-manifest`; Git writes work.

### Changed

- Shared 64 MiB metadata budget in publication, API and training snapshot readers.
- API hashes the same bounded byte buffer it decodes; no second unchecked read.
- Oversized JSON is rejected before publishing an immutable file.
- Metadata schema, canonical bytes, stored hashes, split and quality gates are unchanged.

### Verification results

- API cohort-core / worker snapshot suites: 79 PASS, 6 pre-existing FAIL.
  All three new regression tests pass. The six failures reproduce with the HEAD
  test file; currentness, repository and materialization failure-path source is
  byte-identical to HEAD after line-ending normalization. Existing fixtures omit
  artifact_root/policyVersion or return int instead of a SQL result. Not changed.
- Preserved 21,181,768-byte manifest and its 5,127-page index copied into isolated
  temporary storage: API and training reader PASS with identical full manifest;
  second fresh Python process PASS. Both readers reject corrupted copy by SHA-256.
  Production artifacts were only read and remain unchanged.
- Scoped ruff lint/format PASS (5 files); scoped mypy PASS (3 source files).
- `npm run docs:check` PASS; `npm run code-map:check` PASS; maps regenerated.
- Local API confirmed same failed parent/cohort and null training/candidate IDs.
- Disposable application-role PostgreSQL E2E verified committed freeze, restart/replay
  eligibility and a fresh-process dataset with 120 exact-node/render targets. It then
  stopped at its existing 105-second soft deadline (105.828 s) while preparing the
  separate stale-input case: full test FAIL, no complete stale-input proof claimed.
  Fixture cleanup completed and its application test role was dropped. No rerun or
  timeout weakening; operator data was not changed.
- Independent Claude Opus 5.5 CLI audit PASS, 0 open P0/P1; report and receipt:
  `ai_docs/quality/TASK-1234_AUDIT_claude-opus-5-5.md` and adjacent `.receipt.json`.
  Payload SHA-256 `4a264a795c8661567e329907f083ba3ad3e3c39d31e3a6e015943f2e50919537`
  matches the frozen brief and receipt. Model confirmed by CLI init; high effort
  was requested, not independently confirmed (report self-labels standard).

### Review findings and retained risks

- P2-1: portable production-comparison export retains a 16 MiB copy limit. It is
  outside this parent freeze/training path; its separate export remains unavailable
  for this large cohort. No change to that report workflow in this repair.
- P2-2: full stale-input E2E case remains unverified after the test's soft deadline.
  Retain the coverage gap explicitly. Currentness and evidence validation source is
  identical to HEAD; static independent review found no P0/P1. No gate was weakened.
- P2-3: raw metadata may use 64 MiB plus the decoded Python object; this finite
  resource budget is accepted for the repair. Larger JSON fails before publication.

### Definition of Done / handoff

- Code, edge boundaries, immutable replay, restart proof, scoped quality checks,
  documentation and independent review completed for the metadata repair.
- API/schema, migrations and model activation are unaffected by this change.
- Parent TASK-1230 remains active. Its completion requires actual training/evaluation,
  which is not claimed by closing this independent compatibility repair.

### Not completed

- Deployment, fresh loaded processes and same-parent resume remain pending explicit
  result acceptance/merge authorization and operator service restart. No new learning,
  training, activation, merge or push performed. Git and Claude OAuth are no longer
  blockers in this session. Resume must use existing parent
  `42f30e0e-9707-4cf9-aaf6-10482f6e9d60` through its existing resume endpoint.
- Stale-input section of the full freeze-currentness PostgreSQL regression remains
  unverified because its soft deadline elapsed; baseline unit failures documented above.
