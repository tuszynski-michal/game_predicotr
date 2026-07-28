---
title: TASK-0096 — Grid calibration profiles and perspective editor
status: done
last_updated: 2026-07-28
---

# TASK-0096 — Grid calibration profiles and perspective editor

## Goal

Turn the 27 accepted source-quad corrections into immutable, versioned
calibration profiles, apply them to all 387 boards without per-board manual
editing, regenerate separate calibrated artifacts and pass the independent
cell-grid quality gate.

## Context

TASK-0095 fixed the logical 100 × 100 cell step but detector-driven quads still
produce P95 line error `42.1563 px`, so `board-cell-crops-v2` remains
quarantined. TASK-0094 contains 27 accepted, human-adjusted source quads across
both source groups and every board position.

D-060 supersedes arbitrary line editing on an already cropped board. The editor
continues to expose four source-frame corners and the derived perspective 5 × 3
grid. The calibration profile reuses those accepted corrections as anchors.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/delivery/MILESTONE_05_EXECUTION_PLAN.md`
- `ai_docs/tasks/completed/0094-cell-grid-golden-annotations-crop-quality-gate.md`
- `ai_docs/tasks/completed/0095-board-cell-cropper-v2-corpus-regeneration.md`

## Assumptions

- The 27 accepted entries are the only human calibration input required for the
  current two source sessions.
- A profile scope is exactly `(source_group, board_position)`, producing 18
  profiles for the current corpus.
- Each accepted quad becomes an immutable sequence anchor. Corner corrections
  are represented in the detected quad's local basis.
- Between two anchors, local corner corrections are linearly interpolated by
  domain `sequence_number`; outside their range, the nearest anchor is used.
- A scope with one anchor applies its correction unchanged.
- The accepted source quad is used only to create a published profile anchor.
  Corpus regeneration consumes the profile artifact, not the golden file.

These assumptions define a technical calibration strategy, not a new product
rule. They will be recorded in D-061.

## Scope

### 1. Versioned profile contract

- create deterministic `grid-calibration-profiles-v1`,
- fingerprint the accepted golden and detector report,
- require one published profile for every source-group/position pair,
- persist anchor observation, sequence, detected quad, accepted quad and local
  corner corrections,
- validate ordering, uniqueness, finite values, quad geometry and safe scope,
- make published profiles immutable and byte-stable.

### 2. Profile application

- resolve the profile using source group and board position,
- interpolate or clamp by `sequence_number`,
- reconstruct a calibrated source quad from the current detector quad,
- reject missing, ambiguous, invalid or out-of-bounds results explicitly,
- record profile version, profile ID, anchor provenance and calibrated quad in
  every board artifact.

### 3. Perspective editor and publishing workflow

- preserve the existing four-corner perspective editor and derived tilted grid,
- expose profile scope, anchors, interpolation preview and publish status,
- publish only from a complete accepted golden,
- never edit or overwrite a published profile or historical crop artifact.

### 4. Calibrated corpus and quality gate

- materialize a separate calibrated namespace for 43 images, 387 boards and
  5805 cells,
- retain v1 and detector-only v2 bytes unchanged,
- evaluate all 27 golden boards and 405 cell artifacts,
- allow training only when line P95 is at most `5 px`, all scopes resolve and
  all artifact/source-chain checks pass,
- generate deterministic profile, crop and quality reports with JSON schemas.

## Out of scope

- manual correction of all 387 boards,
- arbitrary six-line correction on a cropped board,
- page detector or OCR changes,
- symbol labeling, dataset export or model training,
- database persistence or Admin API integration,
- mutation of v1 or detector-only v2 artifacts.

## Acceptance criteria

- [x] Exactly 18 published profiles cover both source groups and positions 0–8.
- [x] All 27 accepted golden entries are represented as immutable anchors.
- [x] Profile selection and sequence interpolation/clamping are deterministic.
- [x] Missing/ambiguous scopes, drift and invalid calibrated quads fail safely.
- [x] The editor previews the source quad, tilted 5 × 3 grid, canonical board,
      15 cells, profile scope and interpolation behavior.
- [x] Calibrated artifacts use a separate namespace and record profile
      provenance without changing v1 or detector-only v2.
- [x] The complete calibrated corpus has 43 images, 387 boards and 5805 cells.
- [x] The 27-board quality report passes line P95 ≤ 5 px and verifies 405 cells.
- [x] Identical generation and evaluation reruns preserve exact SHA-256 values.
- [x] Automated tests cover contracts, interpolation, clamping, scope safety,
      immutability, artifact provenance, determinism and the quality gate.
- [x] Ruff, mypy, relevant tests, JSON Schema and format checks pass.
- [x] Requirements, architecture, Decision Log, `CURRENT_STATE.md` and Outcome
      are updated.

## Expected files

- `services/worker/src/game_predictor_worker/images/`
- `services/worker/tests/`
- `scripts/m5_cell_grid_review/`
- `scripts/`
- `ai_docs/quality/m5-grid-calibration-profiles*.json`
- `ai_docs/quality/m5-board-cell-crops-v2-calibrated*.json`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe -m ruff check services/worker scripts
.venv\Scripts\python.exe -m mypy services/api/src services/worker/src scripts
.venv\Scripts\python.exe -m pytest services/worker/tests
.venv\Scripts\python.exe scripts/build_m5_grid_calibration_profiles.py --check
.venv\Scripts\python.exe scripts/crop_m5_board_cells_calibrated.py --check
.venv\Scripts\python.exe scripts/evaluate_m5_calibrated_cell_crops.py --check --require-pass
```

