---
title: TASK-1052 — Import resume with originals replaced by verified crops
status: done
last_updated: 2026-10-18
---

# TASK-1052 — Import resume with originals replaced by verified crops

## Status

`done`

## Goal

Retrying an import whose originals were deleted after a verified crop neither
copies them back nor fails; every import path that needs the whole frame
refuses with `SOURCE_ORIGINAL_CROPPED` before it writes anything.

## Context

[Photo crop plan](../delivery/PHOTO_CROP_STORAGE_EXECUTION_PLAN_20261017.md),
revision 3 (R11). A retry (`retry_job` → `requeue_job_with_fresh_progress`)
re-runs `ensure_original` for every original of the import manifest
(`images/source_ingestion.py`); a missing file is copied from the import source
or fails with `IMAGE_SOURCE_UNAVAILABLE`. Browser staging is removed 24 h after
the handoff and `waiting_for_review` does not protect it.

## Dependencies / entry conditions

TASK-1051. Plan revision 3 accepted.

## Recommended execution

`claude-opus-5-5`, reasoning `xhigh`. Audit: Codex `gpt-6.1-sol` / `high`
(none when the quota is exhausted, recorded in Outcome).

## Relevant docs

- Plan R11, revision 3; D-562
- `images/source_ingestion.py`, `images/orchestration.py`,
  `images/large_import_geometry_guard.py`, `images/page_geometry_preflight.py`,
  `storage/image_job_repository.py` (`retry_file`), `api/image_imports.py`
  (page geometry override)

## Scope

- `ensure_original`: a missing original whose registry row is
  `original_deleted` and whose crop and attestation verify is accepted
  without a copy; any other missing file behaves as today.
- `retry_file` of a source whose original was deleted, page geometry override,
  preflight and the geometry guard without an existing report refuse with
  `SOURCE_ORIGINAL_CROPPED` before any write.
- Confirm (and test) that a retried import skips completed files and reuses the
  geometry guard report, so no whole frame of a deleted original is decoded.

## Out of scope

Runs on operator data (TASK-1050); re-importing a file (restores the original
as today).

## Acceptance criteria

- [x] (partly: covered at the workflow boundary, no full PostgreSQL import
      retry; see Deviations) Restart/PostgreSQL test: import with an original deleted by the
      deletion job, staging removed → retry completes without
      `IMAGE_SOURCE_UNAVAILABLE` and without a copy; with staging present →
      no copy either.
- [x] Refusals with `SOURCE_ORIGINAL_CROPPED` and no side effects for each
      whole-frame path.
- [x] Lint, mypy, focused and PostgreSQL tests pass; audit closed.

## Verification

```powershell
D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/worker/tests -k "source_ingestion or source_crop or geometry_guard"
```

## Risks / open questions

- Import paths not found by the inventory; the deletion runs per original
  only after the pilot proves the retry on real data.

## Outcome

Commit: v1.7.417 / `d53201b5b9911577194df1bd9068cc51a735a8bd`.

### Changed

- `images/source_ingestion.py`: `ensure_original(..., replaced_by_crop=...)`
  skips the copy only when the caller marks the original as replaced and the
  crop sibling carries an attestation of this original (checksum and size)
  bound to the crop file checksum; otherwise the existing copy path runs.
  `ingest(..., replaced_originals=...)` passes the set through.
  `manifest_exists(job)` and `originals_replaced_in_manifest(source_job_id)`
  are new read-only helpers.
- `images/production_workflow.py`: only a retry (the job's manifest already
  exists) asks the registry (`deleted_original_checksums`, rows
  `original_deleted`) and passes the result to ingestion; a new import of the
  same file copies the original back (R10).
- `images/large_import_geometry_guard.py`: a new report refuses with
  `SOURCE_ORIGINAL_CROPPED` when a sampled original was replaced; an existing
  report is reused unchanged.
- `images/page_geometry_preflight.py`, `images/neural_page_geometry_preflight.py`:
  a managed re-preflight refuses before it materializes its own manifest.
- `storage/image_job_repository.py`: `retry_file` refuses with
  `409 SOURCE_ORIGINAL_CROPPED` for a file whose original row is
  `original_deleted`, before any change.
- `api/image_imports.py` and `application/managed_reprocess_evidence.py`:
  a page geometry override refuses `SOURCE_ORIGINAL_CROPPED` when the managed
  original was replaced, also while the browser staging still exists.
- `API_CONTRACT.md`: retry, re-preflight, guard and override behavior.

### Deviations

- There is no end-to-end PostgreSQL test of a full import retry (it would need
  the whole recognition pipeline). Coverage instead: the workflow boundary with
  the real original store, real ingestion and a real verified crop (retry
  keeps the crop with staging present or removed; a new import restores the
  original), the existing resume test showing that settled files only run the
  database stages `manual_review`/`validation`, the guard report reuse, and the
  registry query on PostgreSQL (TASK-1048 tests and the `retry_file` test).

### Audit

Codex `gpt-6.1-sol` / `high`, round 1:
[TASK-1052_AUDIT_gpt-6.1-sol.md](../quality/TASK-1052_AUDIT_gpt-6.1-sol.md),
verdict REVISE (P0-1..4, P1-1). One fix round:

- P0-1: the skip requires the registry state `original_deleted`, passed by
  the workflow; tests without the row keep `IMAGE_SOURCE_UNAVAILABLE`.
- P0-2: only a retry of the same import (existing manifest) asks the
  registry; a new import restores the original; tests at ingestion and
  workflow level.
- P0-3: the override refuses before decoding, with staging present; HTTP test.
- P0-4: both preflights check the source manifest before writing their own.
- P1-1: workflow-level retry test added; the remaining gap is listed above.

No second audit round.

### Verification

- `test_import_resume_with_cropped_originals.py` 11, `test_image_source_ingestion.py`,
  `test_neural_page_geometry_api.py` (override refused with staging): 48 passed together.
- `test_large_import_geometry_guard.py`: 12 passed (new report refused,
  existing report reused).
- PostgreSQL: `test_image_batch_store.py::test_image_job_operations_aggregate_and_retry_failed_stage`
  (retry refused with `SOURCE_ORIGINAL_CROPPED`, then allowed without the row).
- Regression: worker subset (ingestion, workflow, guard, preflight, resume,
  crop, normalization, import, neural) 428 passed, 2 skipped; API subset (image
  imports, neural page geometry, managed reprocess, image jobs, source crop,
  lateral) 277 passed. Two workflow test stubs gained `manifest_exists`.
- ruff clean; mypy of the changed modules clean apart from the two known errors.
