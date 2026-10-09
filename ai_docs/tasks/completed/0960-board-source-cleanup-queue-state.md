---
title: TASK-0960 — Preserve review queue state across source cleanup batches
status: done
last_updated: 2026-10-09
---

# TASK-0960 — Preserve review queue state across source cleanup batches

## Goal

Fix the repeatable source-cleanup failure and finish the operator-approved
replacement of 275 Mumie source images, retaining the exact replacement manifest.

## Context

The first 55-image batch committed. The second failed with SQLSTATE 23514:
`Cannot delete image review queue state for job ...: projection is missing`.
The cleanup explicitly deleted the entire import's queue state even though
other source images and their review items remained. The review-item delete
trigger requires that state and already removes it when the final item leaves.
A database-only diagnostic reproduced the failure and rolled back in full.

## Dependencies / entry conditions

- Operator approved all 275 listed source ranges and their derived data,
  including two approved symbol-cell decisions, after the exact preview.
- Initial batch removed 55 sources, 443 boards and 6645 cells. The remaining
  220 sources and 1755 boards were verified after the failed second batch.
- No API/Admin/worker lifecycle actions are authorized.
- No schema change, trigger disabling, owner-role mutation or wider deletion.

## Recommended execution

Bounded Codex fix; recommended configuration: `gpt-6.1-sol`, `medium`.
One read-only Claude audit attempt; no audit loop. No accepted-plan review gate
exists for this standalone bug fix. CLI unavailability is recorded explicitly.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md` — controlled cleanup
- `ai_docs/architecture/DATA_MODEL.md` — cleanup operations and review projection
- `ai_docs/quality/MUMIE_SOURCE_REPLACEMENT_20261009.md`
- `ai_docs/quality/MUMIE_SOURCE_REPLACEMENT_20261009.csv`

## Scope

- Let the existing delete trigger own review queue counts and state lifecycle.
- Test two committed source deletions of the same import in fresh sessions.
- Restore only missing queue counters damaged by the known first-batch bug,
  from verified surviving review queue items, with a new cursor version.
- Continue approved cleanup through preview-bound local API batches.
- Preserve all filenames, sequence ranges, old checksums and execution receipts.

## Out of scope

New upload/import, catalog symbols, models, training cohorts, unrelated data,
changes to API shape, migrations, service restarts, push or deployment.

## Acceptance criteria

- [x] Root cause reproduced with full rollback.
- [x] First source deletion preserves the remaining import queue state.
- [x] Final source deletion removes the empty state through its existing trigger.
- [x] Regression uses real PostgreSQL triggers and separate committed sessions.
- [x] Damaged counters restored without altering surviving review items.
- [x] All 275 approved source IDs and their board/cell data removed.
- [x] Replacement manifest updated with actual results and counters.
- [x] Scoped tests/lint completed and other verification attempts documented.
- [x] Review and type-check limitations explicitly retained below.

## Expected files

- `services/api/src/game_predictor_api/storage/cleanup_repository.py`
- `services/api/tests/integration/test_cleanup_repository.py`
- `ai_docs/quality/MUMIE_SOURCE_REPLACEMENT_20261009.md` and `.csv`
- `ai_docs/process/CURRENT_STATE.md`
- Claude audit report; operational evidence under ignored `artifacts/`.

## Test cases

Two sources from one import: delete one, commit, open a fresh session, verify
one queue item and counts `(1, 1)`; delete the second, commit, verify no items
or queue state. Preserve existing cleanup blockers and retry receipts.

## Outcome

### Changed

- Removed unconditional import queue-state deletion from source cleanup.
  The existing trigger maintains counts and deletes the last empty state.

### Verification results

- PostgreSQL regression: 1 passed in 10.82 seconds, isolated `_test` database.
- Diagnostic transaction: reproduced SQLSTATE 23514 and rolled back.
- Existing cleanup domain/API tests: 10 passed. Initial sandbox runs could not
  create temporary directories / reached the timeout; the same tests passed
  with a unique repository-local temporary directory and normal local access.
- Scoped Ruff check: passed.
- Seven missing counters restored from queue items whose identity/status matched
  source review items. Microsecond epoch versions invalidate pre-repair cursors;
  the previously accepted 217 review items were left unchanged.
- Retry of API batch 2 succeeded: another 55 sources, 439 boards and 6585 cells.
  A new read-only process found its preserved queue counts `(25699, 25699)`;
  the running API is using the corrected lifecycle without a service restart.
- Initial scoped mypy reached its 90-second sandbox timeout; a normal-access
  retry with a separate cache also reached its 55-second limit. No successful
  type check is claimed. No public annotations, method signatures or API types changed.

### Not completed

- Full scoped mypy did not finish within either bounded attempt. Regression
  and existing domain/API tests pass; the fix removes one existing SQL call
  and changes no type contract. No success is claimed for mypy.
- Claude audit unavailable: the script generated a 24 KB brief, but no CLI
  was found on PATH or in the standard user installation locations. No
  substitute self-review or fabricated PASS. Compact review handoff:
  `ai_docs/quality/TASK-0960_REVIEW_HANDOFF.md`.
- Operator's new corrected-photo upload has not been performed.

### Final operational verification

- All five API batches confirmed. Total: 275 sources, 2198 recognized boards,
  32970 symbol cells, 281 source geometry revisions and 2475 sequence numbers.
- Read-only verification from a fresh connection found zero target source,
  board, geometry, review and symbol records; five receipts and zero queue
  count mismatches. Preserved accepted review count remains 217.
- No trigger disabling, owner-role mutation, schema migration, service
  restart, new upload, push or deployment.
- Photo/range/checksum manifest remains in `ai_docs/quality/`; all 275 rows
  now carry `removed` and their actual batch number.
