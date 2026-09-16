---
title: TASK-0428 Finalize selected image cropping
status: done
last_updated: 2026-09-04
---

# TASK-0428 — Finalize selected image cropping

## Scope

- verify that a `cut` folder is accepted by the existing board import,
- document operational boundaries and the required new-import workflow,
- update requirements, architecture, current state and decision log,
- run focused and repository quality gates without a large benchmark.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Definition of Done

- helper JSON is ignored and all `seq_*` JPEG ranges reach import unchanged,
- docs distinguish new imports from reprocessing managed originals,
- no API, database or worker change is introduced,
- focused tests, format, lint, typecheck and Admin build pass,
- any operational A/B measurement not safely runnable is reported explicitly.

## Outcome

- Board import now uses a named JPEG-only filter; a focused test proves that
  `seq_*.jpg|jpeg` pass unchanged while `manual-image-crop-output-v1.json` is
  ignored.
- Requirements, architecture, current state and Decision D-321 document the
  local-only workflow, new-import boundary and continued use of immutable
  managed originals for historical reprocessing.
- Verification passed: manual-selection core 27/27, Admin 380/380, focused
  integration 16/16, Admin lint, both typechecks and production Admin build.
- The repository-wide format check still reports five pre-existing files
  outside this task's new code (`next-env.d.ts`, cleanup control, repair
  workspace, symbol review workspace and its style contract); all newly added
  files and the new CSS block are formatted.
- No operational A/B import was run: it requires an operator-selected writable
  directory and would create a new staging. The UI is ready for a bounded real
  comparison without a synthetic benchmark.
