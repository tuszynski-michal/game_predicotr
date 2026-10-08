# TASK-0922 — Durable stake saves and immutable results (T2)

## Status

done

## Goal

Save/clear/recalculate independent machine-game-stake slots with compact immutable deduplicated results, expected revisions, actor/body-bound retry receipts and retained paginated journal.

## Context

User requested complete MANAGEMENT_PANEL_EXECUTION_PLAN.md implementation.

## Dependencies / entry conditions

T1 / TASK-0921 audited and committed. Lead verifies current branch/log before execution. Existing user dirty
metadata remains excluded. No user API/Admin lifecycle or production data writes.

Confirmed T1: v1.7.252 / c708c6e63d8ee00c8a879b0beab4ed73a62fcd62.
New game-bound handlers use a separate single-game GameStorageSession; T1's
multi-game metadata assignment handlers keep their plain public Session.

Implementation clarification: mutation transaction is READ COMMITTED to observe
concurrent exact-retry receipts after their advisory lock. A separate bounded
read-only REPEATABLE READ application-role GameStorageSession captures a coherent
calculation/rules/start snapshot; no owner fallback or independent numeric write.
This avoids a fixed old snapshot missing the preceding committed receipt.

## Recommended execution

gpt-6.1-sol / high; transactions, snapshots, concurrency and durability. Independent gpt-6-astra / high review
as accepted model table. Escalate unresolved safety/data/contract findings.

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
- ai_docs/architecture/API_CONTRACT.md
- ai_docs/architecture/DATA_MODEL.md
- ai_docs/architecture/SYSTEM_ARCHITECTURE.md

## Scope

Save/clear/recalculate independent machine-game-stake slots with compact immutable deduplicated results, expected revisions, actor/body-bound retry receipts and retained paginated journal. Delegate to existing search/calculation/detail services, validate current active attachment/ancestry and preserve prior numeric rows, start symbols, rules/fingerprint. Save only from server-validated search context, not client-invented numeric results; at most six arbitrary pinned spin positions, evaluated spin count≤100000. Archive/detach/revoke checked at commit; reserve public revalidation hook for T5. Journal search including zero hits and symbol changes through panel-scoped adapters; no orphaned success audit.

## Out of scope

Unrelated modules, accounts, hosting/synchronization, Redis, production migrations,
API/Admin lifecycle, push/merge/model activation and destructive history deletion.

## Acceptance criteria

- [x] Complete task scope and corresponding plan behavior implemented.
- [x] Test cases below verified with meaningful assertions.
- [x] Atomicity, eligibility and error semantics preserved.
- [x] Focused format/lint/types and changed-contract checks pass.
- [x] Independent review has no unresolved P0–P2.
- [x] Outcome/evidence, separate commit and CURRENT_STATE updated by lead.

## Technical notes

Save/clear/recalculate independent machine-game-stake slots with compact immutable deduplicated results, expected revisions, actor/body-bound retry receipts and retained paginated journal. Delegate to existing search/calculation/detail services, validate current active attachment/ancestry and preserve prior numeric rows, start symbols, rules/fingerprint. Save only from server-validated search context, not client-invented numeric results; at most six arbitrary pinned spin positions, evaluated spin count≤100000. Archive/detach/revoke checked at commit; reserve public revalidation hook for T5. Journal search including zero hits and symbol changes through panel-scoped adapters; no orphaned success audit.

## Expected files

Existing shared UI/API/client/navigation and management foundation modules from
preceding tasks. New task-specific management modules/tests/migrations as needed;
executor reports exact paths/symbols before coding. Lead owns documentation/staging.

## Test cases

Fresh DB session reload, exact retry after commit with old revision, mismatched operation body, concurrent edit, missing rules/boards, six independent stakes, clear retains journal, unchanged recalculation dedup, changed before/after snapshot.

Reopening a persisted selection may update pins/range under CAS even if its
start sequence no longer appears in current top search hits or the editor is
another authorized actor. Only the exact current slot's trusted context/start
can take this path; arbitrary foreign search contexts remain rejected.

## Verification

Use repository-pinned Python/npm commands, explicit120s bounds. Focused first,
lint/types next, broader regression/build only after focused checks. No service
startup for tests. Record exact commands/results; don't invent live evidence.

## Risks / open questions

No unresolved product questions. Record infrastructure limitations and verify
fresh sessions/test processes without operating user's local services.

## Outcome

