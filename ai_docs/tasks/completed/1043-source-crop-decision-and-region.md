---
title: TASK-1043 — Decision D-562, documentation and pure crop functions
status: done
last_updated: 2026-10-17
---

# TASK-1043 — Decision D-562, documentation and pure crop functions

## Status

`done`

## Goal

D-562 and the requirements describe the verified cropped variant of a managed
original, and pure functions for the crop region, verification rule and crop
attestation exist with tests for the plan examples.

## Context

Stage A of the accepted
[photo crop plan](../delivery/PHOTO_CROP_STORAGE_EXECUTION_PLAN_20261017.md)
(R1, R2 revision 1, R6, R7). The requirement that a managed original stays the
immutable decode source changes by operator decision of 2026-10-17.

## Dependencies / entry conditions

Plan accepted; stage A ordered with audits. No DB or file changes.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (plan table). Escalate if the orientation
mapping or the verification rule cannot express the measured P1 result.
Audit: Codex `gpt-6-astra` / `high`.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/PHOTO_CROP_STORAGE_EXECUTION_PLAN_20261017.md`, sections 2–4
- `ai_docs/requirements/IMAGE_INGESTION.md`, sections „Discovery” (originals) and 2 „Normalizacja”
- `ai_docs/architecture/DATA_MODEL.md`, `ai_docs/architecture/SYSTEM_ARCHITECTURE.md` (managed original identity)

## Scope

- D-562 full entry and index row.
- Requirements and architecture text for the cropped variant (no behavior yet).
- New pure module `services/api/src/game_predictor_api/domain/source_crop.py`:
  protected bbox, margin, orientation mapping (1, 3, 6, 8), iMCU alignment,
  `not_beneficial` rule, verification mask rule, attestation canonical JSON
  build/parse/validate and deterministic crop/attestation relative paths.

## Out of scope

Database, loaders, jobs, API, UI, running `jpegtran`.

## Acceptance criteria

- [ ] P1 example `[43,0,775,478]`, 1080×589, 4:2:0 → oriented crop `[32,0,784,480]`.
- [ ] Orientation 6 and 3 with nonzero offsets round-trip; 2/4/5/7 → `SOURCE_CROP_ORIENTATION_UNSUPPORTED`.
- [ ] The crop always contains bbox + margin or reaches the image border.
- [ ] Verification rule accepts mismatches only on the 1 px ring of non-border crop edges with protected quads ≥ 8 px away.
- [ ] Attestation round-trips; a changed field or checksum is rejected.
- [ ] `ruff`, `mypy --strict`, focused pytest, `docs:check` pass.

## Technical notes

Region and verification rules: plan R6 and R7. Coordinates are
`exif-normalized-rgb-pixels-v1`; boxes are half-open `[left, top, right, bottom)`.
Attestation fields: plan R2 revision 1.

## Expected files

- New: `services/api/src/game_predictor_api/domain/source_crop.py`, `services/api/tests/test_source_crop.py`.
- Existing: `ai_docs/process/DECISION_LOG.md`, `ai_docs/process/decisions/DECISION_LOG_2026.md`,
  `ai_docs/requirements/IMAGE_INGESTION.md`, `ai_docs/architecture/DATA_MODEL.md`,
  `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`, code map.

## Test cases

Plan R6 examples; orientation round trips; clamp at borders; alignment for 8×8,
16×8, 16×16; verification masks (ring only, inner mismatch, quad too close);
attestation tamper cases.

## Verification

```powershell
# from the worktree root, timeout 120 s each
D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/test_source_crop.py
D:\game_predicotr\.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/domain/source_crop.py services/api/tests/test_source_crop.py
D:\game_predicotr\.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api/domain/source_crop.py
```

## Risks / open questions

- Sequence-label regions per source are resolved in TASK-1044.

## Outcome

Commit: v1.7.404 / `415b093d79b7fb2fb71949b73509d1d29b1fc965`.

### Changed

- New pure module `services/api/src/game_predictor_api/domain/source_crop.py`:
  `PixelBox`/`ProtectedBox`, `protected_box_from_points`, `clamp_protected_box`
  (padded quads may reach past the image border), `margin_box`, orientation
  mapping (`oriented_to_raw_box`, `raw_to_oriented_box`, `raw_dimensions`;
  EXIF 1/3/6/8, mirrored ones rejected), `imcu_size`, `align_raw_box`,
  `plan_source_crop`, `is_crop_beneficial` (≥ 5%), `verify_crop_pixels`
  (plan R7), `compose_canvas` (fill 0), `SourceCropAttestation` with
  `encode_attestation`/`decode_attestation` (closed schema, self checksum
  `attestationSha256`, consistency of raw/oriented boxes, iMCU alignment,
  protected box inside the crop) and deterministic sibling paths
  (`cropped_original_relative_paths`, `cropped_sibling_paths`).
- D-562 (full entry and index row; D-533 row moved to the index archive),
  `IMAGE_INGESTION.md` section 2, `SYSTEM_ARCHITECTURE.md` (normalization),
  `DATA_MODEL.md` (`source_images` note), code map regenerated.

### Verification results

- `pytest services/api/tests/test_source_crop.py`: 29 passed (P1 example
  `[43,0,775,478]` → `[32,0,784,480]`; mapping equals `ImageOps.exif_transpose`
  for orientations 1/3/6/8 on random arrays; iMCU 8×8 and 16×8; ring-only
  mismatches; image borders exact; protected quads near the ring; attestation
  round trip and tamper cases; sibling paths).
- `ruff check` and `ruff format --check` on both files: pass.
- `mypy` (strict) on `source_crop.py` and its test: no errors in these files.
  The run reports 2 errors in `schemas/source_lattice_geometry.py:36,38`,
  identical on `main` v1.7.400 when checked the same way; pre-existing, outside scope.
- `docs:check` scripts: decision links, window, startup budget, skill mirrors OK.

### Audit

Codex `gpt-6-astra` / `high`, round 1:
[TASK-1043_AUDIT_gpt-6-astra.md](../quality/TASK-1043_AUDIT_gpt-6-astra.md),
verdict REVISE (P0-1..3, P1-1..2). One fix round, all closed:

- P0-1: the attestation now requires every stored edge on the iMCU grid unless
  it is the image border, a protected box clamped to the original, and a crop
  containing `margin_box(protected, margin_px)`; tests for unaligned
  right/bottom, border edges and an insufficient margin.
- P0-2: `ProtectedBox` normalizes coordinates to `float`; byte-identical round
  trip for integer coordinates is tested.
- P0-3: iMCU, margin and counters are type- and range-checked before any
  arithmetic; a resealed document with a zero iMCU fails with
  `SOURCE_CROP_ATTESTATION_INVALID`.
- P1-1: protected quads near the ring now fail with
  `SOURCE_CROP_VERIFICATION_FAILED` (plan R7), the reason stays in the message.
- P1-2: `imcu_from_sampling_factors` and a progressive JPEG test (Pillow,
  4:2:0, in memory) planning `[32,0,784,480]`.

After fixes: `pytest services/api/tests/test_source_crop.py` 36 passed;
`ruff check`/`ruff format --check` pass. No second audit round (not requested;
fixes stay inside the reported findings).

### Not completed

- Nothing in scope. Loaders, DB and jobs follow in TASK-1044–1046.

### Documentation updates

D-562, requirements, architecture, data model, code map.

### Recommended next task

TASK-1044.
