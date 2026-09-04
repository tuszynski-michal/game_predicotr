---
title: TASK-0427 Selected image crop review workspace
status: done
last_updated: 2026-09-04
---

# TASK-0427 — Selected image crop review workspace

## Scope

- add the `Przytnij wybrane zdjęcia` card below Semi-auto selection,
- reuse the bounded manual image viewer, zoom, fullscreen and scroll memory,
- expose two draggable horizontal crop lines and a shaded crop preview,
- support `F`/right to save, left to navigate and explicit overwrite,
- show durable progress and completion output guidance.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/tasks/completed/0425-local-selected-image-crop-domain.md`
- `ai_docs/tasks/completed/0426-safe-selected-image-crop-renderer.md`

## Definition of Done

- setup, loading, empty, error, review and done states are explicit,
- saving and navigation cannot race,
- accepted coordinates reappear when revisiting a photo,
- changing an accepted file requires an explicit re-save,
- the viewer remains backward compatible for existing consumers,
- focused UI tests, lint and typecheck pass.

## Outcome

- Mounted `Przytnij wybrane zdjęcia` below the existing Semi-auto workspace.
- Extended `ManualImageViewer` with backward-compatible optional overlay and
  lightweight viewport-change reporting while retaining its bounded URL cache.
- Added two draggable horizontal lines, shaded excluded regions, progress,
  reset, fullscreen/zoom and durable cursor/viewport restoration.
- Added serialized save/navigation semantics: `F` and right save/advance, left
  only navigates, and edits to accepted files require `Zapisz ponownie`.
- Verification: seven focused Admin contract tests, Admin typecheck and lint
  passed.
