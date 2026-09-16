---
title: TASK-0473 — Restore virtual previews in unreadable board review
status: done
---

## Relevant docs

- ../../requirements/ADMIN_APP.md — Weryfikacja symbolu na planszy
- ../../architecture/API_CONTRACT.md — unreadable-board-reviews
- ../../process/DEFINITION_OF_DONE.md

## Scope and dependencies

Repair the existing detail-to-asset contract: propagate the current render-spec
checksum from the persisted cell through OpenAPI, generated client, wrapper and UI.
Keep checksum validation and legacy file previews unchanged. No migration, data
mutation, worker restart or new endpoint. Independent of the missing deferred
geometry-slot bug reported for source 3565–3573 (investigation remains open).

## Tests and DoD

- Detail serializes the current render-spec checksum, or null for legacy cells.
- Virtual thumbnail URL pins both checksums; legacy URL remains unchanged.
- Existing asset endpoint still rejects missing/stale render-spec checksums.
- Focused tests, formatting, lint, typecheck, generated contract and Admin build.

## Outcome

Implemented end-to-end. Root cause: the detail omitted render-spec identity
although the virtual asset endpoint requires it; UI supplied only crop checksum.

Verification: 2 focused API tests and 4 domain tests passed; 2 client request
tests and 2 Admin contract tests passed. Ruff check/format, scoped mypy
(`--follow-imports=silent`), Admin typecheck, scoped ESLint, OpenAPI drift and
production Admin build passed. Full endpoint suite reached its 120 s timeout;
unscoped mypy exposed pre-existing imported-module errors and timed out. No
claim of a full green application suite. Build-generated next-env change reverted.

No database writes, migration or worker restart. Running API request timed out
after 8 s, so live UI confirmation remains operator acceptance: reload Admin;
if API still serves the old contract, restart API only when safe. Code and
generated contract tests prove the checksum is carried on a fresh process.
