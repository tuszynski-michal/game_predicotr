---
title: TASK-0902 — read-only owner lookup during another game's maintenance
status: done
last_updated: 2026-10-07
---

# TASK-0902 — read-only owner lookup during another game's maintenance

## Status

`done`

## Goal

Allow the staged Mumie import to start while an unrelated 777 game remains
non-writable, preserving the owner and all per-game write fences.

## Context

The exact production start reproduced HTTP 409 with `details.gameId` naming
777v2, although the upload, completed preflight and active storage belong to
Mumie. The geometry-guard dependency locates the upload owner. Its textual
`SELECT` is classified as a write by `GameStorageSession.do_orm_execute`, so
an unrelated registry entry in `migrating` stops the lookup.

## Relevant docs

- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`
- `ai_docs/architecture/API_CONTRACT.md` — storage status and image imports

## Scope

- Express the existing owner probe as a SQLAlchemy read statement.
- Preserve qualified allowlisted tables, explicit game predicates, RLS,
  ambiguity errors, transaction boundaries and maintenance write fences.
- Test lookup and the HTTP start dependency using the real application role,
  including an unrelated non-active game and a fresh session.
- Retry the authorized Mumie staging through the normal API and inspect its
  durable job ownership. Apply the fix to the API started by this chat.

## Out of scope

777 provisioning or activation, changing game ownership, deleting data,
schema migration, model activation, frontend/API shape changes, push or merge.

## Assumptions

777 games remain independent and retain their current registry statuses.
The user's request authorizes starting the identified Mumie import, but does
not authorize completing 777 provisioning or overriding write guards.

## Expected files

- `services/api/src/game_predictor_api/storage/game_entity_locator.py` — `locate`
- `services/api/tests/integration/test_application_role_isolation_postgres.py`
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/process/CURRENT_STATE.md`

## Acceptance criteria

- [x] A non-active unrelated game cannot cause owner lookup to request WRITE.
- [x] The exact staging resolves exclusively to Mumie; writes to non-active
  games still return `GAME_STORAGE_WRITE_UNAVAILABLE`.
- [x] The HTTP start dependency proceeds past unrelated maintenance.
- [x] A fresh process starts/reuses the correct durable Mumie import.
- [x] Focused regressions, format, lint and type checks pass; task committed
  separately on `v1.1-vision-lab-hybrid-geometry`.

## Technical notes

Use a typed textual SELECT (`TextClause.columns`) for the known literal owner
probe. Do not infer generic textual SQL intent by parsing strings or weaken
the default WRITE classification of unknown SQL. Registry enumeration remains
read-only; each probe retains its own game scope and explicit owner predicate.

## Verification

Isolated PostgreSQL application-role regressions, then scoped Ruff/mypy and
routing/import tests. Limit each finite step to 120 seconds. The production
replay uses normal API validation and records only the authorized staging job.

## Outcome

- Root cause reproduced with the exact staging: preflight HTTP 200; start
  HTTP 409 naming unrelated 777v2 `migrating`. The real application-role
  regression failed before the fix with the same routing error.
- Renumbered from provisional TASK-0901 to TASK-0902 after a concurrently
  created independent report-performance planning task occupied TASK-0901.
  That task and its files are excluded from this fix and commit.
- Owner probes and registry enumeration now use typed textual SELECTs.
  No owner mapping, write guard, schema, API response, OpenAPI or generated
  client changed. Requirements and ownership architecture document the fix.
- `pytest services/api/tests/integration/test_application_role_isolation_postgres.py
  -q`, with explicit isolated PostgreSQL opt-in: 25 PASS (38.03 s). Covers
  maintenance states migrating/deleting/blocked, both owners and a missing id,
  outer-scope restoration, ORM/raw-SQL write refusal, RLS and HTTP start
  dependency validation. Test databases/roles were removed by normal teardown.
- `pytest services/api/tests/test_game_storage_routing.py
  services/api/tests/test_image_imports_api.py -q`: 64 PASS (77.65 s).
  An initial sandboxed run failed at API fixture setup due local database
  access; the same tests passed with local-service access. No tests weakened.
- Ruff check and format check PASS for both changed Python modules. Strict
  scoped mypy PASS for both, preserving pytest's typed decorators through
  a normal pytest import override; other dependency imports are skipped.
  Unchanged dependency graph/full suite and frontend builds were not run.
- Controlled restart replaced only the API launched by this chat. New
  launcher PID 15980/server PID 29900; `/api/v1/health` HTTP 200. No worker
  was interrupted or newly started. General lane is already running.
- The authorized live start created exactly one import job
  `d82d9aba-d59c-46f7-9ee8-8a7415565e3d` for Mumie
  `fea55cc1-ebf4-4cee-b3ab-a520017ed1be`. Fresh-process HTTP GET 200 and
  scoped retention read confirm the job and staging owner after response loss.
  Both independent 777 game ids/statuses are unchanged (777 active, 777v2
  migrating). No provisioning, activation, reassignment or deletion occurred.
- Runtime limitation: neural preflight takes about 32–35 s; start took 71 s,
  exceeding the diagnostic client's 55 s response limit. Server audit reports
  succeeded, and the committed job persisted. It is `created` in the general
  worker queue; full import completion was not awaited. Performance tuning is
  outside this classification fix; do not restart an existing import blindly.
- Evidence: `artifacts/mumie-import-409-20261007/`. No model activation,
  cleanup, production schema migration, push or merge. DoD and every task
  criterion checked against the isolated tests and durable live job.
- Completion v1.7.244; full commit hash recorded after commit.
