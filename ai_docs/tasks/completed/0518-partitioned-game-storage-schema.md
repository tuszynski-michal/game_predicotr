---
title: Partitioned game storage schema and ownership registry
status: done
last_updated: 2026-09-08
---

# TASK-0518 — Schemat partycjonowany i rejestr własności

## Status

`done`

## Goal

Prepare an empty, fail-closed `game_data_v2` schema with explicit game ownership,
partitioning, same-game foreign keys and durable migration metadata.

## Context

This task implements TASK-0518 from the user-approved conversation plan
„Partycje danych gier, szybka Weryfikacja symboli i migracja new-siedem”.
The plan was recovered from conversation history; this document preserves its
exact implementation scope. It does not authorize migrating user data.

## Dependencies / entry conditions

- TASK-0517 database deletion completed. API and workers remain stopped.
- Managed files were detached to `artifacts/data.detached-20260908-legacy-reset`;
  `artifacts/data` is empty. PostgreSQL is not reset and still contains legacy paths.
- Existing dirty worktree changes belong to the user and are outside this task.
- Assumption: common catalog is retained in `public`; only game-owned data gets
  v2 copies. All jobs remain a common public coordinator, preserving global
  execution-slot uniqueness; multi-game release metadata remains public too.

## Recommended execution

`gpt-6-astra`, `high`; independent schema review: `gpt-6-astra`, `high`.
Escalate unresolved ownership, cross-store references or data safety conflicts.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` (Games, Symbols)
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md` (per-game ownership/cohorts)
- `ai_docs/architecture/DATA_MODEL.md` (catalog, observations, review, cohorts)

## Scope

- Alembic migrations creating an empty `game_data_v2` schema.
- Complete table/dependency map: common catalog, game-owned data, shared data.
- LIST(game_id) partitioning of large observations, review, decision history,
  bulk-operation targets and cohort samples.
- Missing game_id, composite foreign keys and supporting indexes.
- Small dependent metadata stays in the same store as its referenced records;
  shared records must never require an alternative old/new FK target.
- Game location, storage generation and durable migration state registry.
- No default partition; an unprepared game fails closed on insert.
- Versioned create/migrate/delete table manifest.

## Out of scope

Runtime routing/write fences (0519), new current-cell representation (0520),
data copy/cutover, creating game partitions on the user database, file cleanup,
reset, training, API/UI changes and performance benchmarks.

## Acceptance criteria

- [x] Frozen Alembic DDL creates only empty v2/control structures.
- [x] All tables are classified with a unique owner or an explicit shared scope.
- [x] Every v2 game-owned FK enforces matching game_id; FK access paths exist.
- [x] Large tables are LIST(game_id), with no default/implicit partition.
- [x] Versioned manifest covers create/migrate/delete and registry/checkpoint.
- [x] Isolated PostgreSQL audit proves partition rejection and cross-game rejection.
- [ ] Independent review (root agent); implementation documentation/tests/lint/typecheck pass.

## Technical notes

Freeze the new DDL rather than importing mutable application ORM during Alembic
execution. Add public catalog composite candidate keys without copying catalog
records. Keep public legacy tables unchanged except additive catalog keys. New
registry records are not backfilled and do not switch runtime routing. A missing
registry/partition is not permission to fall back silently to another store.

## Expected files

- Existing `services/api/alembic/versions/0104_game_deletion_access_paths.py`: parent
  revision only; no modification planned.
- New `services/api/alembic/versions/0105_partitioned_game_storage.py`: upgrade/downgrade.
- New frozen schema snapshot and manifest in the storage package.
- New focused schema tests and isolated PostgreSQL integration tests.
- Existing `ai_docs/architecture/DATA_MODEL.md`, `CURRENT_STATE.md`, `DECISION_LOG.md`.

## Test cases

- Manifest covers every existing ORM table plus maintenance tables.
- DDL preserves domain columns/checks and same-game composite keys.
- Missing partition, missing owner or foreign-game parent fails with no partial write.
- Two isolated game partitions accept their own keys and reject crossed references.
- Registry/checkpoints persist across connections; populated downgrade fails closed.

## Verification

