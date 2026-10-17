---
title: TASK-1046 — Crop-aware source frame in the API, serving and gates
status: todo
last_updated: 2026-10-17
---

# TASK-1046 — Crop-aware source frame in the API, serving and gates

## Status

`todo`

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

- [ ] Without crops all responses are byte-identical to before.
- [ ] Cropped source: served image has the original oriented size; ETag is the crop checksum.
- [ ] Reprocess and out-of-box corrections are rejected with stable codes.
- [ ] Lint, mypy, API tests of changed modules, `openapi:check` pass.

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

Wypełnia agent po pracy.
