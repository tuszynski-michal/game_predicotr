---
title: TASK-0064 — Review storage and Admin API
status: done
last_updated: 2026-07-29
---

# TASK-0064 — Review storage and Admin API

## Goal

Persist an immutable TASK-0063 whole-layout active-learning selection as an
idempotent review batch and expose read-only Admin API operations required by
the manual-review UI.

## Dependency

TASK-0063 produced the checksum-bound selection report. Existing game and
symbol catalogs remain authoritative for the target game. TASK-0065 will build
the UI; TASK-0066 will add resolution/correction audit and feedback export.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- D-073 in `ai_docs/process/DECISION_LOG.md`

## Scope

- add Alembic tables for immutable review batches and whole-layout review
  items,
- preserve source/model/calibration hashes and the exact 15-cell prediction
  snapshot without storing image binaries,
- validate report schema, checksum, class catalog, paths, row-major cells,
  board/source identity, confidence and alternatives,
- import one selection report atomically and idempotently by report checksum,
- reject a reused checksum with different game or payload,
- expose batch list/detail and cursor-paginated item list/detail,
- filter items by batch and status while preserving deterministic selection
  rank,
- regenerate OpenAPI and the TypeScript Admin client.

## Acceptance criteria

- [x] Schema changes exist only in Alembic migration `0014`.
- [x] A batch references an existing game and stable source report checksum.
- [x] Each imported item contains exactly 15 row-major cells.
- [x] Predictions reference active symbols of the selected game.
- [x] Paths are relative POSIX paths and checksums are valid SHA-256 values.
- [x] Retrying the same report returns the same batch and items.
- [x] Conflicting reuse of a report checksum fails closed.
- [x] List/detail responses preserve model, confidence, alternatives and source
      context needed by TASK-0065.
- [x] No endpoint resolves labels or mutates the model/dataset in this task.
- [x] OpenAPI/client drift checks and focused quality checks pass.

## Out of scope

- Admin UI,
- approve/correct/reject transitions,
- review audit events and feedback dataset export,
- geometry editing,
- loading image binaries through the API,
- retraining or online model changes.

## Expected files

- `services/api/alembic/versions/0014_review_batches_items.py`
- review domain/application/schema/API/repository modules,
- API models and composition-root wiring,
- API/domain/migration/repository tests,
- generated OpenAPI and TypeScript client,
- architecture/process documentation

## Verification

All commands use bounded timeouts. Unit/API tests use an in-memory repository.
Migration and SQLAlchemy repository tests use the existing isolated PostgreSQL
test fixture when available and otherwise remain explicit skips.

## Outcome

Completed 2026-07-29.

- Added Alembic migration `0014_review_batches` and matching SQLAlchemy models
  for immutable review batches and whole-layout items.
- Added framework-independent report validation, idempotent application
  service and SQLAlchemy repository.
- Added read-only Admin API list/detail endpoints and one checksum-bound import
  endpoint. No label resolution endpoint exists.
- Regenerated OpenAPI and the TypeScript Admin API client.
- Focused verification: 27 tests passed; 2 isolated PostgreSQL tests were
  explicitly skipped because `GAME_PREDICTOR_RUN_POSTGRES_TESTS` was not
  enabled. Ruff, strict mypy for changed modules, OpenAPI drift and client
  TypeScript checks passed.
- The whole-monorepo mypy run was bounded and timed out after 60 seconds; the
  strict changed-scope run completed successfully.
