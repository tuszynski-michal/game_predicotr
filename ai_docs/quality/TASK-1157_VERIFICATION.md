# TASK-1157 — verification and handoff

Date: 2026-11-04. Branch: `codex/full-board-detection`. Entry HEAD:
`6325a0579c6f2cd5aed66b4cf894c09682be4ab1` (v1.7.561). Closing commit: v1.7.562;
authoritative full hash is recorded in the completed task Outcome.
Executor: gpt-6-astra/high. Actual Opus 5.5/high R1: PASS,0P0/P1,5P2, preserved in
TASK-1157_AUDIT_ROUND1.md. Coordinator classified normal-crash recovery P2-1 as a
blocking durability P1; one correction round completed below. Focused R2 PASS,
0P0/P1, coordinator P1 closed. R2 P2-6/P2-7 accepted as documented limitations.

## Implemented scope

- Explicit additive trainingMode and detectorReadiness, new policy/snapshot v3,
  full TRAIN/A with partial REG assessment, exact labels and role-specific admission.
- Existing SCREEN_GRID_V1 network/batches/photo evaluator; photo-first checkpoint,
  exact A input, best-step exposure, cumulative resume budgets. No second trainer.
- One typed variant per run, three independently measured runtime paths, actual
  CPU ONNX parity, closed proof checked against spec envelope/receipt/files/frozen
  TRAIN/A, conservative variant cost/VRAM admission, durable operation/source/slot 1+1.
- Exact reserved/completed request projection for T5; future T4 trigger requires a
  new validated routing version. Existing fit-or-pixels-v1 rejects other callbacks.
- Report v4/gate v3 and SQL v7 capability via Alembic0180; old bodies unchanged.
- Explicit historical cohort replacement only for required other games, all pins
  included in preview/parent/child/evaluation. Default old command replay preserved.
- Backend/OpenAPI/SDK/wrapper/request contract and existing result renderer v4 guard.

## Executed checks

Counts below are individual invocations, not a sum of unique tests. Some checks overlap.
All finite child commands had explicit timeout at most120 seconds. Tests use controlled
fixtures, not real model training or claims of detection accuracy.

| Check | Result | Evidence / scope |
|---|---|---|
| Final changed API/workflow/policy/checkpoint/rescue/report set | 67 PASS,16.00s | pytest seven files; `artifacts/s1157fin3`; includes exact cohort choice/currentness/replay, legacy command defaults, strict partial REG, non-reset exposure and routing proof |
| Final selector / independent cohort HTTP | 3 PASS,36 deselected,3.30s | `test_grid_correction_cohort_contract.py` and `test_grid_correction_learning_api.py`, selector `screen or correction_request`; `artifacts/s1157http` |
| Training handler/recovery and contract set | 41 PASS,2 fixture failures; corrected fixtures2 PASS | `s1157fin1`/`s1157fin2`; missing schema_version in two new fake jobs corrected, not product gates weakened; final67 includes both corrected tests |
| CPU optimizer/checkpoint resume | 2 PASS,7.92s | `test_screen_correction_training.py`; actual tiny optimizer, detector changes and grid-only freeze, exact resumed sequence; also included final67 |
| Export dynamic shapes and actual parity | 2 PASS,14.70s | `test_screen_rescue_onnx.py`; tiny CPU graphs, both screen orientations and board192x320, relative1e-4;2 PyTorch legacy-export FutureWarnings |
| Proof→registered artifacts→inspector→runtime replay | 3 PASS,22.52s | `test_screen_rescue_proof.py`; actual tiny ONNX files/receipt/spec envelope/frozen source identity, damaged proof rejection;6 exporter FutureWarnings |
| Disposable PG migration | 1 PASS,20.84s | `test_screen_correction_migration_postgres.py`; additive functions, old bodies/permissions preserved, empty downgrade/reupgrade, history downgrade guard |
| Disposable PG closure and incomplete TRAIN | 2 PASS,53.19s | `test_grid_correction_registry_postgres.py -k screen`; RLS, closure rollback, partialREG, reconnect, invalid full TRAIN zero writes |
| Independent second v3 cohort on existing fixture labels/roles | 1 PASS,2 deselected,37.71s | same file `-k "screen and not invalid"`; added actual service prepare/capture/materialize/freeze/replay on existing sources and role ledger. Image/proof boundaries explicitly substituted as documented in test; not human-label accuracy evidence |
| Worker v4 full A / partialREG report restart | 1 PASS,5 deselected,4.69s | `test_grid_correction_evaluation_pipeline.py -k screen_report`; five partialREG photos/fifteen targets; repeated report bytes same; also included final67 |
| Existing API / training-handler regression | 54 PASS,5.98s | `s1157j`; additive default assertion/spec envelope fixture fixes, before final selector changes |
| Client HTTP wrapper | 4 PASS | direct WT `tsx --test packages/admin-api-client/test/grid-correction-learning-request.test.mjs`; no real requests |
| Client TypeScript | PASS | direct `tsc --noEmit`, cwd WT packages/admin-api-client |
| Admin TypeScript | PASS, isolated strict path configuration | existing `artifacts/task1156-preflight/admin-tsconfig.json`, extends real Admin config and maps SDK to this WT, incremental=false. Not the standard workspace invocation: junction would resolve root SDK |
| Python types | Zero new errors; one confirmed baseline error | scoped57 changed source modules, repo config + follow-imports=silent + temporary torch/torch.* skip. grid_training_runs.py:228 object not iterable matches shadow HEAD:199. Logs `artifacts/task1157-preflight/mypy-current.txt` and `mypy-baseline.txt`. Not global mypy PASS |

