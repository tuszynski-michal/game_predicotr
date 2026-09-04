---
title: TASK-0426 Safe selected image crop renderer
status: done
last_updated: 2026-09-04
---

# TASK-0426 — Safe selected image crop renderer

## Scope

- select a writable parent and a top-level `seq_*` source child,
- create or safely resume the sibling `<source> cut` directory,
- canonicalize EXIF once and render a full-width JPEG crop at 1:1 resolution,
- journal source/output checksums around every file mutation,
- recover an interrupted write without overwriting foreign data.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/tasks/completed/0425-local-selected-image-crop-domain.md`

## Definition of Done

- only owned empty or manifest-bound output directories are writable,
- rendering preserves canonical source width and selected band height,
- source files are never changed,
- retries and interrupted writes are deterministic and fail closed,
- focused storage/renderer tests and Admin typecheck pass.

## Outcome

- Added parent/child directory discovery and strict top-level `seq_*` scanning.
- Added safe creation/resume of `<source> cut`; non-empty foreign outputs and
  source inventory changes are rejected.
- Added EXIF-aware browser rendering of a full-width 1:1 band at JPEG quality
  0.98, with no rotation, perspective transform or downscaling.
- Added journal-before-write, source/output SHA-256 verification and restart
  recovery for missing, matching and conflicting results.
- Verification: focused core and Admin contract tests plus both package
  typechecks passed.
