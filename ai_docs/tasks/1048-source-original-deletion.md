---
title: TASK-1048 — `source_original_deletion` job, cleanup and anchor/cohort guards
status: todo
last_updated: 2026-10-17
---

# TASK-1048 — `source_original_deletion` job, cleanup and anchor/cohort guards

## Status

`todo`

## Goal

Originals of verified crops can be deleted only through a planned, separately
confirmed, re-verifying and resumable job; cleanup and future calibration
or cohort builds stay consistent with deleted originals.

## Context

Stage B of the accepted
[photo crop plan](../delivery/PHOTO_CROP_STORAGE_EXECUTION_PLAN_20261017.md)
(R8, R10, revision 2). This is the only destructive step; the operator
decided to delete without a photo copy (D-562).

## Dependencies / entry conditions

TASK-1047 (run table, job types, crop registry rows `verified`).

## Recommended execution

`claude-opus-5-5`, reasoning `xhigh` (plan table). Audit: Codex `gpt-6-astra` / `high`.

## Relevant docs

- Plan R8, R10, revision 2; D-562
- `storage/cleanup_repository.py` (TASK-1042 shared-original rules)
- `domain/grid_calibration.py`, `storage/grid_training_cohort_artifacts.py`

## Scope

- Run kind `original_deletion` on the TASK-1047 endpoints: the plan lists
  `verified` crops whose blobs are still eligible, with bytes to free; start
  additionally requires `acknowledgeIrreversible: true`.
- Worker execution per blob: re-check eligibility, registry row `verified`,
  crop and attestation files verify (loader), original SHA-256 and size equal
  the row, no active image job; then unlink the original and mark
  `original_deleted` in the same unit; reconcile after a restart (missing
  original with `verified` row → re-verify crop, then mark).
- Cleanup (`cleanup_repository.py`): deleting the last source of a blob also
  removes its crop, attestation and registry row; shared rules unchanged.
- Guards from plan revision 2: calibration anchor selection skips blobs in
  state `original_deleted`; cohort building refuses them before copying (stable
  code, no partial cohort).

## Out of scope

UI (TASK-1049), running on operator data (TASK-1050).

## Acceptance criteria

- [ ] Deletion never runs without its own preview, token, `confirmed` and `acknowledgeIrreversible`.
- [ ] A blob that became ineligible, a changed original, a missing or invalid crop each keep the original.
- [ ] Interruption after unlink before the state write is reconciled after restart.
- [ ] Cleanup removes crop files and row only with the last reference.
- [ ] New calibration profiles never pin a deleted original as anchor; cohorts refuse deleted originals.
- [ ] Lint, mypy, focused and PostgreSQL tests pass.

## Technical notes

R8. Deletion uses `unlink` without quarantine (operator decision). Each blob is
one unit: verify, unlink, update row; failures are counted, never hidden.

## Expected files

Confirmed at task start.

## Test cases

See acceptance criteria.

## Verification

```powershell
D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/worker/tests -k "source_crop or original_deletion"
```

## Risks / open questions

- Irreversibility; mitigated by R5, R8 and the pilot.

## Outcome

Wypełnia agent po pracy.
