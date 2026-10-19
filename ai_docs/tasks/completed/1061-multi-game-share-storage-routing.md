---
title: Multi-game share control-plane routing regression
status: done
last_updated: 2026-10-19
---

# TASK-1061 — Multi-game share control-plane routing regression

## Status

`done`

## Goal

Create one durable share link containing three games without HTTP 500, preserving game selection and atomic revocation.

## Context

The operator's requests failed with HTTP 500. A rolled-back reproduction raised
`GAME_STORAGE_SESSION_SCOPE_CONFLICT`: pending share memberships were mistaken
for writes to the game stores. All three games pass readiness. The previous
PostgreSQL panel test used plain `Session`, bypassing the runtime routing hook.

## Scope

- Exclude only shared `board_search_share_sessions` memberships from pending game-store inference.
- Keep routing and multi-game write rejection for actual game data.
- Exercise three-game creation, durable authentication, and revocation using `GameStorageSession`.

## Out of scope

API changes, schema migrations, service lifecycle, tunnel changes, and merging/pushing main.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/ADMIN_APP.md` — online sharing, D-548.
- `ai_docs/architecture/API_CONTRACT.md` — multi-game panel control plane.
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/guides/MULTI_GAME_BOARD_SEARCH_SHARE_OPERATOR.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Acceptance criteria

- [x] Three memberships save atomically through the runtime session without binding a game store.
- [x] Fresh-process access preserves the selected games and the panel can be revoked atomically.
- [x] Mixed share metadata and actual game data still route the actual game.
- [x] Writes to two actual game stores remain rejected.
- [x] Relevant tests, lint, formatting, isolated typecheck and docs checks pass.

## Expected files

- `services/api/src/game_predictor_api/storage/database.py` — `_pending_game_id`.
- `services/api/tests/test_database.py` — routing regression tests.
- `services/api/tests/integration/test_board_search_panels_postgres.py` — runtime-session regression.
- `ai_docs/architecture/API_CONTRACT.md` — clarify existing transaction boundary.

## Technical notes

The exclusion is limited to the already shared table declared in frozen manifest v3
and inherited by v19. It does not disable routing, use owner credentials, split
the transaction, or alter domain behavior. No product decision is needed.
The test may create and drop its isolated, uniquely named test database; no
operator data is committed by verification. No cross-family review is required
by a plan for this independent regression fix.

## Verification

Run focused pytest suites and opt-in PostgreSQL panel test with a 120-second
process timeout; run ruff, mypy, code-map generation/check and docs:check.

## Outcome

Commit: v1.7.432 (hash dopisuje kolejny commit).

### Changed

- Excluded shared share-membership metadata from pending game-store inference,
  retaining runtime routing and guards for actual game data. No migration,
  owner-role workaround, API change, or split transaction.
- Strengthened the PostgreSQL regression to create three members and revoke
  them with `GameStorageSession`; a fresh interpreter authenticates every game.
- Added regressions for mixed shared/game writes and rejection of two game stores.
- Cross-family audit was not required by a plan for this standalone bug fix.

### Verification results

- Focused pytest: database, panels and routing — 24 passed (15.49 s).
- PostgreSQL migration/durable panel regression — 1 passed (23.88 s, final run).
- Operator's three existing games, new Python process: create and authenticate
  every selected game passed; transaction rolled back, no link retained.
- Ruff lint and formatting passed; mypy `--follow-imports=silent` passed for
  `storage/database.py`. Code-map generation and freshness check passed.
- `npm run docs:check` passed before closure; rerun as part of closure.

### Not completed

- The unrestricted mypy dependency traversal reported pre-existing annotation
  errors in `schemas/source_lattice_geometry.py:36,38` and reached its 120 s
  timeout. Isolated checking of the changed module passed. Initial pytest in
  the restricted sandbox timed out; rerun outside that restriction passed.
  No orphaned test/typecheck processes remain.
- No services were started, stopped or restarted. No browser acceptance on the
  operator's device, merge to main or push was performed.

### Documentation updates

- API architecture clarifies the existing shared transaction boundary.
- Regenerated code maps; task closure updates CURRENT_STATE and archive.

### Recommended next task

- Operator acceptance: create one link for all three games in Udostępnianie,
  then explicitly approve merging and pushing main.
