---
title: TASK-0893 — Filter symbol verification by import folder
status: done
last_updated: 2026-10-07
---

# TASK-0893 — Filter symbol verification by import folder

## Status

done

## Goal

Operator can restrict `Weryfikacja symboli` to current crops imported from one selected image-directory import folder.

## Context

The global symbol-review workspace already filters game, symbol, review state,
confidence, prediction source and change time. It does not distinguish crops
originating from different folder imports of the same game, which makes a
targeted verification workflow impractical.

## Dependencies / entry conditions

- Current V2 symbol-review cells persist the immutable `import_job_id`.
- Existing local Admin `listJobs` provides game-scoped image-directory import
  job labels through `sourceDisplayName`.
- No product decision is blocked: the filter represents an existing import job
  identifier and never exposes a local filesystem path.

## Recommended execution

gpt-6.1-sol, high. The change spans the authoritative API contract,
cursor-bound query scope, bulk-operation fingerprint and Admin UI. Escalate if
the existing job list cannot identify only `image_directory` imports without a
new API contract.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/APP_V3_FUNCTIONAL_INVENTORY.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`

## Scope

- Add an optional `importJobId` to symbol-review page, skip and count scopes,
  including keyset cursor binding and bulk filter selection.
- Use the existing `image_symbol_review_cells.import_job_id` field and a V2
  supporting index created through Alembic.
- Regenerate the Admin API client and expose a game-scoped folder selector
  listing only image-directory import jobs.
- Clear the folder scope when the game changes; use it for page reads,
  counters, navigation and bulk actions.

## Out of scope

- Import, crop, prediction or model behavior.
- Changing job retention, revealing absolute source paths or adding a new job
  endpoint.
- Data migration or destructive cleanup.

## Acceptance criteria

- [x] Operator can select all folders or one completed/current
  image-directory import from `Weryfikacja symboli` after selecting a game.
- [x] Page, count, direct navigation and keyset cursors return only cells with
  the selected import job id.
- [x] Filter-scoped bulk preview and operation cannot affect another import.
- [x] Changing game clears the folder filter and stale async job-list results
  cannot overwrite the current game.
- [x] OpenAPI, generated client, focused tests, formatting, lint and types
  pass; no unrelated working-tree changes enter the commit.

## Technical notes

`import_job_id` is already immutable on the current V2 cell projection.
Thread the optional UUID through `SymbolCellReviewListFilter`, API query
parameters, extended query clauses and the bulk-selection snapshot. Include it
only when set in cursor and operation fingerprint payloads so unfiltered
workflows preserve their meaning. A composite V2 index starts with
`game_id, import_job_id` and retains the canonical sequence key for list and
skip ordering.

The UI derives its dropdown from existing `listJobs({ gameId, jobType:
'import' })`, retaining only `inputPayload.importKind === 'image_directory'`.
It shows the safe `sourceDisplayName` with a short job suffix, uses a neutral
fallback for historical payloads and keeps an all-folders option. Jobs loading
is separate from crop page loading; an error does not hide the existing global
review workflow.

## Expected files

- Existing: `services/api/src/game_predictor_api/{api,application,domain,schemas}/image_symbol_reviews.py`.
- Existing: `services/api/src/game_predictor_api/storage/{image_symbol_review_repository.py,image_symbol_review_bulk_operation_repository.py,models.py}`.
- New: `services/api/alembic/versions/0146_symbol_review_import_filter_index.py`.
- Existing: `packages/admin-api-client/src/{index.ts,generated/*}`.
- Existing: `apps/admin/src/features/symbol-reviews/{symbol-review-actions.ts,symbol-review-state.ts,symbol-review-bulk-actions.ts,symbol-review-workspace.tsx}`.
- Existing: focused API and Admin tests; requirements, API contract and current state.

## Test cases

- An import id compiles into list, count, seek and bulk scopes; absent id adds
  no SQL clause, cursor key or bulk fingerprint input.
- A cursor issued for one import fails in another import scope.
- API handlers pass `importJobId` to list, skip and counts.
- A filter-selection bulk request preserves the import id.
- UI sends the selected folder id to page/count/skip and bulk selection,
  clears it on game change, and lists only image-directory jobs.

## Verification

```powershell
# From C:\Users\tuszy\Documents\game_predicotr; every command has a 120 s timeout.
# Run focused Python and Node tests, OpenAPI generation/check, scoped formatting,
# lint, typecheck and the Admin production build.
```

## Risks / open questions

- The existing job list is bounded; its existing UI limit is set high enough
  for the local operator workflow, but it does not constitute a new job
  catalog API.

## Outcome

### Delivered

- Added optional `importJobId` to the authoritative symbol-review list, skip,
  count and bulk filter scopes. Keyset cursors and durable bulk fingerprints
  bind the selected import; omitted input preserves unfiltered behavior.
- Added Alembic revision `0146_symbol_review_import_filter_index` with the V2
  visible-current-cells index for `game_id`, `import_job_id` and canonical
  review ordering. No data was migrated or removed.
- Regenerated OpenAPI and the Admin client. The workspace lists only safe
  `image_directory` import jobs after choosing a game, clears the selector on
  game change and keeps job-list failure separate from crop review loading.

### Verification results

- Focused API tests: 35 passed; one existing Starlette deprecation warning.
- Admin symbol-review tests: 40 passed. Admin API-client tests: 75 passed.
- OpenAPI artifact/client drift check, scoped Ruff lint/format, scoped Admin
  ESLint, both TypeScript checks and the Admin production build: PASS.
- The wider selected API suite had 74 passed and one pre-existing assertion:
  `test_list_endpoint_uses_keyset_cursors_without_duplicates` expects a 5 s
  list timeout while the current implementation records 20 s. It is unrelated
  to the import scope and was left unchanged.

### Not completed

- No live-Admin manual acceptance, migration application or data operation was
  performed.

### Commit

- v1.7.235; full hash recorded after commit.
