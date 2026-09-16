---
title: TASK-0391 — Safely delete empty browser staging history
status: done
last_updated: 2026-09-02
---

# TASK-0391 — Safely delete empty browser staging history

## Goal

Allow an operator to delete an unused browser staging after failed preflight or
import attempts, without deleting reviewable or manually corrected data.

## Context

The staging `1-19809` contained no recognized boards or review items, but its
automatic source-geometry and deferred-board records held foreign keys to the
source images. The generic database-reference error made an otherwise empty
staging impossible to remove.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`

## Scope

- classify automatic revision-0 source geometry and unresolved deferred-board
  records as removable technical history;
- remove those records transactionally before their source images;
- retain fail-closed protection for manual/resolved geometry, canonical,
  review, rollout and training-cohort references;
- add an isolated PostgreSQL regression test.

## Out of scope

- deleting the operator's staging directory or production data;
- changing browser-staging API contracts or schema;
- automatic cleanup or GC policy changes.

## Acceptance criteria

- [x] An empty cancelled import with automatic revision-0 geometry can be
  discarded together with its technical execution history.
- [x] Manual source geometry remains protected and causes a stable domain
  conflict without changing any record.
- [x] Canonical, review, rollout and training-cohort references remain
  protected.
- [x] The regression is verified against an isolated PostgreSQL schema.

## Technical notes

Only `pending` deferred geometry without a board or review link and automatic
revision-0 source geometry are removable. Any other geometry state is treated
as domain data and blocks deletion before files or database rows are changed.

## Expected files

- `services/api/src/game_predictor_api/storage/browser_staging_retention_repository.py`
- `services/api/tests/integration/test_browser_staging_retention_repository.py`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'
.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_browser_staging_retention_repository.py -q
.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/storage/browser_staging_retention_repository.py services/api/tests/integration/test_browser_staging_retention_repository.py
.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api/storage/browser_staging_retention_repository.py
```

## Risks / open questions

- The implementation deliberately does not delete a staging with any manual
  geometry or downstream reference. Such data requires its dedicated cleanup
  workflow, not the browser-staging delete action.

## Outcome

### Changed

- `discard_unused` removes safe automatic geometry preflight residue before
  deleting source images and executions.
- The repository rejects every non-pending/resolved-link geometry row, manual
  or nonzero source revision, and all known downstream references.

### Verification results

- Isolated PostgreSQL regression test passed.
- Ruff check and formatting passed for changed Python files.

### Not completed

- No user data was deleted during this task.

### Documentation updates

- Documented the precise boundary between removable automatic geometry residue
  and protected domain geometry.

### Recommended next task

- Retry deletion of the staging from the Admin UI after restarting the API;
  only use a dedicated cleanup path for staging that contains manual or
  reviewable results.
