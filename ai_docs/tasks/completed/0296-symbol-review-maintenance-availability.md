---
title: Symbol review maintenance availability and loaded-result counter
status: done
last_updated: 2026-08-27
---

# TASK-0296 — Symbol review maintenance availability and loaded-result counter

## Goal

Keep an already complete symbol-cell review projection available for reads and
mutations while an explicitly requested reconciliation job is processing, and
show the operator how many results of the selected symbol are currently loaded
in the bounded Admin buffer.

## Scope

- Mark reconciliation jobs started from a `ready` projection as maintenance
  jobs that preserve availability.
- Allow the symbol review query and mutation boundary to accept `rebuilding`
  only while such a marked job remains active.
- Keep an initial or failed/inactive incomplete backfill fail-closed.
- Show `loaded / total` for the current symbol and state filter without keeping
  more than three pages (180 crop records) in browser memory.
- Document why browser staging and geometry preflight do not increase the board
  projection until the image import/cropping pipeline is started.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Out of scope

- Starting, retrying or deleting import and geometry jobs.
- Changing the image import, cropper or symbol inference algorithms.
- Increasing the three-page Admin memory bound.

## Acceptance

- Reassigning an existing cell remains possible while a ready projection is
  undergoing a marked maintenance reconciliation.
- An initial/incomplete rebuild still returns
  `SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE`.
- The workspace shows unique buffered crop count divided by the total count for
  the current filter.
- Existing bounded paging, bulk operation and checksum invariants remain true.

## Outcome

- Maintenance reconciliation jobs started from `ready` carry a durable
  availability marker. Reads, previews and mutations use one shared check and
  remain available only while that marked job is active.
- Initial and otherwise incomplete rebuilds remain fail-closed.
- Admin shows the unique number of crop records in its bounded three-page
  buffer divided by the total result count of the current symbol/state filter.
- Verified with focused API storage tests, Admin state/contract tests, Ruff,
  Admin lint/typecheck and Prettier. No benchmark was run.
