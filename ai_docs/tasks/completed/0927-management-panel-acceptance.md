# TASK-0927 — Integrated management acceptance and operator guide (T7)

## Status

done

## Goal

Review every accepted requirement/task against actual implementation; focused/broader relevant suites, OpenAPI drift, types/lint/build, isolated fresh-process PostgreSQL retention/conflicts/access and shared rendered UI desktop/mobile.

## Context

User requested complete MANAGEMENT_PANEL_EXECUTION_PLAN.md implementation.

## Dependencies / entry conditions

T6 / TASK-0926 audited and committed. Lead verifies current branch/log before execution. Existing user dirty
metadata remains excluded. No user API/Admin lifecycle or production data writes.

Confirmed T6 v1.7.258 / ce64a194e4c7a806c59df25e90b2b174666321b4; independent astra/high review PASS.

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

- [x] Complete task scope and corresponding plan behavior implemented.
- [x] Test cases below verified with meaningful assertions.
- [x] Atomicity, eligibility and error semantics preserved.
- [x] Focused format/lint/types and changed-contract checks pass.
- [x] Independent review has no unresolved P0–P2.
- [x] Outcome/evidence, separate commit and CURRENT_STATE updated by lead.

## Technical notes

Review every accepted requirement/task against actual implementation; focused/broader relevant suites, OpenAPI drift, types/lint/build, isolated fresh-process PostgreSQL retention/conflicts/access and shared rendered UI desktop/mobile. Bounded actual-data diagnostics only; no synthetic scale benchmarks. Add operator guide for additive user-run migration/API/Admin startup and Reviewer public exposure, limitations/backup. All P0–P2 resolved within two fix cycles or stop with evidence. Don't claim real tunnel/live UI/PC reboot tested if unavailable.

## Expected files

- `ai_docs/process/MANAGEMENT_PANEL_OPERATIONS.md`: actual operator commands,
  rollout prerequisites, access use, backups, limitations and manual live gates.
- `services/api/tests/integration/test_management_sessions_postgres.py`: true
  fresh-process capability/history verification using isolated app-role fixture.
- Existing deletion-script test: management RESTRICT references block preflight
  before any destructive lifecycle call; change product code only if regression.
- Acceptance artifacts, requirement/evidence matrix and isolated build copies.
  Optional finite static browser fixture verifies real narrow-screen layout and
  touch interactions without API/Admin/Reviewer lifecycle. No new migration.
- Lead owns shared prose/status/staging/commit; executor owns scoped tests,
  guide and task Outcome. Exact final manifest required.

## Test cases

Requirement-to-test evidence and complete six-stake/local/public flow; focused then broad regression, actual clean generated contract, builds safe for user's live directories, independent final audit, operator actions explicit and honest outstanding live-rollout gates.

## Verification

Use repository-pinned Python/npm commands, explicit120s bounds. Focused first,
lint/types next, broader regression/build only after focused checks. No service
startup for tests. Record exact commands/results; don't invent live evidence.

## Risks / open questions

No unresolved product questions. User service directories and production data
must remain untouched by acceptance. Builds use isolated source copies; new
process durability uses disposable PostgreSQL fixtures. Browser checks, if
available, use only a finite static test fixture and mock data. A jsdom viewport
is not visual layout evidence. Physical device/live ingress/computer restart and
new-management timings without representative production records are separate manual
gates, reported explicitly rather than claimed as verified. Record infrastructure limitations and verify
fresh sessions/test processes without operating user's local services.

## Outcome

Implementation and acceptance evidence prepared on 2026-10-08 after T6
`v1.7.258` / `ce64a194e4c7a806c59df25e90b2b174666321b4`.
Lead owns final status, independent-review receipt, completed-task move,
CURRENT_STATE update and separate versioned commit.

Added the operator guide with actual PowerShell backup, SQL preview, revision
0150, runtime/owner role checks and user-run service/ingress commands. The guide
distinguishes V7 predecessor ancestry from management DDL, link lifetime from PC
availability, creating-browser code caching and outstanding live rollout gates.

Added a true fresh OS-process PostgreSQL capability/history check using the real
disposable application role. Added the hard-game deletion preflight regression:
management RESTRICT references block before a writable lifecycle/deletion call.
No product deletion code change was needed; existing dynamic FK discovery
already handles these references. Added a reproducible static real React/CSS
browser fixture with existing Chrome/Edge discovery, bounded CDP/touch workflow,
unique owned profile, acknowledged screenshots and truthful failure evidence.
Real layout exposed a42px access button; a scoped44px rule and mounted-gate
regression fix it. Management tiles/controls now use the existing dark theme
tokens; historical table headings/amounts remain readable within horizontal
table scrolling. Existing shared search consumer defaults remain unchanged.

