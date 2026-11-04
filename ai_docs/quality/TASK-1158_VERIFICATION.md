---
title: TASK-1158 completeness and independent calibration verification
status: accepted
last_updated: 2026-11-04
---

# TASK-1158 — Verification and deployment handoff

Implementation base: `f78c5b5a1a6dcbc1c0d280a0f4d2204417e5d9a3` (v1.7.562).
Executor: gpt-6-astra/high. Opus R1 PASS is preserved in `TASK-1158_AUDIT_ROUND1.md`.
The coordinator promoted R1 P2-1 to P1; one correction round and focused R2 are complete.
[Focused R2](TASK-1158_AUDIT_claude-opus-5-5.md) is PASS with no open P0/P1.
No operator database migration/write, service restart, training,
inference, model activation, merge or push was performed.

## Delivered contract

- Alembic0181/SQLv8 adds A/B purpose to the existing immutable photo-use ledger.
  Explicit old projections preserve v6/v7 proof JSON; new context/photo/command
  versions consume purpose. Whole component assignments reuse group/copy/session/
  ancestry protection and buffers. Preview does not persist assignments. Legacy
  selection-exposed uses are A only; fresh legacy freeze/start/resume cannot use B.
- Corrections/split/snapshot v4 explicitly binds A/B. TRAIN and checkpoint A retain
  full-screen requirements; assessment B/REG keeps partial labelled targets. Existing
  REG minimum remains5photos/15GT/full0. No new B minimum blocks training.
- Each game's baseline strata are frozen from human GT before threshold selection.
  Per described board: IoU matching, existing24-node normalized mean/max error and
  GT-cell pixel coverage determine correctness. The numeric coverage epsilon1e-6 is
  dimensionless in x/W,y/H, not permission to crop. Candidate correctness is measured
  separately; repairing all baseline errors does not remove the bad stratum.
- B and REG each require30 distinct deduplicated sources in each baseline class.
  Mixed photos may contribute different boards to both classes; overlap is reported.
  Conflicting current human GT on identical byte/pixel copy+slot is unresolved.
  Partial data supports labelled-target claims only; full-photo/FP/duplicate claims
  need full GT. Synthetic fixtures test mechanisms and do not qualify real models.
- The preregistered menu has8axes with at most2 TRAIN/A-derived levels each, at most
 256configurations per game. Correct deduplicated TRAIN/A observations provide
  nearest-rank1%/5% minima and95%/99% maxima, with counts and versioned hashes.
  Required missing references remain manual. No hidden minimum beyond nonempty
  active-axis observations and existing TRAIN/A minima. Plan before B, sealed B
  configuration before REG, deterministic ties; no NN invocation per configuration.
- New A routing adds only fitted-cell input-support violation to existing guards,
  bound to complete preset/exact A/routing SHA and actual A path validation.
  Runtime sees input pixels and fitted cells, not GT; this does not prove detection
  of every omitted row. Other calibration failures do not invent rescue triggers.
- Report-read v5 wraps unchanged raw-quality v3/v4 gates. Raw publication/manual
  proposal eligibility and automatic qualification are separate. Pin v3/acceptance v4
  requires a strict profile, sidecar SHA/currentness and result-bound feature evidence.
  Historical retries recover pin AND policy; SQL IMPORT/VALIDATE uses the same identity.
- Available managed-crop support and raster checksum bind the calibrated raw cache
  and existing RescueAttemptStore identity. Same-operation raster drift fails closed
  before reading an old baseline or consuming another attempt; legacy identity stays
  unchanged. Missing mapping is manual, padding is not image support.
- Generic diagnostic registration uses strict T1 records and the existing evidence/
  command ledger. Actual comparison use excludes B/REG through existing closure;
  metadata-only readiness access is not exposure. Registration is not executed here.

## Executed checks

Logs are host-side under the worktree's ignored `artifacts/task1158/`. Counts below
are per invocation and overlap; they must not be summed as unique tests. All child
commands had timeout120s. PostgreSQL used disposable fixtures, not operator tables.

