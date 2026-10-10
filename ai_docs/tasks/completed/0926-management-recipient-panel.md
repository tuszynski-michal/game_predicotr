# TASK-0926 — Complete online management interface (T6)

## Status

done

## Goal

Reviewer /management gate and entire same-style shared point/machine/game/stake workflow; local share panel only.

## Context

User requested complete MANAGEMENT_PANEL_EXECUTION_PLAN.md implementation.

## Dependencies / entry conditions

T4 andT5 / TASK-0924–0925 audited and committed. Lead verifies current branch/log before execution. Existing user dirty
metadata remains excluded. No user API/Admin lifecycle or production data writes.

Confirmed T5 v1.7.257 / a829b2e5a90f3c7c09c696ec3ca83bce44ce0213; independent astra/high review PASS.

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

- [x] Complete task scope and corresponding plan behavior implemented.
- [x] Test cases below verified with meaningful assertions.
- [x] Atomicity, eligibility and error semantics preserved.
- [x] Focused format/lint/types and changed-contract checks pass.
- [x] Independent review has no unresolved P0–P2.
- [x] Outcome/evidence, separate commit and CURRENT_STATE updated by lead.

## Technical notes

Reviewer /management gate and entire same-style shared point/machine/game/stake workflow; local share panel only. Named actor reflected locally. Public client adapter uses generated contract and independent management proxy/cookie, immediate public corrections with before/after journal and pending-request recovery after reload. One external known person, no account system. Session ending blocks writes without discarding history/acknowledged results.

## Expected files

Move management hierarchy/game/cards/journal/result/recovery and client ports
into `packages/board-search-ui/src/management`; preserve thin Admin wrappers and
existing imports. Extract only management CSS into a shared style entrypoint.
Reviewer adds `app/management/page.tsx` and management gate/public adapter/access
state modules plus rendered tests. The public adapter uses generated T5 contracts,
expected-session identity and its machine-scoped transport. No new API needed.
Lead owns shared prose/staging/commit; executor owns code/tests and Outcome.

## Test cases

Rendered phone complete flow, local/remote visible same saves, two-tab concurrent conflicts, lost response/reload exact operation recovery, unauthorized/revoked/expired UI, no link-admin controls, shared style and old Reviewer regression.

## Verification

Use repository-pinned Python/npm commands, explicit120s bounds. Focused first,
lint/types next, broader regression/build only after focused checks. No service
startup for tests. Record exact commands/results; don't invent live evidence.

## Risks / open questions

No unresolved product questions. Access termination is separate from archive/
attachment eligibility and preserves the same mounted editor, history and pending
operation. Authorization failure cannot discard an uncertain operation. Recovery
keys include the panel session identity; human actor labels hide internal UUIDs.
These defenses implement the accepted session/retry boundary. Record infrastructure limitations and verify
fresh sessions/test processes without operating user's local services.

## Outcome

### Changed

- Extracted the complete management hierarchy, game workspace, six stake cards,
  journal, result views, transport ports and recovery modules into
  `packages/board-search-ui/src/management`. Admin retains thin compatibility
  wrappers and its local link-administration header. Both applications import
  one management-only CSS entrypoint; long labels wrap and controls retain
  44-pixel minimum targets.
- Added Reviewer `/management?share={sessionId}` with a code gate and generated
  public-client adapter. Every request binds `X-Management-Session`, and every
  asset URL binds `expectedSessionId`. Sanitized search and symbol contracts are
  mapped explicitly into the existing board-search source without Admin IDs.
- Access termination keeps the same mounted draft, acknowledged result and
  journal. Live access, mount and abort fences block new requests and late UI
  callbacks, including response-body download. Human actor labels hide the
  immutable session UUID without changing operation identity.
- Structural, stake and refresh recovery use the injected session namespace.
  Authentication/capability failures retain uncertain operations. Aborted or
  unmounted mutations cannot retire a newer pending command; retry preserves the
  original UUID/body. Local-owner defaults and existing workflows remain intact.

### Verification results

All commands used the repository Python subprocess runner with an explicit
120-second timeout; tests ran in fresh processes without starting the user's
API, Admin or Reviewer services.

- `node node_modules/tsx/dist/cli.mjs --tsconfig apps/reviewer/tsconfig.json
  --test apps/reviewer/test-interactions/management-panel.test.mjs`: **13/13 PASS**.
  Covers code unlock/errors, point/machine/assignment/search/Save/Clear/history,
  six independent stakes, immediate opaque public correction with named before/
  after journal, save and correction response loss/reload/exact retry, two-tab
  CAS, cookie/session identity isolation, 401/403 pending retention, visible
  edited composer/range/history after termination, expiry, abort and late body
  fences, and structural unmount/newer-pending recovery.
- `node node_modules/tsx/dist/cli.mjs --tsconfig apps/admin/tsconfig.json --test
  apps/admin/test-interactions/management.test.mjs
  apps/admin/test-interactions/management-cards.test.mjs`: **23/23 PASS**.
- Shared package unit and rendered interaction suites: **77/77** and **49/49
  PASS**. Existing public share/correction/proxy/security suites in Reviewer:
  **41/41 PASS**.
- Scoped Prettier and ESLint for the shared management directory, new Reviewer
  page/modules/test and changed Admin wrappers/layout/test: **PASS**. Direct
  `tsc --noEmit --incremental false` in board-search-ui, Admin and Reviewer:
  **PASS**, without Next typegen/build output. Scoped `git diff --check`: **PASS**.
- Full Reviewer unit suite: **228/235 PASS**. The same seven failures reproduce
  in a temporary isolated `git archive HEAD` snapshot: two unchanged source
  contract assertions (grid-audit resolver and static-image text) and five
  remote-selection fake-loopback proxy fixtures returning 502 instead of 200.
  The snapshot was removed; these modules were not changed by T6.
- Independent astra/high review received the completed source and evidence;
  final review receipt is recorded by the lead before commit.

### Not completed and limitations

- Phone interaction coverage uses rendered React/jsdom with a 390-pixel window
  setting. CSS was source-audited for wrapping and target size. No physical phone,
  browser layout screenshot, live external link or production-data flow was
  exercised; jsdom does not prove rendered geometry.
- No live service startup, Next build, database writes, deployment, push or merge
  was performed. The seven baseline Reviewer failures remain outside this task.
- Task completion, commit version/hash and CURRENT_STATE receipt remain with
  the lead; no executor commit was created.

### Documentation updates

The executor updated this Outcome only. The lead owns architecture/current-state
closure and acceptance metadata. No API contract extension or code generation
was required; the adapter consumes the committed T5 generated contract.

### Next

Record the independent review receipt, stage only the supplied T6 manifest,
create the separate task commit, update CURRENT_STATE and continue the accepted
plan in its documented sequence.

Independent astra/high review: PASS; no unresolved P0-P2. Independent public13 and Admin23 passed; all reported findings fixed and covered. Shared77/49, old public/security41, scoped types/lint/format accepted. Seven broader Reviewer failures reproduced on unchanged HEAD. No visual/physical Android or live rollout claim.

Acceptance compared with T6 scope and approved plan: shared complete panel,
recipient access isolation, preserved draft/history/pending operations and old
consumer behavior pass the recorded checks. Lead updated architecture and
CURRENT_STATE. Full completion version/hash follows after the commit.

### Recommended next task

T7 / TASK-0927: integrated acceptance, regressions, builds and operator guide.

Completion commit: v1.7.258 / ce64a194e4c7a806c59df25e90b2b174666321b4.
