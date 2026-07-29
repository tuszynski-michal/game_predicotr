---
title: TASK-0066 — Review corrections and labeled feedback export
status: done
last_updated: 2026-07-29
---

# TASK-0066 — Review corrections and labeled feedback export

## Goal

Complete the manual-review write path: atomically approve, correct or reject a
whole 5 × 3 review item, retain every decision as immutable audit evidence and
materialize immutable, versioned labeled-feedback exports without changing a
model online.

## Dependency

TASK-0064 provides immutable review batches/items and TASK-0065 provides the
read-only workspace and safe local image delivery.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- D-074 and D-075 in `ai_docs/process/DECISION_LOG.md`

## Accepted implementation assumptions

- A resolution applies to the complete board, never to a partially persisted
  subset of cells.
- `accepted` and `corrected` persist exactly 15 row-major labels bound to the
  immutable cell `sampleId`; corrected symbols must be active in the batch game.
- Label persistence requires explicit confirmation that the displayed geometry
  is accepted. `rejected` persists no training labels and is excluded from
  feedback.
- Every command carries an idempotency key and expected item revision. An exact
  retry returns the existing result; key reuse with another payload or a stale
  revision fails closed.
- Changing a resolution appends a new immutable audit event and updates only the
  current projection on `review_items`.
- A feedback export freezes the current resolved state under a monotonically
  increasing game-local version and checksum. A later decision creates a new
  export version; it never mutates the previous payload.
- Export payloads contain metadata and local crop references/checksums, not image
  binaries. Retraining remains an explicit later batch operation.

## Scope

- add Alembic persistence for resolution revisions, audit events and feedback
  exports,
- add framework-independent validation for resolution commands and canonical
  feedback payloads,
- add atomic/idempotent repository operations and optimistic revision checks,
- expose resolve/history and create/list/get feedback-export Admin endpoints,
- regenerate OpenAPI and the typed TypeScript client,
- add approve/correct/reject controls, a 15-cell correction editor, audit history
  and feedback export controls to the review workspace,
- keep geometry correction itself out of this task; accepted geometry is an
  explicit prerequisite to saving labels,
- add domain, API, repository, client and UI tests.

## Acceptance criteria

- [x] Accept/correct persists exactly 15 labels only after geometry confirmation.
- [x] A corrected symbol must be active in the review batch game.
- [x] Reject persists no labels and contributes no feedback sample.
- [x] An exact command retry cannot create a second audit event.
- [x] A stale revision or changed payload under one idempotency key fails closed.
- [x] Every changed decision remains visible in immutable chronological history.
- [x] Feedback export is blocked while any item is pending.
- [x] Feedback export excludes rejected items and contains 15 samples per accepted
      or corrected item.
- [x] Re-export of unchanged state is idempotent; changed state creates a new
      immutable version.
- [x] UI exposes explicit busy, success and controlled error states.
- [x] Focused tests, lint, typecheck, build and OpenAPI/client drift pass.

## Out of scope

- interactive geometry-corner editing,
- model training or online learning,
- activation or rollback of a model,
- bulk image ingestion,
- storing image binaries in PostgreSQL.

## Outcome

Completed 2026-07-29.

- Alembic `0015` adds item resolution revisions, append-only audit events and
  immutable game-local feedback versions with state/payload checksums.
- Domain/API/repository enforce full-board decisions, accepted geometry, active
  symbols, idempotency and optimistic concurrency.
- Generated Admin client and UI expose the 15-cell correction editor,
  approve/correct/reject, chronological history and feedback export history.
- Feedback remains blocked by pending items, excludes rejected boards and never
  mutates an older export or trains a model online.
- Verification passed: 50 focused backend tests with one explicit PostgreSQL
  skip, 74 Admin tests, Ruff, domain/application mypy, Admin/client TypeScript,
  changed-file ESLint, OpenAPI/client drift and the production Next.js build.
- Browser smoke passed at desktop and 390 px with controlled error/retry, no
  console errors and no horizontal overflow. Ready-state mutation remains
  covered by tests until the local PostgreSQL integration environment is run.
- A broad Python mypy graph reached the 60-second guard; the bounded strict
  domain/application run completed successfully instead.