Implemented and independently audited; lead retains final status, completion move,
staging, version/hash and CURRENT_STATE ownership.

### Changed

- Six independent machine/game/stake slots, server-validated reproducible search
  contexts, CAS revisions and actor/body/target-bound UUID retry receipts.
- Atomic save, replace, confirmed clear, refresh and current-cell correction;
  compact immutable deduplicated result versions retain complete numeric rows,
  start symbols/checksum, published rules and calculator fingerprint.
- Bounded numeric summaries with exact arbitrary pinned spin values, frozen cost,
  full history on demand and keyset journal pagination. Search including zero
  hits and correction before/after are recorded atomically.
- Current eligibility and T5 commit-revalidation hook; coherent bounded read-only
  REPEATABLE READ application-role calculator snapshot alongside READ COMMITTED
  mutation locks. Separate NullPool avoids reader-pool starvation.
- Explicit panel game adapters reuse existing search, calculator, detail and
  human correction writer. Historic metadata reads bypass automatic game routing,
  and remain available after detach/archive or missing storage registry.
- Restored exact saved context/start permits another authorized actor to update
  pins/range without selecting a new current hit; foreign contexts/start edits
  remain rejected. Added API, OpenAPI, generated client and AbortSignal wrappers.

### Verification

Each finite command below ran through the local excluded harness
`.venv/Scripts/python.exe artifacts/management-t2/run_bounded.py` with a 120-second
subprocess limit (PowerShell environment assignment precedes the PostgreSQL
command). HTTP/TestClient and PostgreSQL checks ran outside the sandbox; no
user API/Admin process was started or stopped.

- `.venv/Scripts/python.exe -m pytest services/api/tests/test_management_stakes.py services/api/tests/test_management.py services/api/tests/test_board_search_approximate_win_api.py services/api/tests/test_board_search_approximate_win_domain.py services/api/tests/test_board_search_api.py services/api/tests/test_board_search_domain.py services/api/tests/test_board_search_board_detail_api.py services/api/tests/test_board_search_stale_refresh.py -q` — PASS: 95 tests in 93.36s; one existing AnyIO deprecation warning.
- `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .venv/Scripts/python.exe -m pytest services/api/tests/integration/test_management_stakes_postgres.py -q` — PASS: 1 comprehensive disposable PostgreSQL application-role test in 19.57s.
- `.venv/Scripts/python.exe -m ruff check services/api/src/game_predictor_api/domain/management_stakes.py services/api/src/game_predictor_api/schemas/management_stakes.py services/api/src/game_predictor_api/application/management_stakes.py services/api/src/game_predictor_api/api/management_stakes.py services/api/src/game_predictor_api/storage/management_stake_models.py services/api/src/game_predictor_api/storage/management_stake_repository.py services/api/src/game_predictor_api/storage/management_result_snapshots.py services/api/src/game_predictor_api/storage/management_game_adapter.py services/api/src/game_predictor_api/main.py services/api/src/game_predictor_api/storage/game_storage_routing.py services/api/src/game_predictor_api/storage/management_models.py services/api/src/game_predictor_api/storage/management_manifest.py services/api/alembic/versions/0149_management_stake_saves.py services/api/tests/test_management_stakes.py services/api/tests/integration/test_management_stakes_postgres.py` — PASS: all changed scoped modules.
- `.venv/Scripts/python.exe -m ruff format --check services/api/src/game_predictor_api/domain/management_stakes.py services/api/src/game_predictor_api/schemas/management_stakes.py services/api/src/game_predictor_api/application/management_stakes.py services/api/src/game_predictor_api/api/management_stakes.py services/api/src/game_predictor_api/storage/management_stake_models.py services/api/src/game_predictor_api/storage/management_stake_repository.py services/api/src/game_predictor_api/storage/management_result_snapshots.py services/api/src/game_predictor_api/storage/management_game_adapter.py services/api/src/game_predictor_api/main.py services/api/src/game_predictor_api/storage/game_storage_routing.py services/api/src/game_predictor_api/storage/management_models.py services/api/src/game_predictor_api/storage/management_manifest.py services/api/src/game_predictor_api/storage/models.py services/api/alembic/versions/0149_management_stake_saves.py services/api/tests/test_management_stakes.py services/api/tests/integration/test_management_stakes_postgres.py` — PASS: 16 files already formatted.
- `.venv/Scripts/python.exe -m mypy --follow-imports=silent services/api/src/game_predictor_api/domain/management_stakes.py services/api/src/game_predictor_api/schemas/management_stakes.py services/api/src/game_predictor_api/application/management_stakes.py services/api/src/game_predictor_api/api/management_stakes.py services/api/src/game_predictor_api/storage/management_stake_models.py services/api/src/game_predictor_api/storage/management_stake_repository.py services/api/src/game_predictor_api/storage/management_result_snapshots.py services/api/src/game_predictor_api/storage/management_game_adapter.py` — PASS: no issues in 8 task-specific product modules.
- `cmd.exe /c npx tsx --test packages/admin-api-client/test/management-stakes-request.test.mjs packages/admin-api-client/test/management-request.test.mjs packages/admin-api-client/test/board-search-share-corrections.test.mjs` — PASS: 4 request tests; URL/query/body, UUID/CAS, AbortSignal and API error propagation.
- `cmd.exe /c npm run typecheck --workspace @game-predictor/admin-api-client` — PASS.
- `.venv/Scripts/python.exe scripts/export_admin_openapi.py --check` — PASS: OpenAPI artifact is current.
- `cmd.exe /c npm run check:generated --workspace @game-predictor/admin-api-client` — PASS: generated client is current.
- `cmd.exe /c npx prettier --check packages/admin-api-client/src/index.ts packages/admin-api-client/test/management-stakes-request.test.mjs` — PASS.
- `git diff --check -- services/api packages/admin-api-client` — PASS.

