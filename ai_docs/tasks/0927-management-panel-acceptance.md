# TASK-0927 — Integrated management acceptance and operator guide (T7)

## Status

todo

## Goal

Review every accepted requirement/task against actual implementation; focused/broader relevant suites, OpenAPI drift, types/lint/build, isolated fresh-process PostgreSQL retention/conflicts/access and shared rendered UI desktop/mobile.

## Context

User requested complete MANAGEMENT_PANEL_EXECUTION_PLAN.md implementation.

## Dependencies / entry conditions

T6 / TASK-0926 audited and committed. Lead verifies current branch/log before execution. Existing user dirty
metadata remains excluded. No user API/Admin lifecycle or production data writes.

## Recommended execution

gpt-6.1-sol / high; full-flow and requirements verification. Independent gpt-6-astra / high review
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

Review every accepted requirement/task against actual implementation; focused/broader relevant suites, OpenAPI drift, types/lint/build, isolated fresh-process PostgreSQL retention/conflicts/access and shared rendered UI desktop/mobile. Bounded actual-data diagnostics only; no synthetic scale benchmarks. Add operator guide for additive user-run migration/API/Admin startup and Reviewer public exposure, limitations/backup. All P0–P2 resolved within two fix cycles or stop with evidence. Don't claim real tunnel/live UI/PC reboot tested if unavailable.

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

Review every accepted requirement/task against actual implementation; focused/broader relevant suites, OpenAPI drift, types/lint/build, isolated fresh-process PostgreSQL retention/conflicts/access and shared rendered UI desktop/mobile. Bounded actual-data diagnostics only; no synthetic scale benchmarks. Add operator guide for additive user-run migration/API/Admin startup and Reviewer public exposure, limitations/backup. All P0–P2 resolved within two fix cycles or stop with evidence. Don't claim real tunnel/live UI/PC reboot tested if unavailable.

## Expected files

Existing shared UI/API/client/navigation and management foundation modules from
preceding tasks. New task-specific management modules/tests/migrations as needed;
executor reports exact paths/symbols before coding. Lead owns documentation/staging.

## Test cases

Requirement-to-test evidence and complete six-stake/local/public flow; focused then broad regression, actual clean generated contract, builds safe for user's live directories, independent final audit, operator actions explicit and honest outstanding live-rollout gates.

## Verification

Use repository-pinned Python/npm commands, explicit120s bounds. Focused first,
lint/types next, broader regression/build only after focused checks. No service
startup for tests. Record exact commands/results; don't invent live evidence.

## Risks / open questions

No unresolved product questions. Record infrastructure limitations and verify
fresh sessions/test processes without operating user's local services.

## Outcome

Pending execution and independent review.
