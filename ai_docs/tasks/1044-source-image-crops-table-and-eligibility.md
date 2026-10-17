---
title: TASK-1044 — `source_image_crops` migration and blob eligibility
status: todo
last_updated: 2026-10-17
---

# TASK-1044 — `source_image_crops` migration and blob eligibility

## Status

`todo`

## Goal

The `source_image_crops` table (plan R1) exists through an Alembic migration,
and a read-only eligibility query (plan R5) returns per blob the protected quads
or the exclusion reasons, consistent with the P1 selection.

## Context

Stage A of the accepted
[photo crop plan](../delivery/PHOTO_CROP_STORAGE_EXECUTION_PLAN_20261017.md).
The query decides what may later be deleted, so false eligibility is the main risk.

## Dependencies / entry conditions

TASK-1043 (pure region functions, D-562). Migration runs only on `*_test`
databases here; the operator database migration needs separate consent.

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Audit: Codex `gpt-6-astra` / `high`.

## Relevant docs

- Plan sections R1, R5, R6; D-562
- `ai_docs/architecture/DATA_MODEL.md` (source images, geometry revisions)
- D-484 (geometry completeness gate)

## Scope

- Migration `0167_source_image_crops` (number after checking the Alembic head),
  ORM model, repository with insert/state transitions used later by jobs.
- Read-only eligibility query grouped by blob, with exclusion reasons, and
  protected quads collected for R6.
- Comparison report against the P1 manifest for the 40 sources (from the
  artifact; no operator DB access in this task).

## Out of scope

Jobs, loaders, API endpoints, operator DB migration.

## Acceptance criteria

- [ ] Upgrade and downgrade on `*_test` pass; constraints from R1 enforced.
- [ ] PostgreSQL integration tests: shared blob with one ineligible row, pending correction, `grid_issue`, page exclusion, active job, incomplete geometry, unapproved current revision.
- [ ] Protected quads include board corners, cell quads and padded quads.
- [ ] Lint, mypy and focused tests pass.

## Technical notes

R5 conditions are the source of truth. If a condition has no reliable column,
the query treats the source as ineligible with an explicit reason.

## Expected files

To be confirmed at task start against `services/api/src/game_predictor_api/storage/models.py`
and `services/api/alembic/versions/`.

## Test cases

See acceptance criteria.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'  # dedicated *_test databases only
D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/integration -k source_image_crop
```

## Risks / open questions

- Sequence-label regions: find where they are stored per source or exclude such sources.

## Outcome

Wypełnia agent po pracy.