Verification (exact commands, hashes, logs and requirement-to-test mapping in
`artifacts/management-panel-t7/evidence.json` and `requirement-matrix.md`):

- Focused management/access/stake/delete-preflight tests:31 PASS.
- Actual app-role PostgreSQL T1/T2/T5 migration, transaction, replay/CAS,
  retention, expiry and true new-process tests:3 PASS in117.16s, bounded120s.
  Read-only inspection confirms no corresponding disposable test databases
  remain. No production data cleanup was executed.
- Shared UI:77 unit and49 rendered interactions PASS. Public rendered13 and
  Admin rendered25 PASS. Generated management request tests5 PASS.
- Relevant broader backend suites:94 PASS. Full Reviewer:233/235 PASS; only
  two prior unchanged source assertions remain (grid-audit loopback-only source
  assertion and square-cell crop source assertion). Five earlier sandbox fake
  loopback502 failures disappeared under approved finite network access.
- OpenAPI drift and generated-client drift PASS; client/shared/Admin/Reviewer
  scoped type checks PASS; changed Python Ruff lint/format and generator mypy
  PASS; scoped Reviewer lint and all changed JS/CSS formatting PASS.
- Final isolated source-copy builds: Admin PASS31.99s, Reviewer PASS25.02s
  with previously announced300s bounds. Both copies contain final product CSS
  and gate source; user's app .next directories were not used as build outputs.
  Next emits a multiple-lockfile/inferred-root warning; copied workspace source
  links and isolated output paths are recorded in evidence.
- Final real Chrome390×844 touch fixture PASS14.75s: unlock, point, machine,
  active assignment, six stakes, search, explicit save, frozen history and
  confirmed clear. Six stages have document width/scrollWidth390 and touched
  controls at least43.9px (0.1px subpixel tolerance around44). Actual stylesheet,
  dark theme and touch sanity pass. The symbol bitmap is a mock fixture asset.
- Independent offline full0146→0150 SQL preview PASS12.28s; no DB connection.
- Bounded final read-only actual DB diagnostics show0149_management_stake_saves,
  one active game and zero points/machines/slots/results/journal; sessions table
  absent. Count/schema reads took0–16ms with connect5s/statement2s bounds.
  Earlier0146 evidence is historical; acceptance did not apply any production
  migration. Empty management data does not establish representative hierarchy,
  chart or search performance. No synthetic seed/load benchmark was run.

Remaining manual gates: user-run0150 migration/role rollout, real phone Android
touch, actual ingress/cookie use across devices, service restart and PC reboot.
Browser emulation and fresh test processes do not claim these gates completed.
Existing unrelated V7 ownership/unmapped-table and transitive broad mypy failures
remain outside scope. No API/Admin/Reviewer/tunnel lifecycle, production writes,
destructive user cleanup, push, merge or deployment was performed.

Every accepted product clause is mapped in the matrix. Focused functionality,
atomicity/eligibility/error semantics, durable replay/history, shared regressions,
contracts and scoped quality gates are satisfied. Independent final review and
the lead's commit/state receipt close the remaining task bookkeeping.

Independent astra/high review: PASS; no unresolved P0–P2. The reviewer verified
the complete requirement matrix, transaction/access/retry/history evidence,
scoped quality/contracts, final source-copy builds, real touch/layout screenshots
and exact file hashes. The current guide example is0149→0150; independent
historical0146→0150 offline SQL preview also passed. Physical-device/live access,
production migration/service/computer restart and representative timing gates
remain explicitly manual. The two prior unrelated Reviewer source assertions
are not a scoped regression. Lead may close this task and its separate commit.

### Lead acceptance and delivery

The lead compared the final implementation and evidence with every T1–T7
requirement and this task's Definition of Done. Automated contract, persistence,
authorization, race/retry, interaction, real-browser layout and isolated build
gates pass. Independent astra/high review has no unresolved P0–P2. Two unrelated
Reviewer source-contract failures remain documented with baseline evidence.
Physical Android, live public ingress, production performance and an actual
computer reboot remain operator rollout checks; no such evidence is claimed.

The accepted implementation plan ends here. Production migration and service
startup remain manual operator actions in MANAGEMENT_PANEL_OPERATIONS.md. No
deployment, push, merge, hosting purchase, Redis or user-data cleanup was done.
Full task commit version/hash is recorded after the separate commit.
