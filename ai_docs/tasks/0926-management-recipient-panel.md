# TASK-0926 — Complete online management interface (T6)

## Status

todo

## Goal

Reviewer /management gate and entire same-style shared point/machine/game/stake workflow; local share panel only.

## Context

User requested complete MANAGEMENT_PANEL_EXECUTION_PLAN.md implementation.

## Dependencies / entry conditions

T4 andT5 / TASK-0924–0925 audited and committed. Lead verifies current branch/log before execution. Existing user dirty
metadata remains excluded. No user API/Admin lifecycle or production data writes.

## Recommended execution

gpt-6.1-sol / high; remote mutations, auditing and recovery. Independent gpt-6-astra / high review
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

Reviewer /management gate and entire same-style shared point/machine/game/stake workflow; local share panel only. Named actor reflected locally. Public client adapter uses generated contract and independent management proxy/cookie, immediate public corrections with before/after journal and pending-request recovery after reload. One external known person, no account system. Session ending blocks writes without discarding history/acknowledged results.

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

Reviewer /management gate and entire same-style shared point/machine/game/stake workflow; local share panel only. Named actor reflected locally. Public client adapter uses generated contract and independent management proxy/cookie, immediate public corrections with before/after journal and pending-request recovery after reload. One external known person, no account system. Session ending blocks writes without discarding history/acknowledged results.

## Expected files

Existing shared UI/API/client/navigation and management foundation modules from
preceding tasks. New task-specific management modules/tests/migrations as needed;
executor reports exact paths/symbols before coding. Lead owns documentation/staging.

## Test cases

Rendered phone complete flow, local/remote visible same saves, two-tab concurrent conflicts, lost response/reload exact operation recovery, unauthorized/revoked/expired UI, no link-admin controls, shared style and old Reviewer regression.

## Verification

Use repository-pinned Python/npm commands, explicit120s bounds. Focused first,
lint/types next, broader regression/build only after focused checks. No service
startup for tests. Record exact commands/results; don't invent live evidence.

## Risks / open questions

No unresolved product questions. Record infrastructure limitations and verify
fresh sessions/test processes without operating user's local services.

## Outcome

Pending execution and independent review.
