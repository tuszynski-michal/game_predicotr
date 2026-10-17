---
title: TASK-1049 — Storage panel: photo cropping and original deletion
status: done
last_updated: 2026-10-17
---

# TASK-1049 — Storage panel: photo cropping and original deletion

## Status

`done`

## Goal

The Admin Storage panel lets the operator plan, review and start crop runs and,
in a separate clearly warned step, original deletion runs, and follow their
progress.

## Context

Stage B of the accepted
[photo crop plan](../delivery/PHOTO_CROP_STORAGE_EXECUTION_PLAN_20261017.md).
Uses only the TASK-1047/1048 API through the generated client.

## Dependencies / entry conditions

TASK-1047 and TASK-1048 API and generated client.

## Recommended execution

`claude-sonnet-5-5`, reasoning `high` (plan table), delegated; escalate to
`claude-opus-5-5` when an API change is needed. No audit.

## Relevant docs

- `apps/admin/src/features/storage/storage-workspace.tsx` (existing pattern)
- `ai_docs/architecture/API_CONTRACT.md` (source crop runs)

## Scope

- Section „Przycinanie zdjęć”: scope (all / game / checksum list), plan,
  preview with eligible count, original bytes, estimated saving and exclusion
  reasons, start with confirmation, progress and result.
- Separate „Usuń oryginały przyciętych zdjęć” step: deletion plan, bytes to
  free, explicit irreversible warning (no photo backup), acknowledgement
  checkbox and confirmation.
- Existing inventory and GC behavior unchanged (regression test).

## Out of scope

API changes, running jobs on operator data.

## Acceptance criteria

- [x] State and interaction tests for plan, start, progress, failure and the deletion warning.
- [x] Inventory and GC regression test passes.
- [x] Lint, typecheck and tests of the Admin workspace pass.

## Technical notes

Polish UI copy; no hand-written response types.

## Expected files

`apps/admin/src/features/storage/*` (confirmed at task start).

## Test cases

See acceptance criteria.

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
```

## Risks / open questions

- None known.

## Outcome

Commit: v1.7.412 (hash dopisuje kolejny commit).

Executed by a delegated `claude-sonnet-5-5` / `high` agent (plan table), reviewed
and re-verified by `claude-opus-5-5`. No audit (plan table).

### Changed

- `apps/admin/src/features/storage/source-crop-state.ts`: scope draft to API
  scope (all games, one game, 1-500 distinct SHA-256 values, optional limit),
  Polish labels for statuses, exclusion reasons (with the raw code) and
  outcomes, progress, the start gate (deletion needs the acknowledgement),
  Polish messages for the run error codes, resume of the newest run per kind.
- `source-crop-actions.ts`: plan, refresh, start and list through the generated
  client wrapper; a deletion is never sent without `acknowledgeIrreversible`.
- `source-crop-panel.tsx` and `.module.css`: section „Przycinanie zdjęć” (scope,
  plan with polling, preview with eligible count, original bytes, estimated
  saving and exclusion reasons, confirmation, progress, result with failures
  and error) and a separate red section „Usuń oryginały przyciętych zdjęć” with
  the permanent warning „Brak kopii zdjęć — operacji nie można cofnąć”, an
  acknowledgement checkbox gating the start, a confirmation dialog, progress and
  deletion outcomes. Mounted after the GC section in `storage-workspace.tsx`.
- `features/jobs/job-state.ts`: Polish labels of the two new job types (the
  `Record<JobType, string>` requires them).

### Tests

- `test/source-crop-state.test.mjs`, `test/source-crop-actions.test.mjs`,
  two contract tests in `test/storage-workspace-contract.test.mjs`.
- `test-interactions/source-crop-panel.test.mjs` (9 jsdom tests: plan and
  preview, scope validation, confirmation, progress, failure, error codes,
  nothing eligible, deletion warning and acknowledgement gating, deletion
  outcomes, resume) and `test-interactions/storage-workspace-regression.test.mjs`
  (3 tests: inventory, GC preview and confirmed start, inventory refresh).

### Verification

- `npm run test --workspace @game-predictor/admin`: 799 passed.
- The two interaction files with `tsx --test`: 12 passed.
- `npm run lint --workspace @game-predictor/admin`: 0 errors (5 existing
  warnings in other features).
- Typecheck: `tsc` with a temporary config mapping
  `@game-predictor/admin-api-client` to the worktree package passes (exit 0).
  The plain `npm run typecheck` in this worktree resolves the client through
  the `node_modules` junction to the main checkout, which does not yet have the
  TASK-1047 client; it passes once the branch is merged.
- `test:geometry` (all interaction tests) has 10 failures in
  `super-game-series-workspace.test.mjs`; the same 10 fail on `main`.
