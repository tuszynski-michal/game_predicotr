---
title: TASK-0373 — Row-first range runtime v5
status: done
version: 0.10
---

# TASK-0373 — Row-first range runtime v5

## Goal

Run the transition-safe row-first proof through the durable semi-automatic
selection job without altering historical v1–v4.1 runs.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md` (D-291, D-292)

## Scope

- Register a new fingerprinted v5 runtime selected solely by the stored run
  contract.
- Decode and EXIF-canonicalize each source once, locate independent rows,
  batch only source-resolution label crops through recognition-only Paddle,
  and require the v5 two-row final proof.
- Preserve source order, bounded internal OCR batches of at most nine crops,
  checksum-bound observations and checkpoints only after a complete source
  batch.
- Give v5 its own grouping/selection policy identity while retaining the same
  evidence-span rule.

## Out of scope

- Default rollout, UI/API changes, real-corpus acceptance measurements,
  migrations, board geometry, cropper, symbol inference and model training.

## Acceptance criteria

- [x] v5 produces `exact` only from two agreeing source-local rows; a single
  row or conflicting visible row remains unknown.
- [x] v1–v4.1 still resolve their existing stored fingerprint and checkpoint
  contracts unchanged.
- [x] No internal Paddle call receives more than nine crops.
- [x] Restart resumes from a complete source-batch checkpoint without duplicate
  observations.

## Expected files

- `services/worker/src/game_predictor_worker/semi_automatic_selection/row_first_runtime_v5.py`
- `services/worker/src/game_predictor_worker/semi_automatic_selection/middle_row_grouping.py`
- `services/worker/src/game_predictor_worker/semi_automatic_selection/range_only_ocr.py`
- `services/worker/src/game_predictor_worker/semi_automatic_selection/job.py`
- focused worker tests and the completed task record

## Outcome

Implemented a fingerprint-selected `RowFirstBatchRuntime` that
EXIF-canonicalizes each source once, locates source-local rows and sends only
direct label crops to bounded recognition-only Paddle batches. A final exact
requires two agreeing rows from the same source; a single or conflicting
visible row remains unknown.

V5 has separate runtime, grouping and selector identities. Its job path saves
checkpoints only after complete six-source batches and reconciles the audit on
restart, preserving checksum-bound observations without duplicating a committed
prefix. Historical v1–v4.1 dispatch and checkpoint contracts remain unchanged.

Focused worker verification passed: 124 tests, Ruff check/format check and the
configured API-plus-selection mypy run. No real-corpus rollout, benchmark or
default activation was performed; TASK-0374 remains the first acceptance gate.
