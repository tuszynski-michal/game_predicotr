---
title: Fix structured preflight production import
status: done
version: 0.10
---

# TASK-0390 — Fix structured preflight production import

## Goal

Make a production `structured_default` import consume the exact, checksum-bound
page geometry accepted by its preflight as the final outer-board proof. Correct
sources must reach virtual crops and symbol inference; genuinely inconsistent
or source-unsafe geometry must remain available for manual correction.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Add a new structured-engine version that accepts source-specific preflight
  quads without changing historical v1 replay.
- Treat a checksum-bound `registered` page manifest as the final outer-board
  proof for v2, while keeping row-major, overlap and padded source-support
  gates fail-closed. Games without drawn internal cell lines must not be sent
  to correction solely because LSD cannot rediscover those lines.
- Pin new production import jobs to the corrected engine version so their
  pipeline fingerprint cannot reuse defective v1 stage results.
- Make crop-stage validation distinguish legacy v19 crop failures from the
  structured `verified/deferred` partition.
- Treat a batch containing only technical failures as failed rather than as a
  review-ready batch.
- Keep stage progress monotonic without counting source ingestion as a
  successful pipeline result.
- Replay immutable shared stage results into every new job-local projection
  instead of skipping directly to review with an empty queue.
- Add regression tests for preflight binding, historical replay, crop
  partitions, job fingerprinting and failure-only batches.
- Re-run one bounded real source before starting a corrected full import.

## Out of scope

- Weakening local board-line quality gates for historical v1 or unregistered
  sources.
- Automatically accepting a board whose local grid evidence is insufficient.
- Deleting historical jobs, stage results or pending geometry rows.
- Changing symbol labels or canonical sequence ownership.

## Definition of Done

- A registered preflight source is passed to v2 as exact source-specific
  initialization and is never replaced by generic full-frame initialization.
- Historical v1 jobs retain their pinned behavior and fingerprint.
- Structured crop payloads may contain verified crops and/or geometry
  deferrals and validate as an exact partition of active positions.
- Failure-only batches finish as failed with a stable error.
- Pipeline success/failure/review counters describe source outcomes, not the
  preceding managed-original copy phase.
- A new job association rebuilds its own review projections even when it reuses
  immutable global stage results.
- Focused worker/API tests, Ruff and mypy for changed modules pass.
- A bounded real-source check confirms either virtual crops or an honest local
  grid deferral, never a missing-preflight failure.

## Outcome

- New `structured_default` jobs pin
  `structured-opencv-independent-board-refinement-v2-pinned-preflight-v1`, so
  their fingerprint cannot reuse defective v1 geometry results. Historical v1
  remains unchanged and rejects the new pinned contract fail-closed.
- V2 consumes the exact checksum-bound `registered` page quads as final outer
  board proof. It derives cells from topology and still enforces source bounds,
  row-major order, overlap and padded crop support without inventing internal
  grid-line evidence.
- Structured crop validation now accepts an exact verified/deferred partition,
  and structured deferrals are persisted by one stage only.
- A new job association replays immutable shared stages into its own review
  projections. A failure-only batch now fails with
  `IMAGE_BATCH_ALL_SOURCES_FAILED` instead of entering review with no items.
- Managed-original ingestion no longer inflates pipeline `successCount`; the
  reported success/failure/review values describe actual source outcomes.
- Bounded checks on real `seq_1-9.jpg` and `seq_10-18.jpg` produced nine
  verified boards, nine virtual crops and zero deferrals for each source.
- Verification completed:
  - focused worker/API suite: `108 passed`;
  - PostgreSQL execution-reuse/replay test: `1 passed`;
  - Ruff for changed Python modules: passed;
  - project mypy checked 494 files and reported only pre-existing errors in
    OCR acceptance scripts and `semi_automatic_image_selections.py`; no changed
    TASK-0390 module produced an error.
