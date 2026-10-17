---
title: TASK-1047 — Durable `source_crop` job (plan and execute) with its API
status: todo
last_updated: 2026-10-17
---

# TASK-1047 — Durable `source_crop` job (plan and execute) with its API

## Status

`todo`

## Goal

An operator can plan a crop run (eligibility over all or selected originals,
counts, estimated saving), confirm it with a token, and a resumable worker job
creates verified lossless crops and their registry rows without touching any
original file.

## Context

Stage B of the accepted
[photo crop plan](../delivery/PHOTO_CROP_STORAGE_EXECUTION_PLAN_20261017.md)
(R6–R9, revision 2). Stage A (TASK-1043–1046) is in `main` with migration
`0167`. Eligibility over ~166k blobs does not fit an HTTP request, so planning
is the first phase of the durable job and execution a second, confirmed phase.

## Dependencies / entry conditions

TASK-1043–1046 merged; `jpegtran` from libjpeg-turbo 3.2.0 in
`.tooling/libjpeg-turbo-3.2.0/bin/`. Stage B cost approved by the operator
(2026-10-17). Running the job on operator data is not part of this task.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (plan table). Audit: Codex `gpt-6-astra` / `high`.

## Relevant docs

- Plan sections R1, R5–R9, revision 2; D-562
- `ai_docs/architecture/API_CONTRACT.md` (image storage), `DATA_MODEL.md`
- Pattern: `storage_gc` (`api/image_storage.py`, `application/storage_gc.py`,
  `storage/storage_gc_repository.py`, worker `storage_gc.py`)

## Scope

- Migration `0168_source_crop_runs`: job types `source_crop` and
  `source_original_deletion` (the second is used by TASK-1048), shared table
  `public.source_crop_runs` (manifest v19) with kind, status, scope, plan and
  execute job ids, manifest path/checksum, preview token, counters, bounded
  failures, timestamps.
- API (pion: backend, OpenAPI, generated client, wrapper, request tests):
  `POST /admin/image-storage/source-crop-previews` (scope: optional game,
  optional checksum list ≤ 500, optional limit) → 201 run in `planning` with
  its plan job; `GET /admin/image-storage/source-crop-runs/{runId}`;
  `POST /admin/image-storage/source-crop-runs` (preview id, manifest checksum,
  token, `confirmed`) → execute job. One active run at a time
  (`SOURCE_CROP_RUN_ACTIVE`); stale or unconfirmed start refused.
- Worker `SourceCropHandler` (lane `general`):
  - plan: keyset pages of eligibility (REPEATABLE READ owner session),
    per-reason exclusion counts, original sizes, a crop plan per eligible blob
    (header-only JPEG read) for the estimated saving; immutable manifest
    `data/source-crop-runs/<runId>/manifest.json`; run becomes `previewed`.
  - execute: per blob re-check eligibility, skip existing registry rows,
    verify original SHA-256, plan, `jpegtran -copy all -optimize -crop`,
    5% benefit rule, R7 pixel verification, attestation, atomic file writes
    (crop then attestation), registry row `verified`; checkpoint every 25
    blobs; resume after restart without duplicates; per-blob failures do not
    stop the run.
- `jpegtran` adapter with version check (`SOURCE_CROP_TOOL_UNAVAILABLE` before
  any file is written), path from `GAME_PREDICTOR_JPEGTRAN_PATH` or the
  `.tooling` default; operator instruction in `LOCAL_OPERATION_GUIDE.md`.
- `NON_IMAGE_JOB_TYPES` keeps crop-run jobs from excluding every original.

## Out of scope

Deleting originals (TASK-1048), UI (TASK-1049), running on operator data.

## Acceptance criteria

- [ ] Migration upgrade/downgrade on `*_test`; downgrade refused with history.
- [ ] Plan writes a manifest whose eligible set equals the eligibility reader; counts per reason.
- [ ] Execute creates crops whose pixels equal the original region except the edge ring, with valid attestation and `verified` row; originals keep SHA-256, size and mtime.
- [ ] Restart in the middle resumes without duplicates; a blob that fails verification leaves no crop files and the run continues.
- [ ] HTTP: preview, start (confirmation, stale token, active run), get; OpenAPI and client regenerated.
- [ ] Lint, mypy, focused API/worker tests, PostgreSQL tests pass.

## Technical notes

R7 verification uses `verify_crop_pixels`; `jpegtran` output that differs in
the inner region is a failure, never accepted. Files are written as
`.<uuid>.part` next to the target and renamed; the attestation is the last
file, so the loader never sees a crop without attestation. A crop file
without registry row is re-verified and either registered or removed (it is
this job's own output).

## Expected files

Confirmed at task start (new worker module, API service/router/schemas,
repository, migration, manifest v19, tests).

## Test cases

See acceptance criteria; the real `jpegtran` is exercised when installed and
skipped otherwise; a Python block-aligned cropper stands in for unit tests.

## Verification

```powershell
D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/worker/tests -k source_crop
D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests -k source_crop
```

## Risks / open questions

- Planning time for the whole library is unknown; measured in TASK-1050.

## Outcome

Wypełnia agent po pracy.
