# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Mandatory process rules

**Before any task, read `AGENTS.md` in full and follow its read order.** It is binding for Claude Code: read order, plans, task lifecycle, commit versioning, merging into `main`, timeouts, consent for costly or destructive work, audits and the source-of-truth hierarchy. This file does not repeat those rules. Until you have read it:

- Talk to the user in Polish; invoke the `caveman` skill with `lite` at session start (chat only).
- Do not run benchmarks or load tests (`m7:*`, `m35:*`, `*:benchmark`, `image-selection:10000`, …), destructive data operations or service restarts without an explicit request.
- Cross-model audits: skill `audit-task` (`scripts/audit_task.ps1`).

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

Domain invariants (`sequence_number` order, images as paths, Alembic-only schema changes, no Redis/Celery/microservices/cloud without measured need) are in `AGENTS.md`, „Zasady nadrzędne”.
