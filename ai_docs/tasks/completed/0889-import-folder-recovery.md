---
title: Import folder recovery and V3 registration control
status: done
last_updated: 2026-10-07
---

# TASK-0889 — Import folder recovery and V3 registration control

## Status

done

## Goal

Restore the user's uploaded Mumie folder after reload/restart and hide unused
classical registration settings on the neural V3 path.

## Context / dependencies

MAIN branch v1.1-vision-lab-hybrid-geometry, HEAD v1.7.230 / 5470c8b7.
Actual list endpoint fails with GAME_NOT_FOUND for an old deleted game.
New staging b770bcc8-0002-4de0-ad01-60efa82d4835 contains 2575 uploaded JPEGs.
The user's report authorizes this fix. Existing dirty documentation receipts
and untracked .claude/v7-output must remain outside this commit.

## Recommended execution

gpt-6.1-sol, high. Review the data boundary and regression tests locally.
Escalate the plan if repair requires destructive changes or a new API contract.

## Relevant docs

- AGENTS.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/requirements/IMAGE_INGESTION.md (browser staging; classical registration)
- ai_docs/architecture/API_CONTRACT.md (browser-selections)
- ai_docs/delivery/IMPORT_FOLDER_RECOVERY_EXECUTION_PLAN.md

## Scope / technical notes

Optional retention metadata for a deleted game must not prevent listing other
physical ready folders. Catch only GameStorageRoutingError/GAME_NOT_FOUND in
the read repository, return None, preserve files and game ownership. Other
routing/infrastructure errors remain errors. No schema/API type changes.
Panel must surface list errors, retain an earlier valid list, expose loading
and empty states, and refresh finalized uploads before preparing their report.
Hide the classical registration select only for grid_profile_mumie_v1; retain
V1.1 and pinned history. No hidden import/preflight submissions.

## Out of scope

Data deletion/migration, reassignment of orphan files, new upload/import,
training, model activation, old-game processing and broad UI refactoring.

## Acceptance criteria

- [x] Deleted-game staging does not break list reads, including after restart.
- [x] Storage faults other than GAME_NOT_FOUND still propagate.
- [x] List failure is visible, retry works, previous folder cards remain.
- [x] Uploaded folder remains actionable when report preparation fails.
- [x] V3 hides registration selection; V1.1 retains selection and request value.
- [x] Actual 2575-file folder appears after API restart and page reload.
- [x] Focused tests, lint, format, types/build, documentation and separate commit.

## Expected files

- services/api/src/game_predictor_api/storage/browser_staging_retention_repository.py — board_import_status.
- services/api/tests/test_browser_staging_list_recovery.py — proposed regression tests.
- apps/admin/src/features/imports/image-folder-import-panel.tsx — refreshJobs, chooseFolder, registration select.
- apps/admin/test-interactions/neural-import-readiness.test.mjs — interaction fixtures and regressions.
- ai_docs/requirements/IMAGE_INGESTION.md; ai_docs/architecture/API_CONTRACT.md.
- ai_docs/requirements/APP_V3_FUNCTIONAL_INVENTORY.md; ai_docs/process/CURRENT_STATE.md.
- ai_docs/guides/MUMIE_MAIN_APP_OPERATOR_GUIDE_20261006.md.

## Test cases / verification

Two finalized folders, deleted game plus active game: listing returns both with
null orphan status and correct active status, same after new service instance.
GAME_STORAGE_LOCATION_MISSING and an unexpected storage failure: raise.
Panel list failure then successful refresh: error then visible actionable card.
Reload/remount: restored card. Uploaded finalized folder plus failed report:
card and error visible, retry succeeds. V1.1 registration change: selected value
submitted; V3: control absent, no automatic submit.

Run from absolute MAIN paths using artifacts/grid-v3-deployment-20261004/run_step.py
with timeout 120: pytest focused regression/image-import API; tsx interaction
suite; Node import unit suites; scoped ruff/eslint/prettier; mypy repository;
Admin tsc and build. Actual results belong in Outcome, not this plan.

## Risks / open questions

No blocking product decisions. Returning null status does not authorize an
orphan's import into another game. Main app refresh remains explicit.

## Outcome

### Changed

- MAIN optional retention read tolerates only GAME_NOT_FOUND; no deletion or
  reassignment. Current finalized upload is visible again alongside other
  current-game sources. API schema/client unchanged.
- Persistent list section exposes loading, empty and failure states; previous
  cards survive a failed refresh. Newer requests supersede delayed responses.
  Upload finalization refreshes the list before preparing the report.
- Classical registration select is hidden for Mumie V3. V1.1 retains both
  options and sends the chosen value. Earlier pinned history is preserved.
- The same obsolete registration metric is hidden in a neural report. A fresh
  configured Mumie report shows V3 and neural geometry before its first job;
  pinned classical report labels remain unchanged. Actual read-only report
  returns2575 sources/23175 new boards and a ready symbol model.

### Verification results

- Backend recovery/routing/import suites:68 PASS (92.58s); focused recovery
  rerun after fixture import/lifetime fixes:4 PASS. No production DB fixture.
- Admin import unit suites:66 PASS. Neural import interactions:13 PASS,
  including retry/remount, stale response, report failure and V1.1 variant.
- Scoped ruff and Prettier PASS; ESLint0 errors, one pre-existing img warning.
  Admin tsc PASS; repository mypy PASS. Final Admin build PASS (35.48s).
- Own diff audit PASS; mechanical JSX indentation/reflow changes follow the
  now-always-visible list section. Source contract tests retain previous
  assertions, adjusted only for the new section marker/title and JSX spacing.
- Actual controlled API restarted:root40856, listener7244, health ok. Startup
  check's10s readiness deadline expired; existing process subsequently became
  ready. It was inspected, not duplicated. GET returns upload b770bcc8 with
  2575 files and ready status. Page reload restores it with report action,
  with no Mumie registration select. Screenshot in artifacts/import-folder-
  recovery-20261006/folder-recovered.png.

### Not completed

- No new geometry job/import/training/activation, DB migration, data cleanup
  or push. Historical missing-game staging is retained. Read-only folder
  report is allowed; analysis/import remains an operator action.

### Documentation updates

- Requirements and API contract record orphan-status semantics; functional
  inventory IMPORT-02/07 and operator guide describe the visible folder list.
- CURRENT_STATE updated. Existing dirty receipts remain outside this commit.

### Recommended next task

- Operator may prepare geometry and start the recovered folder's import using
  the existing main-app workflow. Track unrelated completeness wording and
  slow startup separately, without broadening this fix.

### Completion

- Version v1.7.231; full commit hash recorded after commit.