| Check | Result | Evidence |
|---|---|---|
| Initial pure calibration/purpose |14PASS|`unit-foundation.txt`|
| Completeness/features |4PASS|`unit-features.txt`|
| Durable rescue/restart regression |7PASS|`unit-rescue-ipc.txt`|
| Runtime/retry/phase resume |18PASS|`unit-runtime-retry2.txt`|
| Combined domain/API request/worker/strict diagnostic scope |53PASS,2existingFAIL|`unit-final-scope.txt`|
| Raster drift, available support, v4 preview and legacy reinference |12PASS|`unit-raster-preview.txt`|
| Actual existing A evaluator and routing proof |1PASS|`unit-a-routing-fixed.txt`|
| PostgreSQL positive qualified flow + old proof migration |2PASS,43.27s|`pg-calibrated.txt`|
| PostgreSQL v4 freeze/full A/partial B, rollback/new connection |1PASS,27.43s|`pg-freeze-v4.txt`|
| PostgreSQL diagnostic registration/rollback/replay/fences |1PASS,19.86s|`pg-diagnostic-registration.txt`|
| Ruff lint/format,71changed Python files |PASS|`ruff-final.txt`, `ruff-format-final.txt`|
| mypy57modules, follow-imports=silent |0new errors;1baseline error|`mypy-final2.txt`, `mypy-baseline.txt`|
| SDK strict types and request serialization |PASS;1request test|Executed `npm run typecheck --workspace @game-predictor/admin-api-client` and direct WT request test; stdout was not archived|
| Admin isolated strict types, raw PASS with auto-unqualified v5 |PASS;1interaction test|`admin-types.txt`, `admin-v5.txt`|
| Admin OpenAPI and generated SDK drift |PASS|`openapi-check.txt`, `sdk-generated-check.txt`|
| Admin scoped ESLint |PASS|`admin-eslint.txt`|
| Scoped frontend Prettier |PASS|`frontend-format-final.txt`|
| Generated code map/currentness |PASS|`map-generate.txt`, `map-check.txt`|
| Required docs checks and Git whitespace |PASS|`docs-check.txt`, `diff-check.txt`|

The positive PG test uses the actual strict report/profile sidecar reader, registry
publication/currentness, operation preparation, production workflow recheck and API
prewrite guard. It accepts matching game/model/source/nodes evidence, recovers the
same IMPORT pin/policy from a fresh process, then rejects report drift. It does not
inject empty qualification blockers. Its observations and image geometry are synthetic;
it proves the integration contract, not real NN quality or statistical independence.

The A evaluator test executes the existing screen evaluator with5 full A photos and
controlled engine outputs, verifies exact A and actual path counts, and excludes B.
It does not run a trained network. The raster test changes support/checksum under the
same operation and verifies no extra attempt. Disposable PG confirms old context
v1/v2 JSON bytes across0180→0181, purpose fences, transaction rollback and durable retry.

Two old run-preview assertions expect a two-preset catalogue and the retired unsupported
corrections policy. Both failures were reproduced with exact HEAD service and tests
(`baseline-preview.txt`, `baseline_preview_probe.py`); they were not weakened.
The mypy Row-to-tuple assignment at `virtual_grid_geometry_repository.py:2886` is
identical to HEAD line2875 through `--shadow-file`. Configuration is the full project
pyproject copied to `artifacts/task1157-preflight/mypy.toml`, with only torch/torch.*
follow-imports skipped; all project imports use silent, not skip. This is not global
mypy PASS. No global configuration was weakened.

Two wrappers printed a Unicode checkmark through cp1250 after saving successful logs;
the Admin interaction and generated-client check themselves passed. Tests were not
rerun for stdout encoding. Subsequent wrappers use UTF-8 output.

## Operator diagnostic staging — not executed

Durable metadata-only manifest, outside the removable worktree:

`D:/game_predicotr/artifacts/full-board-detection/operator-diagnostic-registration/task1158-v1.json`

File SHA256: `e4a3a120404f225e478ac13aba708e048706e1a3e73f3eb7a11f7b4e4523e172`.
Strict inputs: `D:/game_predicotr/artifacts/task1155-input-replay-r2/base.json` and
`candidate.json`. Two record bindings, one diagnostic use/source after deduplication.
Status is `staged_not_registered`; `readinessAccessIncluded=false`. No role history
was changed. The manifest is excluded from Git and the Anthropic audit package;
the auditor may read only this path/SHA, code and synthetic tests, never the payload.

T6/deployment prerequisite: separately approve deployment/migration0181 and the
registration write, verify the manifest SHA, then from the deployed checkout run:

```powershell
Set-Location D:/game_predicotr
$env:PYTHONPATH = 'D:/game_predicotr/services/api/src;D:/game_predicotr/services/worker/src'
Get-FileHash -Algorithm SHA256 'D:/game_predicotr/artifacts/full-board-detection/operator-diagnostic-registration/task1158-v1.json'
.venv/Scripts/python.exe scripts/register_grid_diagnostics.py execute `
  --manifest 'D:/game_predicotr/artifacts/full-board-detection/operator-diagnostic-registration/task1158-v1.json' `
  --actor local-owner --approved-deployment
```

Execute is atomic with10s statement/3s lock limits; duplicate record binding replays.
The SQL closure must be registered before preparing new B/REG. This command is an
instruction for separately approved deployment, not authorization or a claim that
registration happened. Readiness134 metadata accesses are absent from the manifest.

## Limits and remaining work

No real independent B/REG population was evaluated; the live readiness134/197GT/0full
from T1 was not rescanned. No empirically qualified production profile is claimed.
Pre-T0 and T0 counts are policy comparisons on the same baseline predictions, not a
rerun of an old executable. Partial targets and mixed-source overlap are explicit;
there are no confidence intervals or claims of independent60photos per role.

