---
title: TASK-0098 — Local image grid calibration and held-out gate
status: in_progress
last_updated: 2026-07-28
---

# TASK-0098 — Local image grid calibration and held-out gate

## Goal

Replace sequence-clamped board geometry with a local-frame correction scoped to
one source image, regenerate versioned crops and reopen symbol labeling only
after a genuinely disjoint geometry review passes.

## Context

Real labeling showed that sequence 1 was readable while later boards from the
same image were cut incorrectly. Inspection proved that profiles scoped to
`source_group + board_position` used distant anchors such as sequence 74 for
sequence 2. The reported P95 `1.8337 px` was measured on the same 27 boards
used as profile anchors, so it did not measure generalization over the other
360 boards.

The accepted golden already provides one human-adjusted anchor for 27 distinct
source images. A diagnostic on the first source image showed that applying its
single correction to a local bounding-frame basis for every board keeps all
symbols visible on boards 1–3. This task turns that diagnostic into a
versioned, verified pipeline.

The owner has 56 explicit symbol decisions in
`artifacts/m6-symbol-review/reviewed-labels.json`. They were copied unchanged
to a checksum-addressed geometry-quarantine backup before implementation.

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
- `ai_docs/tasks/0059-labeled-symbol-dataset-export.md`
- `ai_docs/tasks/0097-whole-layout-assisted-symbol-labeling.md`

## Assumptions

- One accepted source quad can calibrate the local detector bounding-frame
  basis for the other boards on the same source image.
- A missing source-image anchor produces `needs_review`; it never falls back to
  an anchor from another image or sequence.
- Existing labels remain immutable evidence for their exact old
  `cropSampleId`. They are not automatically transferred to regenerated crops.
- A previous label may later be shown as a suggestion linked by stable
  `observationId`, but only a new explicit decision can accept the new crop.

## Scope

### 1. Local image profiles

- derive each board's local basis from its own detector bounding frame,
- scope a calibration profile to the exact source-image checksum,
- apply one accepted source-image correction to every board on that image,
- reject a missing profile instead of clamping a distant anchor,
- retain source group, sequence, position, detector and accepted provenance.

### 2. Versioned regeneration

- create a new cropper/profile namespace without overwriting v1 or v2,
- preserve stable `observationId` and create new `cropSampleId`,
- materialize only images with an accepted local profile,
- list remaining source images as `needs_review`.

### 3. Independent quality gate

- prepare held-out boards from source images/positions not used as anchors,
- evaluate only the held-out subset for the pass/fail metric,
- report anchor-fit metrics separately and never use them as generalization,
- require complete visual page review for every source before full-corpus
  `trainingAllowed = true`.

### 4. Label safety

- keep the 56 existing decisions and their checksum-addressed backup,
- quarantine them from training when their crop geometry is replaced,
- do not silently migrate labels between crop versions.

## Out of scope

- symbol classifier training,
- automatic acceptance of symbol suggestions,
- changing sequence numbers or OCR decisions,
- manual correction of all 387 boards,
- cloud services or a new job queue.

## Acceptance criteria

- [ ] No board uses an anchor from a different source image.
- [ ] Twenty-seven existing accepted source images produce deterministic local
      profiles and crops.
- [ ] Sixteen currently unanchored source images are explicit review items.
- [ ] Held-out geometry uses no board that supplied its profile correction.
- [ ] Anchor-fit and held-out metrics are reported separately.
- [ ] Full-corpus `trainingAllowed` stays false until every source page and the
      held-out gate pass.
- [ ] Existing 56 decisions and their backup remain byte-for-byte unchanged.
- [ ] New crops receive new crop identities; no label is auto-migrated.
- [ ] Tests cover local scope, missing profiles, deterministic regeneration,
      disjointness and checksum drift.
- [ ] Ruff, mypy, tests, schemas and deterministic checks pass.
- [ ] Requirements, architecture, decision log, M6 plan and `CURRENT_STATE.md`
      reflect the measured outcome.

## Expected files

- `services/worker/src/game_predictor_worker/images/local_grid_calibration.py`
- `services/worker/src/game_predictor_worker/images/rectification.py`
- `services/worker/src/game_predictor_worker/images/cell_grid_v2_quality.py`
- `services/worker/tests/test_local_grid_calibration.py`
- `scripts/build_m5_local_grid_calibration_profiles.py`
- `scripts/crop_m5_board_cells_local.py`
- `scripts/review_m5_local_grid_calibration.py`
- `ai_docs/quality/m5-local-grid-calibration-*.json`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_local_grid_calibration.py services/worker/tests/test_board_cell_crops.py
.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images scripts services/worker/tests
.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/images scripts
```

## Risks / open questions

- Some images contain hand/navigation occlusion. Correct geometry cannot recover
  source pixels hidden by an object; such cells must remain rejected/reviewed.
- The 16 missing image anchors and held-out decisions require owner review after
  the software prepares the deterministic queue.

## Outcome

In progress:

- implemented exact-source local calibration based on each board detector
  bounding frame; cross-image fallback is forbidden,
- generated 27 deterministic source-image profiles and versioned v3 crops for
  243 boards / 3645 cells; 16 unanchored images remain explicit
  `needs_review`,
- prepared a deterministic corrective queue of 25 boards: 16 missing image
  anchors and 9 disjoint held-out boards covering positions 0–8,
- reused the perspective editor with live homography, angled grid and 15-cell
  preview; a pristine pre-fix review document is migrated without touching any
  human decision,
- preserved the 56 old-crop symbol decisions and their checksum-addressed
  backup without automatic migration,
- focused verification passes: 23 Python tests, Ruff and mypy. Browser smoke
  confirmed both missing-anchor and held-out states.

Owner review of the 25-board queue is the current gate. Independent held-out
metrics, complete v3 schemas and final `trainingAllowed` remain pending.

The owner completed `25/25`, but the gate did not pass: 18 boards retained
reported symbol cuts, including all 9 held-out boards. TASK-0100 now evaluates
a symbol-aware lattice refinement before TASK-0098 can publish production
profiles or enable training.
