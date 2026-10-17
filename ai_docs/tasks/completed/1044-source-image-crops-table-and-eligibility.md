---
title: TASK-1044 — `source_image_crops` migration and blob eligibility
status: done
last_updated: 2026-10-17
---

# TASK-1044 — `source_image_crops` migration and blob eligibility

## Status

`done`

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

- [x] Upgrade and downgrade on `*_test` pass; constraints from R1 enforced.
- [x] PostgreSQL integration tests: shared blob with one ineligible row, pending correction, `grid_issue`, page exclusion, pending proposal, active job, incomplete geometry, unapproved current revision (plus import not completed, unaccepted source revision, board without quads).
- [x] Protected quads include board corners, cell quads, padded quads and sequence-label quads; every active board must have its own quads.
- [x] Comparison report against the P1 manifest for the 40 sources: [SOURCE_CROP_P1_COMPARISON_20261017.md](../quality/SOURCE_CROP_P1_COMPARISON_20261017.md).
- [x] Lint, mypy and focused tests pass.

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

Commit: v1.7.405 / `a07276127b83a9954f69062a7fdcbe973587089e`.

### Changed

- Migration `0167_source_image_crops`: shared table `public.source_image_crops`
  (plan R1, CHECKs for derived paths, smaller crop, boxes, protected box inside
  the crop, state/time consistency, iMCU 8/16, orientations 1/3/6/8), manifest
  `game-data-v2-manifest-v18` (`ADDED_SHARED = {source_image_crops}`), guarded
  downgrade `SOURCE_IMAGE_CROPS_DOWNGRADE_HAS_HISTORY`.
- `storage/game_data_v2_manifest_v18.py`, ORM `storage/source_image_crop_models.py`
  (`public`, registered in `models.py`), runtime imports moved to v18
  (`catalog_repository`, `game_partition_lifecycle`, `game_storage_routing`,
  `grid_cohort_asset_retention`), `schema_readiness.EXPECTED_ALEMBIC_HEAD = 0167`.
- Pure `domain/source_crop_eligibility.py`: `CropExclusion` (18 stable reasons),
  `CropSourceFacts`, `classify_blob` (all sources of a blob must qualify and agree
  on identity; protected points are the union of their geometry).
- `storage/source_image_crop_repository.py`: `eligibility` (keyset pages of
  blobs, optional game scope that still judges every sharing game, explicit
  `game_data_v2.`, owner session, read-only), `get`, `record_verified`,
  `mark_original_deleted` (only from `verified`).
- `source_crop.protected_points_from_geometry` (walks board geometry, source
  revision entry, board revision corners/geometry/render spec and render
  manifest; keys `finalQuad`, `sourceQuad`, `symbolGridQuad`, `latticeBoundsQuad`,
  `boardFrameQuad`, `paddedSourceQuad`, `sequenceLabelQuad`, `corners`).
  `sequenceLabelQuad` answers the open question: production sequence-label
  regions are stored in `recognized_boards.board_geometry` and are protected.
- Tests moved to manifest v18 / head 0167 where they assert the runtime manifest.
- Docs: `GAME_DATA_V2_OWNERSHIP.md` (manifest v18), `DATA_MODEL.md` (table).

### R5 mapping (P1 collector → eligibility)

| P1 condition | Reason |
|---|---|
| `geometry_completeness_status='geometry_complete'` | `GEOMETRY_INCOMPLETE` |
| coordinate space present | `NO_COORDINATE_METADATA` |
| at least one non-rejected board | `NO_ACTIVE_BOARDS` |
| `approved_geometry_revision = geometry_revision` | `GEOMETRY_NOT_APPROVED` |
| `completeness_status='complete'` | `BOARD_NOT_COMPLETE` |
| source revision not pending/needs_review/rejected/reverted | `SOURCE_REVISION_NOT_ACCEPTED` (stricter: must be `accepted`) |
| no pending `image_board_geometry_pending` | `PENDING_GEOMETRY_CORRECTION` |
| no `grid_issue` cell | `GRID_ISSUE` |
| shared blob checked across games | all sources of the blob, every game |
| safe path to the original | `UNMANAGED_PATH` (content-addressed path required) |
| — (new) | `IMPORT_NOT_COMPLETED`, `GAME_STORAGE_NOT_ACTIVE`, `PENDING_GRID_PROPOSAL`, `PAGE_SOURCE_EXCLUDED`, `ORIENTATION_UNSUPPORTED`, `IDENTITY_MISMATCH`, `NO_PROTECTED_QUADS`, `PROTECTED_QUADS_INVALID` |