Numeric sweep and sidecar revalidation are bounded, but no performance benchmark was
authorized or run. Existing T3 synchronous inspection cost and archival reason limits
remain. NTFS durable-file assumptions are inherited; physical power-loss/directory-fsync
guarantees and GC remain outside this task. Operator migration, diagnostic registration,
real training/evaluation, model application and service restart require separate approval.

Independent Opus review and coordinator acceptance are complete; task-close records v1.7.563.
T5 consumes the separate raw PASS and automatic qualification states;
T6 must gate deployment on0181 compatibility and diagnostic registration/closure.

## R1 correction round and focused R2

P2-1 / coordinator P1: target membership now comes from the report's authoritative
DB-bound frozen cohort. `load_frozen_assessment` verifies game/cohort/status/manifest
SHA, then uses existing GridCohortSnapshot, GridBoardDataset and GridAssessmentDataset.
There is no parallel GT reader or role ledger. The sidecar cannot choose its authority.
Each observation binds source UUID, normalized pixel SHA, physical slot and exact GT
target SHA. Exact count/membership precedes copy deduplication; omission, substitution
or duplicate source/slot fails. Partial targets remain present. The plan additionally
binds cohort manifest, A/B/REG references, source/target counts and role proof. Worker
prepare, cached B, finish and resume check these values; the final report path reloads
the cohort even when measurements are checkpointed. API checks the same frozen set.

Required `sourceId` and frozen-reference fields strengthen an UNRELEASED T4 v1 sidecar.
R1 data is retained with its source snapshot and was not issued to the operator/app.
Missing fields fail closed (Pydantic field-required or `CALIBRATION_FROZEN_PLAN_CHANGED`);
this is not a migration/version-discriminated reader. No source ID is inferred.
Released raw reports and historical pins retain their interpretation and do not enter
the new v5 automatic qualification path.

P2-2: `calibration_routing_sha` supplies one normalized board-preset/path/routing formula
to evaluator and runtime. The composed test runs the actual A evaluator, selects
board_only, runs RescueAssessmentEngine on that measured path, creates a final numeric
calibration profile, and obtains positive runtime evidence from the same archived
preset/profile. Changed selected path produces no evidence. Controlled detections
replace NN; synthetic numeric B/REG observations do not prove empirical qualification.

P2-5: a fresh subprocess retrieves IMPORT and VALIDATE through the actual SQL admission
lookup, checks identical pin SHA and derived v4 policy, then currentness before and
after report invalidation. VALIDATE continues deriving policy from its pin; no new
acceptance field, nonce or attempt budget was introduced.

| R2 scoped check | Result | Ignored `artifacts/task1158/` evidence |
|---|---|---|
| Domain + worker/raster/phase resume, including changed A/B/REG targets |14PASS|`r2-unit-first.txt`|
| Actual A evaluator, routed assessment and positive runtime profile |1PASS|`r2-routing-second.txt`|
| PG real frozen reader/positive prewrite,6 rehashed target forgeries, cold IMPORT+VALIDATE and drift |1PASS,26.74s|`r2-pg-third.txt`|
| Ruff12changed Python files |PASS|`r2-ruff.txt`|
| mypy9changed production modules, silent imports/prior torch-only override |PASS|`r2-mypy.txt`|
| Scoped format, regenerated map/check, docs and whitespace |PASS|`r2-format.txt`, `r2-map-check.txt`, `r2-docs-check.txt`, `r2-diff-check.txt`|

The first PG invocation lacked an explicit fixture import and did not reach DB. The
next exposed a PNG/JPEG fixture mismatch; sources now use distinct tiny JPEGs. The
first composed test lacked synthetic component IDs. Fixture corrections did not
weaken guards or change product behavior. Earlier green broad suites, SDK/Admin and
operator readiness were not rerun.

Accepted residuals: P2-3 synchronous bounded sidecar/sweep work under admission remains
unbenchmarked, without adding a cache. P2-4 minima count deduplicated sources, not
independent sessions/ancestry components; existing component partition fences remain.
No statistical guarantee, independence claim or additional minimum was added.

Focused R2 closes coordinator P1/R1 P2-1 and R1 P2-2/P2-5. New nonblocking P2-6 is
accepted: the composed test constructs observation metadata from the real assessment
wrapper; it does not run through `run_with_rescue.observation_sink`. The auditor checked
the shared proof expressions statically. This is a residual test boundary, not a claim
that the complete sink path was executed. No third review or behavior change was made.

T6 receives a targeted partial-A/grid-only acceptance check: verify that the production
VALIDATION detail contains every frozen A target and remains usable with partial A.
This specific production-handler scenario was not executed here and is not reported
PASS. The existing pure dataset/phase tests and full-A composed test cover different
boundaries. Known P2-3/P2-4 and inherited T3 limits remain accepted.

Pre-close verification compared all R2 source hashes and unchanged R1 code/test/API/UI
hashes (82 paths): PASS (`artifacts/task1158/preclose-source-check.json`). Only close-out
documentation and the coordinator's final audit report changed after the code freeze.
