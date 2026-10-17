---
title: TASK-1045 — Crop-aware source frame in the worker
status: done
last_updated: 2026-10-17
---

# TASK-1045 — Crop-aware source frame in the worker

## Status

`done`

## Goal

Every worker read of a managed original goes through the canonical loader,
which serves a verified crop when the original is absent (plan R2 revision 1),
and operations needing the full frame stop with a stable error.

## Context

Stage A of the accepted
[photo crop plan](../delivery/PHOTO_CROP_STORAGE_EXECUTION_PLAN_20261017.md).
Without crops on disk, behavior must stay byte-identical.

## Dependencies / entry conditions

TASK-1043 (attestation and region functions).

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Audit: Codex `gpt-6-astra` / `high`.

## Relevant docs

- Plan sections 1, R2, R4; D-562
- `ai_docs/requirements/IMAGE_INGESTION.md` section 2

## Scope

- `CanonicalSourceFrame.crop`, crop resolution in `decode_canonical_source_bytes`
  callers and `CanonicalSourceLoader.load`.
- `require_inside_valid_box` in virtual cell rendering and grid reinference.
- `SOURCE_ORIGINAL_CROPPED` in page geometry preflight (classic and neural).
- Migration of direct worker reads (plan section 1) to the loader or an explicit error.
- Cohort dataset decoding through the loader.

## Out of scope

API serving and gates (TASK-1046), jobs creating crops (stage B).

## Acceptance criteria

- [x] Original present: render specs and cell checksums unchanged (regression test).
- [x] Crop fixture (orientation 1 and 6): identical pixels inside the valid box; cells rendered from a crop canvas equal the original renders.
- [x] Quad outside the valid box → `SOURCE_REGION_UNAVAILABLE`.
- [x] Tampered crop or attestation → stable error, never a silent canvas.
- [x] Direct `data/originals` reads in the worker are covered (see Outcome).
- [x] Lint, mypy, worker tests of changed modules pass (2 timing-flaky shadow tests, see Outcome).

## Technical notes

Plan R2 revision 1 is the contract. The original wins when present.

## Expected files

`services/api/src/game_predictor_api/domain/canonical_source.py`,
`services/worker/src/game_predictor_worker/images/normalization.py`,
`page_geometry_preflight.py`, `neural_page_geometry_preflight.py`,
`virtual_cell_extraction.py`, `grid_reinference_handler.py`,
`grid_cohort_dataset.py`, `production_workflow.py` (confirmed at task start).

## Test cases

See acceptance criteria.

## Verification

```powershell
D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/worker/tests -k "source_frame or canonical or preflight or virtual_cell"
```

## Risks / open questions

- `images/geometry.py` and `images/rectification.py` byte sources to confirm.

## Outcome

Commit: v1.7.406 / `279a22cec42feac3fa9e42b992d914b8ef3c16a9`.

### Changed

- `domain/canonical_source.py`: `CanonicalSourceCrop` (attestation, `valid_box`),
  optional `CanonicalSourceFrame.crop`, `pixel_checksum_sha256` (original pixels
  or attested canvas), identity check of a crop frame against its attestation,
  `decode_cropped_source_bytes` (attestation self-checksum and original, crop
  file SHA-256, EXIF orientation kept, decoded box size, crop pixel checksum,
  canvas checksum; stable `SOURCE_CROP_*` codes) and `require_inside_valid_box`
  (one pixel clear of the edge ring on non-border edges; unbounded along image
  borders, so partially visible cells behave as on the original).
- Worker `normalization.py`: `CanonicalSourceLoader(allow_crop=...)` falls back
  to the crop siblings only when the original file is gone; without the opt-in
  it raises `SOURCE_ORIGINAL_CROPPED`. Helpers `managed_original_is_cropped`,
  `original_cropped_error`.
- Opt-in (`allow_crop=True`) only where known quads are rendered:
  `symbols/training_dataset.py`, `images/pending_symbol_reinference.py`,
  `images/grid_reinference_handler.py` (proposal lattice nodes must lie inside
  the valid box, otherwise the source outcome is `conflict` /
  `SOURCE_REGION_UNAVAILABLE`).
- `virtual_cell_extraction.py`: pixel drift check uses `frame.pixel_checksum_sha256`;
  padded and source quads must lie inside the valid box.
