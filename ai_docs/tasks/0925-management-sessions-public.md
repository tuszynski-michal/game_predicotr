# TASK-0925 — Panel capability sessions and 48/72-hour links (T5)

## Status

todo

## Goal

Independent multi-game panel sessions, local create/list/revoke panel links, separate code/token/cookie and exact allowlisted public routes/proxy.

## Context

User requested complete MANAGEMENT_PANEL_EXECUTION_PLAN.md implementation.

## Dependencies / entry conditions

T4 / TASK-0924 audited and committed (T2 API available). Lead verifies current branch/log before execution. Existing user dirty
metadata remains excluded. No user API/Admin lifecycle or production data writes.

## Recommended execution

gpt-6.1-sol / high; authorization, expiry and isolation. Independent gpt-6-astra / high review
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

Independent multi-game panel sessions, local create/list/revoke panel links, separate code/token/cookie and exact allowlisted public routes/proxy. Full module management only, machine/game validation on all game reads/writes including symbols/images. Commit-bound session revalidation; no public link-admin endpoints. Named link audit, five failed codes lock, default8h with1/4/8/24/48/72h; extend old board-search max/options to72h without scope/timestamp changes. Existing Reviewer ingress; never execute startup/public exposure for verification. Reuse domain calculator/writer, public opaque board versions; no internal paths/review IDs/secrets in replies/audit.

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

Independent multi-game panel sessions, local create/list/revoke panel links, separate code/token/cookie and exact allowlisted public routes/proxy. Full module management only, machine/game validation on all game reads/writes including symbols/images. Commit-bound session revalidation; no public link-admin endpoints. Named link audit, five failed codes lock, default8h with1/4/8/24/48/72h; extend old board-search max/options to72h without scope/timestamp changes. Existing Reviewer ingress; never execute startup/public exposure for verification. Reuse domain calculator/writer, public opaque board versions; no internal paths/review IDs/secrets in replies/audit.

## Expected files

Existing shared UI/API/client/navigation and management foundation modules from
preceding tasks. New task-specific management modules/tests/migrations as needed;
executor reports exact paths/symbols before coding. Lead owns documentation/staging.

## Test cases

Purpose/cookie isolation old vs new shares, forged machine/game, expiry/revoke before/in-flight commit,5 bad codes, secret-free errors/audit, allowlisted routes and CSRF/origin boundary,48/72 options schema/client/wrapper, old single-game/regression scopes, audit+mutation transaction.

## Verification

Use repository-pinned Python/npm commands, explicit120s bounds. Focused first,
lint/types next, broader regression/build only after focused checks. No service
startup for tests. Record exact commands/results; don't invent live evidence.

## Risks / open questions

No unresolved product questions. Record infrastructure limitations and verify
fresh sessions/test processes without operating user's local services.

## Outcome

Pending execution and independent review.
