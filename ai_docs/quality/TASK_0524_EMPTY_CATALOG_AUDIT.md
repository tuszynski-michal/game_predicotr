---
title: TASK-0524 empty catalog audit
status: accepted
last_updated: 2026-09-09
---

# TASK-0524 empty catalog audit

## Bound preview

- Game: `777` (`new-siedem`)
- Game ID: `03d64bfe-4d29-47dd-9153-76bd99b3b5d9`
- Preview SHA-256:
  `c4fc91bc2140fc70e889d6e4394bb77d9162ac4e8094d3780419af30d5ece0b7`
- Preview rows: 2 479 490
- Managed artifact references: 7 826, shared: 0
- Active jobs: 0
- Stagings: 3

## Database receipt

The deletion was fenced and executed in independently committed batches.
The terminal receipt is `database_done`, with 1 947 journal batches. The
receipt reports the exact principal counts:

| Relation | Deleted |
|---|---:|
| `cell_observations` | 1 013 955 |
| `image_symbol_review_cells` | 1 013 955 |
| `recognized_boards` | 67 597 |
| `image_review_items` | 67 597 |
| `image_symbol_prediction_revisions` | 67 597 |
| `source_images` | 7 818 |
| `image_source_geometry_revisions` | 7 738 |
| `jobs` | 60 |
| `games` | 1 |

## Final read-only checks

- Game catalog rows: 0.
- Direct rows with non-null `game_id`: 0.
- One-hop dependent rows whose owner has non-null `game_id`: 0.
- `game_data_v2` was not yet installed at this checkpoint, so it contained no
  game partitions or data.
- Remaining global jobs, filename verification records and GC records have no
  game owner and were intentionally preserved.

## Filesystem boundary

No physical asset deletion was executed. Both protected locations still
exist after the database operation:

- `C:\Users\user\Documents\777`
- `artifacts/legacy-chat-search/777-v0.1-layouts.sqlite3` (19 808 256 bytes)

Managed asset deletion requires a new reference-aware preview and separate
operator confirmation.
