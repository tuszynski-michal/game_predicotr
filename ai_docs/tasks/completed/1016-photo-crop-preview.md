---
title: TASK-1016 — P1 photo crop preview gallery
status: done
last_updated: 2026-10-14
---

# TASK-1016 — P1 photo crop preview gallery

## Status

`done` — artifact prepared; operator visual acceptance pending.

## Goal

Prepare a local HTML gallery of 30–50 existing photographs across games,
showing a crop around all approved grids and measured file-size differences.

## Dependencies / entry conditions

The operator explicitly started P1 of the preliminary plan in the chat.
Only copies and a read-only metadata snapshot are authorized. The existing
originals, database rows and running services must not be changed.

## Recommended execution

`gpt-6-luna`, reasoning `medium`, as assigned to P1 in the chat plan.
The lead coordinates read-only source selection and independent verification.
Escalate geometry/coordinate ambiguity to the lead. P1 requires operator
visual acceptance; independent Claude implementation review is not assigned.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`, normalization and virtual rendering
- `ai_docs/architecture/DATA_MODEL.md`, source geometry and render manifests
- `ai_docs/quality/PHOTO_CROP_PREVIEW_20261014.md`

## Scope / out of scope

Read-only source selection; 50 px margin around all source grids and padded
cell support; copied before/after assets; local gallery and JSON/CSV metrics.
Exclude geometry correction and conflicting approval revisions. No production
code, API, database writes, migrations, original deletion, P2–P4 or plugins.

## Acceptance criteria

- [x] 40 photographs across two games and all 360 approved grids are shown.
- [x] Each source produces one crop containing every protected quad.
- [x] Actual byte counts and compression limitations are visible.
- [x] The gallery works locally with filtering, overlays and enlargement.
- [x] Source hashes, sizes and modification times remain unchanged.
- [x] Database access was enforced read-only by PostgreSQL.

## Outcome

### Changed

Prepared the self-contained gallery and optional ZIP in
`D:/game_predicotr/artifacts/photo-crop-preview-20261014/`; recorded the result
in `ai_docs/quality/PHOTO_CROP_PREVIEW_20261014.md`. No application code changed.
Temporary generation/verification tools and manifests remain with artifacts.

### Verification results

40 sources / 360 grids; 36 sources from 777 a1 and 4 from Mumie a1.
Originals: 10 992 053 B. Cropped JPEG: 7 845 699 B. Measured reduction:
3 146 354 B (28.6239%). Full JPEG control: 10 993 481 B. Exact-pixel WebP:
21 562 010 B. All source hashes, sizes, mtimes, copy hashes, quad containment,
WebP pixels and JPEG dimensions passed independent checks in a new process.
Chrome desktop/mobile checks passed, with 40 cards, working game filter and
enlargement, no JavaScript errors or horizontal mobile overflow.

Documentation link/window checks passed (42 active tasks, 10 done sections).
Final gallery checks also verified all 80 visible before/after images, overlay
toggles and fitted/100%/200% enlargement. Staged diff checks passed at closure.

### Overlay regression correction (2026-10-14)

Operator review revealed that the crop bbox right/bottom coordinates were
incorrectly used as SVG viewport width/height. The prior visual review missed
this issue. Fixed the actual HTML and generator to use right-left/bottom-top,
retaining the coordinate translation by left/top. Regression checks passed
for all 40 images and 45 016 cropped points, plus a nonzero-offset fixture.
Original and cropped image SHA-256 values are unchanged. Updated screenshots
and ZIP; no database or production geometry changes.

### Not completed

Operator visual acceptance, P2–P4 and integration merge. No space was reclaimed
from user data; the gallery adds copies. JPEG preview uses recompression and
does not establish production render compatibility. The sample is purposeful,
not a statistical estimate of the complete library. 777 a2 had no eligible
sources under the explicit geometry-approval criterion.

### Commit

Task documentation commit: **v1.7.361 / `063f259048080e94cffc79cce5eb0da335a69863`** on
`codex/photo-crop-p1`; integration merge awaits operator approval.

### Numbering correction

On 2026-10-14 the operator provided V3 fine-tuning plan revision 6, reserving
TASK-0993 through TASK-1015. Its TASK-1007 conflicts with the original P1
identifier. The current gallery record is TASK-1016; the previous identifier
TASK-1007 in v1.7.361/362 remains historical. No commit history is rewritten.
Numbering correction commit: **v1.7.363 / `c36087bcfa22f32d432d32fe6baa3a33237ad24e`**.
Future photo-storage tasks must avoid the reserved V3 range and recheck
availability before assigning any new identifier.

### Documentation updates

Added this task and the evidence report; updated CURRENT_STATE rolling window
and README. No source-of-truth product behavior or architecture changed.

### Recommended next task

Review the gallery. Decide whether to design P2 storage representation and
retention, after separate scope and cost authorization.
