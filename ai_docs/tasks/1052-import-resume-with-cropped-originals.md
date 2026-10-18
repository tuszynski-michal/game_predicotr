---
title: TASK-1052 — Import resume with originals replaced by verified crops
status: todo
last_updated: 2026-10-18
---

# TASK-1052 — Import resume with originals replaced by verified crops

## Status

`todo`

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

- [ ] Restart/PostgreSQL test: import with an original deleted by the
      deletion job, staging removed → retry completes without
      `IMAGE_SOURCE_UNAVAILABLE` and without a copy; with staging present →
      no copy either.
- [ ] Refusals with `SOURCE_ORIGINAL_CROPPED` and no side effects for each
      whole-frame path.
- [ ] Lint, mypy, focused and PostgreSQL tests pass; audit closed.

## Verification

```powershell
D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/worker/tests -k "source_ingestion or source_crop or geometry_guard"
```

## Risks / open questions

- Import paths not found by the inventory; the deletion runs per original
  only after the pilot proves the retry on real data.

## Outcome

Wypełnia agent po pracy.
