---
title: TASK-0100 — Symbol-aware grid refinement spike
status: done
last_updated: 2026-07-28
---

# TASK-0100 — Symbol-aware grid refinement spike

## Goal

Test whether the visible 5 × 3 symbol lattice can refine cell boundaries more
reliably than the red board frame alone, without training a symbol classifier
or auto-accepting geometry.

## Context

The owner completed all 25 TASK-0098 geometry decisions. Eighteen boards still
have at least one cell where the proposed grid cuts a symbol, including every
one of the nine disjoint held-out boards. The exact-source frame correction is
a substantial improvement over sequence-clamped profiles, but its central
assumption did not pass the held-out gate: the frame and local perspective do
not uniquely determine the symbol lattice on every board.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- D-058–D-062 in `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/0098-local-image-grid-calibration-held-out-gate.md`

## Assumptions

- The frame-based quad remains a useful bounded search region.
- Symbol foreground can be localized without knowing its class.
- The known 5 × 3 topology supplies a strong prior: one center per logical
  slot, monotonic rows and columns, and approximately projective spacing.
- A proposal is never accepted solely from its score. Low confidence or failed
  validation preserves the frame geometry and routes the board to review.

## Scope

1. Rectify a board with its reviewed frame quad.
2. Estimate one symbol center and confidence inside each approximate slot.
3. Fit a robust projective lattice from reliable centers to ideal 5 × 3
   centers.
4. Reject implausible transforms, insufficient coverage and excessive
   residuals.
5. Benchmark the proposal on the 25 reviewed boards, separately for
   missing-anchor and held-out subsets.
6. Materialize deterministic before/after overlays for boards reported with
   cut symbols.

## Out of scope

- recognizing the symbol class,
- training or exporting a model,
- replacing TASK-0098 artifacts,
- automatically migrating labels,
- accepting geometry without owner review.

## Acceptance criteria

- [ ] Every proposal records all center candidates, confidence, inlier count,
      residuals and fallback reason.
- [ ] A proposal cannot leave the source image or create a non-convex quad.
- [ ] Benchmark reports frame baseline and symbol-aware result separately.
- [ ] Missing-anchor and held-out subsets remain separate.
- [ ] Before/after overlays are reproducible and do not overwrite source data.
- [ ] Tests cover deterministic localization, fallback and transform guards.
- [ ] Ruff, mypy and focused tests pass.
- [ ] The owner visually accepts or rejects the spike before production use.

## Expected files

- `services/worker/src/game_predictor_worker/images/symbol_grid_refinement.py`
- `services/worker/tests/test_symbol_grid_refinement.py`
- `scripts/benchmark_m5_symbol_grid_refinement.py`
- `ai_docs/quality/m5-symbol-grid-refinement-report.json`
- ignored overlays under `artifacts/m5-symbol-grid-refinement/`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_symbol_grid_refinement.py
.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images/symbol_grid_refinement.py services/worker/tests/test_symbol_grid_refinement.py scripts/benchmark_m5_symbol_grid_refinement.py
.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/images/symbol_grid_refinement.py scripts/benchmark_m5_symbol_grid_refinement.py
```

## Risks / open questions

- Moiré, glare, occlusion and differently shaped symbols may move a raw visual
  centroid away from the logical symbol center.
- The spike must prove improvement visually; a lower self-measured residual is
  not sufficient because the same detected centers produced the transform.

## Outcome

In progress:

- all 25 reviewed boards produced a guarded symbol-aware proposal with 15
  reliable center candidates,
- median center-to-logical-center residual fell from `6.6874 px` to
  `2.0558 px`,
- on the nine disjoint held-out boards the same metric fell from `6.6964 px`
  to `2.0441 px`,
- deterministic before/after overlays were generated for the 18 boards on
  which the owner reported cut symbols,
- the report remains `spike_review_required` and `trainingAllowed = false`;
  the self-measured residual is not treated as sufficient acceptance evidence,
- three focused tests, Ruff, mypy and deterministic report `--check` pass.

The owner visually accepted the expanded gallery of all 25 overlays. The spike
is complete. Production integration and a new crop namespace move to
TASK-0101.
