---
title: TASK-1049 — Storage panel: photo cropping and original deletion
status: todo
last_updated: 2026-10-17
---

# TASK-1049 — Storage panel: photo cropping and original deletion

## Status

`todo`

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

- [ ] State and interaction tests for plan, start, progress, failure and the deletion warning.
- [ ] Inventory and GC regression test passes.
- [ ] Lint, typecheck and tests of the Admin workspace pass.

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

Wypełnia agent po pracy.
