---
title: TASK-1048 — `source_original_deletion` job, cleanup and anchor/cohort guards
status: done
last_updated: 2026-10-17
---

# TASK-1048 — `source_original_deletion` job, cleanup and anchor/cohort guards

## Status

`done`

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

`claude-opus-5-5`, reasoning `xhigh` (plan table). Audit: Codex `gpt-6.1-sol` / `high`
(operator change 2026-10-17).

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

- [x] Deletion never runs without its own preview, token, `confirmed` and `acknowledgeIrreversible`.
- [x] A blob that became ineligible, a changed original, a missing or invalid crop each keep the original.
- [x] Interruption after unlink before the state write is reconciled after restart.
- [x] Cleanup removes crop files and row only with the last reference.
- [x] New calibration profiles never pin a deleted original as anchor; cohorts refuse deleted originals.
- [x] Lint, mypy, focused and PostgreSQL tests pass.

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

Commit: v1.7.411 / `f78cb876980ba3213fd40993f8191f239ed2af6a`.

### Changed

- Worker `source_original_deletion.py` (`SourceOriginalDeletionHandler`),
  registered for `source_original_deletion` in `cli.py`; the API accepts the
  `original_deletion` kind again (`EXECUTABLE_RUN_KINDS`).
  - Plan: verified, eligible crops with original bytes and the attestation
    checksum; `irreversible: true`; reasons `NOT_CROPPED`, `ALREADY_DELETED`.
  - Execute under the blob lock: registry row and planned attestation, crop and
    attestation through the loader with the attested canvas, original SHA-256
    and size; then `SqlSourceCropCatalog.delete_original_if_still_eligible`
    takes the exclusive storage write fence of every game of the blob (session
    advisory lock with the key of `GameStorageRouter`), opens a fresh
    REPEATABLE READ snapshot, checks lease, eligibility (same games) and
    `crop_covers_points` (today's protected quads inside the attested crop with
    margin and ring clearance), unlinks and marks `original_deleted` with
    `deletion_job_id` in one transaction.
  - Restart: a missing original with a `verified` row is reconciled after crop
    verification; an original deleted by the same job before the checkpoint is
    counted once.
- Migration 0168 adds `source_image_crops.deletion_job_id` (FK `jobs`, CHECK
  only with `original_deleted`); dropped on downgrade.
- Cleanup R10 (`cleanup_repository.py`): an original deleted as last reference
  brings its crop and attestation paths and its registry row; the quarantine
  directory uses Windows long paths (`application/cleanup.py`), since a crop
  path under the quarantine key exceeded `MAX_PATH`.
- Guards: `train_grid_profile(unavailable_anchor_checksums=...)` skips deleted
  originals as anchors; `grid_calibration_repository.create_candidate` binds the
  game for write (shared fence) before reading `deleted_original_checksums`;
  V3 cohort materialization binds for write and refuses deleted originals
  before any copy (first page: whole cohort; later pages: their members).
- Docs: `API_CONTRACT.md`, `DATA_MODEL.md`, `LOCAL_OPERATION_GUIDE.md`.

### Deviations from the plan

- Checkpoint every 25 originals, as for crop runs.
- New skip outcomes `cropOutdated` and `gameBusy` (fence wait over 120 s).
- Jobs started in another game after the deletion (a new import of the same
  file restores the original through `ensure_original`; other jobs read the
  crop or fail closed with `SOURCE_ORIGINAL_CROPPED`) are not fenced: only the
  games of the blob are.

### Audit

Codex `gpt-6.1-sol` / `high`, round 1:
[TASK-1048_AUDIT_gpt-6.1-sol.md](../quality/TASK-1048_AUDIT_gpt-6.1-sol.md),
verdict REVISE (P0-1..3, P1-1). One fix round:

- P0-1: `crop_covers_points` in the delete transaction; `cropOutdated` keeps
  the original; unit test.
- P0-2: exclusive storage write fences of the blob's games before the fresh
  snapshot; calibration and cohort materialization take the shared fence
  before reading the registry.
- P0-3: `deletion_job_id` makes a restart count the job's own deletion once;
  unit test.
- P1-1: `test_cleanup_repository.py` (TASK-1042 workflow) now covers a
  retained original keeping crop, attestation and row, and the last reference
  removing them with the original already deleted; it exposed and fixed the
  quarantine `MAX_PATH` failure.

No second audit round.

### Verification

- Worker `test_source_original_deletion_job.py` 10 + `test_source_crop_job.py`
  28 (2 jpegtran skips without the tool path): passed.
- API `test_source_original_deletion_guards.py`, `test_source_crop_runs_api.py`,
  cleanup 38, calibration/cohort/source 200: passed.
- PostgreSQL: `test_source_original_deletion_postgres.py` (crop, deletion,
  lost state write, retry, reconciliation, loader with crop),
  `test_cleanup_repository.py` 5, `test_source_crop_runs_postgres.py` 4,
  `test_source_image_crops_postgres.py`: passed. Broader subset (`cleanup or calibration or cohort or source_crop or
  source_original or superseded_import or schema or baseline`): 55 passed, 4 failed, all outside this task: pre-existing also on `main`:
  `test_grid_cohort_asset_guard_postgres.py::test_publication_receipt_and_gc_quarantine_are_serialized`,
  `test_grid_reinference_postgres.py::...lost_reply[cleanup_reset]`; two
  retention-edge tests need `GAME_PREDICTOR_GC_RETENTION_EVIDENCE_ROOT`.
- ruff clean; mypy only the two known errors.
