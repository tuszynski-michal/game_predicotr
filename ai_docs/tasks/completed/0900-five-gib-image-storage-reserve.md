---
title: Five GiB hard reserve for image imports
status: done
last_updated: 2026-10-07
---

# TASK-0900 — Five GiB hard reserve for image imports

## Status

`done`

## Goal

Allow managed image imports when their conservative estimate leaves at least 5 GiB
free on every managed volume; block only below that reserve.

## Context

Mumie import was blocked despite about 50 GiB free space. The configured hard
reserve is 30 GiB, while the requested operational minimum is 5 GiB. The
reported `GAME_STORAGE_WRITE_UNAVAILABLE` is a separate game-storage status
failure, not the capacity-guard error, and cannot be attributed to free space
without a live status read.

## Dependencies / entry conditions

- MAIN `v1.1-vision-lab-hybrid-geometry`; current HEAD is v1.7.242.
- C: has 61,257,211,904 free bytes (about 57.1 GiB) at investigation time.
- API and Docker are unavailable at investigation time, so no live game storage
  status is read or changed.
- Assumption: 5 GiB is the remaining free-space reserve after the conservative
  managed-artifact estimate, not permission to start an import whose expected
  data cannot physically fit.

## Recommended execution

gpt-6.1-sol / high. Change the one shared configured reserve and pass it to
both capacity admission and GC manifests. Escalate if restoring a non-active
Mumie game-storage location requires a data-state mutation.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`

## Scope

- Set the default hard managed-storage reserve to 5 GiB.
- Keep configured overrides, warning at 80 GiB and automatic GC at 60 GiB.
- Make GC manifests use the same runtime threshold as write admission.
- Cover default configuration, threshold behaviour and the two application
  construction paths with focused tests.
- Record the separate `GAME_STORAGE_WRITE_UNAVAILABLE` operational limitation.

## Out of scope

- Changing a game storage registry row, data cleanup, migration, import retry,
  restart, deployment, push or merge.
- Changing the 512 MiB physical browser-staging reserve or upload size limits.
- Weakening the conservative artifact estimate.

## Acceptance criteria

- [x] A default API instance keeps 5 GiB after its estimated image output.
- [x] A configured override is applied consistently to capacity admission and
      generated GC policy manifests.
- [x] The write guard blocks when the remaining space would be below 5 GiB.
- [x] The documented operational policy names the three distinct thresholds.
- [x] The unrelated non-active game-storage error is not misreported as disk
      capacity and no game data is mutated during diagnosis.

## Technical notes

`StorageCapacityGuard` must evaluate `free - estimate >= hard_reserve` on each
distinct managed volume. `StorageGcService` must receive a
`StorageRetentionPolicy` built from the same runtime settings so automatic and
manual GC receipts describe the active threshold rather than a divergent
hard-coded default. Browser staging remains independently guarded by its
512 MiB physical-space check.

## Expected files

- Existing: `services/api/src/game_predictor_api/config.py` (`ApiSettings`);
  `domain/storage_capacity.py` (`StorageCapacityPolicy`);
  `domain/storage_retention.py` (`StorageRetentionPolicy`);
  `main.py` (`create_application`);
  capacity/config/application tests; `LOCAL_OPERATION_GUIDE.md`;
  `CURRENT_STATE.md`.
- New: this task only.

## Test cases

- Default settings and policies expose a 5 GiB reserve.
- Estimated import leaving exactly 5 GiB is permitted; one byte less is blocked.
- A non-default configured reserve reaches both GC construction paths.
- Existing 512 MiB browser-staging check remains unchanged.

## Verification

```powershell
# Run from repository root; each finite command has a 120-second limit.
$env:PYTHONPATH = "$PWD\services\api\src;$PWD\services\worker\src;$PWD\.venv\Lib\site-packages"
C:\Users\tuszy\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest services/api/tests/test_storage_capacity.py services/api/tests/test_config.py -q
```

## Risks / open questions

- `GAME_STORAGE_WRITE_UNAVAILABLE` requires the live registry status before any
  recovery action. It is not evidence that the capacity threshold caused it.

## Outcome

### Changed

- Default hard reserve changed from 30 GiB to 5 GiB for managed image writes.
- One runtime policy now supplies the configured thresholds to capacity admission
  and both automatic/manual `StorageGcService` construction paths.
- Warning at 80 GiB, automatic GC at 60 GiB, conservative estimate and browser
  staging's independent 512 MiB physical reserve remain unchanged.

### Verification results

- Focused capacity, retention and configuration tests: 70 passed.
- Existing capacity integration tests for browser image imports: 4 passed.
- API composition root instantiated in a fresh Python process.
- Scoped Ruff check/format passed; mypy passed for config and both policy
  modules. `main.py` standalone mypy has 26 pre-existing FastAPI decorator/
  return-type diagnostics outside this change.

### Not completed

- API, PostgreSQL and Docker were unavailable during diagnosis. No live Mumie
  `game_storage_locations` status was read, changed or retried.
- No restart, deployment, cleanup, import or game-data mutation was performed.

### Documentation updates

- IMAGE_INGESTION, SYSTEM_ARCHITECTURE, LOCAL_OPERATION_GUIDE and D-530 now
  define the 5 GiB reserve and distinguish it from the 512 MiB staging check.

### Recommended next task

- After a controlled API/DB start, read Mumie's storage status. Recover it only
  through the supported storage lifecycle if it is not `active`; then retry the
  import with the new API process.