- Whole-frame readers fail with `SOURCE_ORIGINAL_CROPPED`: page preflight
  registration anchors and managed reprepare (`page_geometry_preflight.py`),
  neural managed reprepare, production pipeline `load_rgb` (discovery, anchors)
  and legacy normalization (`production_workflow.py`). Grid shadow and the
  import pipeline keep the default loader, so they refuse crops too.
- Plan revision 2 and D-562 addendum: page-registration anchors are excluded
  from cropping (`PAGE_REGISTRATION_ANCHOR` in `classify_blob` and the
  eligibility SQL: anchors pinned in any calibration profile, every cohort
  source of a historical profile without pinned anchors, manual page overrides,
  all games); TASK-1048 must skip deleted originals when choosing new anchors and
  building cohorts.

### Direct reads of managed originals (worker)

| Reader | Handling |
|---|---|
| `CanonicalSourceLoader` users with opt-in | crop frame, valid-box checks |
| `CanonicalSourceLoader` default users (pipeline normalization, shadow, spikes) | `SOURCE_ORIGINAL_CROPPED` |
| page preflight anchors and reprepare, neural reprepare | `SOURCE_ORIGINAL_CROPPED` |
| production `load_rgb`, legacy normalization | `SOURCE_ORIGINAL_CROPPED` |
| `grid_cohort_dataset` | reads the cohort's own copies, not `data/originals` |
| `images/geometry.py:1390`, `images/rectification.py:985` | legacy normalized PNGs, not originals |
| benchmark, golden and lab tools | missing file fails loudly; outside production |

### Verification results

- `services/worker/tests/test_source_crop_frame.py`: 10 passed (original wins;
  orientations none and 6 served from a block-aligned 4:4:4 crop with pixels
  identical inside the box; default loader and pipeline refuse with
  `SOURCE_ORIGINAL_CROPPED`; missing without crop stays NOT_FOUND; tampered crop
  and attestation; 15 cells rendered from a crop canvas byte-identical to the
  original renders incl. render spec checksums; cell outside the crop refused;
  valid-box ring and border rules; crop frame identity check).
- Worker regression of changed modules (virtual cell, normalization, pipeline
  contract/execution, preflight classic/neural, grid reinference, pending
  reinference, shadow, training dataset): 169 passed, 1 skipped, 2 failed —
  `test_grid_shadow_handler.py::test_bounded_cpu_child_returns_empty_detection_cleanly`
  and `::test_deadline_stops_slow_cpu_child_and_reaps_it` (CPU child timing);
  both pass when rerun alone in the worktree (2 passed, 7.4 s) and on `main`.
- API eligibility after the anchor rule: `test_source_crop_eligibility.py` 23
  passed; PostgreSQL eligibility test (now with a pinned anchor in another game)
  passed.
- `ruff check`/`ruff format --check` pass; mypy strict on the 11 changed source modules: no errors in them (only the 2 pre-existing `source_lattice_geometry.py` errors).

### Audit

Codex `gpt-6-astra` / `high`, round 1:
[TASK-1045_AUDIT_gpt-6-astra.md](../quality/TASK-1045_AUDIT_gpt-6-astra.md),
verdict REVISE (P0-1, P0-2, P2-1). One fix round, all closed:

- P0-1: `training_dataset._managed_source` accepts a missing original only when
  its attested crop siblings exist (path checks kept); the canonical loader then
  verifies the crop. Test: a v4 virtual cohort whose original was removed builds
  from the crop frame (`test_verified_training_dataset.py`, 12 passed).
- P0-2: `render_persisted_virtual_cell_rgb` checks the persisted
  `paddedSourceQuad` against the valid box before the warp. Tests: persisted
  renders inside a crop equal the originals, a cell outside is refused, and a
  crop whose fill equals the lost (black) pixels is refused before the checksum
  could match.
- Also added: decode-and-render tests for EXIF orientations 1 and 6 (a decoded
  block-aligned crop renders the same 15 cells and render specs as its original).
- P2-1: plan R4 no longer lists grid shadow among crop consumers.

After fixes: `test_source_crop_frame.py` 14 passed, `test_verified_training_dataset.py`
12 passed; ruff pass. No second audit round (fixes stay inside the findings).

### Not completed

- API decoders, serving and API gates follow in TASK-1046.

### Documentation updates

Plan revision 2, D-562 addendum, code map.

### Recommended next task

TASK-1046.
