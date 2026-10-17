---
title: TASK-1045 — Crop-aware source frame in the worker
status: todo
last_updated: 2026-10-17
---

# TASK-1045 — Crop-aware source frame in the worker

## Status

`todo`

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

- [ ] Original present: render specs and cell checksums unchanged (regression test).
- [ ] Crop fixture (orientation 1 and 6): identical cell pixels inside the valid box.
- [ ] Quad outside the valid box → `SOURCE_REGION_UNAVAILABLE`.
- [ ] Tampered crop or attestation → stable error, never a silent canvas.
- [ ] `rg` of direct `data/originals` reads in the worker shows only covered call sites.
- [ ] Lint, mypy, worker tests of changed modules pass.

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

Wypełnia agent po pracy.
