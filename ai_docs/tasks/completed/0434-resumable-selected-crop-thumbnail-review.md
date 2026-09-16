---
title: TASK-0434 Resumable selected crop thumbnail review
status: done
last_updated: 2026-09-04
---

# TASK-0434 — Resumable selected crop thumbnail review

## Problem

Preparing a large `cut` directory rewrites one multi-megabyte manifest twice per
JPEG and stops on the first file error. Review is hidden until every output is
ready, so 2815 valid results cannot be inspected when the final two files fail.

## Scope

- migrate v1 sessions to bounded inventory, session, review and 64-result shards,
- isolate preparation failures per file and retry only failed or missing files,
- move automatic detection and rendering to a recyclable browser worker,
- expose prepared results immediately as one progressive atlas-backed grid,
- persist correction selection and review only selected originals,
- retain checksum-bound overwrite and crash recovery semantics.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`

## Definition of Done

- a 2815/2817 v1 session opens the 2815 existing results without rerendering,
- one file failure does not stop remaining preparation,
- at most 100 thumbnails share one deterministic WebP atlas,
- selections survive reload and only selected files enter correction mode,
- the full Admin test, lint, typecheck and build checks pass.

## Outcome

- Added an idempotent v1-to-v2 session migration with immutable inventory,
  compact session/review files and result shards of at most 64 source slots.
- Preparation now records exact per-file failures, continues after them and can
  retry only failed names. Detection and initial render use a recyclable Web
  Worker with a capability-based main-thread fallback.
- Prepared outputs appear in one progressive grid backed by deterministic WebP
  atlases of at most 100 thumbnails. Selection is durable and the full viewer is
  opened only for the selected correction queue.
- Existing results and review decisions are indexed without image decoding or
  checksum recalculation; foreign and changed outputs remain fail-closed.
- Verification passed: core tests `36/36`, Admin tests `385/385`, core and
  Admin typechecks, Admin ESLint, scoped Prettier check and production Admin
  build. The repository-wide Prettier check still reports four unrelated,
  pre-existing files outside this task.
- No user JPEG or live session was modified during implementation. The bounded
  v1-to-v2 migration runs only after the operator opens the local workspace.
