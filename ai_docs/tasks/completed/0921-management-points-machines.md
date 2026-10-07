# TASK-0921 — Management points and machines (T1)

## Status

done

## Goal

Persist and edit points, machines and active game assignments through the new
local Panel Administracyjny tab, preserving archived and detached history.

## Context

User explicitly requested complete MANAGEMENT_PANEL_EXECUTION_PLAN.md T1–T7.
This task implements T1 only; lead continues the remaining tasks after audit/commit.

## Dependencies / entry conditions

Current branch v1.7.250 confirmed from log. Dirty pre-existing CURRENT_STATE and
completed-task metadata are user-owned. No product implementation for this module
exists. Local API/Admin lifecycle is exclusively user-controlled.

## Recommended execution

gpt-6.1-sol / medium; independent gpt-6.1-sol / high review of relations, catalog
eligibility and retained history. Escalate unresolved data-safety findings.

## Relevant docs

- AGENTS.md
- ai_docs/README.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/MANAGEMENT_PANEL_EXECUTION_PLAN.md
- ai_docs/requirements/MANAGEMENT_PANEL.md
- ai_docs/architecture/MANAGEMENT_PANEL.md
- ai_docs/requirements/ADMIN_APP.md
- ai_docs/architecture/DATA_MODEL.md
- ai_docs/architecture/SYSTEM_ARCHITECTURE.md
- ai_docs/architecture/API_CONTRACT.md

## Scope

Points name/city/street, named machines, active-game assignment updates,
archive/restore without deletion, local responsive tab, additive Alembic migration,
OpenAPI/generated client/wrappers/request and interaction tests. Atomic structural
audit and operation UUID/CAS receipts form a reusable foundation for T2.

## Out of scope

Stake saves/charts (T2–T4), public access (T5–T6), production migration,
API/Admin lifecycle, push, hosting and user-data manipulation.

## Acceptance criteria

- [x] Persistent editable point/machine hierarchy with matching local UI styles.
- [x] Assign only live active games; re-read eligibility at mutation boundary.
- [x] Detach/archive retains records/history, reattach/restore works.
- [x] Atomic mutation/audit, exact operation retry and expected-revision conflict.
- [x] Focused tests, format/lint/types and contract checks pass.
- [x] Fresh session persistence and meaningful migration/DB verification.
- [x] Independent review has no unresolved P0–P2.

## Technical notes

Use shared public metadata, stable UUIDs, no global name uniqueness requirement;
nonblank bounded fields. No delete/cascade of history. Reuse catalog routing and
local navigation conventions; no unrelated game-domain changes. Receipt identity
must bind operation UUID, actor, target and canonical body. New schema via Alembic.
T2 will reuse these services and audit schema. Lead owns docs and commits.

## Expected files

Existing main API wiring, metadata/models registration, catalog navigation/client
wrapper/OpenAPI output. Proposed management domain/application/repository/schema/
router, management local UI, migration and focused backend/UI tests.

## Test cases

CRUD, blank inputs, active/draft/archived catalog, eligibility change, detach and
reattach, archive with descendants, retry after response loss, conflicting edits,
new session durability and navigation regression; mobile loading/empty/error.

## Verification

Run repository-pinned Python and npm scripts scoped to changed modules using
explicit120s timeout; record exact commands/results. Never start/restart API/Admin.

## Risks / open questions

No blocking product questions. PostgreSQL/live UI availability may limit rollout
evidence; do not substitute in-memory-only persistence claims.

## Outcome

### Changed

Added the local Panel Administracyjny tab, editable point/machine hierarchy,
active-game assignments and archive/restore. Shared public metadata uses stable
UUIDs, retained detached assignments, atomic immutable structural audit, actor/
target/body-bound operation receipts and optimistic revisions. Migration0148 is
additive; frozen game-store lifecycle manifests remain unchanged. The generated
OpenAPI client and wrapper are updated together. Uncertain commands survive
reload in per-tab session storage; 5xx/transport errors preserve exact retry.

### Verification results

- Backend unit/request tests and migrated disposable PostgreSQL app-role test:
  5 PASS. Real concurrent create retries deduplicate, competing revisions yield
  one conflict, immutable audit rejects deletion, rollback preserves state and a
  fresh Python process reloads the committed hierarchy.
- Admin rendered interactions:4 PASS; generated-client request test:1 PASS.
- Existing Admin navigation regressions:10 PASS. Backend OpenAPI export check
  and generated-client drift check pass.
- Admin/client TypeScript, scoped Ruff, scoped mypy7 modules and ESLint pass.
- Independent gpt-6.1-sol/high review: no unresolved P0–P2. Independently reran
  backend4 and rendered UI/client5 tests successfully outside sandbox restrictions.

### Not completed

No production migration or API/Admin lifecycle operation; live rollout is
user-run. Stake/search integration is deliberately assigned to T2–T4.
The broader ownership gate fails on three pre-existing unmapped V7 tables
(`pilot_acceptances`, `source_observations`, `output_operations`); all five new
management tables are classified. Full transitive mypy reaches unrelated worker
NumPy/V7 errors and its120s bound; scoped changed modules pass. Tests/processes
were stopped at their bounds and no owned orphan remained.

### Documentation updates

D-533, accepted execution plan, dedicated requirements/architecture and task
handoffs0921–0927. Existing user edits and concurrent TASK-0928 are excluded.
Concurrent TASK-0928 consumed v1.7.251; this task follows the actual branch log.

### Recommended next task

TASK-0922 / T2, durable stake saves and immutable results. Whole-plan execution
remains authorized; lead continues after this task's audit and separate commit.

Commit: pending lead commit, next patch from fresh branch log.

### Reproduction commands

Each step was bounded by120s; PostgreSQL used disposable application-role data.

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.venv/Scripts/python.exe -m pytest services/api/tests/test_management.py services/api/tests/integration/test_management_postgres.py -q --basetemp=.venv/pytest-management-safe-2
node node_modules/tsx/dist/cli.mjs --tsconfig apps/admin/tsconfig.json --test apps/admin/test-interactions/management.test.mjs packages/admin-api-client/test/management-request.test.mjs
node --experimental-strip-types --test apps/admin/test/admin-navigation-state.test.mjs
.venv/Scripts/python.exe scripts/export_admin_openapi.py --check
npm run check:generated --workspace @game-predictor/admin-api-client
```
