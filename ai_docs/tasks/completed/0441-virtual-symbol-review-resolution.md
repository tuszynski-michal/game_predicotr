---
title: Virtual-source symbol review resolution
status: done
version: 0.10.150
---

# TASK-0441 — Virtual-source symbol review resolution

## Goal

Allow single and durable bulk symbol decisions to close a board after a manual
`virtual_source` geometry revision without interpreting that revision as legacy
file-backed crops.

## Scope

- Materialize an operational review item from the current virtual render spec.
- Use the virtual geometry checksum as the canonical board identity while the
  source JPEG remains the display asset.
- Convert operational review conflicts in a durable bulk board batch into
  recorded target conflicts instead of failing the whole job with pending
  counters.
- Show operation-level failure details and remaining pending targets in Admin.
- Add regression coverage for manual virtual geometry and bulk conflict
  accounting.
- Update the current-state and relevant architecture/requirements notes.

## Out of scope

- Retrying existing failed jobs or changing game data.
- Rebuilding geometry, crops, symbol projections, or training data.
- Changing geometry thresholds or the v0.10 renderer.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Definition of Done

- A final symbol decision on a board with a complete manual virtual geometry
  revision resolves atomically and preserves the exact 15 current render IDs.
- Legacy file-backed review remains unchanged.
- A board-level `ImageReviewConflictError` in a bulk operation is recorded for
  its targets and processing continues.
- Admin never summarizes an operation-level failure as `0/0/0` without the
  operation error and pending count.
- Focused tests, lint, typecheck, and build checks for the changed slices pass.
- Documentation and `CURRENT_STATE.md` describe the corrected contract.

## Outcome

- Operational review now materializes all 15 current `virtual_source` cells
  from the manual revision's `virtual_render_spec`; the managed original is
  exposed only as the bounded display context.
- Canonical resolution uses the current virtual geometry checksum as board
  identity and keeps the legacy bitmap checksum path unchanged.
- Durable bulk processing records `ImageReviewConflictError` per board target
  and continues instead of failing the job with pending targets and zero
  counters. Admin includes pending count and the operation-level error in its
  terminal toast.
- Read-only verification against game `siedem`, sequence `19819`, returned
  geometry revision 1 and 15 `virtual_source` cells. No game data or failed job
  was changed or retried.

### Verification

- `4 passed` — `test_image_symbol_review_virtual_source.py`.
- `40 passed` — focused virtual symbol review, symbol API and operational
  review tests.
- `1 passed` — isolated PostgreSQL bulk resume/conflict integration test.
- `393 passed` — complete Admin test suite.
- API/worker Ruff check passed.
- Admin lint, typecheck and production build passed.
- Prettier check for changed UI/docs and OpenAPI/generated-client check passed.
- Full Python mypy completed with 35 pre-existing errors in unrelated OCR,
  schema, virtual-renderer and reinference modules before the task-local
  redundant-cast cleanup; a focused rerun reported only pre-existing imported
  module errors and none in the changed repository files.
