# TASK-0923 — Shared search with explicit saved selection (T3)

## Status

todo

## Goal

Optional backward-compatible shared workspace controls for fixed stake, initial selected board/range/pins, draft-change callbacks and explicit Save integration.

## Context

User requested complete MANAGEMENT_PANEL_EXECUTION_PLAN.md implementation.

## Dependencies / entry conditions

T2 / TASK-0922 audited and committed. Lead verifies current branch/log before execution. Existing user dirty
metadata remains excluded. No user API/Admin lifecycle or production data writes.

## Recommended execution

gpt-6.1-sol / high; shared UI state and regression protection. Independent gpt-6.1-sol / high review
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

Optional backward-compatible shared workspace controls for fixed stake, initial selected board/range/pins, draft-change callbacks and explicit Save integration. Controlled pin spin positions not SVG coordinates. Browsing/pinning never persists. Search again preserves old save until successful receipt. Unsaved navigation warns; failed save retains draft. Reuse payline modal and current correction writer; preserve ordinary Admin and one-game recipient defaults.

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

Optional backward-compatible shared workspace controls for fixed stake, initial selected board/range/pins, draft-change callbacks and explicit Save integration. Controlled pin spin positions not SVG coordinates. Browsing/pinning never persists. Search again preserves old save until successful receipt. Unsaved navigation warns; failed save retains draft. Reuse payline modal and current correction writer; preserve ordinary Admin and one-game recipient defaults.

## Expected files

Existing shared UI/API/client/navigation and management foundation modules from
preceding tasks. New task-specific management modules/tests/migrations as needed;
executor reports exact paths/symbols before coding. Lead owns documentation/staging.

## Test cases

Rendered existing consumers unchanged; fixed stake across new searches; selected board/range/pins restore; pins and hover never autosave; stale callbacks game/slot switch ignored; response loss safe retry; disabled duplicate Save; unsaved warning.

## Verification

Use repository-pinned Python/npm commands, explicit120s bounds. Focused first,
lint/types next, broader regression/build only after focused checks. No service
startup for tests. Record exact commands/results; don't invent live evidence.

## Risks / open questions

No unresolved product questions. Record infrastructure limitations and verify
fresh sessions/test processes without operating user's local services.

## Outcome

Pending execution and independent review.
