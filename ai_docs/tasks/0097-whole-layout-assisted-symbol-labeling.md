---
title: TASK-0097 — Whole-layout assisted symbol labeling
status: in_progress
last_updated: 2026-07-28
---

# TASK-0097 — Whole-layout assisted symbol labeling

## Goal

Replace the quarantined single-crop bootstrap with a resumable, loopback-only
5 × 3 board workflow backed exclusively by accepted
`board-cell-crops-v2-calibrated-v1`, and produce the first reviewed decisions
needed by TASK-0059.

## Context

TASK-0096 passed the independent cell-grid gate with line P95 `1.8337 px` and
materialized 43 images, 387 boards and 5805 calibrated cells. TASK-0093 proved
the local review contract and HTTP safety, but its one-crop-at-a-time inventory
uses quarantined v1 artifacts.

The existing `reviewed-cell-labels-v1` decision contract remains valid. This
task changes the verified inventory and the unit of interaction, not the
meaning of an accepted or rejected cell label.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- D-058–D-061 in `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/0059-labeled-symbol-dataset-export.md`
- `ai_docs/tasks/completed/0093-bootstrap-symbol-label-review-tool.md`
- `ai_docs/tasks/completed/0096-grid-calibration-profiles-line-editor.md`

## Assumptions

- The existing game/symbol bootstrap configuration can be reused because it has
  no saved cell decisions and refers to the same corpus.
- A board is complete when all 15 cells have an explicit accepted or rejected
  decision. Partial cell decisions are persisted and resume on the same board.
- Geometry is immutable in this workflow. Only boards from the passed
  calibrated quality report are admitted; any geometry/profile/checksum drift
  blocks inventory generation before review.
- `observationId` is independent of crop bytes. `cropSampleId` includes the
  cropper/profile identity and checksum; it remains the `sampleId` referenced by
  `reviewed-cell-labels-v1`.

These are implementation details of D-058–D-061 and do not add a new product
rule.

## Scope

### 1. Calibrated inventory v2

- verify corpus, reviewed sequences, calibrated crop report, calibration
  profiles and passed quality report as one checksum chain,
- create stable `observationId`, `cropSampleId` and board identity,
- retain board image/overlay paths, profile provenance and 15 row-major cells,
- reject quarantined cropper versions, incomplete boards and any drift,
- emit deterministic `symbol-crop-inventory-v2` plus JSON Schema.

### 2. Whole-layout review domain

- group samples into deterministic sequence-ordered 5 × 3 boards,
- expose board/cell progress and filters,
- persist one or more cell decisions atomically,
- preserve partial boards across restart,
- prevent decisions for geometry not accepted by inventory v2,
- retain identical-byte conflict checks and optional propagation.

### 3. Loopback UI

- show the complete canonical board and all 15 cell crops,
- select a cell and assign/reject/clear it with visible state,
- support keyboard shortcuts, sequence jump, filters and previous/next board,
- show per-board and per-symbol progress,
- remain loopback-only with token, Origin and path/checksum protections.

### 4. First reviewed handoff

- reuse or create the real game/symbol configuration,
- keep review output separate from immutable crops,
- verify that the resulting labels load and can be consumed by TASK-0059,
- do not guess or auto-label any symbol.

## Out of scope

- classifier suggestions, confidence and active learning,
- PostgreSQL/Admin API review storage,
- train/validation/test split or model training,
- OCR approval,
- editing geometry inside the labeling screen,
- mass image ingestion or public deployment.

## Acceptance criteria

- [x] Inventory v2 covers exactly 43 images, 387 boards and 5805 calibrated cells.
- [x] Every sample has stable observation/crop identities and calibration
      provenance; v1 and detector-only v2 are rejected.
- [x] The UI presents one complete 5 × 3 board in row-major order.
- [x] Cell decisions are explicit, atomic, idempotent and resumable.
- [x] Partial and complete board status/progress are deterministic.
- [x] No label can be saved if calibrated geometry or artifact checks drift.
- [x] HTTP remains loopback-only and revalidates served board/crop bytes.
- [x] Existing empty real configuration resumes without fabricating labels.
- [x] Automated tests cover inventory chain, grouping, batch decisions, resume,
      conflicts, filtering, HTTP and path/checksum safety.
- [x] Browser smoke and visual inspection pass on the real calibrated corpus.
- [x] Ruff, mypy, full relevant tests, schemas and format checks pass.
- [x] Requirements, architecture, M6 plan, `CURRENT_STATE.md` and Outcome are
      updated.

## Expected files

- `services/worker/src/game_predictor_worker/images/symbol_dataset.py`
- `services/worker/src/game_predictor_worker/images/symbol_review.py`
- `services/worker/src/game_predictor_worker/images/symbol_review_http.py`
- `services/worker/tests/`
- `scripts/review_m6_symbol_labels.py`
- `scripts/export_m6_symbol_dataset.py`
- `scripts/m6_symbol_review/`
- `ai_docs/quality/m6-symbol-crop-inventory-v2*.json`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_symbol_dataset_export.py services/worker/tests/test_symbol_review.py services/worker/tests/test_symbol_review_http.py
.venv\Scripts\python.exe -m ruff check services/worker scripts
.venv\Scripts\python.exe -m mypy services/api/src services/worker/src scripts
.venv\Scripts\python.exe scripts/export_m6_symbol_dataset.py inventory --check
```

## Risks / open questions

- The first meaningful dataset still requires the owner to label representative
  boards. Completing the software cannot substitute human symbol decisions.
- Current profiles cover two known source sessions. New source groups must pass
  their own calibration before review.
- A rejected cell completes its explicit review state but is excluded from the
  labeled export.

## Outcome

Technical implementation completed 2026-07-28; task remains `in_progress`
until the owner labels the first representative board batch.

- Added deterministic `symbol-crop-inventory-v2` with 43 images, 387 boards and
  5805 cells. It verifies the corpus, reviewed sequences, cell-grid golden,
  profile set, calibrated crop report, passed quality report and all board/crop
  bytes as one chain.
- Added stable `boardId` and `observationId` independent of crop bytes plus
  profile/crop-dependent `cropSampleId`. Inventory SHA-256 is
  `5687f80bf74004cdf6bcb7d35633a4916a7326ff1ffdbee4e9a82cf958e32f89`.
- Replaced the single-crop screen with a complete canonical board, 15 row-major
  cell cards, symbol palette, explicit reject/clear, filters, board/cell
  progress and sequence jump.
- Board decision batches are atomic and idempotent, reject a foreign sample
  without partial writes, retain identical-byte conflict checks and resume
  partial boards from `reviewed-cell-labels-v1`.
- Loopback HTTP serves only known board/crop IDs, revalidates dimensions and
  checksums, and retains token plus Origin protections.
- Browser smoke on the real corpus showed 387 pending boards, 5805 cells,
  exactly 15 cells for sequence 1 and a successful jump to sequence 387.
- Verification passed: deterministic `inventory --check`, 296 worker tests,
  Ruff, mypy for 146 source files, Prettier and diff checks. One Windows socket
  interruption in an existing HTTP test passed immediately in isolation and
  the complete suite then passed cleanly.
- The existing real configuration contains eight symbols and zero labels.
  No symbol was guessed or assigned by the implementation.

The local review server is ready for the owner to label 15–30 representative
boards. After that, TASK-0059 can materialize the first non-empty reviewed
dataset.
