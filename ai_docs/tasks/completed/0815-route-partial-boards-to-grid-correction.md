# TASK-0815 — Route boards with unknown search cells to grid correction

## Status

`done`

## Goal

Boards shown in board search as "częściowa (potwierdzone minimum)" because a
human marked some of their cells `unreadable` or `partial_visibility` enter the
Reviewer's manual grid-correction queue, so the operator can fix their grid.

## Context

2026-10-02 the operator asked to send such boards to "korekta cięcia siatki".
A read-only count on game 777 (`bfc4f949-5c14-4850-b02a-db99610bcfa5`) found
338 boards with at least one unknown search cell: 113 already had a
`Zła siatka` report, 179 had `unreadable` cells, 40 `partial_visibility`
cells, 7 had unknown cells without a current, source-available cell record.
The correction queue (D-462 R4) lists boards with a current `grid_issue` cell.

## Decision (operator, 2026-10-02, chat)

Route all boards with `unreadable` unknown cells (not only those with a
payout) and also the boards with `partial_visibility` unknown cells. The
previous cell decision is replaced by `grid_issue`; the history stays in the
cell review events.

## Scope

- `scripts/route_partial_boards_to_grid_correction.py`: preview by default;
  `--apply` marks the selected cells with the existing checksum-bound
  `mark_grid_issue` decision (`apply_board_mutations`, one transaction per
  board, actor `system:partial-board-grid-route-v1`); a board changed since
  the selection is skipped and reported; `--max-boards` for a trial.
- Run on game 777.

## Out of scope

- The 7 boards whose unknown cells have no current source-available record.
- Any UI or API change; automatic routing of future boards.

## Outcome

### Changed

- New script and `services/api/tests/test_partial_board_grid_route_script.py`.

### Verification results

- Unit tests 2/2; Ruff clean; mypy reports nothing for the script (67
  pre-existing errors elsewhere).
- 777 preview: 219 boards / 343 cells (179 `unreadable`, 40
  `partial_visibility`). Apply: 1 trial board + 218, 0 skipped; a second
  preview selects 0. The correction queue now holds 331 boards with a
  `Zła siatka` report across 20 imports.

### Not completed

- 7 boards without a markable cell record stay as they were.

### Recommended next task

- None; rerun the script when new "częściowa" boards appear.
