# TASK-0925 — Panel capability sessions and 48/72-hour links (T5)

## Status

done

## Goal

Independent multi-game panel sessions, local create/list/revoke panel links, separate code/token/cookie and exact allowlisted public routes/proxy.

## Context

User requested complete MANAGEMENT_PANEL_EXECUTION_PLAN.md implementation.

## Dependencies / entry conditions

T4 / TASK-0924 audited and committed (T2 API available). Lead verifies current branch/log before execution. Existing user dirty
metadata remains excluded. No user API/Admin lifecycle or production data writes.

Confirmed T4 v1.7.256 / 71931a1b8fdf5830f761736ca26f1666acc14d5b; independent sol/high review PASS.

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

- [x] Complete task scope and corresponding plan behavior implemented.
- [x] Test cases below verified with meaningful assertions.
- [x] Atomicity, eligibility and error semantics preserved.
- [x] Focused format/lint/types and changed-contract checks pass.
- [x] Independent review has no unresolved P0–P2.
- [x] Outcome/evidence, separate commit and CURRENT_STATE updated by lead.

## Technical notes

Independent multi-game panel sessions, local create/list/revoke panel links, separate code/token/cookie and exact allowlisted public routes/proxy. Full module management only, machine/game validation on all game reads/writes including symbols/images. Commit-bound session revalidation; no public link-admin endpoints. Named link audit, five failed codes lock, default8h with1/4/8/24/48/72h; extend old board-search max/options to72h without scope/timestamp changes. Existing Reviewer ingress; never execute startup/public exposure for verification. Reuse domain calculator/writer, public opaque board versions; no internal paths/review IDs/secrets in replies/audit.

## Expected files

- Proposed API modules: `domain/management_sessions.py`,
  `application/management_access.py`, `application/management_public.py`,
  `storage/management_session_models.py`, `storage/management_session_repository.py`,
  `schemas/management_sessions.py`, `schemas/management_public.py`,
  `api/management_sessions.py`, `api/management_public.py`.
- Proposed additive Alembic migration `0150_management_sessions`; update shared
  ownership manifest, startup readiness head and focused schema tests together.
- Proposed Reviewer `security/management-proxy.ts` and
  `app/management-api/[...path]/route.ts`; local Admin `management-share-panel.tsx`.
- Existing main/config/local-admin guard and old board-share domain/UI/proxy;
  extend only old lifetime maximum/options/cookie age, preserving one-game scope.
- Backend OpenAPI/generated client plus wrapper module and request tests form
  one contract. Focused authorization/proxy/session tests and disposable PG tests.
- Separate access errors must propagate through recalculation rather than become
  a stale result. Structural/history facade uses metadata Session; only current
  game operations use game-bound Session. Lead owns shared prose/staging/commit.

## Test cases

Purpose/cookie isolation old vs new shares, forged machine/game, expiry/revoke before/in-flight commit,5 bad codes, secret-free errors/audit, allowlisted routes and CSRF/origin boundary,48/72 options schema/client/wrapper, old single-game/regression scopes, audit+mutation transaction.

## Verification

Use repository-pinned Python/npm commands, explicit120s bounds. Focused first,
lint/types next, broader regression/build only after focused checks. No service
startup for tests. Record exact commands/results; don't invent live evidence.

## Risks / open questions

No unresolved product questions. Expected session identity binds each authenticated
fetch and image URL to its originating panel session; cookie replacement cannot
move a pending operation to another link. Actor identity includes stable session
UUID even when two labels match; journal displays its retained human label.
These are authorization defenses within the accepted session boundary. Record infrastructure limitations and verify
fresh sessions/test processes without operating user's local services.

## Outcome

### Changed

Implemented the T5 session/public API/proxy/local link-control vertical. Panel
capabilities have independent persistence, purpose, code, token and cookie; six
lifetimes (1/4/8/24/48/72 hours), an eight-hour default, five-attempt lockout,
named recipients and UUID-bound actors. Every authenticated request binds the
expected session, including asset URLs. Structural and stake writes flush and
revalidate authorization before commit. Current machine/game reads enforce live
attachments; retained detached/archived history remains readable. Public search,
frozen results and journals exclude internal identities, storage paths and secrets.

The Reviewer proxy permits only explicit management routes/methods, validates
origin and CSRF, streams bounded request/response bodies and uses a separate
protected cookie. A stale 401 cannot erase a newer tab's cookie. JSON responses
permit the existing 100,000-spin contract within a bounded 64 MiB budget; images
remain bounded at 8 MiB. Management pages/proxy use same-origin-only CSP.
Local create/list/revoke controls retain separately copied codes and reject stale
list responses during mutations. Existing board-search links only gain 48/72-hour
options and the corresponding cookie maximum. New migration `0150` and the startup
schema guard agree. The shared ingress close callback retains live capabilities
and shares an advisory lock with panel-link creation.

### Verification results

Focused verification (each command bounded at 120 seconds):

- API session/local HTTP tests: 15 passed. The actual loopback middleware checks
  exact create/revoke confirmations; listing does not return codes or hashes.
- Existing session/lifetime/schema/Reviewer lifecycle regressions: combined
  56 passed before the added local HTTP test; unchanged T2 HTTP tests: 5 passed.
- Disposable PostgreSQL application-role test: 1 passed in 38.27 seconds. Covers
  persisted wrong-code/audit commits, exact retry receipts, same-label actor and
  search-context isolation, expiry during the actual final flush, structural and
  stake rollback, revoke/rotation ordering, retained history, forged scope and
  concurrent ingress creation/last-close locking. Fresh applications and database
  sessions read persisted state; no process-restart claim is made.
- Reviewer management/old-share proxy and CSP tests: 25 passed.
- Generated client request tests (public/local/T1/T2): 5 passed.
- Rendered local share controls and existing structure workflow: 6 passed;
  lifetime-state regression: 3 passed. The new controls additionally verify
  stale lists after create/revoke and disable toggling during pending creation.
- Ruff format/check: all 24 changed Python files passed. Strict mypy with silent
  imported-module diagnostics: all 11 new service/API/storage modules passed.
- Client, Admin and Reviewer TypeScript checks passed. Scoped Admin/Reviewer
  ESLint passed. OpenAPI export check, generated-client drift and diff checks passed.

### Not completed and limitations

HTTP/TestClient checks required bounded execution outside the sandbox because
the sandbox worker-thread bridge timed out; no API/Admin process was started.
The fixture now disposes every app engine. The two exact disposable databases
left by earlier test-fixture failures and their test roles were removed after
confirming zero sessions; no T5 database remains. No production migration, live
tunnel, service lifecycle, build, benchmark, push or user-data operation occurred.

### Documentation updates

Product/test staging manifest: `artifacts/management-panel-t5/final-files.json`
(42 files). Evidence: `artifacts/management-panel-t5/evidence.json`. Shared
documentation, final independent review, task completion and the separate commit
are owned by the lead. Commit/version fields await that commit.

Independent astra/high review: PASS; no unresolved P0-P2. All reported findings fixed and covered by regressions. Reviewer confirmed42 evidence hashes and documentation consistency. Independent sessions14, proxy21 and client2 passed; final executor quality/PG/HTTP evidence accepted.

Acceptance compared with T5 scope and approved plan: independent access,
commit-bound authorization, retained history, old one-game isolation and72h
options pass their recorded checks. Lead updated API_CONTRACT, architecture
and CURRENT_STATE. Full completion version/hash follows after commit.

### Recommended next task

T6 / TASK-0926, complete shared recipient interface.
