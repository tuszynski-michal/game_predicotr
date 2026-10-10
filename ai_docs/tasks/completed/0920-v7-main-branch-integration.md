---
title: Integrate V7 improvements into the main vision lab branch
status: done
last_updated: 2026-10-07
---

# TASK-0920 — Pełne poprawki V7 na głównym branchu

## Status

`done`

## Goal

Kod wyboru katalogu zapisu, pełnych propozycji, szybkiego review i silnika V7
jest na v1.1-vision-lab-hybrid-geometry razem z testami i późniejszymi zmianami main.

## Context / dependencies

User explicitly requested missing changes on main. Main HEAD v1.7.249 has only
navigation. Calibration HEAD v1.7.221 contains the complete implementation.
Versions and merge-base are recorded in the accepted integration plan. Old main
metadata is dirty and must not be staged. Services are user-controlled.

## Recommended execution

gpt-6.1-sol / high, own review. Stop on unresolved P0–P2 conflicts or incompatible
domain contracts; do not bypass tests, activation gates or schema readiness.

## Relevant docs

- AGENTS.md; README; process/CURRENT_STATE.md, PLAN_STANDARD.md, TASK_TEMPLATE.md,
  DEFINITION_OF_DONE.md and DECISION_LOG.md.
- requirements/IMAGE_SELECTION.md; architecture/IMAGE_SELECTION.md.
- delivery/V7_BRANCH_INTEGRATION_PLAN.md.
- Calibration WT: requirements/IMAGE_SELECTION.md, architecture/IMAGE_SELECTION.md,
  delivery/V7_COMPLETE_DRAFT_COVERAGE_PLAN.md, delivery/V7_SELECTION_FEEDBACK_TRACE.md.

## Scope / expected files

129 checked product/test paths in apps/admin, packages/admin-api-client,
services/api, services/worker and scripts from merge-base..calibration HEAD.
Three-way reconciliation retains current main edits. New proposed migration
services/api/alembic/versions/0147_merge_v7_main.py; matching schema readiness.
Main requirements/architecture, D-532, this task/plan and CURRENT_STATE.
Private snapshot and reports are implementation aids, not user runtime.

## Out of scope

Database upgrade, service lifecycle, gate/model activation, copied profiles or
run data, operator decisions, source/output JPEG writes, monitors and remote push.

## Acceptance criteria

- [x] Complete V7 product/test vertical is on the requested branch.
- [x] Later main code and prior working changes are retained.
- [x] Backend/OpenAPI/generated client/wrapper remain consistent.
- [x] One Alembic head; old revision IDs unchanged; upgrade not executed.
- [x] Coverage/output/reopen/approval/recovery and main entry regressions pass.
- [x] Relevant format/lint/typecheck and fresh-process verification pass.
- [x] Separate commit, Outcome/CURRENT_STATE, documented manual runtime steps.

## Technical notes

Build candidate in an isolated code-only snapshot before changing live sources.
Preserve both migration branches and join at 0147. Configure/activate only through
existing acceptance protocol, never by deleting a gate. No gap fallback becomes
OCR proof or a target input. Existing immutable draft/owner/receipt rules remain.
Partial numbers and midpoint partitioning produce editable estimated choices.

## Verification

Use existing task0852-check.ps1 with explicit <=120s timeouts and unique logs.
Python tests and Node/tsx focused suites first, then scoped lint/types and
OpenAPI/client drift. Alembic graph/offline SQL only. Fresh snapshot processes,
followed by main checkout verification. No API/Admin restart for testing.

## Risks / open questions

The main database needs a user-run upgrade before loading merged backend.
Old pilot services use their unchanged worktree and existing database. Code
integration does not claim transferred acceptance, trained quality or run data.
No blocking product questions; user authorized the code transfer.

## Outcome

Completion: v1.7.250; 88d5019c7e436e5bd2895220d8fe0187f9ea177a.

Installed all 131 verified product/test files from the three-way candidate,
preserving current main edits and prior metadata. The five textual conflicts
retain both main and V7 behaviour. Both migration histories are unchanged;
0147 merges their heads without DDL. Backend, exported OpenAPI, regenerated
client and wrapper match. D-532 records the integration boundary.

Successful snapshot suites: API 217 + 105, worker 229, existing main job/storage
regressions 74, Admin unit 32, rendered UI 62, client request tests 95: 814 cases.
Fresh target-checkout processes: API 62, writer/coverage/recovery 75, rendered UI
62; full Admin/client types, strict mypy for 46 changed source modules, scoped
ESLint, Ruff, Python formatting, Prettier and generated-client drift pass.
The checked graph has one 0147 head; both prior heads are refused by readiness.
Offline DDL tests preserve constraints and blocked activation. No live SQL ran.

Integration repairs include a typed optional checkpoint argument map, the
missing source-policy field in the generic cancellation test fixture, current
saved-run client methods in main-entry tests, and a long-path-aware corruption
fixture. Ordinary fixture roots are kept short on Windows; dedicated long-path
recovery tests remain enabled. Initial sandbox path-access failures were
resolved through isolated permitted checks. A combined API suite exceeded
105 seconds and was split into two bounded passing suites; no test was skipped
to obtain success. Owned timed-out check processes were inspected; no owned
orphan remained. Earlier unrelated test processes were left untouched.

Own review: all seven acceptance criteria and the accepted plan are met for
code integration. Later main models, source-image read routing, neural snapshots
and job controls remain. No unresolved P0–P2 finding in this scoped review.

Not executed: real PostgreSQL role integration (opt-in test excluded), full
repository suite/build, performance benchmark, live folder recognition, online
migration, runtime acceptance/configuration, API/Admin/worker lifecycle,
operator decisions, source/output JPEG writes, corpus/shared runtime changes,
monitor, training, model activation, remote push or deployment. Test success
does not certify OCR accuracy or a folder's execution time. Main runtime remains
a separate user migration/configuration step, documented below.

## Manual runtime preparation after the code commit

The user stops main API/worker processes in their own terminals before migration.
Keep the existing pilot worktree, pilot database and ports 8020/3020 unchanged.
From C:\Users\tuszy\Documents\game_predicotr on the requested main branch:

```powershell
npm run db:migrate
npm run api:dev
```

The first command uses the checkout's configured owner database and provisions
runtime roles; do not point it at the existing pilot database. The second belongs
in the user's API terminal after successful migration. Admin is started in its
own terminal with `npm run admin:dev`; a running Admin may instead need a manual
restart to load the generated client. These commands are documented, not run by
the agent. They do not transfer calibrated profiles or activate V7. Main requires
its own verified acceptance and configuration before its start gate opens.
Until then, TASK-0919 navigation continues to the existing calibrated panel.