The new conditions are stricter than P1. The artifact comparison is in
[SOURCE_CROP_P1_COMPARISON_20261017.md](../quality/SOURCE_CROP_P1_COMPARISON_20261017.md);
facts the P1 manifest lacks are reported as not evaluated (TASK-1050 pilot).

### Audit

Codex `gpt-6-astra` / `high`, round 1:
[TASK-1044_AUDIT_gpt-6-astra.md](../quality/TASK-1044_AUDIT_gpt-6-astra.md),
verdict REVISE (P0-1..3, P1-1, P2-1..2). One fix round:

- P0-1: new `ACTIVE_IMAGE_JOB`: any `created`/`processing` job of the source's
  game or a global job excludes the game's originals, except the explicit
  `NON_IMAGE_JOB_TYPES` allowlist (payout, snapshot, android_build, validate,
  super_game_series_derive, storage_inventory); an unknown type excludes.
  Stage B must add its own crop job types to the allowlist.
- P0-2: geometry is read per board (`CropBoardGeometry`); a board without
  quads, or fewer board rows than `active_board_count`, gives
  `BOARD_GEOMETRY_MISSING`; the union is computed only afterwards.
- P0-3: artifact-only comparison report for the 40 P1 sources (plan of R6 equal
  to the measured lossless crop 40/40, contains the P1 bbox 40/40, no board
  without quads); missing facts listed as not evaluated.
- P1-1: the PostgreSQL test now creates a real `grid_issue` (cell mutation
  through the review repository), a page exclusion, a pending proposal, an
  active job in a third game, incomplete geometry and a board without quads;
  rows whose unmodelled parents (staging, reinference target) are not part of
  this task are inserted with `session_replication_role = replica` (FK triggers
  only; CHECKs and routing apply).
- P2-1: box CHECKs reject NULL elements, multi-dimensional or offset arrays,
  inverted raw and protected boxes and a raw box of a different area; negative
  tests added.
- P2-2: `eligibility` refuses a session that is not REPEATABLE READ or
  SERIALIZABLE (`SOURCE_CROP_ELIGIBILITY_SNAPSHOT_REQUIRED`), so facts and
  geometry come from one snapshot; tested.

### Verification results

- Unit: `test_source_crop_eligibility.py` 22, `test_source_crop.py` 38, plus
  manifest/routing/lifecycle/readiness/proposal/reinference schema tests: 124
  passed together before the fix round; after it the classifier suite 22/22.
- PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`, dedicated `*_test`
  databases), after the fix round: `test_source_image_crops_postgres.py`
  4 passed (96 s) — head 0167 and manifest v18 on a provisioned game, `shared`
  ownership row, downgrade to 0166 and back, downgrade refused with a registry
  row; 8 constraint violations; eligibility over three games with every
  exclusion of the acceptance criteria, game scope, keyset paging, checksum
  filter and the snapshot requirement; real `grid_issue` mark.
- Before the fix round, manifest/migration integration tests on v18:
  `test_grid_model_evaluation_bridge_postgres`, `test_grid_training_lane_migration_postgres`,
  `test_postgres_baseline` (upgrade/downgrade/upgrade cycle),
  `test_per_game_isolation_new_game`, `test_game_partition_lifecycle_postgres`,
  `test_game_storage_routing_postgres`, `test_application_role_isolation_postgres`:
  67 passed (555 s).
- `ruff check`/`ruff format --check`: pass; `mypy` strict on the new and changed
  modules: no errors in them (only the 2 pre-existing `source_lattice_geometry.py` errors).

### Not completed

- No operator DB access and no migration of the operator database (separate consent).

### Documentation updates

`GAME_DATA_V2_OWNERSHIP.md`, `DATA_MODEL.md`, code map.

### Recommended next task

TASK-1045.
