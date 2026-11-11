---
title: TASK-1183 — Material, protected split and reference sampling
status: active
last_updated: 2026-11-11
---

# TASK-1183 verification

Implementation follows T2 of EFFECTIVE_GRID_LEARNING_PLAN_20261111.md.
This report separates implementation tests from current operator data. No training,
activation, operator migration, service restart or operator database write occurred.

## Delivered behavior

- New v4 previews close byte/pixel aliases, known sessions and indivisible imports
  before conflict handling. A whole conflicting component is explicitly excluded
  from new use; history is neither rewritten nor released. Source population and
  registry proofs remain in the manifest and fence freeze/currentness.
- Excluded components stay in every import order as neutral positions. The conflict
  closure and its ten original canonical photos on each side receive no new role,
  BUFFER or representative. Historical TRAIN/VALIDATION/REG anchors, excluded ones
  included, restrict their own ten-photo neighborhoods to the same role; an excluded
  historical A/B anchor keeps its purpose buffer during purpose refinement. A roleless
  photo between two different historical anchors is a forced buffer, not an
  exclusion. Fresh REG keeps the ten-photo rule; exclusion does not widen it to20.
- `learningMaterial` counts current proven corrected/good labels with existing4:1
  weights. Canonical photos and board positions count once. Photo category counts
  may overlap. BUFFER is separate from unassigned material.20photos/60boards are
  explicitly only geometry lower bounds, not content readiness. An infeasible split
  adds `roleShortfalls`: protected per-role counts, minima and exact deficits.
- Seed20261108 selects ordinary REG groups independently of difficulty and content
  annotation availability. A separate hard sample requires existing verified
  `original_target` provenance for the pinned base plus current human geometry.
  Candidate output is never a selection input. Missing content is listed only for
  selected sources.5full content REG,30boards/10photos blind repeatability and u/δ
  remain required by the existing content pipeline. Legacy v1 `selectionState`
  keeps its meaning (five fully content-labelled photos).
- Exact geometric change does not prove missing-row, shifted-board, clipped-edge,
  neighbor-takeover, perspective or incomplete-image. All unsupported categories
  remain unknown and missing representation is explicit; no inferred diagnosis or
  synthetic human approval was introduced. A malformed historical producer proof
  yields an unknown reference with reason `NEURAL_GRID_PROOF_INVALID`; only that
  validated data boundary is mapped, other exceptions propagate.
- Partial TRAIN is admitted only with paired content policy/geometryOnlyTraining
  evidence; full detector minima10TRAIN/5A remain. Snapshot materialization preserves
  this pin for the T3 worker. Legacy consumers retain their old behavior.
- Excluded pins are recaptured with their own content mapping before the preview
  is sealed, so the capture page matches `expectedLabelsSha256`.
- Alembic0184 adds `recording_photo_cohort_v4`, private
  `recording_correction_report_bind_v5` and public wrapper command v7, preserving
  existing SQL bodies. v7 routes register/validate/bind of effective-material cohorts
  to v4/bind v5. Bind v5 validates through v4 (partial TRAIN, excluded proofs) and
  keeps the historical report pair set of v4-policy cohorts; v6 reports still need
  `production-cell-content-evaluation-v1`. No tables or historical rows change.
  Downgrade refuses new-policy cohort history. Deployment requires a separate
  operator migration together with T3 (the current worker rejects partial TRAIN).

## Verification

### R1 corrections (claude-opus-5-5/high, 2026-11-11)

The executor changed on operator instruction (Codex limit). R1 findings of
`TASK-1183_AUDIT_claude-opus-5-5.md` were fixed in one round on the clean delivery
worktree `D:/game_predicotr/worktrees/effective-grid-delivery`. Inherited Codex WIP
was reviewed before the changes; two gaps were found and fixed (the fresh-REG
neighbor check widened the buffer to twenty photos; excluded historical A/B anchors
lost their purpose buffer). Ordinary historical buffers were also misreported as
excluded neighborhoods and are now forced buffers.

| Finding | Fix | Test |
|---|---|---|
| P0-1 lost buffers | full orders, neighborhood masks, anchor roles/purposes | `test_excluded_neighbors_*`, `test_excluded_historical_anchor_*`, `test_exclusion_does_not_widen_*`, `test_excluded_b_anchor_*` |
| P1-1 stale labels | recapture of excluded pins | `test_content_capture_accepts_excluded_pins_*` through real `_capture`; fails when the pins are skipped |
| P1-2 bind via v3 | bind v5 + wrapper v7 | PostgreSQL bind pairs, replay, permission, excluded-proof change |
| P2-1 legacy state | v1 `selectionState` = five full content photos | `test_legacy_selection_state_keeps_full_content_photo_meaning` |
| P2-2 lost reply | see below | PostgreSQL |
| P2-3 rollout | 0184 is deployed only together with T3 | documentation |
| P2-4 manifest size | producer identifiers plus `producerSha256`/`baselineNodesSha256` | existing reference tests |
| P2-5 proof errors | `NEURAL_GRID_PROOF_INVALID` -> unknown with reason | `test_malformed_historical_proof_*` |
| P2-6 other worktree | every check below re-run in delivery | — |

Lost reply: the SQL register function has never been idempotent (v3 neither). The
exact replay is the application freeze receipt (`repo.replay` before any SQL,
shared by all policies). The PostgreSQL test proves that re-executing a committed
register key fails closed without a second use or release; report binding has its
own idempotency and replays the exact receipt.

