# TASK-0814 — Bulk refresh of stale board-search documents

## Status

`in_progress`

## Goal

Every board-search document whose board geometry changed after the document
was written (`documentStale`, TASK-0773) can be rebuilt in one resumable
operator command, so "Pokaż planszę" shows the photo instead of the symbol
schema; the 777 backlog of 62 142 such documents is refreshed.

## Context

2026-10-02 the operator opened "Pokaż planszę" for board #486288 in "Wyszukaj
plansze" and saw only the default symbol graphics until they pressed "Odśwież
odczyt tej planszy". The modal falls back to the schema whenever the board's
current identity checksum (`recognized_boards.geometry_checksum_sha256`)
differs from the search document's `board_checksum_sha256`
(`board_search_board_detail._is_stale`). A read-only count on the local
database found 62 142 of 499 997 documents of game 777
(`bfc4f949-5c14-4850-b02a-db99610bcfa5`) in that state, all `pending`.
The per-board refresh already exists (TASK-0773,
`SqlAlchemyBoardSearchApproximateWinRepository.refresh_board_document`); no
bulk path does. The full `scripts/rebuild_board_search_projection.py`
rebuilds all ~500 000 documents in one transaction with the search marked
`rebuilding`, which the operator rejected in favour of a targeted refresh.

## Dependencies / entry conditions

- Facts: TASK-0773 refresh semantics; D-484 withheld boards (a refreshed
  pending board of an incomplete image keeps its document without symbol
  evidence, or loses it when it no longer owns the position).
- Operator consent (2026-10-02, chat): run the targeted refresh of these
  62 142 boards on the local development database.

## Recommended execution

Claude Opus 5.5, reasoning high — one coherent backend vertical (repository
query, service loop, CLI) touching live operational data; escalate to a
review if the apply leaves documents stale after a refresh.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-470, D-484 entries)

## Scope

- Read-only repository query selecting stale operational documents of one
  game in sequence order after a cursor, with the same identity rule as
  `_is_stale`.
- `BoardSearchBoardDetailService.refresh_stale_documents` — refreshes one
  bounded batch through the existing `refresh_board_document` and reports
  refreshed / removed / still-stale positions.
- `scripts/refresh_stale_board_search_documents.py`: preview by default,
  `--apply` to write; one transaction per batch; resumable because the
  selection is the staleness itself; JSON progress lines.
- Run the preview and the apply for game 777.

## Out of scope

- Finding and fixing the writer that changes board geometry without a
  projection sync (separate task; the backlog will regrow until then).
- Any change to the modal, API contract or full rebuild script.

## Acceptance criteria

- [ ] Preview performs no writes and reports the stale count and a sample.
- [ ] Apply refreshes each stale board exactly like the modal button,
      commits per batch and survives interruption (re-run continues).
- [ ] A board still stale after its refresh is reported, not looped on.
- [ ] Isolated PostgreSQL test: a stale document is selected, refreshed and
      no longer selected; a fresh one is never touched.
- [ ] After apply on 777 the stale count is 0 (or the residue is explained).

## Technical notes

- Selection: `image_board_search_fast_documents` joined to
  `image_review_items` → `recognized_boards`; stale when
  `coalesce(geometry_checksum_sha256, '') <> board_checksum_sha256`;
  `sequence_number > cursor`, ordered, `LIMIT batch_size`; storage bound
  with `GameStorageRouter` (READ).
- Per board: `board_document` → `refresh_board_document` (sync review item +
  sequence candidates, unchanged human decisions) → `board_document` again:
  `None` = removed, else re-check with `board_view_source`.
- Cursor = last selected sequence number, so a board that stays stale is
  counted once per run.

## Expected files

- `services/api/src/game_predictor_api/storage/board_search_approximate_win_repository.py`
  (new `stale_document_sequence_numbers`).
- `services/api/src/game_predictor_api/application/board_search_board_detail.py`
  (new `refresh_stale_documents`, `BoardSearchStaleRefreshBatch`).
- New: `scripts/refresh_stale_board_search_documents.py`.
- Tests: `services/api/tests/test_board_search_stale_refresh.py` (new),
  `services/api/tests/integration/test_board_search_approximate_win_repository.py`.

## Test cases

- Service with a fake repository: refreshed, removed and still-stale
  outcomes; cursor advances; empty batch ends.
- Script: preview prints count without calling refresh; apply loops batches
  until empty and aggregates totals.
- PostgreSQL: stale selection + refresh round trip.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_search_stale_refresh.py
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_board_search_approximate_win_repository.py
npm run python:lint
npm run python:typecheck
```

## Risks / open questions

- Some refreshed pending boards may leave board search (D-484), as with the
  per-board button.
- Root cause of the drift remains open.

## Outcome

Wypełnia agent po pracy.