| Ruff format/lint | PASS | 72 changed Python files; `ruff format`, `ruff check --fix`, zero remaining findings |
| OpenAPI / generated drift | PASS | WT exporter `--check` and WT client `check-generated-client.mjs`; regenerated locally |
| Code map | regenerated and --check PASS | both CODE_MAP files from current source |
| docs:check | PASS | decision links, current-state window, startup44,658/45,000B, skill mirrors |
| git diff --check | PASS | no whitespace errors |
| Admin scoped ESLint | PASS | from apps/admin with its existing config; initial root-cwd attempt found no ESLint config and made no changes |

No broader test repetition is necessary for documentation-only finalization.

### Execution limitations and corrected failures

The first API TestClient attempts blocked in Windows asyncio socketpair creation before
any application request. A bounded faulthandler trace identified socket.accept in
Proactor initialization. Those processes were stopped; filtered process checks found
no surviving copies. The same scoped tests passed with authorized local IPC access.
This is an execution-environment limitation, not an application fix.

Earlier small fixtures exposed and fixed: injected evaluation engines incorrectly reading
production artifact paths; spec.json envelope vs payload interpretation; request-default
compatibility; and fake-test shape/metadata assumptions. No human GT, roles, policy gates,
tests or integrity checks were weakened for a green result. Corrupt new screen export
recovery now fails explicitly instead of silently resuming training.

PG harness creates its own uniquely named databases and owns cleanup in finally. It
uses existing ApiSettings owner configuration only for creation, without printing or
overriding credentials. The test bodies perform no writes to the operator database.
No operator migration, service restart, default assignment, operator-data training, operator-image inference,
GPU operation, merge or push was performed.

## Compatibility and recovery matrix

| Existing input | New screen correction behavior | Recovery |
|---|---|---|
| Historical grid-only cohort | mode blocker; old workflow unchanged | prepare/freeze a new full TRAIN/A v3 cohort for that already required game |
| Legacy screen cohort without v3 photoSplit/reference | SCREEN_HISTORY_CORRECTION_POLICY_REQUIRED, metadata-only rejection | reuse qualified GT through existing independent cohort prepare/capture/materialize/freeze with policyVersion=application-grid-corrections-v3 and whole imports; preserve old hash/roles |
| Current eligible v3 cohort on pinned base | allowed if exact required-game selection/full TRAIN+A/currentness agree | pin explicit cohortId+manifestSha256 |
| Historical v3 cohort on ancestor base | only if already verified by base publication and ancestry | preserve original base; no rebase or automatic newest choice |
| Missing/foreign/nonrequired/duplicate/stale/wrong family or incompatible base | reject, no silent scope narrowing | explicit valid replacement for the same required game |
| Last bounded T1 reading: full0 real data | canStart=false for detector | acquire complete qualified photos; separate grid-only remains available |

Independent cohort preparation does not require starting shared training, preventing
mutual startup dependency between two games. Its prepare endpoint already exposes v3;
T5 should surface this existing action in advanced settings. No fresh point authoring
is required for already qualified unchanged labels. New closure still checks currentness,
role protection, aliases and exact labels. Test fixture substitutions do not establish
that current operator data is full: T1's measured full0 remains authoritative.

## T4 / T5 handoff

- T4 uses `GridAssessmentDataset` for v3 REG (and its later independent B reference),
  partial targets preserved. TRAIN/checkpoint A are full and selection-exposed. No
  new role ledger; all-validation-v1 cannot be independent B. Future acceptance policy
  must extend T2's central `is_game_scoped_neural_acceptance` rather than bypass it.
- T4 runtime trigger hook is `execute_path(..., trigger=...)`; current routing permits
  only the existing `suspicious` function. Other callbacks return
  GRID_RESCUE_ROUTING_PROOF_REQUIRED without spending budget. New routing needs its own
  TRAIN/A and exported path proof. B selects auto-accept thresholds, not routing.
- T5 consumes raw/source `rescueExecution` contract grid-rescue-execution-v1. `identity`
  binds sourceSha256, operation pin/model, baselinePresetSha256, opencvVersion,
  preprocessingContract, positions,width,height. Each `attempt` has exact request,
  reservationSha256, resultSha256 (nullable), state completed/consumed_without_result;
  summary includes reasonCodes and canonical sha256. Stage request includes effective
  typed screen/crop geometry and board detection/quad with environment versions.