No Codex audit of these corrections was performed: audyt Codex niewykonany —
kontynuacja na polecenie operatora po wyczerpaniu limitu. This is not a PASS.

### Commands and results

Python `D:/game_predicotr/.venv/Scripts/python.exe`, cwd = delivery worktree,
`PYTHONPATH=services/api/src;services/worker/src`, every finite test command
under `timeout 120`, `--basetemp` under `D:/game_predicotr/artifacts/t1183r1/`.

- 141 PASS (17.04s): `test_grid_learning_material.py`, `test_grid_content_sampling.py`,
  `test_grid_validation_purpose.py`, `test_schema_readiness.py`,
  `test_grid_correction_split.py`, `test_grid_correction_incremental_split.py`,
  `test_grid_render_selection.py`, `test_screen_correction_reader_contract.py`,
  `test_screen_correction_reports.py`, `test_grid_diagnostic_readiness.py`,
  `test_grid_quality_lineage.py`, `test_grid_quality_measurements.py`,
  `test_grid_quality_repoint.py`.
- PostgreSQL disposable (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`):
  `test_effective_grid_material_postgres.py` 1 PASS (23.35s);
  `test_grid_learning_v4_postgres.py` 1 PASS (102.95s), the real v4
  preview/freeze/train/evaluate/bind path after the R1 changes. Metadata-only
  fixtures, not proof of human labels or operator readiness.
- Ruff format/check PASS on the 21 changed Python files.
- mypy strict (project config, normal import following, no `--follow-imports=silent`)
  on the 18 changed production/migration files: 0 errors in them; 14 errors in 8
  untouched transitively imported modules, an error set identical to the same
  command on a clean `git archive HEAD` export. The command takes about 90s and
  ran as a controlled background typecheck with a 400s limit.
- Pre-existing failures, identical on the clean HEAD export and not changed here:
  `test_grid_correction_split_adapter.py` 6 FAIL (fixture labels lack `nodes`),
  `test_grid_training_cohort_core.py` 6 FAIL (outdated fixtures).
- Public DTO/OpenAPI/SDK/wrapper/request tests belong to T4.

## Current operator data — read-only observation after P0

Delivery modules and the genuine evidence reader, one REPEATABLE READ READ ONLY
transaction, budget105s, outer timeout120s, observed68.188s. Script and JSON:
`D:/game_predicotr/artifacts/t1183r1/t2_inventory_delivery.py` and `.json`. No
reservation, freeze, job, label or migration was written.

Mumie A2 `246a1f54-eee8-49d5-b11a-0fde70e5eecd`: the new v4 grid-only preparation is
`GRID_CORRECTION_SPLIT_INFEASIBLE`.

| Observation | Photos | Boards / detail |
|---|---:|---|
| Seed conflict closure (`GRID_CORRECTION_PROTECTION_CONFLICT`) | 1121 | 34 |
| Excluded neighborhood (`GRID_CORRECTION_EXCLUDED_NEIGHBORHOOD`) | 20 | 17; 3 historical A photos hold all 17 |
| Protected TRAIN before failure | 159 | 271 |
| Protected VALIDATION before failure | 4 | 4; deficit 1 photo and 11 boards |
| Protected REG before failure | 13 | 21 |
| Labelled photos outside exclusions | 185 | 308 |

The excluded closure contains import `ce7b2f19-9cf8-4d8e-bf65-990f62d6ede2` plus
aliases in `d7747436-5ebb-46af-af02-070d4cdaa290` and
`fbca1ab5-37d2-4206-b18d-1ecc52d1f317`. The three historical A photos lie within ten
photos of that closure, so they cannot serve as an independent control; A then
misses the existing minimum. More human-approved A material or a resolved conflict
is required; the split is not relaxed. The pre-P0 observation (A 7/23, 62.468s,
`artifacts/effective-grid-learning-20261111/t2-inventory.json`) is superseded. Its 45
latest content annotation rows / 0 human-approved were not re-read. No model-quality
improvement was measured.

## Internal report contract for T4

`photoSplit.learningMaterial`: version, weights, roles (dictionary by role;
corrected/good/unknownBoards and Photos, total photos/boards,
photoCategoriesMayOverlap), exclusions (componentKey, sourceIds, importIds,
photos, labelledPhotos, boards, priorRoles, priorPurposes, reasonCodes,
orderingMethods), excludedPhotos/Boards, availablePhotos/Boards,
minimumPhotos/Boards, minimumBasis=`geometry-three-role-lower-bounds`,
photoDeficit/boardDeficit, deficitsAreLowerBounds and historyModified.
Preparation errors expose the same optional `learning_material` internally; an
infeasible split adds `roleShortfalls` (basis, roles with photos, boards, minima and
deficits). Exclusion reason codes: `GRID_CORRECTION_PROTECTION_CONFLICT`,
`GRID_VALIDATION_PURPOSE_CONFLICT`, `GRID_CORRECTION_EXCLUDED_NEIGHBORHOOD`.

`contentSampling`: existing fields plus baseVersionId, strata ordinary/hard
(sourceIds, geometryFullPhotos, contentFullPhotos), difficultyReferences,
unknownReferencePhotos, categoryCounts, unrepresentedCategories,
hardSampleAvailable, missingContentSourceIds, geometryFullPhotos and selectionBasis.
Board references may carry `reasonCode` `NEURAL_GRID_PROOF_INVALID`.
`selectionState` concerns choosing geometry groups; content readiness can still be
not_evaluable. These fields remain inside the existing versioned split/manifest.
