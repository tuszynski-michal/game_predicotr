# TASK-0431 — Pinned page geometry for v0.10 reprocess

## Status

`done`

## Goal

Make every new v0.10 managed reprocess pin and validate the exact page-geometry
manifest from its managed source lineage before any board processing begins.

## Context

A managed reprocess of 2,200 sources retained the managed originals but omitted
the exact page-geometry manifest. The worker therefore used the active 36-corner
profile and produced 19,798 board-cell deferrals despite the source browser
import having a complete verified manifest.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/tasks/completed/0424-source-specific-36-corner-grid-calibration.md`

## Scope

- Add a replay-compatible managed reprocess schema v6 that requires the exact
  page-geometry manifest and managed-original manifest checksum.
- Resolve that evidence through a bounded, same-game import lineage and reject
  missing, cyclic, foreign or incompatible provenance without fallback.
- Make the worker validate and consume the pinned manifest before processing.
- Preserve schema v4 and all historical image-import payloads.
- Add focused API/domain/worker tests and update generated OpenAPI types.

## Out of scope

- Changing geometry thresholds or board-cell estimator v19.
- Mutating, deleting or reprocessing live game data.
- The end-to-end 36-corner candidate gate and large-import UI, which require
  separate tasks after this safety invariant is complete.

## Acceptance criteria

- [x] A new managed reprocess is schema v6 and pins both immutable manifests.
- [x] Direct schema-v5 and transitive managed source lineages are supported.
- [x] Missing, changed, partial, foreign and cyclic provenance blocks creation
      or execution with a stable error and never selects an active grid profile.
- [x] The effective fingerprint includes both manifest checksums.
- [x] Schema v4 and historical schema v1-v5 jobs remain replayable.
- [x] Focused tests, lint and OpenAPI/client checks pass; the repository-wide
      Python typecheck remains blocked by two pre-existing errors listed below.

## Technical notes

The exact `PageGeometryManifestV1` is authoritative for v0.10. A learned grid
profile may help create a preflight manifest, but cannot replace it in a managed
reprocess. Human decisions and canonical sequence ownership remain untouched.

## Expected files

- `services/api/src/game_predictor_api/application/jobs.py`
- `services/api/src/game_predictor_api/schemas/jobs.py`
- `services/worker/src/game_predictor_worker/images/source_ingestion.py`

## Verification

```powershell
python -m pytest services/api/tests/test_jobs.py services/api/tests/test_image_imports_api.py services/worker/tests/test_source_ingestion.py services/worker/tests/test_page_geometry_registration.py
pnpm api:openapi:check
pnpm python:lint
pnpm python:typecheck
```

## Risks / open questions

- Source artifacts may be absent for old schema-v4 jobs. They remain replayable,
  but creating a new v0.10 reprocess from them must fail closed.

## Outcome

### Changed

- Added a bounded, same-game evidence resolver that validates the selected
  managed-original manifest, completed preflight and exact page manifest.
- New reprocess jobs use schema v6 and include both checksums in their immutable
  input and effective fingerprint. The worker verifies them again before the
  pipeline and cannot fall back to an active profile.
- Preserved schema v4 response and worker replay while extending OpenAPI with a
  separate schema-v6 payload.

### Verification results

- `108 passed` across focused API/domain/worker suites.
- Additional focused worker/API run: `62 passed`.
- `npm run python:lint` passed.
- `npm run openapi:check` passed and the generated client is current.
- Admin API client TypeScript typecheck passed.
- Repository-wide mypy was stopped after the 120-second command limit. An
  earlier bounded run reached completion and reported only pre-existing errors
  in `schemas/image_reviews.py:328` and
  `storage/virtual_grid_geometry_repository.py:325`; the task-local redundant
  cast it also found was fixed.

### Not completed

- No live reprocess, profile activation, cleanup or other data mutation was run.
- End-to-end grid-profile quality gates and large-import diagnostics belong to
  the next tasks in the accepted plan.

### Documentation updates

- Updated image-ingestion requirements, iterative-import architecture, API
  contract, decision D-324 and current state.

### Recommended next task

- Add the source-disjoint end-to-end quality gate for schema-v2 36-corner grid
  profiles before implementing the large-import UI guard.