- This is a projection of immutable receipts, not an independent execution claim. A
  reserved-only attempt is not evidence of a tensor. T5 may reconstruct matrix/output
  shape/interpolation/padding/pixel/tensor hashes strictly from a completed request and
  original bytes; no second inference. Preserve T1 diagnostic-v1 semantics.
- T5 can send trainingMode/rescueVariant/historicalCohorts through the current wrapper.
  UI must explain excluded partial TRAIN/A, retained partialREG, and old-cohort reference
  blockers. It must not claim actual detector training or active rescue on current full0.

## Outstanding gates

Focused Opus R2 PASS closes the coordinator's durability requirement. Reports:
[R1](TASK-1157_AUDIT_ROUND1.md), [R2](TASK-1157_AUDIT_claude-opus-5-5.md).
Code and non-documentation source SHA remain identical to frozen R2 before commit.
Actual detector improvement, calibration and production activation remain unverified:
the last bounded T1 reading blocks them; no new operator-data scan was performed.
T2 residual P2 findings remain T2's documented risks,
not silently fixed or reclassified by this task.

## Single correction round after R1

- R1 P2-1 / coordinator P1: same-directory tempfile→flush/fsync→os.link no-replace
  publishes complete immutable receipts. No direct writes to the authoritative path.
  Before publication no CPU is authorized; after reservation missing result consumes
  the attempt. Ignored orphan temporary files do not become receipts. Corrupt/foreign
  committed evidence still fails closed. Process-crash durability is tested; no claim
  of storage-device/power-loss guarantees beyond the filesystem contract is made.
- R1 P2-2: same source/pin/environment/dimensions with only expected positions changed
  returns original cached baseline plus NEURAL_GRID_SLOT_BINDING_REQUIRED (existing
  auto-crop blocker) and summary GRID_RESCUE_SLOT_BINDING_REQUIRED. It retains old
  receipt identity, no rescue calls, no new budget, no overwrite. Actual drift fails.
- R1 P2-3: accepted residual. Synchronous inspect_rescue may extend the pin-admission
  transaction. Failure reason is not archived in the pin. No cache/transaction redesign
  without measurements; T5 must show unavailable/unknown rather than invent a reason.
- R1 P2-4: new composed test executes real prepare_split v3, GridCohortEvidenceReader
  capture/approval/render, exact lattice/hash, actual _capture label guard. Only SQL
  row/population/context and final publication boundaries are fixtures. Full TRAIN/A
  and partial REG yield identical hashes and used labels. Valid human GT drift in
  each role raises GRID_CORRECTION_LABELS_CHANGED before publication. This is not a
  new PG run or a human-label accuracy claim; persisted roles/transactions are covered
  by already executed disposable PG checks.
- R1 P2-5: documented checkpoint ranking as the selected recognition pipeline from
  original photos, including an admitted rescue path, bound to that bestStep and its
  exposure/export path proof. Baseline wins ties; B/REG never choose this pipeline.

Correction verification (no repeat of the67-test suite):

| Check | Result |
|---|---|
| Real reader/capture + rescue store contracts | 21 PASS,8.43s; `test_screen_correction_reader_contract.py` + `test_screen_rescue_contract.py`, `artifacts/s1157r2a` |
| Runtime actual tiny ONNX proof + alias replay | 1 PASS,2 deselected,10.92s; `test_screen_rescue_proof.py -k runtime`, `artifacts/s1157r2b`;2 known exporter FutureWarnings |
| Ruff format/lint | 4 modified/new Python files, PASS |
| Mypy runtime | PASS,1 changed source file, same limited repo config/follow-imports=silent |

The controlled child processes use os._exit at before-fsync, before-reserve-publication,
after-reservation and before-result-publication points; all terminate with expected
exit71. Fresh processes/stores reuse spent reservations. Unrelated empty/truncated/
foreign receipts are not reclassified as normal crash success. No operator data read,
DB connection, service, real-image inference or training was added in this round.

### Accepted R2 limitations — no third code/test round

- P2-6 / T5: alias summary entries with GRID_RESCUE_SLOT_BINDING_REQUIRED belong to
  the original `identity.positions`. Even completed entries were not applied to this
  alias occurrence, whose returned detections are baseline. Mark these attempts as
  another scope; never display them as this alias's actual network input. No contract
  change or second inference is needed.
- P2-7: artifacts require NTFS/same-volume hard links. Root confirmed D: NTFS by
  read-only DriveInfo. No directory fsync or power-loss guarantee. Orphan temporary
  `.rescue-pending-*` files are ignored and may accumulate; safe GC is outside scope.
  Unsupported filesystems fail closed. No cleanup of operator files was performed.
- P2-3 remains documented: synchronous inspection may prolong admission and its
  unavailable reason is not archived; T5 must show unknown rather than reconstructing
  a fictional historical reason. No cache/transaction redesign without measurements.
