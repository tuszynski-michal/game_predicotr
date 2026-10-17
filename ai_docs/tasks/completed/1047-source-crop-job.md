---
title: TASK-1047 — Durable `source_crop` job (plan and execute) with its API
status: done
last_updated: 2026-10-17
---

# TASK-1047 — Durable `source_crop` job (plan and execute) with its API

## Status

`done`

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

`claude-opus-5-5`, reasoning `high` (plan table). Audit: Codex `gpt-6.1-sol` / `high`
(operator change 2026-10-17; without audit once the Codex quota is exhausted).

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
  token, `confirmed`) → execute job; implemented as
  `POST /admin/image-storage/source-crop-previews/{previewId}/start` (high-impact
  target `source-crop-preview:{previewId}`). One active run at a time
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

- [x] Migration upgrade/downgrade on `*_test`; downgrade refused with history.
- [x] Plan writes a manifest whose eligible set equals the eligibility reader; counts per reason.
- [x] Execute creates crops whose pixels equal the original region except the edge ring, with valid attestation and `verified` row; originals keep SHA-256, size and mtime.
- [x] Restart in the middle resumes without duplicates; a blob that fails verification leaves no crop files and the run continues.
- [x] HTTP: preview, start (confirmation, stale token, active run), get; OpenAPI and client regenerated.
- [x] Lint, mypy, focused API/worker tests, PostgreSQL tests pass.

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

Commit: v1.7.410 / `4d157a61d33a908d3020907aaafacf86b3f6d337`.

### Changed

- Migration `0168_source_crop_runs`: job types `source_crop` and
  `source_original_deletion`, shared table `public.source_crop_runs`
  (manifest v19, `game_data_v2_manifest_v19.py`), one active run
  (`uq_source_crop_runs_active`), application-role ACL copied from
  `storage_gc_runs`, downgrade refused with history. Head and manifest bumps in
  runtime and tests (`schema_readiness` head `0168_source_crop_runs`).
- API pion: `application/source_crop_runs.py`, `storage/source_crop_run_repository.py`,
  `schemas/source_crop_runs.py`, `api/source_crop_runs.py` (four routes), the
  start route registered as high-impact (`source-crop-preview:{previewId}`),
  `SourceCropJobPayload`, OpenAPI and generated client, wrapper methods and
  `source-crop-runs-request.test.mjs`.
- Worker: `source_crop.py` (`SourceCropHandler`, `SqlSourceCropCatalog`) and
  `images/jpegtran.py` (version 3.2.0 or `GAME_PREDICTOR_JPEGTRAN_VERSION`,
  30 s per original). Plan writes `data/source-crop-runs/<runId>/manifest.json`
  with per-reason counts (eligibility reasons plus `ALREADY_CROPPED`,
  `ORIGINAL_MISSING`, `ORIGINAL_HEADER_MISMATCH`, `CROP_PLAN_INVALID`) and a
  header-only saving estimate. Execute per original under a PostgreSQL advisory
  lock: current eligibility and registry, original SHA-256 and decoded identity,
  plan, `jpegtran -copy all -optimize -crop`, 5% rule, R7 verification, the
  loader's own `decode_cropped_source_bytes`, crop then attestation by atomic
  rename, registry row in a REPEATABLE READ transaction that re-checks
  eligibility, protected points and the lease. Checkpoint every 25 originals.
- `synchronize_source_crop_job` in the API job repository and every worker
  store transition: cancel, failure, retry and lease recovery reach the run
  atomically.
- `NON_IMAGE_JOB_TYPES` includes both new job types. Docs: `API_CONTRACT.md`,
  `DATA_MODEL.md`, `GAME_DATA_V2_OWNERSHIP.md` (v19), `LOCAL_OPERATION_GUIDE.md`
  (jpegtran), plan model table (operator decision on the audit model).

### Deviations from the plan

- The start route is `POST /admin/image-storage/source-crop-previews/{previewId}/start`
  instead of `POST /source-crop-runs`, matching the high-impact target pattern.
- `limit` bounds the eligible originals in the manifest; exclusion counts cover
  the originals examined until then.
- Checkpoint every 25 originals (task) instead of 100 (plan R8); tool error code
  `SOURCE_CROP_TOOL_UNAVAILABLE` (task) instead of `JPEGTRAN_UNAVAILABLE` (plan).
- The HTTP preview of `original_deletion` is refused
  (`SOURCE_CROP_KIND_UNSUPPORTED`) until TASK-1048 registers its handler.
- A new preview supersedes an unstarted `previewed` run.
- An execute restart that finds an original recorded by the same job after the
  last checkpoint counts it as cropped; a registry row whose files are missing
  is reported as `SOURCE_CROP_FILES_MISSING`, never skipped silently.

### Audit

Codex `gpt-6.1-sol` / `high` (operator change 2026-10-17), round 1:
[TASK-1047_AUDIT_gpt-6.1-sol.md](../quality/TASK-1047_AUDIT_gpt-6.1-sol.md),
verdict REVISE (P0-1..5, P1-1..3). One fix round, all addressed:

- P0-1: every worker write checks the current lease in its own transaction
  (`assert_job_lease`: plan, processing, checkpoint, completion, registry
  insert); per-original file work runs under a session-level advisory lock and
  re-checks the lease before removing leftovers, so a superseded executor
  cannot touch a newer executor's files.
- P0-2: after an exception from the registry write the worker reads the
  registry: the same attestation keeps the files and counts the crop, no row
  removes them, an unreadable state keeps them for reconciliation. A registered
  row with missing files is a reported failure.
- P0-3/P0-4: `synchronize_source_crop_job` runs with every job state change
  (API cancel and retry, worker fail, cancel acknowledgement, lease recovery,
  quarantine); retry reopens the run with its checkpoint or fails with
  `SOURCE_CROP_RUN_ACTIVE`; a handler that meets a finished run refuses with
  `SOURCE_CROP_RUN_FINISHED` instead of completing silently.
- P0-5: `original_deletion` previews refused until TASK-1048.
- P1-1/P1-2: exact version 3.2.0 (configurable), 30 s timeout; tests.
- P1-3: PostgreSQL tests with the real worker store and `LocalJobWorker`: a
  process killed mid-run resumes in new objects after lease expiry without
  duplicate crops; stale lease writes are refused; cancel, failure, retry,
  recovery and superseding reach the run.

No second audit round.

### Verification

- `services/worker/tests/test_source_crop_job.py`: 28 passed (real
  `jpegtran` 3.2.0 cases with `GAME_PREDICTOR_JPEGTRAN_PATH`).
- `services/api/tests/test_source_crop_runs_api.py`: 11 passed.
- PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`):
  `test_source_crop_runs_postgres.py` 4 passed,
  `test_source_image_crops_postgres.py` passed.
- `@game-predictor/admin-api-client` request test passed, `tsc --noEmit` clean;
  `openapi:check` current; `docs:check` OK; code map regenerated.
- API subset (`source_crop or jobs_api or schema or image_storage or local_admin
  or openapi or game_data_v2`): 204 passed. Full worker suite: 3102 passed,
  45 skipped, 1 failed (`test_vision_lab_symbol_large_rgb_runs.py::test_another_root_cannot_admit_same_manifest`,
  unrelated, passes alone 15/15 — timing under load).
- ruff clean; mypy only the two known errors in `schemas/source_lattice_geometry.py`.
