# TASK-0922 — Durable stake saves and immutable results (T2)

## Status

todo

## Goal

Save/clear/recalculate independent machine-game-stake slots with compact immutable deduplicated results, expected revisions, actor/body-bound retry receipts and retained paginated journal.

## Context

User requested complete MANAGEMENT_PANEL_EXECUTION_PLAN.md implementation.

## Dependencies / entry conditions

T1 / TASK-0921 audited and committed. Lead verifies current branch/log before execution. Existing user dirty
metadata remains excluded. No user API/Admin lifecycle or production data writes.

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

- [ ] Complete task scope and corresponding plan behavior implemented.
- [ ] Test cases below verified with meaningful assertions.
- [ ] Atomicity, eligibility and error semantics preserved.
- [ ] Focused format/lint/types and changed-contract checks pass.
- [ ] Independent review has no unresolved P0–P2.
- [ ] Outcome/evidence, separate commit and CURRENT_STATE updated by lead.

## Technical notes

Save/clear/recalculate independent machine-game-stake slots with compact immutable deduplicated results, expected revisions, actor/body-bound retry receipts and retained paginated journal. Delegate to existing search/calculation/detail services, validate current active attachment/ancestry and preserve prior numeric rows, start symbols, rules/fingerprint. Save only from server-validated search context, not client-invented numeric results; at most six arbitrary pinned spin positions, evaluated spin count≤100000. Archive/detach/revoke checked at commit; reserve public revalidation hook for T5. Journal search including zero hits and symbol changes through panel-scoped adapters; no orphaned success audit.

## Expected files

Existing shared UI/API/client/navigation and management foundation modules from
preceding tasks. New task-specific management modules/tests/migrations as needed;
executor reports exact paths/symbols before coding. Lead owns documentation/staging.

## Test cases

Fresh DB session reload, exact retry after commit with old revision, mismatched operation body, concurrent edit, missing rules/boards, six independent stakes, clear retains journal, unchanged recalculation dedup, changed before/after snapshot.

## Verification

Use repository-pinned Python/npm commands, explicit120s bounds. Focused first,
lint/types next, broader regression/build only after focused checks. No service
startup for tests. Record exact commands/results; don't invent live evidence.

## Risks / open questions

No unresolved product questions. Record infrastructure limitations and verify
fresh sessions/test processes without operating user's local services.

## Outcome

Pending execution and independent review.
