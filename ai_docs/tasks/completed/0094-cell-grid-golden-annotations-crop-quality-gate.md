---
title: TASK-0094 — Independent cell-grid golden annotations and crop quality gate
status: done
last_updated: 2026-07-28
---

# TASK-0094 — Independent cell-grid golden annotations and crop quality gate

## Goal

Create an independent, human-accepted reference dataset for the source-image
board frame and its derived internal `5 × 3` grid, then use it to measure the
current cropper before implementing cell-grid v2.

The output of this task is the quality gate for TASK-0095. The golden annotations
must not be generated and accepted solely from the current cropper output,
otherwise the implementation would be tested against its own assumptions.

## Context

The first real M6 labeling attempt exposed a systematic geometry defect in the
historical crop corpus:

- the board was rectified to `500 × 300`,
- a global `25 px` horizontal and `15 px` vertical inset was applied,
- `90 × 90` crops were then advanced with a `90 px` step,
- internal crop boundaries therefore crossed symbol areas instead of following
  the logical `100 × 100` cell slots.

The existing `symbol-crop-inventory-v1` and its 5805 crops are quarantined as
historical diagnostic input. They cannot be used for symbol labeling or model
training.

Decision D-059 requires an independently accepted cell-grid golden set before
the production cropper is corrected.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/delivery/MILESTONE_05_EXECUTION_PLAN.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`

## Scope

### 1. Deterministic review sample

Prepare a deterministic, stratified sample of at least 27 rectified boards:

- all nine board positions shown on a source page must be represented by at
  least three boards,
- both current source-image groups must be represented,
- the sample should include the available variation in blur, glare, perspective
  and image quality,
- the selection and ordering must be reproducible.

The task does not require manually reviewing every source board.

### 2. Versioned golden schema

Define `cell-grid-golden-v1` with at least:

- stable board observation identity,
- source image identity and checksum,
- sequence number and board position,
- rectified `500 × 300` board checksum,
- detected source quad used by the historical cropper,
- four human-adjustable corners of the actual board frame in source-image
  pixels,
- the derived perspective projection of four internal vertical and two
  internal horizontal grid lines,
- review state and reviewer decision,
- schema version and generation metadata.

The source quad is the reviewed input to rectification. Its coordinates must be
validated against the source-image dimensions, convexity, orientation and
minimum edge/area constraints. The canonical output remains RGB 500 × 300.

### 3. Local grid review tool

Provide a local loopback-only review tool or extend the existing local review
surface so that the reviewer can:

- see the original source image around the selected board,
- see the detected-quad suggestion and the derived angled 5 × 3 grid,
- drag four board-frame corners,
- see the generated canonical 500 × 300 board,
- preview all 15 resulting cell crops live,
- accept, reopen and resume a review,
- use clear keyboard controls for the main actions,
- see the source identity, sequence number and board position.

Suggested lines are assistance only. A board enters the golden set only after an
explicit reviewer decision.

### 4. Source-chain validation

Validate that every golden entry points to the expected source image and
rectified board through stable identities, paths and checksums. Missing or
mismatched artifacts must fail explicitly rather than being silently skipped.

### 5. Historical cropper baseline

Measure cell-grid v1 against the accepted golden annotations and create a
deterministic report containing at least:

- absolute error for every internal line,
- absolute corner errors of the detected source quad,
- P50, P95 and maximum line error,
- affected board positions and source groups,
- boards and cells where a current boundary cuts through the main symbol area,
- the exact cropper and golden schema versions.

The report establishes the pre-fix baseline. It does not approve cell-grid v1.

## Out of scope

- implementing cell-grid/cropper v2,
- regenerating the full crop corpus or inventory v2,
- creating operational calibration profiles for source groups,
- labeling symbol classes,
- training or exporting a symbol classifier,
- automatic online learning from each reviewer click.

## Acceptance criteria

- [x] The review sample contains at least 27 boards.
- [x] Every one of the nine board positions has at least three reviewed boards.
- [x] Both current source-image groups are represented.
- [x] Every golden annotation has an explicit human acceptance decision.
- [x] The golden data is not accepted solely from cropper-generated boundaries.
- [x] `cell-grid-golden-v1` is versioned and validates identities, paths,
      checksums and coordinate ranges.
- [x] The local review tool displays the source image, four editable board-frame
      corners, the derived perspective grid, the canonical rectified board and
      all 15 live crop previews.
- [x] Review progress can be resumed without losing accepted annotations.
- [x] Re-running sample selection and report generation is deterministic and
      idempotent.
- [x] The cell-grid v1 baseline reports per-line errors plus P50, P95 and maximum
      error.
- [x] Failures are reported by board position and source group.
- [x] Automated tests cover schema validation, deterministic selection, review
      persistence and metric calculation.
- [x] Formatting, lint, type checks and relevant tests pass.
- [x] `ai_docs/process/CURRENT_STATE.md` and this task's `Outcome` are updated
      after completion.

## Expected files

Exact names may change if the existing module boundaries require it, but the
implementation is expected to touch:

- `services/worker/src/game_predictor_worker/images/`
- `services/worker/tests/`
- `scripts/review_m5_cell_grid.py`
- a local review UI under `scripts/`
- versioned schemas or reports under `ai_docs/quality/`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

Run the repository commands appropriate to the changed Python and local-review
surfaces, including:

```powershell
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
```

Also run the new deterministic sample-selection and baseline-report commands
twice and confirm identical output for identical inputs.

Perform a browser smoke test of the local grid review tool:

1. open a pending board,
2. move at least one board-frame corner,
3. verify that all affected crop previews update,
4. accept the board,
5. restart the tool and confirm that the decision is restored,
6. reopen the board and confirm that it returns to the review queue.

## Risks and controls

- Human decisions are required for the 27-board golden set. The application
  should preselect and order the sample so the reviewer does not have to search
  through all source boards.
- Equal-grid suggestions may be close to correct, but they remain untrusted
  until accepted.
- This task must not quietly implement the v2 cropper; separating the golden
  reference from the production algorithm protects the quality gate from
  circular validation.

## Outcome

Implementation completed on 2026-07-28.

Execution assumptions:

- the deterministic review set contains exactly 27 boards: three for every
  board position,
- both current source groups occur in the sample for every board position,
- historical `board.png` artifacts are retained only as integrity evidence and
  baseline input; the independent golden starts from the original source image,
- the detector source quad is an untrusted suggestion and requires an explicit
  human decision,
- the review also records which cells have their main symbol cut by v1 so the
  baseline can report affected boards and cells without inferring human visual
  judgment from line distance alone.

Correction after the first real review:

- the owner observed that axis-aligned lines did not follow the tilted board,
- inspection confirmed that the detected quad for sequence 1 used approximately
  `(122, 408)` as its top-left corner while the visible frame begins closer to
  `(117, 399)`,
- D-060 replaces downstream slanted-line correction with four-corner
  source-quad review and a live perspective projection,
- the previous pending artifact contained no draft or accepted decision, so it
  may be migrated without losing human work.

Implemented:

- `cell-grid-golden-v1` validates the complete manifest → source image →
  annotation → rectified board chain by stable identity, safe path and SHA-256,
- deterministic stratification selected exactly 27 boards, three for every
  position; both source groups occur at every position,
- the loopback-only editor displays the original source image, four editable
  board-frame corners, a derived angled `5 × 3` grid, a live canonical
  `500 × 300` rectification, 15 live crop previews and the explicit v1
  symbol-impact assessment,
- draft, accept and reopen operations are atomic, resumable and protected by a
  same-origin review token,
- `cell-grid-v1-baseline-v1` calculates per-line errors, linear-R7 P50/P95/max
  and groupings by axis, position and source group, but refuses to run before
  all 27 human decisions exist,
- the real golden is `ai_docs/quality/m5-cell-grid-golden.json` using
  `source-quad-perspective-grid-v1`.

Verification completed before human review:

- Ruff passes for the full worker and scripts scope,
- mypy passes for 137 API/worker/script source files,
- all 279 worker tests pass, including 11 cell-grid domain/HTTP tests,
- Prettier and JavaScript syntax checks pass for the local review surface,
- a perspective browser smoke on a separate golden confirmed visible angled
  source-grid rendering, live numeric corner editing, changed rectification and
  crop previews, accept, persistence after server restart and reopen,
- the real editor was restarted at `http://127.0.0.1:8878/`,
- no decision from the smoke test was written to the real golden.

Human quality gate completed on 2026-07-28:

- the owner adjusted and explicitly accepted all `27/27` boards; every entry
  has `lineSource = human-adjusted`, `v1ImpactReviewed = true` and decision
  revision `1`,
- the final golden has SHA-256
  `a25b1753f8d3c74e13827c6803b82921e36e68f9c3eb3d1bccae88ce6d96c533`,
- the editor and the persisted contract both report `27/27` accepted and
  `0` pending,
- the deterministic v1 baseline report was generated twice with identical
  SHA-256
  `a62532ba30d90a861c374f63f7f9d7406f7b9d50d13313760336d09ecb8df9d5`,
- v1 is rejected and remains forbidden for training: all 27 reviewed boards
  and 395 cell observations are affected; line error is P50 `20.1487 px`,
  P95 `47.0748 px` and maximum `95.7587 px`, while detected-quad corner error
  is P95 `22.7606 px` and maximum `31.8557 px`,
- `ai_docs/quality/m5-cell-grid-v1-baseline-report.json` is the accepted
  pre-fix evidence for TASK-0095.
