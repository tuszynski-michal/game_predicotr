---
title: Move grid diagnostics from import to correction
status: done
last_updated: 2026-10-07
---

# TASK-0890 — Grid diagnostics in grid correction

## Status

done

## Goal

Display grid diagnostics only in Korekta cięcia siatki, preserving the existing correction and import workflows.

## Context

The operator explicitly requested moving image-grid problems out of the already large import section.

## Dependencies / entry conditions

MAIN branch v1.1-vision-lab-hybrid-geometry, HEAD v1.7.231 (5b6a0733c4d5e232a112728fd908eb1115c1eca2).
Previous dirty Outcome receipts, .claude and v7-output are outside this task.
Assumption: this is a UI placement change; existing deferred/correction queue qualification remains authoritative.
No blocking product question; user explicitly chose the destination.

## Recommended execution

gpt-6.1-sol, high. Reuse the existing diagnostics and launcher context.
Reassess scope before any backend qualification change; no delegation required.

## Relevant docs

- AGENTS.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/requirements/ADMIN_APP.md — image geometry completeness
- ai_docs/requirements/APP_V3_FUNCTIONAL_INVENTORY.md — IMPORT-08, MODEL-03
- ai_docs/architecture/API_CONTRACT.md — geometry completeness, grid reviews
- ai_docs/delivery/GRID_DIAGNOSTICS_PLACEMENT_EXECUTION_PLAN.md
- ai_docs/guides/MUMIE_MAIN_APP_OPERATOR_GUIDE_20261006.md

## Scope

Move GeometryCompletenessSection into ReviewerAccessLauncher and reuse its game-filtered jobs.
Narrow the diagnostics client to its actual existing methods, add queue refresh,
update the correction section description and diagnostics copy, and document placement.

## Out of scope

Backend/API/schema, data writes, migrations, cleanup, training, model activation,
import/preflight dispatch, unrelated UI rearrangements and old-game changes.

## Acceptance criteria

- [x] Import does not render or query image-grid diagnostics; missing-board report remains.
- [x] Correction displays existing queue and diagnostic filters/actions for the selected game/import.
- [x] Refresh, loading, error/retry and remount work; old game responses cannot populate a new game.
- [x] V3 explanation preserves automatic full crops independent of other slots.
- [x] Focused tests, format, lint, types, build and fresh main-app screen checks pass.
- [x] Documentation, DoD review and separate v1.7.232 commit are complete (receipt below).

## Technical notes

Reuse existing API and job metadata without new storage or endpoints.
Key the diagnostics by gameId; preserve default game scope and explicit per-import choice.
Source-level placement checks supplement behavior tests; they do not replace them.
No queue records are created or removed by opening these screens.

## Expected files

- apps/admin/src/features/imports/image-folder-import-panel.tsx — remove diagnostics render.
- apps/admin/src/features/imports/geometry-completeness-section.tsx — client/copy.
- apps/admin/src/features/imports/geometry-completeness-state.ts — accurate V3 gate explanation.
- apps/admin/src/features/reviewer-access/reviewer-access-launcher.tsx — diagnostics and refresh.
- apps/admin/src/features/catalog/catalog-workspace.tsx — correction description.
- apps/admin/test-interactions/neural-import-readiness.test.mjs — no diagnostics requests.
- New apps/admin/test-interactions/grid-diagnostics-placement.test.mjs — correction interactions.
- Relevant requirements, operator guide, decision log, plan and CURRENT_STATE.

## Test cases

Import opens without geometry-completeness requests; correction opens for game A,
switches to an import, refreshes, recovers from report failure, remounts and changes
to game B while A has an unresolved response. Queue launch remains available.
Existing geometry state and reviewer launcher contracts remain green.

## Verification

Run from absolute repository paths using the existing run_step.py wrapper with
--timeout 120. Commands use the installed Node executable:

```powershell
& 'C:\Program Files\nodejs\node.exe' --experimental-strip-types --test 'C:\Users\tuszy\Documents\game_predicotr\apps\admin\test\geometry-completeness-state.test.mjs' 'C:\Users\tuszy\Documents\game_predicotr\apps\admin\test\reviewer-access-launcher-contract.test.mjs' 'C:\Users\tuszy\Documents\game_predicotr\apps\admin\test\image-folder-import-panel-contract.test.mjs'
& 'C:\Program Files\nodejs\node.exe' 'C:\Users\tuszy\Documents\game_predicotr\node_modules\tsx\dist\cli.mjs' --tsconfig 'C:\Users\tuszy\Documents\game_predicotr\apps\admin\tsconfig.json' --test 'C:\Users\tuszy\Documents\game_predicotr\apps\admin\test-interactions\grid-diagnostics-placement.test.mjs' 'C:\Users\tuszy\Documents\game_predicotr\apps\admin\test-interactions\neural-import-readiness.test.mjs'
```

Then scoped Prettier/ESLint, Admin tsc and Next build. Inspect actual import and
correction after reload without pressing write/start actions.

## Risks / open questions

Historical whole-image diagnostics do not measure availability of every V3 crop.
Keep that limitation visible. No blocking questions.

## Outcome

### Changed

- Moved diagnostics into the existing correction launcher, reusing its
  game-filtered import context. Import keeps folders, progress and missing
  sequence numbers without mounting grid diagnostics or their requests.
- Added queue/context refresh; preserve selected game and import on refresh.
  Keyed diagnostics by gameId to prevent previous-game data after navigation.
- Renamed the panel to Diagnostyka siatek zdjęć and explained D-523 both in
  its introduction and per-image gate reason. The original filters, previews,
  exception controls and manual low-quality query remain.

### Verification results

- Unit47 PASS: geometry diagnostics state/placement, launcher contract/state,
  import contract. Interaction20 PASS: six new correction tests plus fourteen
  existing/new import tests. Tests cover retry, fresh mount, late previous-game
  response, uncontrolled game selection and no diagnostics requests in import.
- Scoped ESLint PASS with one existing Next img warning in import; final
  launcher/test lint PASS without warnings. Prettier PASS; Admin tsc PASS.
  Final production build PASS (24.39 seconds), including final TypeScript.
- MAIN browser: uploaded folder remains visible; diagnostics absent from import
  and present in correction after full reload. Queue refresh completed and
  existing counts recovered. Screenshot:
  artifacts/grid-diagnostics-placement-20261007/correction-diagnostics.png.
- DoD/plan acceptance review: placement, preserved actions, game isolation,
  loading/error/retry, remount and source-of-truth boundaries covered.
  Viewport390×844: import-scope control worked; responsive stacked layout
  verified and viewport reset. A transient report error recovered through
  explicit refresh (API200; selected import95 incomplete of99), without writes.
- Test setup initially needed the existing CSS-module hook pattern. A type
  guard was added for heterogeneous job payloads. Copy assertions were updated
  for the intentional V3 wording and source formatting; no tests were removed.

### Not completed

- No backend/API/schema changes, data writes, migration, import/preflight,
  training, model activation, cleanup, push or merge.
- Historical whole-image counters retain their original semantics; they are
  not an operational crop-availability count for V3.

### Documentation updates

- D-525, Admin requirements, API documentation cross-reference, operator guide,
  screen inventory, plan and CURRENT_STATE updated.

### Recommended next task

- Continue the operator's next requested screen review. No additional action
  is required to use the relocated diagnostics after refreshing Admin.

### Commit

- Planned v1.7.232; commit hash recorded after the separate task commit.
