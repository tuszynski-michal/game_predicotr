---
title: TASK-0429 Auto-detect selected image crop
status: done
last_updated: 2026-09-04
---

# TASK-0429 — Auto-detect selected image crop

## Problem

The first crop workspace release initialized fixed 18–86% bounds and inherited
the previous accepted band. It did not inspect the current image, so it behaved
as a manual cropper despite being placed in Semi-auto selection.

## Scope

- add a deterministic, lightweight board-region band detector,
- analyze a bounded EXIF-canonical preview and map the proposal to original
  pixels without scaling the saved JPEG,
- calculate a proposal independently for every unaccepted source,
- show detector state/confidence and let the operator accept or adjust it,
- make reset restore the current automatic proposal.

## Out of scope

- board geometry, OCR, symbol recognition and server jobs,
- global rotation, homography or perspective correction,
- automatic acceptance without an operator decision.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/tasks/completed/0425-local-selected-image-crop-domain.md`
- `ai_docs/tasks/completed/0426-safe-selected-image-crop-renderer.md`
- `ai_docs/tasks/completed/0427-selected-image-crop-review-workspace.md`

## Definition of Done

- every unaccepted photo is analyzed independently,
- detection uses bounded preview pixels while output remains source-resolution,
- blue-panel and texture fallback paths are deterministic and tested,
- low-confidence detection remains visibly editable and fail-safe,
- accepted crop coordinates remain stable on revisit/reload,
- focused tests, lint, typecheck and Admin build pass.

## Outcome

- Added a pure, versioned chromatic/texture band detector over a bounded RGBA
  preview with an explicit safe-default result.
- Every unaccepted photo receives an independent proposal; accepted manifest
  coordinates remain authoritative, and reset restores the current proposal.
- Browser integration canonicalizes EXIF through `createImageBitmap`, analyzes
  at most 256 px width, and keeps source-resolution rendering unchanged.
- The supplied real image produced a `414–1068` band for canonical
  `1080×1920` pixels with `0.965` confidence.
- Core tests, focused Admin contracts, both typechecks and Admin lint passed.
