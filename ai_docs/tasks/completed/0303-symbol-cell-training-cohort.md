---
title: Symbol-cell training cohort and independent quality controls
status: done
release: "0.8"
---

# TASK-0303 — Symbol-cell training cohort and independent quality controls

## Goal

Train symbol recognition from individually approved checksum-bound crops rather
than requiring a complete reviewed board. Keep symbol recognition and grid
geometry as independent quality workflows, and bound training cost through a
deterministic diverse cohort.

## Scope

- introduce a v2 immutable symbol-cell cohort while preserving v1 board cohorts,
- qualify only current approved crops without grid issues,
- prioritize human corrections, deduplicate exact crops and select a bounded,
  source-diverse cohort with a target of 1,000 and a hard maximum of 2,000
  samples per active symbol,
- keep source-family-disjoint train/validation/test/regression splits,
- train and evaluate the existing fixed-size CNN/ONNX model from the v2 cohort,
- separate the Admin symbol-recognition and grid-cutting quality panels,
- add small deterministic scalability measurements for 100, 1,000 and 10,000
  board-equivalent candidate volumes without a large physical benchmark.

## Invariants

- an approved crop is bound to its current cell revision, geometry revision,
  crop identity and checksum,
- `?`, grid issues, superseded owners and stale geometry never enter training,
- crops from one source image never leak between dataset splits,
- selection is bounded and does not construct an all-pairs similarity matrix,
- model activation and grid-profile activation remain separate explicit actions,
- existing v1 cohorts, iterations and active model artifacts remain reproducible,
- training or reinference never mutates accepted human decisions.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Acceptance

- one approved crop can enter the next symbol cohort while the other cells of
  its board remain pending,
- exact duplicates are represented once and the final selected count never
  exceeds 2,000 per symbol,
- human corrections are selected ahead of ordinary approvals,
- a v2 cohort can complete the existing training, ONNX and candidate gate,
- Admin presents two independent quality panels and cell-level counts,
- complexity tests confirm bounded memory and linear candidate traversal,
- relevant tests, lint, typecheck, OpenAPI and builds pass.

## Outcome

Implemented in `v0.8.50–v0.8.54`:

- deterministic source-diverse selection with correction priority, exact and
  bounded near-duplicate removal, target 1000 and hard maximum 2000 per symbol,
- v2 immutable cell manifests and migration `0071`, while v1 remains readable,
- production sourcing from current canonical `approved` cells without grid
  issues, with path and checksum verification,
- existing CNN/dataset/ONNX pipeline accepts individual cells without a
  complete board,
- Admin separates symbol recognition from grid geometry controls.

Focused API/worker/Admin tests, Ruff, mypy, Admin lint/typecheck and production
build pass. The bounded-comparison test proves linear candidate traversal; no
large physical benchmark was run. A small in-memory measurement took 0.0482 s
for 1,500 candidates and 0.3552 s for 15,000 candidates, selecting the bounded
8,000-sample cohort for the latter. Repository-wide formatting remains blocked
only by pre-existing formatting drift in Reviewer/Admin generated or unrelated
files.
