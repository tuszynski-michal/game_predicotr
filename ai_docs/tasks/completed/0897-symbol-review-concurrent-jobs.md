# TASK-0897 — Concurrent symbol review job starts

## Status

done

## Goal

Start independent symbol review jobs while earlier jobs run, without a catalog/board deadlock or selecting frozen cards again.

## Context

MAIN logs confirm PostgreSQL deadlocks in `start` at target FK insertion.
The API locks catalog state before board references; the worker locks board
rows before catalog state. Page-wide selection also includes disabled cards.
The existing explicit limit is 10,000 targets per command, not a shared quota.

## Dependencies / entry conditions

User authorizes fixing the reported behavior. HEAD is v1.7.239,
713bf4f2b5d264bea6eaf7d749fbb369e922e312. Existing completion receipts and
untracked user folders are outside this task. No blocking product question.

## Recommended execution

gpt-6.1-sol, high. Review locks, identity-map freshness and rollback locally;
escalate if a cycle remains or API/domain changes become necessary. No delegation.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md` — background operations and frozen targets.
- `ai_docs/architecture/API_CONTRACT.md` — explicit/filter snapshots and idempotency.
- `ai_docs/delivery/SYMBOL_REVIEW_CONCURRENT_JOBS_EXECUTION_PLAN.md`.
- `ai_docs/process/DEFINITION_OF_DONE.md`.

## Scope

Reorder bulk start locks; revalidate fresh targets/state before commit. Exclude
pending/settled cards from page selection. Add focused backend/concurrency/UI
regressions and explain the per-command limit.
Protect concurrent retries by a transaction advisory lock scoped to game and
idempotency key; this replaces early catalog serialization without capping jobs.

## Out of scope

Production data changes, migration, worker redesign, training, deployment,
service restart, cleanup, push and merge. No global concurrency cap or limit increase.

## Acceptance criteria

- [x] Start and worker acquire board references before catalog state; a concurrent start succeeds or returns a real revision conflict without deadlocking.
- [x] Frozen filter revision and explicit crop identity remain fail-closed after waiting; no stale ORM cache can bypass validation.
- [x] Failed start rolls back job, operation and targets; identical replay returns the existing operation.
- [x] Page selection excludes both processing and settled cards; two independent jobs can be submitted without refreshing the frozen page.
- [x] 10,000 limit applies per command; reset, direct save, polling and frozen-page regressions pass.
- [x] Scoped format/lint/types, tests and Admin build pass; documentation updated, commit receipt follows below.

## Expected files

- Existing `services/api/src/game_predictor_api/storage/image_symbol_review_bulk_operation_repository.py` — `start`, `_require_ready_state`, `_snapshot_explicit_targets`.
- Existing `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx` — selection availability.
- Existing `apps/admin/test-interactions/symbol-review-partial.test.mjs` — consecutive jobs.
- Proposed `services/api/tests/test_symbol_review_bulk_start_locking.py` and `services/api/tests/integration/test_symbol_review_bulk_start_locking_postgres.py` — bounded lock/freshness regressions.
- Existing requirements, API contract, operator guide and CURRENT_STATE; proposed plan and this task.

## Test cases

Start holds no catalog lock while waiting for board FK. Worker finishes and
start revalidates after waiting. Explicit/filter stale changes reject and roll
back. Two independent jobs plus pending/settled page selection work without an
automatic page read; target choice clears each time.

## Verification

Use the existing `artifacts/grid-v3-deployment-20261004/run_step.py` with a
120-second timeout, absolute Windows paths and the repository Python/Node.
Run focused pytest and Node interaction/helper suites first, then scoped Ruff,
Prettier, ESLint, TypeScript and the known Admin build. Isolated PostgreSQL
tests migrate a fresh randomly named test database only; no production rows or
production migration are touched.

## Risks / open questions

Bulk start holds bounded FK locks across up to 10,000 targets. Catalog is
locked only after those checks. Genuine concurrent changes still return a
revision conflict and require fresh preview; they must not be silently accepted.

## Outcome

### Changed

- Confirmed MAIN deadlock at target FK insertion from API logs. Start now
  flushes board/cell references before locking catalog state, then refreshes
  state and explicit target identities before revalidation. A late conflict
  rolls back the whole HTTP transaction. The per-game/key advisory lock
  preserves simultaneous retry idempotency without serializing unrelated jobs.
- Page-wide selection skips pending and settled cards, and becomes disabled
  when no eligible card remains. Card toggles also guard frozen targets.
  Existing target reset, toolbar, paging, direct saves and background polling
  remain unchanged. All acceptance criteria and the plan were checked locally.

### Verification results

- Fresh-process backend unit/availability: 10/10 PASS.
- Isolated real PostgreSQL: 4/4 PASS in 25.28 s, including concurrent start
  while worker holds the same board, independent/stale explicit targets,
  frozen-filter drift, whole-start rollback, simultaneous retry and reconnect.
  Four test games have 15 logical cells each. The randomly named test database
  is removed by fixture finalization; production data is untouched.
- Focused backend/API regression: 24/24 PASS, 28 unrelated tests deselected.
  Wider backend/API run: 51 PASS / 1 pre-existing failure. The unchanged
  `test_list_endpoint_uses_keyset_cursors_without_duplicates` expects a 5,000 ms
  read timeout, while HEAD already uses 20,000 ms. No related code/test changed.
- Admin interaction suite: 16/16 PASS. New cases cover pending and completed
  cards, two separate operations without a page read, separate keys, exhausted
  page, fresh target selection and transition to settled while another job runs.
  Existing accessible controls and touch interactions are retained; no layout
  or device-specific behavior changed. No physical Android run was performed.
- Admin helpers/contracts: 40/40 PASS. Prettier, ESLint, TypeScript, Ruff
  lint/format PASS. Scoped mypy (repository plus its application protocol,
  `--follow-imports=skip`): PASS. Dependency-following mypy timed out at 120 s
  without output; its process tree was terminated and absence checked before
  retrying with the local scope. No checks or production settings were weakened.
- Admin build PASS in 23.58 s. Bounded command receipts are copied to
  `artifacts/symbol-review-concurrent-jobs-20261007/verification.json`.

### Not completed

- Full dependency-following mypy; wider pre-existing timeout assertion remains
  outside scope. No production saves, migration, training, cleanup, restart,
  deployment, push or merge. Running API was launched without hot reload;
  applying the backend fix to it requires a controlled API restart. Admin
  production process also requires restart to load its completed build.

### Documentation updates

- Requirements, API lock/idempotency contract, Mumie operator guide, plan and
  CURRENT_STATE explain independent jobs, frozen-card selection and per-job cap.

### Recommended next task

- Apply the completed API/Admin build through the authorized restart workflow.
  Separately reconcile the historical 5,000/20,000 ms timeout test contract.

### Commit

- Completion version v1.7.240; full hash is recorded after commit.
