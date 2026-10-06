# TASK-0891 — Clarify neural preflight proposals and automatic import

## Status

done

## Goal

The MAIN Mumie report distinguishes neural proposals from mandatory manual
geometry correction and keeps automatic import available after preflight.

## Context

The operator sees2575 manual corrections although the actual neural Run3
preflight produced23175 bound full lattices eligible for neural-auto-crop-v1.
All source entries retain NEURAL_GRID_GATE_UNCALIBRATED; that is not proof
of incorrect cuts. Record the requested shared Laboratory/main DB lifecycle
in the existing functional inventory, without representing it as delivered.

## Dependencies / entry conditions

- MAIN branch v1.1-vision-lab-hybrid-geometry, actual HEAD v1.7.232/88b2ac08.
- Existing D-523 operational crop admission and immutable manifest retained.
- Evidence: artifacts/mumie-preflight-diagnosis-20261007/summary.json.
- Assumption: UI interpretation repair only; no new engine/classification.
- No blocking product question. Lab integration is a separate feature.

## Recommended execution

gpt-6.1-sol, high. Inspect actual source/model pins and preserve legacy
semantics. Reassess scope if a backend eligibility or contract change becomes
necessary; no delegation or model override is authorized by the table alone.

## Relevant docs

- AGENTS.md; ai_docs/README.md; ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md; ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/NEURAL_PREFLIGHT_PRESENTATION_EXECUTION_PLAN.md
- ai_docs/requirements/IMAGE_INGESTION.md
- ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/requirements/APP_V3_FUNCTIONAL_INVENTORY.md
- ai_docs/guides/MUMIE_MAIN_APP_OPERATOR_GUIDE_20261006.md

## Scope

- Correct folder lifecycle, geometry outcome, coverage and source editor labels
  for jobs with a valid neural snapshot; show the pinned model export.
- Give the reused source editor an optional neural presentation flag; hide
  classical calibration-pattern copy only for that flag. Preserve defaults.
- Mount the neural source editor only when explicitly expanded or inspecting
  a replacement. The actual271 MB manifest must not load behind closed details.
- Explain automatic full crop flow and real correction cases.
- Record separate Laboratory tab for per-game grid/symbol training, main DB
  candidate registry, retained version/provenance and explicit activation.

## Out of scope

API/schema changes, inference rerun, import dispatch, database writes,
migrations, cleanup, training, model activation, 777 engine changes and
implementation of the larger Laboratory feature.

## Acceptance criteria

- [x] Neural review count is presented as proposals, never mandatory errors.
- [x] Completed all-review neural report enables the existing explicit import;
  fresh mount/restoration reproduces the same meaning and does not dispatch it.
- [x] Classical geometry labels and import safeguards remain unchanged.
- [x] Report shows actual analysis progress and pinned neural export.
- [x] Documentation records actual diagnosis and future Laboratory requirement.
- [x] Focused tests, lint, formatting, types, build and fresh MAIN UI read pass.

## Technical notes

Use isNeuralGeometryPreflight/neuralImportSnapshot; no inference from game
name. Keep progress/API statuses unchanged. Extend outcome helper with an
optional neural flag derived from the pinned job; historical callers preserve defaults. A neural
proposal count is not an eligible board count or population accuracy.

## Expected files

- apps/admin/src/features/imports/image-folder-import-state.ts: lifecycle/outcome.
- apps/admin/src/features/imports/image-folder-import-panel.tsx: report/labels.
- apps/admin/src/features/imports/page-geometry-correction-panel.tsx: optional neural labels.
- apps/admin/test/image-folder-import-state.test.mjs: neural/legacy regressions.
- apps/admin/test/neural-import-preflight.test.mjs and image-folder-import-panel-contract.test.mjs.
- apps/admin/test-interactions/neural-import-readiness.test.mjs: mounted report.
- apps/admin/test-interactions/page-geometry-qualification.test.mjs: shared legacy regression.
- Existing operator guide, functional inventory, CURRENT_STATE, DECISION_LOG.
- New proposed plan and this task; diagnostic report under ai_docs/quality/.

## Test cases

- Completed neural preflight with all sources review → proposals, enabled import.
- Processing neural result → analysis, without claiming final quality.
- Fresh mount, imported/importing/failed staging → preserved stage, no false
  mandatory manual correction. Legacy entries retain deferred/manual labels.
- Source/report viewing never dispatches import, training or activation.
- Closed neural preview performs zero review-source requests; opening requests
  sources, preserves the saved proposal count and restart-safe draft behavior.

## Verification

Run scoped Node unit tests and tsx interaction tests from apps/admin, then
Prettier check, ESLint, tsc --noEmit and next build. Each process is launched
through artifacts/grid-v3-deployment-20261004/run_step.py --timeout120 with
an absolute cwd. Fresh read-only MAIN report and screenshot prove persistent
presentation. Pass means all acceptance criteria and no unrelated staged files.

## Risks / open questions

Structural eligibility is not measured correctness. No population quality
percentage is inferred. Shared Laboratory is recorded, not implemented here.

## Outcome

### Changed

Neural proposals replace the misleading mandatory-correction labels. The
report shows processed sources and the actual trained export; full valid
crop import remains explicit and enabled. Closed neural source previews
perform no all-source request; the shared editor preserves legacy defaults.

### Verification results

- Unit68/68 and interaction30/30 PASS, including fresh mount, explicit lazy
  expansion, source binding and legacy qualification regressions.
- Scoped format/types PASS. Lint PASS with four existing warnings: one img
  warning and three unused legacy identifiers. Final Admin build PASS,30.20s.
- Read-only actual MAIN report after controlled API restart:2575/2575,
  iteration03-f896da7196431be2, symbol model ready, Import enabled. No neural
  review-sources request behind the closed preview. Mobile390×844 has no
  horizontal overflow; screenshots in artifacts/mumie-preflight-diagnosis-20261007/.
- API parent19632, health ok. Old parent40856/child7244 ownership checked;
  latest30 jobs contained no active job. Initial restart command referenced
  unavailable PowerShell7 and launched nothing; built-in Windows PowerShell
  started the controlled API once. No duplicate service.
- Acceptance criteria and plan compared point by point; all scoped items pass.
- Completion version v1.7.233; commit hash recorded after commit.

### Not completed

Laboratory implementation and any data/model operations. Explicit review of
all sources and report validation still parse a large manifest; lazy loading
avoids the unnecessary request but does not implement backend pagination.

### Documentation updates

Operator guide, D-526, functional inventory MODEL-09, diagnostic report,
execution plan and CURRENT_STATE updated. Laboratory is explicitly a requested
future integrated feature, not a delivered training interface.

### Recommended next task

Design and implement shared per-game Laboratory using the existing training
and registry flows, including grid-network training and main DB lifecycle.