Run profile generation, corpus generation and evaluation twice and compare
exact report SHA-256 values.

## Risks / open questions

- The current golden measures the same two source sessions to which the
  profiles apply. Passing G5.3 validates this bounded corpus, not a new cabinet,
  camera or capture session. A new source group must be calibrated explicitly.
- Linear interpolation assumes gradual session drift. Every result is clamped
  to accepted anchor ranges and validated geometrically; no extrapolation is
  allowed.

## Outcome

Completed 2026-07-28.

- Added deterministic `grid-calibration-profiles-v1`: 18 published scopes cover
  both source groups and all positions 0–8, with all 27 accepted golden quads
  represented as immutable sequence anchors. Corrections use the detector
  quad's local basis and deterministic exact/interpolation/clamp behavior.
- Added strict source fingerprints, scope/geometry validation and stable
  failures for incomplete, ambiguous or drifted profile inputs. D-061 records
  the accepted architecture.
- Added `board-cell-crops-v2-calibrated-v1` without mutating v1 or detector-only
  v2. Every board records profile ID/version, anchor sequences and interpolation
  weight. The complete corpus has 43 images, 387 boards, 5805 cells and zero
  review results.
- The independent 27-board/405-cell report passed with line P95 `1.8337 px`
  against the `5 px` budget and `trainingAllowed = true`.
- Deterministic report SHA-256 values are:
  - profiles:
    `6928c0cb6909c9106d9f4e1a9bd153500eec56f0b96be3d7f8b6cc2a06ec6242`,
  - calibrated crops:
    `cefe1a54ea912cac6d8a7cc9dff74d432c3cd56898b91e6213abff5af3a4787b`,
  - calibrated quality:
    `8e53f463a42897265bc36cd82b56c72dbd6f05fd128e18de7fc066e09f0470eb`.
- Preserved the four-corner perspective editor and added profile scope,
  anchors, publish state and interpolation preview. Browser smoke and visual
  inspection passed on the real accepted corpus.
- Verification passed: 290 worker tests, Ruff, mypy for 145 source files,
  three JSON Schema validations, formatting/diff checks, full deterministic
  regeneration, and the unchanged detector-only v2 quality report
  (`d66b129c...`, P95 `42.1563 px`).

TASK-0097 can now use only the calibrated corpus for whole-layout assisted
symbol labeling. A new cabinet, camera or capture session remains a new source
group and therefore requires explicit calibration.
