---
title: TASK-0101 — Production symbol-aware crops and geometry gate
status: in_progress
last_updated: 2026-07-28
---

# TASK-0101 — Production symbol-aware crops and geometry gate

## Goal

Turn the accepted TASK-0100 spike into immutable full-corpus crop artifacts,
while preserving explicit fallback, provenance and an independent visual gate.

## Context

Frame-only local calibration improved geometry but failed every held-out board.
The symbol-aware spike found 15 reliable centers on all 25 reviewed boards,
reduced held-out median residual from `6.6964 px` to `2.0441 px`, and passed
owner review. Full-corpus validation subsequently rejected propagation of one
exact-image frame correction across all page positions. Production data must
start from each detector board independently, use a new crop namespace and
cannot overwrite v1–v5 artifacts or migrate the existing 56 labels.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- D-058–D-063 in `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/0098-local-image-grid-calibration-held-out-gate.md`
- `ai_docs/tasks/completed/0100-symbol-aware-grid-refinement-spike.md`

## Scope

- apply guarded symbol-aware refinement independently to every detected board,
- create a new immutable crop namespace and record refiner metrics/provenance,
- fail closed to `needs_review` when localization or transform guards fail,
- route only strict fallback boards to exact-observation manual correction,
- regenerate the complete 43-image / 387-board corpus after those corrections,
- create a page-level visual gate before setting `trainingAllowed = true`.

## Out of scope

- symbol class recognition or model training,
- auto-accepting geometry,
- changing OCR or sequence numbers,
- overwriting older crop namespaces,
- migrating old labels to new crop identities.

## Acceptance criteria

- [x] Every detector board is refined independently without cross-position
      propagation of an image-level frame correction.
- [ ] Every board records refiner version, center coverage, inliers and
      residuals.
- [ ] Any failed guard makes the source image `needs_review`.
- [x] Strict full-corpus benchmark routes 381/387 boards automatically and
      exactly 6 fallbacks to manual review.
- [ ] Complete successful corpus has 43 images, 387 boards and 5805 cells.
- [ ] Old crop artifacts and 56 decisions remain unchanged.
- [ ] Full-page visual review remains required before training is allowed.
- [ ] Schemas, tests, Ruff, mypy and deterministic checks pass.
- [ ] Documentation records measured production outcome.

## Expected files

- `services/worker/src/game_predictor_worker/images/local_grid_calibration.py`
- `services/worker/src/game_predictor_worker/images/rectification.py`
- `services/worker/src/game_predictor_worker/images/symbol_grid_refinement.py`
- `services/worker/tests/test_local_grid_calibration.py`
- `services/worker/tests/test_symbol_grid_refinement.py`
- `scripts/build_m5_complete_local_grid_profiles.py`
- `scripts/crop_m5_board_cells_symbol_aware.py`
- `scripts/crop_m5_board_cells_detector_symbol_aware.py`
- `scripts/review_m5_symbol_grid_fallbacks.py`
- `services/worker/src/game_predictor_worker/images/symbol_grid_fallback_review.py`
- `ai_docs/quality/m5-full-symbol-grid-refinement-detector-report.json`
- `ai_docs/quality/m5-board-cell-crops-v6-detector-symbol-aware-affine-report.json`

## Outcome

The exact-image calibrated-start v5 route was rejected by page-level visual
inspection because some lower boards included sequence-number/background
pixels. Detector-per-board v6 refined 381/387 boards; 6 strict fallbacks are
isolated as sequences `11`, `33`, `123`, `172`, `266`, `337`. A deterministic
six-item perspective-editor queue is prepared at
`artifacts/m5-symbol-grid-fallback-review/reviewed-geometry.json`. Completion
waits for owner correction/acceptance of those six boards, full regeneration,
43-page visual approval and final schema/determinism checks.
