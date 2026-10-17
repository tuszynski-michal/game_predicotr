---
title: TASK-1046 — Crop-aware source frame in the API, serving and gates
status: done
last_updated: 2026-10-17
---

# TASK-1046 — Crop-aware source frame in the API, serving and gates

## Status

`done`

## Goal

The API serves a full-frame image for cropped sources (plan R3), decodes them
through the crop-aware loader, and blocks operations listed in plan R4.

## Context

Stage A of the accepted
[photo crop plan](../delivery/PHOTO_CROP_STORAGE_EXECUTION_PLAN_20261017.md).
Frontends must keep working unchanged.

## Dependencies / entry conditions

TASK-1043, TASK-1045.

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Audit: Codex `gpt-6-astra` / `medium`.

## Relevant docs

- Plan sections 1, R3, R4; D-562
- `ai_docs/architecture/API_CONTRACT.md` (source asset endpoints, reprocess)

## Scope

- `application/image_review_assets.py` `_resolve` and the source endpoints
  (full-frame JPEG cache under `data/working/source-frame-previews/`).
- API decoders (`virtual_cell_previews.py`, `virtual_grid_geometry.py`,
  `geometry_correction_reverts.py`, `grid_training_cohort_artifacts.py`,
  `v7_label_geometry_calibration.py`, `review_assets.py`,
  `image_import_geometry_guard_preview.py`) through the crop-aware loader or an explicit error.
- Gates: reprocess `SOURCE_ORIGINAL_CROPPED`; geometry correction, revert and
  proposals `SOURCE_REGION_UNAVAILABLE` outside the valid box.
- OpenAPI, regenerated client and request tests for changed error responses.

## Out of scope

Crop jobs and Storage UI (stage B).

## Acceptance criteria

- [x] Without crops all responses are byte-identical to before.
- [x] Cropped source: served image has the original oriented size; ETag unchanged (deviation from plan R3, see Outcome).
- [x] Reprocess and out-of-box corrections are rejected with stable codes.
- [x] Lint, mypy, API tests of changed modules, `openapi:check` pass.

## Technical notes

Plan R3/R4. No new endpoint; existing routes change behavior only for crops.

## Expected files

Confirmed at task start.

## Test cases

See acceptance criteria.

## Verification

```powershell
D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests -k "review_asset or reprocess or geometry_correction"
```

## Risks / open questions

- Browser caches marked `immutable` keep the old full original: harmless by design.

## Outcome

Commit: v1.7.407 (hash dopisuje kolejny commit).

### Changed

- `application/image_review_assets.py`: for the four source asset kinds a
  missing original with an attested crop is served as a full-frame JPEG
  (crop on the fill canvas, original oriented size, no EXIF, quality 92) from
  the regenerable working file
  `data/working/source-frame-previews/<attestation_sha256>.jpg` (atomic write; an unusable crop gives `404 IMAGE_REVIEW_ASSET_NOT_FOUND` with
  the reason). New `resolve_managed_source_path` / `resolve_grid_review_source_path`
  return the managed original path for canonical loaders (never the preview).
- Crop opt-in (`allow_crop=True`) and managed paths: `virtual_grid_geometry.py`
  (correction render and proposal preview), `geometry_correction_reverts.py`
  (restored cells; `SOURCE_REGION_UNAVAILABLE` mapped to its own 409 code),
  `virtual_cell_previews.py` (atlas and reference renders;
  `_managed_virtual_source_path` accepts a cropped original;
  `render_spec_cell_rgb` checks the padded quad against the valid box before
  the warp).
- Refusals `SOURCE_ORIGINAL_CROPPED`: V3 cohort source copy
  (`grid_training_cohort_artifacts.decode_source`), managed reprocess
  (`require_full_managed_originals` in `create_managed_image_reprocess_job`),
  managed page source and managed browser selection
  (`managed_reprocess_evidence.py`).
- `API_CONTRACT.md`: crop behavior of the source endpoints, reprocess, cohorts
  and geometry commands.

### Deviations from the plan

- R3 said ETag = crop checksum. Endpoints keep their ETag behavior: the
  pending endpoint sets `source_checksum_sha256` explicitly, the others leave
  Starlette's file-derived ETag, which differs for the preview. A cached full
  original keeps the same coordinates, so it stays correct, and no endpoint or
  frontend change is needed (`API_CONTRACT.md` states this exactly).
- Frontends are unchanged; the Reviewer gets one interaction test for the new
  refusal, and Admin has no grid-review geometry editor (its page geometry
  panel works on import staging, whose managed reprepare refuses cropped
  originals).
- `v7_label_geometry_calibration.py` and `review_assets.py` do not read managed
  originals (V7 lab sessions and legacy source folders); the geometry guard
  preview reads staging or the managed browser selection, which now refuses
  cropped originals.
- No OpenAPI change: error codes travel in the existing error envelope.

### Verification results

- `services/api/tests/test_source_crop_api.py`: 9 passed (present original served
  unchanged; cropped source served as a full-frame preview of the original size,
  stable path, fill outside; loader path stays the managed original; tampered
  attestation not served; missing without crop not found; stored render spec
  refused outside the crop; V3 cohort refuses; reprocess gate, managed page
  source and browser selection refuse; gate accepts present originals).
- `scripts/export_admin_openapi.py --check`: OpenAPI artifact is current.
- API regression of the changed modules (25 test files: review assets, image
  reviews and grid reviews, virtual cell previews, virtual grid geometry,
  geometry correction reverts, grid training cohorts, managed reprocess
  evidence, neural page geometry API, lateral reprocess, pending board-cell
  geometry, jobs and image imports APIs, symbol cell review, geometry
  completeness, source crop): 621 passed (441 s).
- `ruff check`/`ruff format --check` pass; mypy strict on the 7 changed source
  modules: no errors in them (only the 2 pre-existing `source_lattice_geometry.py`
  errors); the test module only reports its pytest-local fixture import, as the
  other API tests do.

### Audit

Codex `gpt-6-astra` / `medium`, round 1:
[TASK-1046_AUDIT_gpt-6-astra.md](../quality/TASK-1046_AUDIT_gpt-6-astra.md),
verdict REVISE (P0-1, P0-2, P1-1..3). One fix round, all closed:

- P0-1: the preview file is named by the attestation checksum (original,
  geometry and crop), not by the crop bytes; test with equal crop bytes and
  different attestations.
- P0-2: `SOURCE_REGION_UNAVAILABLE` and `SOURCE_ORIGINAL_CROPPED` are 409 in the
  `ImageGridReviewError` handler (`main.py`); test through `create_app`.
- P1-1: HTTP tests: the grid-review source endpoint serves the original
  (bytes) or the cropped original (full frame size, same `Content-Type` and
  `Cache-Control`); `POST /image-imports/{id}/reprocess` through `create_app`
  returns `409 SOURCE_ORIGINAL_CROPPED` and creates no job.
- P1-2: Reviewer interaction test (`operational-review-geometry-editor.test.mjs`):
  the editor loads a source of the original natural size, shows the
  `SOURCE_REGION_UNAVAILABLE` refusal and saves nothing (3/3 passed with `tsx`;
  `node_modules` linked into the worktree by junctions to the main checkout).
- P1-3: `API_CONTRACT.md` and this Outcome now describe ETag as implemented.

After fixes: `test_source_crop_api.py` 15 passed; Reviewer interaction file 3
passed; prettier applied to the test. No second audit round.
