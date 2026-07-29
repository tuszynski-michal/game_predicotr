---
title: TASK-0065 — Manual review administration UI
status: done
last_updated: 2026-07-29
---

# TASK-0065 — Manual review administration UI

## Goal

Build the local, read-only manual-review workspace on top of TASK-0064. The
administrator can select an immutable batch, navigate its deterministic queue
and inspect the original source, whole 5 × 3 board, cells, predictions,
confidence and alternatives without creating a review decision.

## Dependency

TASK-0064 provides immutable/idempotent batch persistence, item list/detail
and the generated Admin client. TASK-0066 will add approve/correct/reject,
audit and feedback export.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- D-073 and D-074 in `ai_docs/process/DECISION_LOG.md`

## Scope

- add a navigation entry and a dedicated manual-review workspace,
- expose narrowly scoped read-only image responses for one stored review item:
  source image, canonical board and one of its 15 crops,
- resolve all files below configured local roots and fail closed on missing,
  ambiguous, unsafe or checksum-mismatched source assets,
- list immutable batches and show loading, empty, error and retry states,
- load a bounded first page of items in deterministic selection-rank order,
- filter items by explicit status and navigate the visible queue,
- render the whole 5 × 3 board, selected crop and 15-cell prediction grid,
- show source/sequence/model provenance, confidence and alternatives as text,
- keep all review actions disabled and explicitly assigned to TASK-0066,
- add state/action/API/UI contract tests.

## Acceptance criteria

- [x] The browser never receives or supplies an arbitrary filesystem path.
- [x] Source image checksum is verified before it is served.
- [x] Batch and item loading have explicit loading, empty and error states.
- [x] Items remain ordered by `selectionRank`; current position is textual.
- [x] The 15 cells are rendered in row-major order with row/column labels.
- [x] Selecting a cell changes its crop and visible prediction details.
- [x] Confidence and alternatives are visible as text, not only color.
- [x] Missing assets have a controlled placeholder without hiding item data.
- [x] No UI action resolves, corrects, rejects or mutates a review item.
- [x] Responsive layout and keyboard-accessible controls are covered.
- [x] Focused tests, lint, typecheck, build and OpenAPI/client drift pass.

## Out of scope

- approve/correct/reject transitions,
- geometry correction,
- audit events,
- feedback dataset export,
- retraining or online model changes,
- bulk image processing.

## Expected files

- review asset resolver and API route/tests,
- generated OpenAPI/Admin client,
- `apps/admin/src/features/reviews/*`,
- navigation/workspace integration and CSS,
- Admin UI tests,
- architecture/process documentation.

## Verification

All commands use bounded timeouts. UI logic is tested independently from React,
API transport behavior is tested with generated-client-compatible fixtures and
the production build validates the composed workspace.

## Outcome

Completed 2026-07-29.

- Added source/board/cell image resolvers and item-scoped FastAPI endpoints.
  Source discovery verifies SHA-256; all paths remain below configured local
  roots and no endpoint accepts a filesystem path.
- Added the generated-client review operations and a read-only Admin workspace
  with batch/status selection, deterministic queue navigation, whole-board
  context, 15 row-major cells, selected crop and textual model evidence.
- Added controlled loading, empty, error/retry and missing-image states. No
  resolution mutation is present before TASK-0066.
- Verification passed: 30 focused API tests, all 72 Admin tests, Ruff, strict
  mypy, ESLint for changed UI, Admin/client typechecks, OpenAPI/client drift,
  and the Next.js production build.
- Browser smoke passed at desktop and 390 px with no console errors or
  horizontal overflow. The real TASK-0063 item resolved its source, board and
  first crop from the accepted local corpus.
- The broad Admin ESLint invocation reached the 60-second guard once; the
  changed-file ESLint run then completed successfully.
