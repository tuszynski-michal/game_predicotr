---
title: TASK-0514 — Admin launcher and report for v0.10.4
status: done
last_updated: 2026-09-08
---

# TASK-0514 — Admin launcher and report for v0.10.4

## Status

`done`

## Goal

Expose the opt-in v0.10.4 run in Admin through an explicit backend readiness
contract, durable report replay and an actionable geometry review summary,
without opening the release gate or changing historical defaults.

## Context

TASK-0510–TASK-0513 provide the immutable per-run variant, lateral proposal,
safe renderer contract and idempotent managed reprocessing. The operator still
cannot select the variant, prepare its compatible preflight, replay that state
after refresh or distinguish its review outcomes in Admin.

## Dependencies / entry conditions

- TASK-0510–TASK-0513 are committed and their focused gates passed.
- `LATERAL_PARTIAL_RELEASED` remains `False` until TASK-0515 acceptance.
- Existing cleanup, migration 0102, `next-env.d.ts` and virtual-repository
  changes are unrelated user work and must remain outside this task.

## Recommended execution

Use `gpt-5.6-sol` with `high` reasoning. The change crosses the Admin, OpenAPI
and read-model boundary; escalate to an independent `gpt-6-astra high` review
before commit, especially for accidental job creation during report reads and
for release-gate bypasses.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/DECISION_LOG.md` (D-374 and related import decisions)

## Scope

- Add a typed, read-only v0.10.4 readiness/gate projection to an existing
  image-import read contract.
- Allow the report request to select the per-run variant and replay the latest
  compatible page preflight and existing run without creating a job.
- Add the test-engine option, explicit compatible-preflight action and
  `Przetwórz w v0.10.4` managed-original action to Admin.
- Display grid engine, page-registration variant and symbol-model version as
  separate values.
- Split report counts into full grids, lateral proposals, manual correction
  and technical errors.
- Surface all source slots, unavailable-cell masks and automatic proposal
  provenance in the geometry editors.
- Update OpenAPI, generated client, wrapper and focused interaction tests.

## Out of scope

- Enabling `LATERAL_PARTIAL_RELEASED` or claiming real-data acceptance.
- TASK-0515 corpus, benchmark, release decision or operator rollout.
- Database migrations, reimports, service restarts or data cleanup.
- Changing v3 output, historical job snapshots or per-game default policy.

## Acceptance criteria

- [x] Admin visibly offers `v0.10.4 — testowy, niepełne boki` only with the
      backend-reported gate state and never sends a mutation while disabled.
- [x] `Pokaż raport` is read-only and replays a compatible preflight/run after
      refresh; missing evidence has a stable reason and explicit prepare action.
- [x] New and managed-original actions send the exact variant and compatible
      manifest references.
- [x] Report and history display grid engine, page-registration variant and
      symbol-model version separately.
- [x] Report categories and editor provenance/masks are visible and typed.
- [x] Historical/default UI and payloads remain unchanged without the variant.
- [x] Focused API, client and Admin tests, OpenAPI, lint/typecheck/build pass.
- [x] Independent review has no unresolved P0–P2 finding before commit.

## Technical notes

The release constant remains the execution source of truth. The additive
capability response must be derived from the same gate used by the mutating
endpoints; the browser cannot infer readiness from a label. Variant-aware
report preview may look up existing immutable jobs but must not call any create,
retry or worker path. Optional fields must not change the checksum of legacy
preflights. A missing or unfinished v4 preflight is an actionable artifact
state, while a closed quality gate is a release blocker, not a technical error.

## Expected files

- Existing: `services/worker/src/game_predictor_worker/images/lateral_partial_contract.py`
- Existing: `services/api/src/game_predictor_api/schemas/image_geometry_rollout.py`
- Existing: `services/api/src/game_predictor_api/schemas/image_imports.py`
- Existing: `services/api/src/game_predictor_api/api/image_imports.py`
- Existing: `services/api/src/game_predictor_api/application/jobs.py`
- Existing: `services/api/src/game_predictor_api/storage/image_grid_review_repository.py`
- Existing: `services/api/src/game_predictor_api/schemas/image_grid_reviews.py`
- Existing: `packages/admin-api-client/openapi/openapi.json` and generated client
- Existing: `apps/admin/src/features/imports/image-folder-import-actions.ts`
- Existing: `apps/admin/src/features/imports/image-folder-import-panel.tsx`
- Existing: `apps/admin/src/features/imports/import-geometry-review-summary.tsx`
- Existing: Admin/API/client focused tests

## Test cases

- Closed gate appears as disabled with `IMAGE_GEOMETRY_ENGINE_VARIANT_NOT_ENABLED`;
  clicking report does not call preflight creation or reprocess.
- Enabled capability sends the exact variant in report, geometry-preflight,
  browser start and managed reprocess requests.
- Reloaded report restores only a same-game, same-staging, same-manifest and
  same-variant preflight/run; legacy report checksum remains stable.
- Missing, processing, failed and completed-without-manifest preflights have
  distinct actionable report states.
- Review counts classify automatic lateral proposals separately from generic
  manual correction and preserve legacy totals.
- Editors show source-derived slot numbers, exact unavailable mask and
  `automatic_proposal` origin without treating it as a manual decision.

## Verification

```powershell
# Focused Python, Node and generated-contract commands resolved from repo scripts.
# Then Admin lint, typecheck and production build; no migration or service start.
```

The task stops before commit for independent review.

## Risks / open questions

- Large review counts must remain database-aggregated and must not load all
  images or all review records into the API process.
- A v3 guard-resolution manifest cannot be silently rebound to v4 evidence;
  the existing backend blocker remains authoritative.

## Outcome

Completed and accepted by independent review.

- The existing engine-policy GET now projects the v0.10.4 capability from the
  same fail-closed release gate used by preflight/start/reprocess mutations.
- The staging report accepts an optional per-run variant and performs only
  read-side lookup. It replays a matching immutable preflight and import run,
  exposes distinct missing/in-progress/review/failed/incomplete artifact
  reasons, and keeps the legacy checksum unchanged when no variant is chosen.
- Admin persists the operator's per-game variant choice locally, shows the
  explicit staging action and forwards the variant only through report,
  explicit preflight preparation and explicit start. A disabled capability
  cannot dispatch work. History/report expose separate engine, registration
  and symbol-model versions from pinned snapshots.
- The managed-original action now finds only an exact same-game,
  same-selection, same-source-manifest and same-registration v4 preflight. It
  can prepare that preflight with `managedSourceJobId` after browser staging
  deletion and reprocesses only with its completed job id and manifest checksum.
  A repeated action first refreshes a cached created/processing job from the
  backend, so completion is observed without changing the active browser report;
  refresh failure remains fail-closed and does not dispatch reprocessing.
- Preflight polling and explicit refresh replay a completion into the active
  browser report, clear the artifact blocker and unlock start without reopening
  the report. Managed-original preparation has isolated state, so preparing
  staging B cannot replace the job, readiness or manifest displayed for browser
  report A.
- Guard replay is strict across game, selection, source/page manifests, guard
  job, engine variant and rollout revision/fingerprints. Stale callbacks are
  ignored against the current job and report refs even when their revision
  changes after callback creation; foreign evidence and attempts to bind a v3
  guard to v4 produce explicit blockers.
- Cold-start replay is bound to the exact persisted unclassified symbol-model
  snapshot while keeping the public inference fingerprint null. An arbitrary
  model cannot impersonate that snapshot, and ordinary legacy preflight
  checksums remain byte-for-byte unchanged, including legacy cold-start without
  a geometry-engine variant; the stricter snapshot binding enters only the v4
  checksum.
- Grid-review counts now classify both unconfirmed automatic proposals and
  accepted partial boards from persisted completeness, unavailable masks or
  geometry qualification. Full grids exclude those accepted partials. Typed
  proposal provenance and masks are exposed in Admin and Reviewer editors while
  all filename-derived slots remain.
- Verification passed: API/domain focused `47`, Admin `445`, Reviewer `183`,
  generated client `57`, interaction/contract `39`; Admin/Reviewer/client
  typecheck and lint; both production web builds; OpenAPI drift; Ruff. The root
  Python typecheck is currently blocked before source analysis by the unrelated
  dirty `scripts/legacy_777_v01_chat_search.py` being discovered under two
  module names; a source-only retry was stopped after 60 seconds without output.
- No migration, service restart, user-data operation, reimport or release-gate
  activation was performed.
- Independent `gpt-6-astra high` review accepted the gate after three review
  rounds. The fixes cover managed/browser preflight isolation, strict replay
  identity, cold-start snapshot matching, stale guard callbacks, actual partial
  classification and preservation of the legacy cold-start checksum.
