# TASK-0816 — Share query log groups searches of the same pattern

## Status

`done`

## Goal

The Admin's share-link query log shows each searched pattern once, with the
times of all its searches separated by commas (D-486).

## Context

Operator request, 2026-10-02: a recipient who searches the same pattern again
later produced a separate log entry each time.

## Decision (operator, 2026-10-02, chat)

The same pattern is one group even when the start board or spin range of the
follow-up differ; the chart is the newest one. Delete removes the whole group.

## Scope

- API: `groupByPattern` on `listBoardSearchShareQueries` (searches only),
  `occurrenceTimes` on every entry, `wholePattern` on
  `deleteBoardSearchShareQuery`. Grouping is a read in
  `BoardSearchShareQueryLogService`; storage and the public surface are
  unchanged.
- OpenAPI, generated client, client wrapper and request test.
- Admin log: comma-separated times, group delete.

## Out of scope

- Recording the recipient stake (TASK-0817).

## Outcome

### Changed

- `application/board_search_share_queries.py`, `api/board_search_shares.py`,
  `schemas/board_search_shares.py`; `packages/admin-api-client`;
  `apps/admin/src/features/board-search/board-search-share-query-log*.ts(x)`.
- `API_CONTRACT.md`, `DECISION_LOG.md` (D-486), `CURRENT_STATE.md`.

### Verification results

- `test_board_search_share_query_log.py` 14/14 (4 new); Ruff clean.
- Admin API client tests 76/76; OpenAPI artifact and generated client current.
- Admin typecheck and ESLint clean; share panel interaction tests 6/6. The
  query log interaction test was already failing before this task (it
  expected the pre-D-478 view) and now covers the grouped view.

### Not completed

- Not checked in a browser against live data.

### Recommended next task

- TASK-0817 (recipient stake on the log charts).
