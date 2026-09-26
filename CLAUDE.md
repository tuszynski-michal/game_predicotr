# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Mandatory process rules

`AGENTS.md` holds the binding working rules for AI agents and applies to Claude Code in full: read order, task lifecycle, commit versioning, timeouts, dirty-worktree handling and the source-of-truth hierarchy. Key points:

- Before any task read `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`, the relevant requirements/architecture docs and the active task file directly in `ai_docs/tasks/` (only docs listed in its `Relevant docs`). Do not read `ai_docs/tasks/completed/` or `ai_docs/archive/` unless the active task references them.
- Before writing or executing a plan, read `ai_docs/process/PLAN_STANDARD.md` and `ai_docs/process/TASK_TEMPLATE.md` in full. Plans end with the section `Przypisanie modeli do zadań` (table: `Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review`, one row per task).
- Communicate with the user in Polish. Write docs in the language of the edited document.
- Follow the stage execution rule owned by `AGENTS.md`: an explicit request to
  run a stage of an accepted plan authorizes its ordered tasks and assigned
  implementer/auditor delegation. Audit, commit and document each task; stop
  at the stage boundary or a genuine blocker. For plans without stages, keep
  the per-task stop unless the user explicitly requests the whole plan.
- Source-of-truth order: `ai_docs/process/DECISION_LOG.md` > `ai_docs/requirements/` > `ai_docs/architecture/` > active task > code comments > implementation. Report conflicts instead of assuming the code is right.
- Each finished task gets its own commit. The message starts with `vX.Y.N` (e.g. `v0.10.388 - short scope`); N is the previous versioned commit on the current branch + 1. Before committing, run `git diff --cached --check`; stage only the task's hunks.
- After finishing: update `CURRENT_STATE.md`, fill the task's `Outcome`, move the `done` task to `ai_docs/tasks/completed/`, and add a `DECISION_LOG.md` entry when domain or architecture changes.
- Every command needs an explicit timeout (≤120 s by default). Run dev servers and workers as controlled background processes. Do not run benchmarks or load tests (`m7:*`, `m35:*`, `*:benchmark`, `image-selection:10000`, …) without an explicit request.
- Never run destructive data operations (`db:reset:local`, GC, cleanup, legacy deletion) without explicit consent. Implementing one is not permission to run it.
- Fixes must be durable: they must survive a new process or terminal and a reboot. Label session-only workarounds as workarounds.

## Environment

Windows and PowerShell first. All npm scripts call `.venv\Scripts\python.exe` directly and use `powershell -File scripts/*.ps1` wrappers. Toolchain: Node ≥22.13 <25, npm 11 (npm workspaces: `apps/*`, `packages/*`), Python 3.12, and Docker Desktop for PostgreSQL 18. `.tooling/` holds the optional isolated JDK/Android SDK and the release signing keys: never print or commit them.

The repo root contains many ignored scratch directories (`.codex-task-*`, `test-temp-*`, `.tmp`, `.test-tmp`, `.pytest-tmp`, `worktrees/`, `artifacts/`). Ignore them when searching.

## Commands

```powershell
npm install
python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e ".[dev]"

npm run db:up; npm run db:migrate      # PostgreSQL on 127.0.0.1:5432 + Alembic head
npm run api:dev                        # FastAPI on 127.0.0.1:8000 (/docs, /api/v1/health)
npm run admin:dev                      # Next.js admin panel, 127.0.0.1:3000
npm run reviewer:dev                   # Next.js reviewer, 127.0.0.1:3001
npm run worker:once | worker:poll      # durable job worker, lane "general" (also worker:image-selection:*)

npm run quality                        # full gate: format:check, openapi:check, lint, typecheck, test, snapshot/fixture validation
npm run python:lint                    # ruff on services/api, services/worker, scripts
npm run python:typecheck               # mypy --strict
npm run python:test                    # all pytest (scripts/run_python_tests.ps1, -Suite Api|Worker)
npm run openapi:generate               # after ANY API contract change
npm run openapi:check
```

Single tests:

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_page_geometry_preflight.py -k name
npm run test --workspace @game-predictor/reviewer          # node --test test/*.test.mjs
npm run test:geometry --workspace @game-predictor/reviewer # tsx interaction tests in test-interactions/
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
```

PostgreSQL integration tests (`services/api/tests/integration/`) are skipped unless `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'`. They create and drop dedicated `*_test` databases, never the dev database `game_predictor`. `npm run db:baseline:verify` runs the migration lifecycle suite.

## Architecture

The product analyses deterministic layout sequences (3 × 5 symbol boards) for a slot-like game.

- **`apps/mobile`** is an Expo/React Native Android app and is fully offline. Its only data source is a versioned SQLite snapshot bundled into the APK, produced by `snapshot:generate`. It never talks to the API or PostgreSQL, and the release APK must not declare the `INTERNET` permission. It uses `packages/shared-ts` for domain contracts and the signature codec.
- **`services/api`** (`game_predictor_api`) is a local-only FastAPI Admin API. Layers: `api/` (HTTP routers) → `application/` (use cases) → `domain/` (pure logic) with `storage/` (SQLAlchemy/PostgreSQL) and `schemas/` (Pydantic). Alembic migrations live in `services/api/alembic/versions/` (numbered `NNNN_*.py`; `alembic.ini` at the repo root). Config rejects non-loopback hosts, origins and DB URLs (`postgresql+psycopg` only).
- **`services/worker`** (`game_predictor_worker`) is a separate process that claims durable jobs from PostgreSQL by lane (`general`, `image-selection`). It runs image ingestion and geometry (`images/`: page/board geometry registration, preflight, cell crops, grid calibration), symbol classification (`symbols/`, ONNX/torch), payouts, imports and snapshots. It writes artifacts to the filesystem and results to PostgreSQL. Job types without a registered handler end with `JOB_HANDLER_NOT_REGISTERED`.
- **`apps/admin`** (Next.js, port 3000) is the local administration panel. **`apps/reviewer`** (Next.js, port 3001) is a separate manual review/selection UI. It can be exposed through a Cloudflare Quick Tunnel and proxies an allowlist to the API with session-cookie auth; the API, DB and admin always stay on loopback. See `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`.
- **API contract flow:** FastAPI owns the schemas. `scripts/export_admin_openapi.py` writes OpenAPI into `packages/admin-api-client`, which generates the TypeScript fetch client used by admin and reviewer. Never hand-write response types. An API change must ship backend, OpenAPI, the regenerated client, the client wrapper and a request test together.
- **`packages/manual-image-selection-core`** holds shared TS logic for manual image selection (admin and reviewer). **`packages/domain-fixtures`** holds language-neutral golden JSON cases (payouts, targets) executed by both TS and Python tests.
- **`scripts/`** holds milestone-prefixed (`m4:`–`m7:`, `v01:`…) data-pipeline, acceptance and benchmark tools, exposed as npm scripts. Many are heavy or benchmark-class.

Domain invariants (from AGENTS.md):

- `sequence_number` is domain data that defines deterministic layout order. Target calculation must not run until the sequence position is unambiguous.
- Images are stored as a path plus metadata, never as blobs in domain tables.
- Schema changes go only through Alembic.
- Do not introduce Redis/Celery, microservices or cloud without measured need.
