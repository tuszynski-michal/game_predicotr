---
title: TASK-0095 — Board cell cropper v2 and corpus regeneration
status: done
last_updated: 2026-07-28
---

# TASK-0095 — Board cell cropper v2 and corpus regeneration

## Goal

Implement the versioned `board-cell-crops-v2` algorithm, regenerate the
complete 43-image corpus into separate immutable artifacts and measure the
detector-driven result against the accepted 27-board source-quad golden.

## Context

TASK-0094 proved that historical v1 is not suitable for labeling or training.
Its global 25/15 px inset changed the grid step to 90 px and produced P95 line
error `47.0748 px`. The accepted golden contains 27 independently adjusted
source quads and is the quality reference for this task.

TASK-0095 fixes the crop algorithm but does not infer calibration profiles from
the golden. The complete corpus continues to use the detector quads so the
evaluation remains independent. If v2 still exceeds the accepted line-error
budget, the result remains quarantined and TASK-0096 must introduce explicit,
versioned calibration profiles.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/delivery/MILESTONE_05_EXECUTION_PLAN.md`
- `ai_docs/tasks/completed/0094-cell-grid-golden-annotations-crop-quality-gate.md`

## Scope

### 1. Cropper v2

- preserve canonical board rectification at RGB `500 × 300`,
- split the board into fifteen logical row-major slots of `100 × 100`,
- apply a versioned `5 px` inset independently inside every slot,
- produce fifteen RGB `90 × 90` cells,
- draw a diagnostic overlay showing slot boundaries and inset boundaries,
- preserve stable review reasons and all-or-nothing page behavior.

### 2. Immutable v2 artifacts

- write only below the `board-cell-crops-v2` namespace,
- retain historical v1 artifacts without modification,
- persist board, overlay and cell checksums, source quad, transform matrix,
  grid contract and quad provenance,
- fingerprint normalization and detection reports,
- make an identical rerun byte-stable and avoid rewriting identical assets.

### 3. Complete corpus regeneration

- process all 43 normalized source images,
- preserve 387 board positions and row-major order,
- produce exactly 5805 cells when every upstream page is complete,
- reject drift, unsafe paths, invalid quads and incomplete pages explicitly.

### 4. Independent quality report

- compare the detector-driven v2 source quads and derived internal lines with
  the 27 accepted golden quads,
- report per-corner and per-line errors plus P50, P95 and maximum,
- group failures by source group and board position,
- set `trainingAllowed` only when P95 line error is at most `5 px`, every
  golden board is present and no source-chain or artifact failure exists,
- do not substitute golden quads into the regenerated detector-driven corpus.

## Out of scope

- deriving or applying group/position calibration profiles,
- editing additional source quads,
- changing page detection or OCR,
- labeling symbols or exporting a training dataset,
- mutating, deleting or reclassifying v1 artifacts.

## Acceptance criteria

- [x] `board-cell-crops-v2` uses 100 × 100 logical slots and per-cell 5 px inset.
- [x] Every successful board contains 15 deterministic RGB 90 × 90 crops.
- [x] The full corpus contains 43 images, 387 boards and 5805 cells.
- [x] All v2 paths are separate from v1 and existing v1 bytes are unchanged.
- [x] Report and artifacts validate upstream identities, paths and checksums.
- [x] Re-running generation and evaluation is deterministic and idempotent.
- [x] The 27-board quality report contains corner and line P50/P95/max metrics.
- [x] A failing quality budget keeps v2 quarantined and points to TASK-0096.
- [x] Automated tests cover slot mapping, inset, invalid input, drift,
      all-or-nothing output, determinism and golden evaluation.
- [x] Ruff, mypy, relevant tests and JSON/format checks pass.
- [x] `CURRENT_STATE.md` and this task's `Outcome` are updated.

## Technical notes

- `PerspectiveBoardCellCropper` v1 remains immutable historical code.
- Prefer a separate v2 implementation and explicit versioned report contract.
- The accepted golden is evaluation input only; using its quad during complete
  corpus generation would make the quality measurement circular.
- TASK-0096 owns any reusable calibration profile and its editor.

## Expected files

- `services/worker/src/game_predictor_worker/images/`
- `services/worker/tests/`
- `scripts/crop_m5_board_cells_v2.py`
- `scripts/evaluate_m5_board_cell_crops_v2.py`
- `ai_docs/quality/m5-board-cell-crops-v2*.json`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe -m ruff check services/worker scripts
.venv\Scripts\python.exe -m mypy services/worker/src scripts
.venv\Scripts\python.exe -m pytest services/worker/tests
.venv\Scripts\python.exe scripts/crop_m5_board_cells_v2.py --check
.venv\Scripts\python.exe scripts/evaluate_m5_board_cell_crops_v2.py --check
```

Run generation and evaluation twice and compare exact output SHA-256 values.

## Risks / open questions

- Detector quads are expected to remain outside the 5 px budget after the
  cell-step defect is fixed. That measured failure is not a reason to copy
  golden quads into production output; it is the entry condition for TASK-0096.

## Outcome

Completed 2026-07-28.

- Added immutable `board-cell-crops-v2` with a canonical RGB `500 × 300`
  board, fifteen logical `100 × 100` row-major slots, a local `5 px` inset
  and fifteen RGB `90 × 90` cell artifacts.
- Regenerated all `43` source images into `387` boards and `5805` cells below
  the separate v2 namespace. Existing v1 remained unchanged at `6579` files
  and `196994964` bytes.
- Added deterministic generation and independent quality CLIs, explicit JSON
  schemas, upstream fingerprints, safe-path and checksum verification, quad
  provenance and diagnostic overlays.
- The crop report is byte-stable at SHA-256
  `d7d55fccd35e2760ae269cc4c7a25b5afc8271cbb640f1e940ef79af2ae486cc`.
  The quality report is byte-stable at SHA-256
  `d66b129c759abe140979d48f85a93804c33a37ff07050301d7259721bbd43e8d`.
- Independent evaluation verified `27` golden boards and `405` artifacts.
  Detector-driven v2 has line-error P50 `20.5613 px`, P95 `42.1563 px` and
  maximum `91.88 px`; quad-corner P95 is `22.7606 px`.
- Because line P95 exceeds the accepted `5 px` budget, the result has status
  `quarantined_calibration_required`, `trainingAllowed = false` and
  `nextTask = TASK-0096`. Golden quads were not substituted into corpus
  generation.
- Verification passed: Ruff, mypy for `141` source files, `283` worker tests,
  JSON Schema validation with Ajv, repeated `--check` generation/evaluation
  and the expected failing `--require-pass` quality gate.