The real application-role test verifies concurrent exact retries and competing
revisions, all six slots sharing an identical version, late session-guard rollback
of the actual human writer plus receipt/audit, zero-hit search journaling, ambient
game scope with concurrent metadata change under a coherent read snapshot,
current correction followed by refresh, unavailable pins after range shrink,
stale refresh preserving previous numbers, immutable database history, restored
cross-actor selection, fresh Python process visibility and retained history after
detachment/archive/missing registry.

Independent gpt-6-astra/high audit: PASS, no unresolved P0–P2. Auditor also ran
3 focused pure T2 tests and confirmed existing OpenAPI paths/schemas are unchanged.

### Limitations / not performed

No production migration or data writes, local API/Admin lifecycle, full build,
benchmark, push/merge, hosting, accounts, Redis or model activation. Existing
broad ownership gate-3 V7 omissions remain baseline outside this task; management
tables have a separate shared-control-plane manifest and frozen game-store
manifests were not changed. An initial sandbox TestClient run stalled and was
stopped/checked for owned orphan processes; successful checks used the approved
bounded external runtime. Unrelated user/other-chat files remain outside staging.

### Definition of Done / next step

Task scope, corresponding T2 behavior, focused verification, atomicity, retained
history, error semantics and independent audit are satisfied. Lead must stamp
the separate task commit, mark done/move the task and update CURRENT_STATE before
starting T3. T3 consumes the typed ManagementStakeService/Repository port and
generated management client wrappers; T5 supplies the existing revalidation hook.

### Exact task product files

- `services/api/src/game_predictor_api/domain/management_stakes.py`
- `services/api/src/game_predictor_api/schemas/management_stakes.py`
- `services/api/src/game_predictor_api/application/management_stakes.py`
- `services/api/src/game_predictor_api/api/management_stakes.py`
- `services/api/src/game_predictor_api/storage/management_stake_models.py`
- `services/api/src/game_predictor_api/storage/management_stake_repository.py`
- `services/api/src/game_predictor_api/storage/management_result_snapshots.py`
- `services/api/src/game_predictor_api/storage/management_game_adapter.py`
- `services/api/src/game_predictor_api/main.py`
- `services/api/src/game_predictor_api/storage/game_storage_routing.py`
- `services/api/src/game_predictor_api/storage/management_models.py`
- `services/api/src/game_predictor_api/storage/management_manifest.py`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/api/alembic/versions/0149_management_stake_saves.py`
- `services/api/tests/test_management_stakes.py`
- `services/api/tests/integration/test_management_stakes_postgres.py`
- `packages/admin-api-client/openapi/openapi.json`
- `packages/admin-api-client/src/generated/index.ts`
- `packages/admin-api-client/src/generated/types.gen.ts`
- `packages/admin-api-client/src/generated/sdk.gen.ts`
- `packages/admin-api-client/src/index.ts`
- `packages/admin-api-client/test/management-stakes-request.test.mjs`

Completion commit: v1.7.253 / 1a93bc521316c92eaaed8443e26e2f382a72c25a.