Commands run from repository root. Each child process is limited to 120 seconds.
Integration tests create/drop only a fresh randomly named
`game_predictor_task0518_<12 hex digits>` database, never the user DB. Before DROP,
the fixture verifies zero remaining connections and does not use FORCE.

```powershell
.venv/Scripts/python.exe -c "import os,subprocess; env=dict(os.environ,GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'); subprocess.run(['.venv/Scripts/python.exe','-m','pytest','services/api/tests/test_game_data_v2_schema.py','services/api/tests/integration/test_game_data_v2_postgres.py','-q','--tb=short','--show-capture=no'],timeout=120,check=True,env=env)"
```

Formatting/lint use `.venv/Scripts/python.exe -m ruff format` / `ruff check` on
the migration, manifest and two new test modules. Typecheck uses
`mypy --follow-imports=silent` on those four files. These commands were also
run through `subprocess.run(..., timeout=120, check=True)`.

## Risks / open questions

- The empty schema is not application readiness; routing and projection triggers
  must be integrated in subsequent tasks before importing/training.
- PostgreSQL DDL and foreign-key partition behavior require an actual DB audit.

## Outcome

### Changed

- Added Alembic 0105, frozen SQL snapshot and ownership/lifecycle manifest v1.
- Created 65 LIST(game_id) parents and same-game composite PK/FK/indexes;
  public symbols/rules/jobs get additive candidate keys only.
- Added location/generation registry, durable migration receipt/checkpoint and
  seeded definition manifest. No game registrations or partitions are seeded.
- Empty downgrade holds table locks, rejects populated data/receipts and uses
  no CASCADE. Global jobs execution-slot uniqueness is preserved.
- Real-catalog audit caught a checksum CHECK present in 0035 but absent from
  ORM; the v2 snapshot now retains it. It also exposed legacy 0082 OR precedence;
  v2 uses the documented stronger previous-valid AND current-valid rule, with
  a SQL regression proof. Public historical tables/migrations are unchanged.

### Verification results

- New focused tests: **8 passed in 14.36 s**, including four isolated PostgreSQL
  tests: complete upgrade, full table/column/type/nullability/CHECK/FK/index audit,
  missing partition, foreign-game INSERT and UPDATE, real v2-to-v2 child
  rejection, global job uniqueness structure, reconnect checkpoint, wrong-game
  checkpoint, rejection of shared-table checkpoint and protected downgrade.
- Empty downgrade/re-upgrade passed against a freshly migrated database.
- Final rerun including historical head-chain assertion: **9 passed in 11.97 s**;
  subsequent Ruff format check and lint passed.
- Ruff format/check and mypy: **passed**, four changed/new Python modules.
- `git diff --check`: passed for tracked changes (untracked snapshot additionally
  generated without trailing whitespace; staged audit belongs to root).
- Wider historical migration suite: **49 passed, 16 failed**. All failures hit
  the prior 0104 deliberate online-only gate during full-head offline SQL.
  The new 0105 range is independently tested offline and the full chain online.
  No tests or safety gate were disabled. Historical head assertion was updated
  to 0105; remaining old harness repair is outside this task's implementation.
- Independent review P2 fixed: PostgreSQL fixture is now function-scoped.
  Registry downgrade must identify `public.game_storage_migrations` exactly;
  a separate test proves the `game_data_v2.image_review_queue_states` blocker.
  Previous game rows can no longer mask a missing registry guard.
- After the separately scoped historical offline-test repair: **73 passed in
  49.04 s** (65 baseline + 8 TASK-0518). Ruff format/check and mypy passed for
  all five Python modules. See `../quality/MIGRATION_OFFLINE_BASELINE_REPAIR.md`.

### Not completed

- No user-data migration, main-database schema update, reset, partition creation,
  import, training, benchmark, API/UI change or service restart.
- Historical test harness repair from 0104 was committed independently; no
  migration safety gate was relaxed.
- No live routing or v2 write-through/append-only/queue triggers: intentionally
  write-closed until TASK-0519, not a partially running application.

### Documentation updates

- DATA_MODEL, full GAME_DATA_V2_OWNERSHIP map, CURRENT_STATE and D-377.

### Recommended next task

TASK-0519 only after the TASK-0518 independent audit gate passes.
