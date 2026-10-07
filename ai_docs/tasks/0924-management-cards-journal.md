# TASK-0924 — Stake overview, history and current results (T4)

## Status

todo

## Goal

Six stake cards for selected machine/game only, compact previews/chart/pins/save time, open/search again/confirmed Clear.

## Context

User requested complete MANAGEMENT_PANEL_EXECUTION_PLAN.md implementation.

## Dependencies / entry conditions

T3 / TASK-0923 audited and committed. Lead verifies current branch/log before execution. Existing user dirty
metadata remains excluded. No user API/Admin lifecycle or production data writes.

## Recommended execution

gpt-6.1-sol / high; response races, history semantics and bounded reads. Independent gpt-6.1-sol / high review
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

Six stake cards for selected machine/game only, compact previews/chart/pins/save time, open/search again/confirmed Clear. Journal under chart/table default20 entries, immutable historical result render, current-data editor label. Queue max2 refreshes, cancellation on navigation; initial last result checking then current. Changed calculation journals before/after; unchanged read dedup; unavailable pins explicitly listed. Refresh cannot overwrite an unsaved draft or later slot revision. No eager full rows/images in point lists/card summaries.

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

Six stake cards for selected machine/game only, compact previews/chart/pins/save time, open/search again/confirmed Clear. Journal under chart/table default20 entries, immutable historical result render, current-data editor label. Queue max2 refreshes, cancellation on navigation; initial last result checking then current. Changed calculation journals before/after; unchanged read dedup; unavailable pins explicitly listed. Refresh cannot overwrite an unsaved draft or later slot revision. No eager full rows/images in point lists/card summaries.

## Expected files

Existing shared UI/API/client/navigation and management foundation modules from
preceding tasks. New task-specific management modules/tests/migrations as needed;
executor reports exact paths/symbols before coding. Lead owns documentation/staging.

## Test cases

Independent slot states, changed symbols/rules and prior history, error marks stale rather than zero, six-card concurrency≤2, obsolete responses cancelled/ignored, out-of-range pins, history pagination, mobile responsive styles and archive/detach readable history.

## Verification

Use repository-pinned Python/npm commands, explicit120s bounds. Focused first,
lint/types next, broader regression/build only after focused checks. No service
startup for tests. Record exact commands/results; don't invent live evidence.

## Risks / open questions

No unresolved product questions. Record infrastructure limitations and verify
fresh sessions/test processes without operating user's local services.

## Outcome

Pending execution and independent review.
