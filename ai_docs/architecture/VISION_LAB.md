---
title: Laboratorium geometrii i symboli — architektura
status: accepted
last_updated: 2026-11-03
---

# Architektura laboratorium wizji

## Compact status and input replay (TASK-1159, D-588)

Existing assignment GET exposes current-game `recognitionStatus`; existing
reinference/proposal reads expose frozen-operation status. These typed projections
reuse exact per-game publication/calibration evidence and never prepare pins or
write qualification. No raw operation pin or private artifact path is added.
Runtime completeness measurements are described as measurements, not human GT.
The catalogue session stays unbound; current evidence is read in a separate game
READ ONLY transaction with explicit READ routing. Expected projection failures
yield unavailable/nullable capabilities without failing the existing assignment.

The local Reviewer optionally browses ordinary boards through the same list API
(`view=all`, optional source filter) and guarded editor. Explicit unchanged-node
save produces `geometry_saved`; it is not a quality measurement or a symbol
approval. The existing human-evidence reader decides GT, and full-photo readiness
requires all nine qualified physical slots. Existing protected data roles remain.

The shared learning path has an explicit v4 opt-in, retaining the legacy mode helper
and historical payloads. Advanced A/B/buffer choices use server-projected exact
copy/component closure and shared constrain/refine protection checks. No new role
store, split solver, automatic B allocation, minima or budget is introduced. Preview
is readonly; assignments and policy are included in the sealed parent/child split
identity and atomic freeze. Current and historical v4 costs/checkpoint selection
count A only; B remains an independent calibration population. Missing B does not
prevent an otherwise admissible training run or manual proposals.

`geometry_core/input_diagnostics_v2.py` separately replays exact completed rescue
requests using their typed override, full baseline preset, source/model/OpenCV and
canonical inputRaster/support. Missing raster, incomplete reservation and foreign
slot scope fail visibly. A crop request is shown only for its exact physical slot.
The v2 file index independently archives sequenceNumber; absent or mismatched
current target sequence yields unavailable. Redetect is labelled screen input
and has no board margin. An approval revision alone is not a human GT claim.
V1 decoder/payloads are unchanged. The file-backed comparison renderer uses
`images/comparison_input_diagnostics.py` to verify archived v1 stage RGB/tensor bytes
or replay v2 against the actual raster. It never substitutes a former full original
for a managed-crop canvas. No online image endpoint or inference is introduced.

### File index contract for request diagnostics v2

The comparison renderer optionally reads `diagnostics/index.json`, a list of
entries with required `sourceId`, `positionIndex`, `sequenceNumber`,
`modelVersionId`, `record`, and `actualRaster`. The source/physical position/model
must select exactly one entry. Its archived integer sequenceNumber must match the
current report board; it must not be derived anew from that current board.
`record` is a report-relative path to the strict checksummed v2 JSON envelope.
`actualRaster` is a report-relative NumPy `.npy` file loaded with allow_pickle=False:
an RGB uint8 array with shape **(record.source.height, record.source.width, 3)**,
not a model-stage tensor, encoded preview, or presumed former full original.
For a managed crop it is the actual canonical canvas used by the completed request,
including its recorded support/padding. Source bytes, inputRaster pixel SHA,
validBox, exact request, preset/model/OpenCV and stage RGB/tensor SHA are verified
by the existing consumer. Both paths must remain inside the report directory.
Missing/ambiguous entry, absent sequence, missing raster, shape/dtype/hash or
request mismatch yields unavailable; no producer, inference or guessed fallback
is introduced. V1 keeps its existing record/pixel contract unchanged.

## Completeness and calibration (TASK-1158, D-587)

Alembic `0181_validation_purposes` adds nullable `validation_purpose` to the existing
immutable `recording_photo_uses` ledger. SQL v8 projects every old v6/v7 JSON field
explicitly, preserving old proof bytes. New context v3/photo-cohort v3/command v5 use
purpose-aware proof inputs. Insert fences and `recording_training_scope_v1` prevent
fresh legacy selection of B, including worker resume. Domain split refinement reuses
the existing solver/components/buffers; explicit A/B assignments do not optimize the
holdout. Corrections/split/snapshot v4 materializes purpose and exact labelled targets.
The existing GridBoardDataset exposes A; GridAssessmentDataset exposes partial B/REG.

`full_board_completeness` measures geometry, confidence, actual input support and
agreement without NN execution. `CalibrationObserver` observes the existing evaluator's
single result pair and human matching. `FullBoardCalibrationRun` persists A/menu before
B, B/sealed configuration before REG, then a bounded sidecar with exact observations,
source/target revisions, role proofs and checksums. The existing evaluator job/report
store/currentness remain authoritative. Missing data produces an explicit unqualified
automatic state without changing the raw quality gate. No new workflow or role store.

Observed source UUID/pixel SHA/slot/GT SHA and counts must exactly equal the independently
pinned frozen assessment before deduplication. API resolves the cohort through the
report and DB header, then reuses the strict snapshot/dataset adapters. Worker checks
the same membership during prepare, finish and resume. Self-rehashed sidecar omissions
or substitutions cannot redefine the assessment. Unreleased T4 sidecars missing the
required source identity/reference fields fail closed; released formats are unchanged.

Report read v5 wraps raw report v3/v4 and its unchanged gate v2/v3. The strict reader
validates both parts; the operation qualifier also verifies sidecar bytes, recomputes
the numeric sweep and checks the exact game/profile. Pin v3 and acceptance v4 extend
all existing strict policy guards and SQL exact IMPORT/VALIDATE lookup. Result evidence
binds source, model, pin, profile, detection and fitted-node SHA; worker and API prewrite
use the same checks. Historical pin v1/v2 retains acceptance v3 on retry.

`grid-checkpoint-input-v2` names exact purpose-A input. The existing screen evaluator
validates `grid-rescue-exact-slots-input-completeness-v2`: old guards plus fitted-cell
input-support violation, with complete board preset and A-input SHA. Old proofs retain
their routing. Other B thresholds never trigger recognition. New calibrated raster
checksum/available box bind both raw cache and the existing RescueAttemptStore identity;
drift rejects the same directory before reading baseline or spending new attempts.
Evaluator and runtime use the same `calibration_routing_sha` normalization formula.

`register_grid_diagnostics.py stage` strictly validates T1 record SHA, archived full
preset and preprocessing version, producing metadata only. Explicit approved deployment
executes `recording_diagnostic_use_v1` atomically in the existing ledger/receipt store.
Duplicate record bindings replay; diagnostic closure blocks new B/REG. Late registered
exposure invalidates existing dependent report bindings, without rewriting past roles.
The private operator staging payload is not part of Git or external audit packages.

## Detector corrections and bounded rescue (TASK-1157, D-586)

`application-grid-corrections-v3` / `application-grid-snapshot-v3` use
`screen-grid-corrections-v1` preset v3 and split `grid-correction-split-v3`.
The existing split solver applies full qualification per role, not to the global
population: full TRAIN/A, partial REG via `GridAssessmentDataset` and the explicit
`human-labeled-targets-v1` purpose. `CohortPhotos` rejects missing full used targets
instead of filtering them. Source, label, split and currentness hashes bind preview,
parent, child, export and report. `historicalCohorts` replaces only already required
other-game pins; new cohorts can be prepared and frozen through the existing cohort
API before either game's shared run. Legacy cohorts without v3 photoSplit fail with
`SCREEN_HISTORY_CORRECTION_POLICY_REQUIRED`; no legacy hash or role is changed.

The existing SCREEN_GRID_V1 network, ScreenGridBatches and photo evaluator implement
the new mode. Binding v3 and `photo-board-checkpoint-state-v1` preserve the photo/board/
error/earliest ordering. `grid-checkpoint-input-v1` with `all-validation-v1` records the
exact frozen USED VALIDATION source/label set. The evaluator checks actual materialized
input equality. It is selection-exposed A, not independent calibration B. Report
`grid-model-evaluation-read-v4` / gate v3 is separate from historical report v3/gate v2.

`geometry_core/rescue.py` defines closed typed overrides without widening the historical
ScreenPreset Literal768. `grid-rescue-recipe-v1` binds one variant and baseline preset.
The trainer alternates baseline/variant optimizer steps, confirms exposure only after
a non-skipped optimizer update, and snapshots exposure at bestStep. The original-photo
evaluator measures each allowed path with shared `grid_rescue_strategy.execute_path`.
`grid_rescue_export.py` compares real PyTorch/ONNX tensors at admitted shapes, including
screen dynamic axes; graph metadata alone is insufficient. Stage/subnet factorization,
input hashes, path coverage, A metrics, weights, checkpoint, spec envelope and receipt
must agree. The artifact inspector rechecks frozen TRAIN/A membership and actual graphs.
Cost admission includes variant canvas/scale, extra path assessment and peak VRAM;
the existing cumulative 8000-step/7200-second ceiling remains unchanged.

The selected path is fixed before inference. Checkpoint metrics rank that selected
original-photo recognition pipeline, baseline or an admitted A rescue path. Export
binds the checkpoint to its own bestStep/exposure/path proof; B/REG never tune it.
`grid_rescue_runtime.py` publishes fsynced temporary files using same-directory
no-replace hard links under operation/source, independent of variant SHA. CPU begins
only after publishing the complete reservation. A pre-publication crash leaves only
an ignored temporary file; reserved without result is consumed. Same-byte aliases
whose identities differ only in expected positions read the original baseline and
receipts, spend no rescue tokens, and carry the existing blocking slot-binding reason.
Source/model/pin drift and corrupt committed receipts remain hard failures.
Exact slot binding and the original trigger
`grid-rescue-exact-slots-fit-or-pixels-v1` are mandatory. An alternate callback returns
`GRID_RESCUE_ROUTING_PROOF_REQUIRED` without computation. T4 must version routing and
validate it on TRAIN/A before enabling completeness-triggered paths; B only chooses
acceptance thresholds. Missing routing proof leaves manual correction.

`rescueExecution` is a projection of these receipts (`grid-rescue-execution-v1`), not
another ledger. Its identity binds source/model/pin, baseline preset, OpenCV and
`neural-grid-rescue-preprocessing-v1`; requests record actual typed geometry and exact
board quad, reservation/result hashes, completed/consumed-without-result state and
reasons. The worker child validates preprocessing/OpenCV versions before execution.
T5 can strictly reconstruct transform/output/padding/interpolation and pixel/tensor
hashes from a completed request, without another inference. Reserved-only entries
cannot be labelled as actual analysed inputs; T1 diagnostic-v1 remains unchanged.
For an alias with `GRID_RESCUE_SLOT_BINDING_REQUIRED`, completed attempts in this
summary belong to the first scope (`identity.positions`), not to this alias occurrence.
They were not applied to its returned baseline. T5 must mark them as another scope
and must not render them as this occurrence's actual network input (R2 P2-6).

The artifact volume must support same-volume hard links; Windows deployments require
NTFS (root confirmed D: as NTFS by read-only DriveInfo). No directory fsync or power-loss
guarantee is implemented. Process crashes may leave ignored `.rescue-pending-*` files;
their GC is outside this task and must not delete active attempts. Unsupported filesystems
fail closed. These R2 P2-7 limits are accepted, without changing the receipt contract.

Alembic 0180 adds `recording_photo_cohort_v2`, `recording_correction_report_bind_v2`
and dispatcher `recording_cohort_command_v4`, preserving historical function bodies.
Runtime has only the public command capability; new private functions keep fixed
owner/search_path and no PUBLIC execution. Downgrade refuses existing v3 cohort history.
Migration is prepared/tested on disposable databases, not applied to the operator.
The artifact inspection currently runs synchronously inside operation-pin admission;
graph/source checks can extend its session duration. Its unavailable reason is not
archived in the pin. This P2 is accepted pending measurement: T5 must distinguish an
unknown historical reason from a fresh inspection, without a speculative cache.

## Operation capabilities and per-game evidence (TASK-1156, D-585)

`domain/neural_grid_operation_pin.py` adapts catalogue-v1's historical axis names:
boardRows is the horizontal count, boardColumns the vertical count. Logical
capabilities are board rows3/columns5 and page rows3/columns3. Original descriptors,
proposal snapshots v1/v2 and their hashes remain unchanged.

New preflight-v14 and engine-acceptance-v3 carry a strict top-level operation pin:
game/model/manifest SHA, capabilities, topology rules ID, qualification policy,
exact report/publication evidence or unqualified, and canonical pin SHA.
`storage/neural_grid_operation_qualification.py` reuses the publication reader,
per-game evaluator contract and D-559 currentness. It never substitutes the mutable
default/assignment for an old execution. Worker and API recheck; the API checks
before automatic write in the existing source transaction. Evidence loss returns
blockers; infrastructure failures propagate. No new qualification/GT/role table.

Acceptance-v3 maps to crop-v2. Legacy preflight-v13 and acceptance-v1/v2 preserve
their interpretation. Public job schemas recognise v14/v3; internal pins are
omitted from transport without adding None fields to historical payloads.
Admin recognises both preflight versions. T4 requires a later qualification policy.

For a trusted acceptance-v3 job, `project_source_geometry` always appends the new
revision as `needs_review`, regardless of worker `ready`, engine kind or claimed
manual source. Only the authoritative recognition finalizer can later promote
it to `accepted`, after the exact game evidence recheck. Promotion changes the
status without rewriting sealed geometry. Other policies and manual writers
retain their existing behavior.

Stable import identity removes only the operation/policy pins, derived pipeline
fingerprint and derived base-manifest hint. SqlAlchemyJobRepository performs an
exact game/type/JSONB comparison under acquire_job_admission(require_idle=False)
before any new evaluation resolution and retains that transaction lock through
persist. A two-row cardinality probe fails closed on ambiguous identities; it is
not a history window. Repeating the same input freezes the original qualification.
To consume new evidence, prepare new explicit grid reinference or change the
explicit source/model/preflight; T5 must expose this operator guidance.

is_game_scoped_neural_acceptance also blocks the worker-metadata human approval
stamp for strict jobs. Availability metadata remains diagnostic; geometry approval
is created only by the existing real manual server command. Production workflow
constructs its stage suite through _new_stage_adapters, which performs the real
exact-evidence recheck and forwards its tuple of blockers without replacing it.


## Input replay and readiness diagnostics (TASK-1155)

`geometry_core/input_diagnostics.py` defines the strict
`full-board-input-diagnostic-v1` envelope and reuses production `screen_input`,
`board_rectifier` and `crop_board`. Each stage binds its exact RGB bytes and
little-endian float32 tensor values; screen uses NCHW, board stores the CHW
sample before stacking. JSON contains checksums and metadata, while PNG/NPY
remain operator artifacts outside domain tables. Replay checks the envelope,
canonical source, decoder, OpenCV version, dimensions, transform and both hashes.
The entire `archived_preset` is retained and its canonical checksum must equal
`model.preset_sha256`; screen/board settings and the known preprocessing version
must also match. Bundle byte checksum remains a separate capture-time pin.

`scripts/diagnose_full_board_input.py` exposes capture, replay, readiness and frozen counts.
Capture does not load ONNX or invoke a runner. The saved-comparison adapter
requires an explicit source/sequence/position binding, a unique exact match
of saved board nodes to the baseline, and a unique equal detector quad in
the candidate. It never maps sequence by detection order. Missing correspondence
fails; candidate correspondence is diagnostic evidence, not a new operational
sequence binding. Policy blockers reuse T0; no diagnostic result authorizes
acceptance. Historical disposition, policy projection and unknown GT are separate.
Capture files are flushed/fsynced before exclusive Windows directory rename.
JSON reports use a flushed/fsynced temporary file and no-replace publication
(Windows rename; exclusive hard link on POSIX). Capture directory publication
is explicitly Windows-only. Existing destinations are never overwritten, even
after a race. Interrupted staging is not a completed capture; Windows directory
fsync and physical power-loss durability are not promised.

`storage/grid_diagnostic_readiness.py` routes a repeatable-read, read-only
transaction through the existing game router and calls `GridCohortEvidenceReader`.
Explicit `max_sources`, a UUID keyset cursor, statement/deadline limits and
one-source-at-a-time qualification bound the operation. Larger budgets are
caller choices, not schema limits. `partial` and `populationComplete=false`
prevent truncated/continuation counts from masquerading as a population report.
The frozen command streams the existing checksummed GridCohortSnapshot metadata
without reading pixels; label/full-photo counts include only used sources and
complete counts must match the manifest. Its counts remain historical. Only
`SOURCE_REPLACEMENT_RETIRED`/`GRID_COHORT_SOURCE_REMOVED` become explicit
`rejectedSources`; other reader/SQL failures and deadlines abort the report.
`selectedSourceCount` includes rejected sources, `sourceCount` counts successful
captures, and the cursor advances across all selected sources. Nominal counts
include rejections; qualified counts do not. This is the nominal-current-human
population, not the entire library. Full human annotation and
unassessed role eligibility have separate fields; no role is invented.

The report's `diagnosticUse` is an input proof for T4, not a second role ledger.
Only images actually used for diagnostic comparison enter it. Metadata readiness
access is marked separately and does not itself exclude controls. T4 must consume
the proof and close existing copy/group relations before independent controls;
T1 does not yet enforce that later qualification or mutate historical roles.
The stable `deduplicationKey` hashes version `diagnostic-use-key-v1` plus
source ID, byte SHA, normalized pixel SHA and purpose. Each use retains unique
`recordSha256` bindings with `sequenceNumber`/`positionIndex`. T1 deduplicates
within a report; T4 must union by that key and record SHA across reports before
applying source/copy/group exclusions, rather than counting exports as new uses.
Pre-release R1 records retained for audit share the v1 schema identifier but
lack the required archived preset. They fail strict decoding with a generic
ValidationError; there is no distinguished migration or compatibility code.
T4 must accept only complete strict-contract/checksum-valid records and must
never infer a missing historical preset (accepted TASK-1155 R2 P2 limitation).

## Explicit correction apply (TASK-1122)

The game/learning-scoped `/grid-correction-learning/{learning_id}/apply` API exposes
GET preview/list/status and explicit POST start/resume. Closed request models,
OpenAPI, the generated TypeScript client and request tests share one contract.
`application/grid_correction_apply.py` reuses the registry publication/assignment
services and the existing jobs table with `learning_kind=grid-correction-apply-v1`.
Payload validation and the worker dispatcher separate apply from the unchanged
learning parent. Learning lists and identity lookups filter the discriminator.

TASK-1152: each newly claimed apply lease checkpoints the persisted progress counters instead of zeroing successes from earlier steps. Waiting and failure/resume retain those counters; the final success count still derives from completed durable steps. Domain monotonicity checks and registry receipts remain unchanged.

The immutable preview pins the candidate descriptor, main report and scope, default
revision/version and every selected assignment. Start requires its digest and the
human photo-only acknowledgement. Independent actual-assigned comparisons run
before publication when a selected game's assignment differs from the learning
base. Their trusted report, descriptor, assignment revision and cohort currentness
are verified separately; they never replace the main publication report.

Each comparison/publication/default/assignment step has a deterministic command
identity and an independent transaction. Durable checkpoints and registry receipts
recover the commit/checkpoint gap after restart or response loss. Waiting releases
the general lane. A failed later step preserves earlier receipts and can be resumed;
there is no compensating automatic rollback. Registry locks protect default and
assignment CAS. A changed default revision of the same base permits a fresh preview;
a different base blocks the old candidate until new applicable evidence exists.
Read endpoints never advance jobs. Existing history/rollback routes remain the
authority, and neither apply nor rollback recrops existing imports.

R1: publication adoption checks the exact canonical evidence and its checksum,
report identity and descriptor pins under the registry lock. An identical
already-published candidate completes the step with a deterministic receipt in
the parent checkpoint; it creates no publication event. GET can recover that
receipt from the immutable publication row after a checkpoint gap. Different
evidence fails both preview and advance. An active apply of the same learning
blocks a second start under the registry lock; failed operations retain their
history without blocking a fresh CAS-pinned preview. Resume of created,
processing or completed operations returns the existing view without requeue.

TASK-1123 also checks the active-operation guard when resuming a failed/cancelled
apply, under the same registry lock. GET adoption requires all preceding comparison
steps to be completed. A conflicting external publication remains a command blocker,
but leaves the historical publish step pending instead of failing the whole read.
Corrupt own receipts and other unexpected failures still fail closed.

TASK-1138: the Admin learning panel accepts each GET result independently. The
workflow list/detail/report is not gated by the slower readiness calculation;
allSettled collects read errors without dropping successful history. A read
sequence and selection generation discard superseded/unmounted answers. Refresh
has its own busy state and synchronous click guard; command locking and durable
POST intents remain separate. A failed list still re-reads the explicit selection;
retained reports must match the selected evaluation identity. Successful full reads
show a timestamp; no read
starts training, publishes or activates a version.

TASK-1140: readiness renders the additive backend `progressCounts` without
reconstructing the split in React. TRAIN board counts distinguish exact labels
in frozen TRAIN sets from new labels, without claiming completed model training;
their photo counts may overlap. Unlabelled
control reserves remain separate from measured controls and their minima.
Buffer photos may include unlabelled sources, while exclusions use the backend's
own scope and reason counts; the UI does not sum these categories.

The guided panel explicitly calls `verifyGridModelEvaluationCurrentness` only
on a click for a completed evaluation with a report, then re-reads the pinned
learning evaluation and the apply preview. Failed reads stop their loading state,
retain the new-apply block and show the explicit refresh retry path.
A separate synchronous command guard and generation reject duplicate clicks,
superseded selections and answers after unmount. Pending verification and
unconfirmed/failed evidence block new apply commands. Durable matching command
replay and operation resume still reach the backend's authoritative validation.
A later authoritative evaluation GET
can reconcile response loss; panel entry never retries a POST. Apply previews
carry a read identity including scope and evidence refresh generation, so an
old optimistic response cannot restore a stale preview or its confirmation.

## Incremental correction split (D-582, TASK-1139)

`domain/grid_correction_incremental_split.py` implements deterministic protected
islands with the existing attestation/component preparation. New learning selects
policy v2 explicitly; v1 preparation and immutable snapshot interpretation remain
available. Snapshot v2 accepts both exact policy identifiers.

Alembic 0178 adds append-only release evidence to the same private recording registry
and labels new reservations `incremental-v2`. The v2 context closes known aliases
and sessions before deciding whether every legacy reservation is releasable.
Its bounded preview is read-only. Existing cohort commands validate the pinned proof
under registry locks, then append releases and uses in one transaction. Runtime
cannot read or write release rows or call the internal context function directly.
Historical v1 validation retains every original binding, checking active role
conflicts for actual used examples and buffers instead of released unused metadata.
New v2 controls and buffers remain hard protections.

TASK-1145 renumbered the undeployed growth migration from 0172 to 0178 after
deployment coordination. Historical audit reports retain 0172. TASK-1147 attaches
0178 after 0177. The shared replacement SQL helper preserves the exact 0175 guard
and current-source population filter for both v6 installation and legacy downgrade.

Reserve candidates require current source-available `grid_issue` evidence bound
to the live board geometry revision. Pending correction is fenced only before
freeze; historical population hashes retain identity/order facts and never include
mutable pending status. Correcting an unused or reserved photo therefore does not
invalidate older actual labels merely because its queue state changed.

`domain/grid_correction_progress.py` derives counters from the same representatives.
Previously used labels are compared to complete frozen TRAIN label documents;
new positions or revisions therefore remain visible. Photo counts can overlap
between used/new TRAIN, while board counts partition available TRAIN.

## Photo-only correction split (D-577, TASK-1120)

`domain/grid_correction_split.py` implements bounded exact one-to-three-block
partitioning over complete imports, with alias/session components, verified
attestations, explicit fallback and stable ties. It deduplicates photo counts and
chooses the representative with most current labels. Limits are 5000 sources,
three million work units and 100000 candidate/state records; exceeding any limit
fails without shrinking the population or returning an unproven optimum.

`storage/grid_correction_split.py` reads own-game metadata, obtains exact labels
from `GridCohortEvidenceReader`, and asks the existing recording capability for
known protections. The opt-in policy extends existing prepare/capture/materialize/
freeze/currentness commands. Immutable cohort documents and snapshots pin the full
population, methods, ranges and buffers. No separate training dataset is invented.
Metadata preparation does not copy images or permanently consume roles.

Alembic0170 adds private append-only `recording_photo_uses`, including BUFFER rows,
owned by the existing nonlogin capability. Runtime receives only a bounded own-game
context reader; final use dispatches through the existing v3 cohort command.
Every assigned source is reserved; `used_in_cohort` distinguishes examples from
metadata-only reservations, which copy no image bytes. All roles are checked before any insert; failure rolls back roles and buffers
together. The v3 wrapper checks only new photo reservations; legacy recording semantics
remain in the family-aware v3 implementation.
Currentness checks the complete selected population and known byte/pixel/session
protections. Unknown historical providers remain visible as photo-only limitations.
No new schema partition or image binary storage is introduced. Training and report
adapters are delivered separately by TASK-1121; old snapshot consumers stay strict.

## Correction learning pipeline (D-578, TASK-1121)

`application/grid_correction_learning.py` composes the existing cohort, shared run
and evaluation services. The public game-scoped `/grid-correction-learning` API
offers ready, preview, start, list/status, cancel, resume and evaluation reads.
Alembic0171 adds the parent job type and an internal scoped-report binding capability.
The worker executes one durable parent step per claim, saves its checkpoint and
releases the general slot while a child runs. Claim skips parents with a pending
child; child creation remains possible while the parent holds that slot. A separate
advisory step lock serializes cancel/resume/create without locking the heartbeat row.
Deterministic child/cohort command keys adopt existing results after response loss.
Freeze expands and deduplicates the used members' board/review/cell identifiers
before joining their game-scoped tables (TASK-1135). It locks the same targets
in ascending identifier order with `FOR UPDATE OF r`; it does not compare every
game cell with every member array. Existing deadlines and other input locks remain.
TASK-1149 consumes each ordered lock cursor with `fetchmany(200)`. It refreshes
the remaining SQL timeout before every fetch and checks the clock after the
batch, instead of issuing timeout SQL for every row. Cursors close on completion
or failure; sequence locks remain individual and ascending, with their SQL
protected by the existing execution hook. The 60/30/5-second limits are unchanged.
Step-lock contention maps to `GRID_LEARNING_BUSY` (409). Resume rejects an active
child still acknowledging cancellation; after acknowledgement it reuses that child.
HTTP exclusions are canonicalized before preview hashing and idempotency commands.

The split adapter preserves measured solver counts in a typed cohort error;
parent preview converts these to `dataAvailability` without parsing messages or
reading sources twice. Successful previews count the existing deduplicated source
representatives, including annotated buffer photos. The pure domain function derives
aggregate minima/deficit lower bounds from the solver's own role minima. This adds
no second evidence source and changes no persisted split document or its SHA.

`application/grid_correction_history.py` composes earlier published cohorts from
verified report IDs, descriptor hashes, ancestry and currentness proofs. Original
cohort base descriptors and snapshot hashes remain unchanged. The new shared-plan
version permits these verified historical bases; legacy plans still require one base.
Each required earlier game contributes its frozen TRAIN and controls. Unknown
sessions are photo sampling units, never newly invented recording rows or proof of
independence. Existing protections and cross-game byte/pixel/group alias checks apply.

Snapshot v2 is paired exactly with the corrections policy. The versioned preset
selects checkpoint metrics in `training_core/grid_correction_metrics.py` and exports
selection evidence in the checksummed training bundle. Report v3/gate v2 live in
`domain/grid_correction_evaluation.py`; publication dispatches by strict version and
retains all currentness gates, while scoped reports do not require unrelated family games.
The existing publication service checks scoped `set_default` against the current
default's version under its registry lock. Own receipt replay precedes this guard;
the candidate's unchanged publication evidence remains reusable for other controls.
The registry binds report SHA and cohort proof SHA atomically through the existing
cohort-command wrapper. Its internal definer has only required catalogue-column reads;
runtime roles receive no direct execution grant on the new binder.

`POST /grid-model-evaluations/assigned-comparison` resolves the actual assignment
server-side and starts the existing evaluation worker with separately pinned baseline
fields. `grid-model-assigned-comparison-v1` is a distinct report type, never eligible
as the main publication report. The shared evaluator performs real baseline inference
on the same cohort; TASK-1122 owns apply receipts and final assignment/currentness CAS.
Legacy snapshots, checkpoint rules, reports and publication gates remain available.

## Larger local symbol experiment (D-506)

Three explicit local modules isolate the multi-reference adapter, RGB protocol
and runner. They reuse SymbolTrainingInputs and neutral RunManager(state_type),
RunControl and symbol_training. Local Configuration/Request/RunState provide
7200-second/50000-step bounds; public types and registries remain unchanged.
The distinct symbol_protocol_digest is serialized into canonical_request and
checkpoint fingerprints while protocol_digest remains None. An immutable run
root prevents admission through a second directory. Strict current source,
dictionary, proof/review/PNG/quad and whole-photo exclusion bindings survive
each start/checkpoint/finish. The local runner additionally verifies real export
artifacts and best epoch. Earlier consumers keep the identical default BOOT,
augmentation, contracts and workflow.

The adapter binds the exact accepted R2 qualification SHA, manifest ID and path.
Per-composition decoded-source caching preserves independent quad rendering.
Per-process validated inputs are private defensive copies; first validation always
recomposes, and subsequent calls still recheck every live/bundle hash and manifest.
Endpoint and shared-ancestor reparse checks run before and after hashing without
deduplicating declared SHA pins by Windows case-insensitive Path equality.

## AI experimental adapter (D-505)

An explicit separate symbol_ai_experiment format composes the fully validated
feedback base with conservative AI review targets and exact source-bound PNGs.
It reuses SymbolTrainingInputs and durable SymbolRunManager via optional format
dispatch; strict D-498/D-502 adapters reject it. Generation4 is isolated from
production and prior runs. The manifest pins both reviews, source batch and
all rasters; human validation remains byte-identical. Human feedback weight4,
AI weight1 and withheld photo isolation survive checkpoint/RNG replay.
An optional exact human-feedback pack preserves current decision/history/source
bindings. It contributes original human targets at weight4 and excludes every
human-reviewed raster from AI targets. Photos with human-training targets cannot
enter the AI audit; no human store is mutated by the experimental adapter.

## Feedback batch context and review provenance (D-504)

`symbol_batch_inputs` dispatches only explicit generation3 to the qualified
feedback adapter, resolving persisted physical image bindings and retaining
all external SHA/photo-pixel exclusions. Batch freeze requires a checked
evaluation and recomputes current/base validation from pinned actual reports.
V2 default keeps exact geometry-reference reuse; `--fresh-geometry` explicitly
requests fresh geometry on a new recording. Existing generation1 inputs stay
byte-compatible. Outputs cannot overlap any added baseline/input root.

Generation3 batch-review preparation validates the composite cohort, then checks
dictionary equality with the original D-498 approval provenance. The packet
pins base live metadata/history, immutable cohort/batch and exact case sources;
it does not copy the full2,052-image feedback inventory into the UI read/write
validation loop. Exact source/PNG/re-render and current-history gates remain.
Old references/default consumers are unchanged; no HTTP/schema changes.

## Persisted source location (D-503)

`symbol_feedback relocate` publishes a create-only checksummed sidecar
`<manifest_id>.sources.json`, bound to the complete qualified inventory,
original folder and actual source root. `SymbolFeedbackAdapter` discovers it
in each new process, verifies full names/SHA before feedback pixels and retains
the original logical paths in reconstructed manifests/decisions. Only direct
image reads may relocate; labels/catalog/bundles cannot. All exact rendering
and live history checks remain. The manifest/checkpoint/run settings stay
unchanged; output guards include the actual root. Removal/drift of the persisted
configuration cannot be masked by a prior in-memory location. This avoids
symlinks, image moves and duplicated training attempts.

## Exact crop feedback adapter (D-502)

The optional local symbol_feedback CLI freezes latest reviewed PNG rasters
with full original decisions and source-bound quads. Its classifier-only
symbol_crop_feedback manifest composes validated D-498 inputs and exact
batch-crop targets without changing either original store or whole geometry.
SymbolFeedbackAdapter verifies metadata before pixels, complete old/current
graphs plus full-folder SHA aliases, operator recording declarations, exact
re-rendered PNG identity, history, inventory, counts and live bindings.
It returns existing SymbolTrainingInputs; the default D-498 adapter does not
accept this format. Local run dispatch selects this adapter by explicit format.

The new split moves first-recording components to diagnostic_test, retains
original validation and admits the new folder only with confirmed independence
from validation. The separate bundle contains source-bound crop decisions;
original origins/trainable flags and all prior artifacts remain unchanged.
Generation3 reuses the durable run protocol and augmentation, with a persisted
weighted sampler driven by the existing checkpointed generator. Unique cohort
metrics and effective draw counts are reported separately. Diagnostic-test
evaluation follows final epoch selection and cannot alter training/calibration.

The generation-3 local registry requires the D-502 purpose. Its versioned
replacement sampler gives approved feedback weight 4, drawing 318 samples
from 264 unique development crops. Both sampler and loader share the persisted
generator. Final reports isolate feedback regression and diagnostic predictions.
`evaluate_frozen_fusion` only applies existing validation temperatures/weight;
it cannot select or calibrate on these additional labels. Missing pinned source
files invalidate admission/checkpoint verification; an immutable crop copy is
not permission to bypass the current source-integrity gate.

## Pakiet kwalifikacji symboli (TASK-0853)

CLI `vision_lab.symbol_preparation prepare|verify` tworzy osobny niezmienny
`lab-symbol-preparation-v1`, bez mutacji geometrii/symbolstore i bez API.
Budowa używa istniejącego geometry-first lock, grantu D-496 i local_row;
rola/protected sprawdzane są przed crop bytes. Kopiuje oryginalne PNG,
pełną kopertę symboli, metadata komponentów oraz raport bramek.
Create-only publikacja następuje przez rename kompletnego sprawdzonego
katalogu na tym samym wolumenie. Retry weryfikuje gotowy pakiet; częściowy
staging nie jest sukcesem. Verify kontroluje manifest, inventory, byte/pixel
SHA, decyzje względem pełnej historii i raport. Format ma qualification_only,
trainable=false i brak assignments; nie jest wejściem obecnego treningu.
Ścieżki CLI są absolutne, output nie może nachodzić na magazyny wejściowe.

## Integracja shadow V3-D (D-495)

CPU inference i czysta geometria trafiają do neutralnego `geometry_core`;
lab zachowuje kompatybilne wrappery. Produkcyjny handler nie importuje
anotacji, runów ani snapshotów labu. Registry i ManagedGridEngineModelStore
weryfikują zamrożony model bez fallbacku.

Jawny VALIDATE kind `grid_geometry_shadow_v3` korzysta z istniejącego lease,
heartbeat, checkpoint i fencing. Pin obejmuje SHA/wymiary/managedpath,
sourceRevision, boardRevision/resolutionRevision, sloty i model. Wynik ma
osobną tabelę gry `image_geometry_shadow_results`, manifestv5, LIST(game_id)
i RLS także na child. Publikacja wyniku nie modyfikuje geometrii produkcyjnej.
Odczyt ponownie porównuje bindingi, a stale blokuje correction handoff.

Pion API–OpenAPI–klient–Admin/Reviewer rozszerza istniejący kontrakt; zapis
korekty pozostaje dotychczasową jawną source/revision-bound komendą.
Szczegóły: `delivery/GRID_V3_SHADOW_CONTRACT_20261005.md`.

T05 rejestruje `hybrid-mobilenet-v1` leniwie: odkrywanie trenerów przez API
nie importuje torch. `hybrid_data` jest obrazowym adapterem propozycji/cropu,
matchingu i metryki; `hybrid_model`/`hybrid_training` działają tylko w workerze,
a `hybrid_inference` używa CPU ONNX Runtime. BaselineEngine pozostaje domyślny.
Opcjonalny `run_id` w istniejącym POST /geometry jest rozłączny z manual preview.
Przed Catalog.image sprawdza się completed run, aktualny manifest, dozwoloną
partycję i zamknięty protokół; holdout daje HOLDOUT_NOT_RELEASED.

`hybrid_protocol` wiąże kanoniczny preset, pełny SHA pretrained wag i wersję
generatora. Create-only kopia w LAB/cache/protocols jest sprawdzana wraz z
rzeczywistymi wagami przed etapami cyklu życia. Opcjonalny protocol_digest
w StartRunRequest jest usuwany z canonical request, jeśli None: istniejące
receipts/fingerprinty/bindingi T04 pozostają identyczne. Checkpoint i raport
zawierają pełny preset. Deterministyczny CUDA runtime wymaga ustawienia cuBLAS
przed inicjalizacją, deterministic algorithms oraz zamrożonych buforów BatchNorm;
gwarancja odtworzenia dotyczy zgodnego sprzętu i bibliotek, nie dowolnego GPU.

RunManager publikuje fenced immutable `onnx` i `best_weights` oraz ich SHA.
Wskaźniki pochodzą wyłącznie z serwera, nie z dowolnych ścieżek w metrics.
Oddzielne best_state w checkpointcie zachowuje wybraną epokę; resume nadal
odtwarza ostatnią ukończoną epokę. Deadline obejmuje eksport i publikację.
Parity odrzuca także NaN/Inf, zanim porówna tolerancje. Proces workera ma UTF-8
logi niezależne od domyślnej strony kodowej Windows. Lista modeli i odczyt
ponownie sprawdzają SHA artefaktów; galeria pokazuje tylko jawnie wybrany model.

Szybki przegląd używa istniejącego POST /annotations: PhotoReviewRequest ma
additive reject, PhotoReview.rejected domyślnie false. CAS/SHA/mapa i receipt
chronią reject jak accept. Reject czyści zaakceptowaną mapę bez geometrii/issues;
tylko accept usuwa rejected. photo_accepted wyklucza rejected. Historia,
backup i rebase zachowują pole. QuickReview ma lokalną stabilną kolejkę i
snapshot wyświetlonej mapy/rewizji, loadguard źródła oraz blokadę pending/ref;
stare odpowiedzi nie powodują przejścia ani obniżenia wspólnego stanu.

T03d rozszerza istniejący POST /annotations o PhotoReviewRequest, a stan o
photo_reviews z domyślnym pustym zbiorem. Source SHA i mapa rewizji wszystkich
pozycji są sprawdzane pod tym samym exclusive/CAS co zapis, przed decyzją.
Review przechowuje aktora/czas, zaakceptowaną mapę i oddzielne issues
needs_correction/needs_review; historia i receipts zachowują zdarzenia.
Zapis geometrii unieważnia akceptację zdjęcia; accept zamyka needs_review tylko
dla full/present, a needs_correction blokuje. Nie ma dodatkowego resolve.
Klient generowany z OpenAPI; panel korzysta ze wspólnego AnnotationState.
Rebase uwzględnia bieżące/historyczne referencje review. Freeze wymaga aktualnej
akceptacji obok dotychczasowej kwalifikacji; nigdy nie zmienia roli źródła.

CLI `vision_lab.rebase_annotations` przenosi payload anotacji pomiędzy dwoma
zweryfikowanymi Catalog, wyłącznie do nowego katalogu. Domyślny preflight jest
bez zapisu; `--apply` ponownie czyta aktualny state pod blokadą exclusive.
Sprawdza referencje bieżących anotacji, timingów, requestów i wyników historii,
całe metadane Source oraz zgodność receipts. Rodziny/split i nieznany format
blokują operację. Zmienia tylko state.snapshot_id (digest katalogu, odrębny od
snapshotId manifestu); oryginalny payload i obrazy pozostają nietknięte.
State i checksummed rebase-report z digestami wejścia/wyjścia publikowane są
w jednym rename tymczasowego katalogu na tym samym wolumenie. Retry akceptuje
tylko identyczny raport i payload; istniejący nowszy cel kończy konfliktem bez
nadpisania. API należy zatrzymać przed końcowym apply i uruchomić na nowych
ścieżkach. Import zdjęć pozostaje istniejącym snapshot.import_folder.

UI ma jednego właściciela AnnotationState dla galerii, geometrii i rodzin.
Odczyt GET /annotations oraz wyniki zapisu odświeżają ten stan monotonicznie
według rewizji. Istniejący GET /sources jest pobierany partiami do pełnego
katalogu metadanych; filtry anotacji poprzedzają paginację UI. Nie zmienia się API.
Statusy i liczniki wynikają wyłącznie z trwałych anotacji; obecna pełna geometria
wymaga full_approved i presence=present. Nawigacja porzuca lokalne zmiany
bez confirm i bez autosave; brak beforeunload. Busy/pending blokuje
nawigację w aplikacji do retry lub jawnego odczytu przyciskiem bez modalu.
Wspólna baza powiadomień packages/ui obsługuje kolejkę, deduplikację i zegar
niezależnie od operacji; zamknięcie toastu nie zmienia stanu zapisu.
Wszystkie warianty mają 4 s widocznego czasu; hover/focus/hidden pauzuje.
Przycisk Kopiuj używa clipboard wyłącznie dla wiadomości i izoluje kliknięcie
od zamykania. Wynik kopiowania pozostaje lokalny w toaście, bez nowych toastów.

POST `/geometry` przyjmuje opcjonalne `preview_board` zgodne z Board.
Bez niego zachowuje detekcję baseline; z nim waliduje bieżące węzły przez
`cell_quads` i generuje cropy przez wspólne `crop_cell`. GeometryResult
oznacza wynik `manual-preview`; assety pozostają w ograniczonym rejestrze
pamięci, bez mutacji anotacji. UI unieważnia odpowiedzi po zmianie węzłów
i przyjmuje wyłącznie najnowsze żądanie. Viewport jest osobną transformacją
źródło→ekran, zamrożoną na czas gestu; nie zmienia pikseli źródła ani węzłów.

Właścicielami reguł i kolejności są `requirements/VISION_LAB.md` oraz
`delivery/VISION_LAB_EXECUTION_PLAN.md`. Eksporter jest osobnym narzędziem
głównego środowiska. Czyta manifestem wskazane źródła, dostępne rewizje,
metadane pochodzenia, słowniki i związane zatwierdzenia; używa krótkiej
transakcji `REPEATABLE READ READ ONLY`, limitów czasu i partii. Snapshot
publikuje atomowo po kontroli checksum. Pierwotny `selective_board_review_v1_1`
i późniejsza ręczna reweryfikacja są odrębne; brak pierwszej wyklucza
porównanie. Laboratorium nie ma połączenia z bazą.

Manifest wejściowy v1 ma `schemaVersion`, `datasetName` i pozycje
`{gameId, sourceImageId, expectedSourceSha256, sourceFamilyId, role}`.
`role` przyjmuje `data`, `comparison_only` albo `777_v2_declared`; ostatnia
wartość dokumentuje deklarację pochodzenia, nie rozstrzyga samodzielnie
kwalifikacji treningowej. Format uruchomienia i katalogu wynikowego opisuje
`guides/VISION_LAB_EXPORT.md`.

Powyższe role opisują niezmienny format źródeł. D-453
dopuszcza historyczne zdjęcia 777 do uczenia geometrii z nowych ręcznie
zatwierdzonych siatek labu, zachowując ich historyczne pochodzenie. Dawne
geometrie v1.1 nie są targetami. T03e zapisuje jawne
`GeometryQualificationRequest` w istniejącym AnnotationStore: jeden atomowy
batch, CAS, receipts, historia i backup, bez zmiany anotacji i photo review.
Wersja `historical-777-lab-geometry-v1`, referencja D-453 i zakres geometry
wiążą dokładny game_id, source_id/SHA, mapę rewizji plansz, autora i czas.
Pierwszy wariant akceptuje tylko źródła folderowe o dokładnej tożsamości
777 (game_name i pierwszy segment filename), z rolą comparison_only;
inne comparison_only, V2 i źródła DB pozostają wykluczone.
Walidacja wymaga aktualnego photo_accepted i pełnego obecnego ręcznego targetu.
Kwalifikacja nie wymaga wcześniejszego mapowania rodzin, ale nie zastępuje go.

CLI `vision_lab.qualify_geometry` domyślnie czyta checksummed payload bez
tworzenia katalogu/.lock; `--apply` ponownie waliduje typed request pod blokadą
AnnotationStore. Nie ma dodatkowego endpointu ani UI. Addytywna odpowiedź
AnnotationState jest objęta OpenAPI i generowanym klientem. API nie przyjmuje
requestu kwalifikacji przez istniejący POST /annotations.

SplitRequest bez purpose zachowuje tryb legacy (w tym dotychczasowe receipts)
i odrzuca role inne niż data. Jawne purpose geometry może użyć skutecznej
kwalifikacji D-453. FrozenSplit zapisuje purpose, `lab-geometry-split-v1`,
fingerprints kwalifikacji oraz osobną mapę pełnych obecnych human targetów;
wyłącznie te targety liczą pokrycie topologii. Rodziny, duplikaty, pomiar
i photoacceptance nadal są wymagane. Stare split fingerprints nie są
przeliczane przy odczycie. Zmiana geometrii, review, rodziny lub kwalifikacji
oznacza istniejący split stale; odczyt dodatkowo sprawdza skuteczność
i fingerprint zamrożonej kwalifikacji. Ponowne accept tej samej mapy może
przywrócić skuteczność kwalifikacji, ale nie kasuje split_stale.
Nie zmienia się Source.training_eligible ani żadna bramka symboli.
Rebase jawnie odrzuca bieżące kwalifikacje i ich historię; import/rebase
nowych zdjęć musi poprzedzać realną kwalifikację do czasu osobnego rozszerzenia.
Implementacja T03e nie oznacza wykonania kwalifikacji lub splitu na danych.

T03f rozszerza istniejący SplitRequest o geometry_source_ids=None (do 10000 ID).
Jawna niepusta unikalna lista znanych źródeł wymaga purpose geometry. Kolejność
requestu pozostaje częścią receipt; pominięcie pola/None usuwa je z hashowanego
requestu, zachowując stare receipts obu trybów. Bez kohorty fingerprint splitu
nie zawiera nowych pól. Błędy domenowe /splits pozostają 409, schematu 422.
build_components obejmuje cały katalog; bramki roli i verified dotyczą całego
komponentu, a akceptacja, targety i assignments wyłącznie jego wybranych źródeł.
Measurement wymaga ID z kohorty, trudności wszystkich członków, jednej gry
i trudności oraz dwóch niezależnych komponentów na stratum. Wszystkie wybrane
źródła komponentu trafiają razem do pomiaru lub jednego podziału.

FrozenSplit policy lab-geometry-cohort-split-v1 wiąże posortowaną kohortę,
leakage_components całego katalogu oraz leakage_component_fingerprints pełnych
Source, StoredFamily (albo null) i kwalifikacji każdego członka niedata (albo
null). Wszystkie te mapy wchodzą do fingerprintu; stare odczyty mają None/{}/{}.
_view porównuje graf i fingerprints oraz skuteczność kwalifikacji wszystkich
członków niedata komponentów z assignments, także niewybranych. Stały brak
kwalifikacji w wykluczonym komponencie nie daje stale. Zmiana daje stale bez
przeliczania zapisanych assignments/fingerprintu; mutacje zachowują wcześniejsze
konserwatywne unieważnianie. Atomowość, CAS, retry, historia i backup należą
do AnnotationStore. Rebase splitu pozostaje zablokowany. Brak nowej trasy/UI.

T03j/D-455 dodaje opcjonalne SplitRequest.geometry_policy o wartości
`lab-geometry-cohort-777-targets-v2`; None jest usuwane przed hashowaniem
requestu/historii, więc legacy, T03e i T03f zachowują receipts i fingerprints.
V2 wymaga purpose geometry oraz jawnej niepustej kohorty. Błędy kombinacji
to GEOMETRY_POLICY_PURPOSE_REQUIRED, GEOMETRY_POLICY_COHORT_REQUIRED oraz
istniejący GEOMETRY_COHORT_EMPTY (HTTP409); nieznany enum daje HTTP422.
FrozenSplit zapisuje v2 w policy_version, bez dodawania pól do starych hashy.
Wspólny geometry_role_eligible jest używany przez freeze i _view; zwalnia
z kwalifikacji jedynie źródła poza geometry_source_ids spełniające ścisły
historical_folder_777 (folder, game_name=777, filename zaczyna się segmentem
777 i zawiera nazwę pliku, role=comparison_only). Brak assignmentu sam w sobie
nie oznacza kontekstu. validate_binding D-453 korzysta z tej samej tożsamości.
Wybrane niedata wymagają własnej skutecznej kwalifikacji. Pełne komponenty
i ich fingerprints pozostają niezmienione; _view v1 nadal wymaga kwalifikacji
wszystkich członków niedata. V2 nie daje fałszywego stale od stałego braku
kwalifikacji kontekstu, ale wykrywa zmiany pełnych metadanych, rodzin,
kwalifikacji i grafu. Konserwatywne stale po mutacjach pozostaje bez zmian.

T03k/D-456 dodaje geometry_policy `lab-geometry-whole-game-pilot-v1` oraz
opcjonalne game_partitions w SplitRequest/FrozenSplit. Mapa obejmuje dokładnie
wszystkie game_id katalogu: co najmniej jedno development, dokładnie jedno
validation, final_test i unseen_game, zgodne z unseen_game_id. Każda część
musi mieć co najmniej jeden pełny target. None jest usuwane z requestu przed
hashowaniem, a starsze polityki nie dodają mapy do danych hashowanych splitu.
Mapa poza pilotem, niepełna/błędna mapa i pusty przydział dają
PILOT_GAME_PARTITIONS_INVALID; brak mapy PILOT_GAME_PARTITIONS_REQUIRED.
Niepusty measurement lub difficulties daje PILOT_MEASUREMENT_NOT_SUPPORTED.

whole_game_split.freeze_whole_game_split jest czystą gałęzią po walidacji
purpose/kohorty. Nie wymaga verified i nie zapisuje rodzin. Każdy komponent
całego katalogu sprawdza wobec mapy (PILOT_CROSS_PARTITION_COMPONENT), a role
kontekstu sprawdza w komponentach dotykających kohorty wspólnym predykatem
D-455. Każdy target ma photo_accepted i pełną geometrię human 5 × 3;
brak targetu daje PILOT_FULL_GEOMETRY_REQUIRED, inna pełna topologia
PILOT_TOPOLOGY_NOT_SUPPORTED. Żaden błąd nie zmniejsza kohorty po cichu.
FrozenSplit wiąże mapę, całą kohortę, pełne komponenty i fingerprints;
assignments/targety są tylko wybrane, measurement pusty.
Odczyt nowej polityki rekonstruuje oczekiwany wynik na bieżącym stanie
z pierwotnym numerem rewizji splitu i porównuje go z zamrożonym rekordem,
bez zastępowania rekordów lub przeliczania starych wersji. W ten sposób
kontroluje także mapę, przydziały, pełne metadane, aktualność targetów i graf
odległych wykluczonych komponentów; różnica lub błąd walidacji daje stale.
Receipts, CAS, backup/restore i zakaz ponownego freeze pozostają w AnnotationStore.

Eksporter czyta tylko wskazane `source_images`, związane
`image_source_geometry_revisions`, `image_page_geometry_overrides`,
`recognized_boards`, `image_board_geometry_revisions`,
`image_board_geometry_review_events`, `image_symbol_review_cells` i
`image_symbol_review_events` oraz niezbędne `games`, `symbols` i
`rules_version_symbols`. Pierwsza krótka transakcja RO zamraża ID,
rewizje i fingerprinty powiązanych wierszy. Kolejne partie w nowych
transakcjach czytają dokładnie te ID; zmiana albo brak wiersza blokuje
publikację. Następuje kopia zarządzanych obrazów po kontroli SHA-256,
tymczasowy manifest, fsync plików i atomowy rename na jednym wolumenie
(fsync katalogu tam, gdzie wspiera go system). Snapshot ID jest SHA-256
kanonicznego wejścia, wersji eksportera oraz zamrożonych ID/rewizji.
Idempotentny retry weryfikuje opublikowane pliki; konflikt kończy błędem.

Dane poza repo pod `C:\Users\tuszy\Documents\game_predictor_vision_data`
obejmują niezmienne manifesty, zarządzane kopie obrazów, anotacje,
checkpointy, raporty i backupy. Zapisy są atomowe; wykonuje się próbę
odtworzenia. `GeometryEngine`, `GeometryResult` i `SymbolRecognizer` są
wspólnymi kontraktami dla baseline oraz przyszłych hybrid i neural_grid.
Wynik zachowuje źródło, topologię, plansze, węzły, pochodzenie punktów,
wersję modelu i powody korekty. Układ plansz ekranu jest niezależny od
`BoardTopology` pojedynczej planszy. 5 × 3 ma 24 węzły, 3 × 3 ma 16.
Nie zakłada się dziewięciu plansz; nieobecność, zasłonięcie i nieczytelność
są osobnymi stanami. Bramka kontroluje kolejność, przecięcia, dodatnie pola
i kompletność bez wymogu konkretnej techniki OpenCV.

TASK-1014 zabezpiecza wymagane bazowe checkpointy i eksportowe wagi obu
profili w osobnym `training-base` zarządzanej wersji na D. Opt-in instalator
publikuje staging atomowo i wiąże receipt z niezmiennym rejestrem modelu,
SHA-256, rozmiarami i historycznymi źródłami. Store weryfikuje komplet plików
przed zwróceniem bazy, bez odczytu C. Inferencyjny manifest i aktywacja
pozostają zgodne; retry wznawia tylko zweryfikowane kompletne pliki.
[Instrukcja i kontrakt bazy](../guides/MANAGED_GRID_TRAINING_BASES.md)
nie upoważniają do usunięcia źródeł, treningu ani kopiowania korpusu.

T02 przyjmuje również dostarczony przez użytkownika folder zdjęć bez
powiązania z DB. Importer plikowy tworzy osobno wersjonowany snapshot,
lokalne identyfikatory, pochodzenie pliku, SHA-256 i zarządzane kopie.
Publikacja jest atomowa, ponowienie sprawdza checksumy, a konflikt nie
nadpisuje istniejącego snapshotu. Snapshot plikowy nie udaje eksportu DB
i nie tworzy zatwierdzeń ani uprawnień do treningu. Prefiks nazwy nagrania
jest kandydatem rodziny, wymagającym weryfikacji w T03. Oba formaty wejścia
są adaptowane do wspólnego katalogu galerii, bez zależności runtime od bazy.

Deklaracja operatora o odległych brzegach i innych folderach nagrań pięciu
gier jest wejściem do mapowania źródło–rodzina (D-453). Granicę rodziny
wyznacza wspólne nagranie i powiązane pochodne, nie odległość w numeracji
lub liczba katalogów. Końce tego samego filmu pozostają razem. Kontrole
SHA i podobieństwa rozstrzygają konflikty z deklaracją; brak trafienia
nie dowodzi niezależności. Przed freeze trzeba powiązać nowy i dotychczasowy
zbiór, bez automatycznego potwierdzania rodzin z samych nazw.

Hybryda używa MobileNetV3-Small, narożników, perspektywy i opcjonalnego
dopasowania. Neural_grid przewiduje pełne węzły. Symbole bazują na
`SpatialSymbolCnn`: RGB, szarość powielona na trzy kanały i fuzja z
udziałem RGB 0/0,1/0,2/0,3. Kalibracja jest tylko na walidacji;
niezgodność modeli jest sygnałem niepewności.

FastAPI `game_predictor_worker.vision_lab` działa na
`127.0.0.1:8102`, a Next.js `apps/vision-lab` na `127.0.0.1:3102`.
Frontend używa proxy z zamkniętą listą tras. FastAPI posiada OpenAPI i
osobny generowany klient kontrolowany w `openapi:check`/`quality`.
Oba wejścia kontrolują Host; zapis wymaga dozwolonego Origin i JSON.
Assety są identyfikowane w rejestrze, bez dowolnych ścieżek od klienta.
Zajęty port zgłasza błąd bez zabijania procesu; brak tunelu.

Testy importów chronią granice: lab nie importuje `storage`, `psycopg` ani
produkcyjnego handlera treningu; produkcyjne wejścia nie importują labu;
neutralny rdzeń nie zależy od bazy ani UI. Izolowane środowisko przypina
PyTorch 2.12.1, torchvision 0.27.1 i CUDA 13.0; główne środowisko pozostaje
bez zmian. Integracja CPU używa ONNX Runtime. Checkpoint v2 zawiera optimizer,
scheduler, RNG, konfigurację i SHA-256 danych. Odczyt v1 pozostaje możliwy
bez obietnicy numerycznie identycznego wznowienia. Produkcyjny
`training_job.py` użyje neutralnego rdzenia dopiero w T12 po regresjach.

Integracja v3 nie wiąże wyboru silnika z nazwą ani wydaniem gry. Adapter
inferencji otrzymuje obraz, topologię 5 × 3 i jawnie wybraną wersję modelu;
nie czyta starych predykcji v1.1 ani roli źródła jako warunku wykonania.
Kontekst gry jest osobnym wejściem mapowania klas symboli, nie częścią
modelu geometrii. Porównanie v1.1/v3 tworzy dwa rozdzielne przebiegi dla
tego samego SHA obrazu i wersjonuje wyniki; żadna ścieżka nie zmienia
ustawienia domyślnego silnika lub decyzji człowieka. Brak słownika/mapowania
daje jawne „symbole niedostępne” przy nadal dostępnym wyniku geometrii.
T11 dostarcza równoległy przegląd geometrii, T12 dołącza symbole, T13
sprawdza parytet, izolację oraz scenariusz `777 v1.1` (D-461).

`vision_lab/runs.py::RunManager` dostarczony w T04 jest
właścicielem trwałego kontraktu runów; panel T08 jest jego klientem.
Stan jest zapisywany atomowo pod
blokadą międzyprocesową i tokenem lease. `requestId` oraz fingerprint
manifestu, konfiguracji, modelu, topologii, preprocessingu i seeda są
trwałe przed spawnem. To samo żądanie zwraca ten sam run; ten sam ID z
innym payloadem daje konflikt. Stany: `queued → running →
succeeded|failed|cancelled`, bez pauzy. `running` wiąże PID, czas startu,
lease i heartbeat, więc restart nie uruchamia duplikatu. Żywy zgodny proces
pozostaje obserwowany nawet przy starym heartbeat/lease. Dopiero potwierdzony
brak zgodnego PID/czasu utworzenia wraz z wygaśnięciem lease daje recoverable
`failed`. Budżet jest naliczany trwale poza checkpointem; crash i retry nie
zwracają kroków ani niepotwierdzonego czasu (szczegóły T04). Cancel jest
utrwaloną intencją i kończy się po checkpointcie; awaria zachowuje ostatni
poprawny checkpoint. Retry jest jawną nową próbą z nowym lease po kontroli
fingerprintu; stary proces zostaje odgrodzony. Sukces wymaga atomowo
opublikowanych checksumowanych artefaktów i raportu.

Stan wszystkich runów i receipts ma checksumowaną kopertę w katalogu runów,
nie w AnnotationStore. Run-local lock ponawia wyłącznie konflikt blokady do
10 sekund; zwykłe odczyty panelu nie przerywają writera. `queued` zawiera
lease/fence oraz launch_deadline. Worker sam zapisuje PID i OS creation time
przy claim. Utworzenie procesu i ponowna kontrola queued są pod tym samym
lockiem; anulowany queued nie uruchamia pracy. Każda próba ma osobny katalog
niezmiennych artefaktów, a dopiero poprawny checkpoint v2 zmienia wskaźnik.

Trwałe rezerwacje kroków i naliczenie czasu są niezależne od checkpointu.
Worker ma dodatkowy monotoniczny watchdog obejmujący walidację, GPU i eksport;
po limicie kończy tylko własny proces. Odczyt po wygasłym lease rozpoznaje jego
brak, zapisuje failed i konserwatywnie nalicza odcinek bez potwierdzenia.
Nie kasuje ostatniego checkpointu. Cofnięty zegar wyczerpuje pozostały budżet.

`ManifestAdapter` sprawdza kopertę `{payload,sha256}`, zamrożony split i pełną
listę targetów T03k względem aktualnych anotacji. `TrainingInputs` udostępnia
wyłącznie development/validation; obraz jest odczytywany przez Catalog z SHA
i EXIF. Kontrola integralności holdoutów nie dostarcza ich do modelu.
POST /runs i cancel/retry, GET /runs oraz /runs/{id} korzystają z tego samego
loopback boundary i generowanego klienta. Ścieżki interpretera, manifestów,
runów i anotacji pochodzą wyłącznie z konfiguracji operatora. Katalog runów
nie może nachodzić na snapshot, anotacje lub manifesty. Rejestr trenerów jest
zamknięty; T05 dodaje leniwą hybrydę, a produkcyjny handler pozostaje niezależny.

## Narzędzia etykiet symboli T06a

TASK-0851/D-496 dodaje opcjonalny `--symbol-dataset-version` / środowiskowe
`VISION_LAB_SYMBOL_DATASET_VERSION`. Moduł `symbol_dataset_version` publikuje
create-only, checksumowany `manifest.json`; jego digest jest ID katalogu.
Referencja zachowuje pełne oryginalne payloady geometrii i symboli, ich sumy,
katalog, wybrane źródła, zatwierdzony słownik, zgodę na wersję oraz dowody
historycznego użycia. Nie jest nowym AnnotationStore ani magazynem etykiet.

Istniejący SymbolLabelStore waliduje ją pod dotychczasowymi blokadami przed
podglądem i zapisem. Request-local grant wiąże instancję stanu i katalogu;
zezwala wyłącznie na przypięte źródła, po sprawdzeniu fingerprintu dawnych ról
i przechodniej sumy starych/aktualnych komponentów. Stale geometrii nie jest
usuwane. Drift zwraca `SYMBOL_DATASET_VERSION_STALE`; brak referencji zachowuje
wcześniejszą politykę, w tym `HOLDOUT_POLICY_UNRESOLVED`. Schema HTTP, bindingi,
renderer i writer pozostają istniejące. ID wersji trafia do metadata decyzji,
token strony wiąże wersję, a receipt nadal chroni dokładny retry.
Kwalifikacja treningu nie używa tego grantu; wszystkie jej bramki zostają.

Manifest jest ograniczony dotychczasowym czytnikiem kopert do 64 MiB i wersją
do 10000 komórek. Obrazy są renderowane tylko dla strony. Launcher
`scripts/vision_lab_symbol_review.ps1` korzysta z trwałego JSON konfiguracji,
zapisuje PID, czas utworzenia i command line, uruchamia ukryte procesy i
sprawdza gotowość osobno. Dopasowany writer geometrii 8105 jest zatrzymywany
przed uruchomieniem API 8102. Cudzy listener blokuje start zamiast być kończony.

D-458 rozdziela budowę narzędzi od kwalifikacji rzeczywistego zbioru.
Oddzielny, jawnie skonfigurowany magazyn symboli nie zmienia formatu
AnnotationStore ani jego receipts i podziałów. Wersje słownika, decyzje
operatora oraz dokładne cropy mają trwałą tożsamość. Zmiana geometrii,
źródła, cropa lub zatwierdzonego słownika unieważnia aktualność etykiety.
Adapter DB czyta wyłącznie zweryfikowany eksport; nie otwiera sesji bazy
i nie tworzy mapowania ani rekordów produkcyjnych.

Nowe trasy pozostają częścią istniejącego lokalnego API i zamkniętego
proxy. OpenAPI jest źródłem klienta. Szczegółowy kontrakt przed kodowaniem
określa `ai_docs/delivery/VISION_LAB_SYMBOL_LABELS_CONTRACT.md`.
Poprawna etykieta nie jest automatycznie próbką dopuszczoną do treningu.
T06b zachowuje bramki pochodzenia, ról i podziału symboli; D-456 ich nie
zastępuje. Holdout sprawdzany jest przed udostępnieniem pikseli.

TASK-0716/D-459 rozszerza istniejące trasy o podgląd lab_board i atomowe
label_board_decide. Podgląd tworzy jeden ograniczony kadr planszy z dokładnie
przeliczonymi węzłami oraz 9/15 niezmienionych cropów RGB96, z jednego odczytu
obrazu po kontrolach roli/holdoutu. Wspólny snapshot obejmuje rewizję symboli,
słownik i aktualne decyzje. Batch ponownie sprawdza wszystkie bindingi pod
blokadami geometry-first; publikuje jeden state z jedną rewizją i receipt,
zachowując odrębne decision_id i historię każdej komórki. Nie wywołuje mutate
rekurencyjnie. Stare requesty i receipts pozostają zgodne; szczegółowy kontrakt
i testy zapisuje TASK-0716, bez zmiany bramek dopuszczenia danych do treningu.

TASK-0717/D-460 dodaje pochodny, paginowany podgląd `kind=lab_queue` do
istniejącego POST /symbol-crops. Metadane aktualności decyzji wylicza pod
blokadami z geometrii i symbolstore bez utrwalania flagi ani masowego
renderowania. Indeks akceptacji oraz uprawnienia source/komponent liczone są
raz na odczyt; piksele tylko dla bieżącej strony, po kontroli roli/holdoutu.
Nierozstrzygnięty globalny podział zatrzymuje odczyt jawnym błędem; zwykły
holdout jest pomijany bez ujawnienia źródła. Błąd nie udaje pustej kolejki.
Token wiąże obie rewizje, grę, sortowanie oraz wersję renderera. Jawne
„Do ponownej oceny” odróżnia drift od braku wcześniejszej decyzji.
TASK-0852/D-497 rozszerza istniejący odczyt do 2000 cropów jednym żądaniem;
domyślny limit 30 pozostaje. Renderer dekoduje każde źródło raz i ogranicza
sumę PNG do 48 MiB przed kolejnym renderowaniem; przekroczenie daje
SYMBOL_QUEUE_PREVIEW_TOO_LARGE bez części strony. Klient odrzuca niepełną
lub zmienioną serię, zachowując token, rewizję i sumę.
Poczekalnia zachowuje wszystkie wyświetlone piksele do jawnego refresh.
Potwierdzony label_cells_decide oznacza tylko dokładne bindingi jako assigned,
zachowuje obrazy/klasę/następny wybór i przesuwa CAS o jedną rewizję.
Nie odnawia read_token; kolejna nawigacja pobiera limit=1 ze świeżym tokenem,
a potem żądaną stronę, uwzględniając lokalnie zapisane pola w offset.
Zmiana busy nie uruchamia odczytu. W trakcie zapisu blokowane są wysłane pola
i kolejny submit, ale można wybierać następne pola/klasę. Niepotwierdzony zapis
blokuje edycję do identycznego retry albo jawnego read. Niezgodny receipt
unieważnia lokalną stronę. Lista etykiet wymaga jawnego read po zapisie kolejki;
pozostałe mutacje zachowują pełny reload. Wersja/grant/holdout i writer bez zmian.
Otwarty edytor całej planszy zachowuje poprzedni snapshot bez automatycznego
odczytu po batchu kolejki. Edycja tej planszy wymaga jawnego „Odczytaj stan”;
nie uruchamia konkurencyjnego czytnika blokującego następny zapis kolejki.
Ten sam `lab_queue` dopuszcza `view=assigned` z wymaganym `symbol_id`
aktywnego słownika. Zwraca wyłącznie bieżące zatwierdzenia bez driftu,
zachowuje kontrolę roli i holdoutu przed odczytem pikseli oraz paginację
do 2000 na żądanie (domyślnie 30). Token wiąże także widok i symbol, więc nie wolno użyć
strony poczekalni jako strony przypisań. Domyślny `view=pending` zachowuje
dotychczasową kolejkę bez zmiany zapisu.
Addytywne `label_cells_decide` w POST /symbols zapisuje 1–30 unikalnych
bindingów do jednej aktywnej klasy w jednym write_atomic, jednej rewizji
i receipt, z odrębnym decision_id od fingerprintu i crop_id. Wszystkie
bindingi są renderowane i sprawdzane przed pierwszą publikacją. Dopiero
zgodny jawny zapis tworzy etykiety; queue nie kwalifikuje próbki do treningu.

## D-498 symbol cohort adapter (TASK-0854)

`symbol_training_manifest` freezes `lab-symbol-training-manifest-v1` through
create-only checksummed publication. It references the immutable preparation
PNG pack, records scoped recording declarations, full merged component evidence,
assignments, class counts and live SHA bindings. `SymbolTrainingAdapter` verifies
these and exact crop pixels on start/checkpoint/finish; it never changes default
symbol gates, geometry manifests or label stores. It is local CLI only, with no
HTTP/API registry change. The fresh Mumie cohort is 255 development/84 validation.

## Scoped symbol run family (TASK-0855)

`symbol_runs.SymbolRunManager` reuses the neutral RunManager, existing artifact
names best_weights/onnx and durable report/checkpoint protocol. The global
geometry training registry and HTTP contracts are unchanged. `symbol_training`
reuses SpatialSymbolCnn with mathematically equivalent fixed4x4 pooling for its
fixed64 input, preserving deterministic CUDA backward. Checkpoints bind requests,
data, optimizer, RNG, history and best weights. Final reports embed validation
logits; `symbol_models` performs bounded validation-only temperature/fusion and
separate model uncertainty/reference-conflict review. Existing default consumers
retain their architecture and training gates. CLI roots/settings are persistent.

## Independent symbol batch (TASK-0856)

`symbol_batch` freezes `mumie-symbol-batch-v1` in an isolated CLI root using
SymbolTrainingAdapter, verified succeeded RunState exports, full-component
exclusions and create-only lab publication. It reuses neutral geometry decoding,
lattice quads, RGB96 cropping and exact RGB/gray training preprocessing. A
per-photo result is published after source-bound atlas/overlay assets; bounded
portions validate existing artifacts and live bindings on resume. Filename
ranges are bounded by the operator folder end, with explicit conflict/count
review and no sequence assignment. `symbol_batch_review` creates a static
bounded uncertainty/class-control gallery and full photo index. It changes no
HTTP registry, annotation store, label history, database or default model.

## Versioned symbol appearance experiment (TASK-0857)

`symbol_augmentation` defines `symbol-light-payline-v1` with sample/seed/epoch
SHA-derived local RNG. Existing affine variation precedes bounded gamma,
brightness, contrast, saturation, hue and occasional translucent green lines.
Grayscale follows augmentation; validation/inference retain the original
preprocessing. `MODELS` remains v1. Additive `ROBUST_MODELS` and optional CLI
`--generation 2` select the pair through persistent run settings, reusing the
neutral RunManager, checkpoint binding, exact resume and budgets. The global
HTTP registry and TrainingConfiguration remain unchanged.

`require_robust_qualification` rejects insufficient validation, invalid/nonfinite
parity or incomplete exports. V2 batch requires an immutable `--geometry-reference`
with matching sources, training manifest and geometry. Pin all prior results and
visuals. `reclassify_photo` renders each old quad, proves its RGB96 pixel SHA and
changes only classifier proposals. Atlas/overlay bytes, count conflicts and
domain ordering remain exact. Both batches survive replay without rewriting
artifacts or human approvals. The targeted 18-case page is read-only evidence.

## Batch crop review (D-501, TASK-0858)

`symbol_batch_labels.prepare` verifies the independent batch exclusions,
D-498 dictionary provenance, source and RGB96 pixel identity, then publishes
a content-addressed reference with exact PNG files. The original read-only
gallery is preserved as review.before-editing.html; its derivative entry page
links exact case IDs to the existing Vision Lab `/symbols/batch` editor.

Optional batch_queue/batch_label_decide extend existing symbol routes and
generated OpenAPI client. `SymbolLabelStore` delegates only these variants to
`BatchReviewStore`; existing default gates and stores remain unchanged.
Original geometry/symbol guards precede the independent store lock. Verify
live metadata, renderer, source and PNG, re-render the selected quad on save,
then publish one atomic state with CAS, immutable decision history and receipt.
Identical retry acknowledges the prior write before CAS and can recover after
policy drift without authorizing new pixels. All results are trainable=false.

The durable launcher accepts optional absolute BatchReference/BatchLabels
paths together. New decisions live outside the original lab roots. React
reuses symbolWriteSession, freezes PNGs, updates only receipt-confirmed cases
and keeps the next selection while a save is pending. Rereads remount PNGs
and require their load events; image failure blocks approval. The sticky
desktop panel and mobile layout expose the palette without opening a photo.

## V3 recording registry (D-554, TASK-1002)

`source_recording_groups` separates closed HTTP DTOs, domain qualification,
managed immutable membership pages and fixed PostgreSQL capabilities. Alembic
0161 installs five private shared tables: groups, occurrences, evidence,
role heads and command receipts. MAIN identities use game RLS; LAB_DESCRIPTOR
identities use opaque pinned references without fabricated game/source rows.
Indexed byte/pixel identities and explicit alias evidence form bounded closure.
No source partition query participates in cross-game closure.

A separately provisioned database-specific nonlogin role owns these objects.
Runtime has only three exact safe function signatures and no direct registry,
ordinal or internal helper access. Provisioning re-applies exact exclusions
after existing broad/default grants. Missing capability provisioning blocks
migration; runtime never falls back to an owner connection.

Commands authenticate scope before receipt replay and recheck replay/CAS under
catalog9910994 then registry9921002 locks. Advisory receipt lookup takes neither
global lock during membership file capture. Attach compares SQL-attested source
identity with the frozen server page inside the writing statement. Related
closure proofs invalidate only dependent resolutions and future bound reports;
global revision changes alone do not stale unrelated candidates.

Trusted deployment providers are SHA-pinned by persistent server configuration.
SQL also requires the matching immutable installation proof; an envelope copy
does not establish trust. Provisional resolutions store dependency bindings
without manufacturing future cohort/use or quality PASS evidence. The future
0995/0997 producers bind actual use and reports through this private boundary.
See [deployment and operator workflow](../guides/SOURCE_RECORDING_GROUPS.md).

## Production descriptive measurement boundary (D-555, TASK-1009)

`grid_quality_measurements` captures on a separate restricted runtime connection
in REPEATABLE READ READ WRITE with explicit WRITE/game/RLS routing. UUID keyset
metadata pages contain at most500 occurrences. A 100-element SHA-ranked heap
uses policy/seed/source occurrence key; full ordered metadata contributes to the
population digest. The capture deadline is60s, each statement at most30s and
locks5s. Timeout rolls back the complete sample. There is no image corpus sweep,
inference or implicit training qualification.

Selected evidence freezes all nine positions and exact producing source/job/model
references or a coverage gap. Current board pointers prove an automatic result;
manual ancestry requires explicit consistent cell before/after source links and
board/review/revision identity. Chronology and node resemblance are insufficient.
A canonical JSON manifest is fsynced and atomically published under its SHA before
committing its reference and receipt. Cold replay verifies the same file and SHA.
The recording six-argument resolver adds an indexed own-source membership lookup;
SQL/permissions_v2 preserve the frozen0161/v1 boundary and exact old signature.

## Application geometry snapshot boundary (D-556, TASK-0995)

`GridTrainingCohortService` orchestrates one-game preparation, metadata capture,
materialization and freeze. The domain module owns exact 24-node qualification,
versioned minima and weights. `grid_training_cohort_evidence` proves current
human events and exact approval receipt/manifest chains. Later cell materialization
or symbol changes preserve a label only after exact derived cell-quad/render
parity and the existing positive sibling-publication verifier. Pending grid
issues, owner, actor, source, geometry and revert checks remain effective.
The legacy geometry exporter and symbol workflows keep their defaults.

Metadata uses ordinal keyset pages of at most 200 members. Identity completion
and image materialization accept at most five sources and decode them sequentially;
only metadata, proofs and paths survive the next decode. The pure canonical
decoder and all-NULL/exact-equality metadata rules live in the API domain, with
backward-compatible worker exports. EXIF orientation None is a valid expected
value, not evidence of a partial canonical group. Completion requires the exact
existing geometry revision and never invents an import lease or model revision.

Content-addressed files under `data/grid-training-cohorts` are verified, fsynced
and published on the same volume before the database reference and receipt.
Public paths remain relative; containment and reparse checks precede native
Windows long-path I/O. The immutable root pins the base catalogue descriptor,
decoder, preprocessing and streamed page indexes. The application-specific worker
adapter `images/grid_cohort_dataset.py` verifies these pins and exact nodes,
checks roles before pixels and caches at most one canonical frame. It composes
outside neutral `training_core` and performs no training or inference.

Freeze uses a restricted READ COMMITTED runtime transaction with one 60-second
budget, statements capped at the remaining budget/30 seconds and locks at five
seconds. File verification precedes final write locks. Ordered catalog, recording,
owner, game projection, sequence, source and target locks protect metadata-only
revalidation, CAS, actual recording use and the immutable receipt atomically.
The additive recording v3 capability preserves historical v1/v2 SQL and grants;
runtime receives no direct private registry SELECT. Ordinary freeze creates no
report binding. A future real evaluation read-v2 report uses the existing trusted
producer and policy; TASK-0997 must provide its full reader, writer and joint
publication currentness barrier before publication.

Capture/materialization hold a transaction-scoped shared cohort asset guard
through file publication and receipt commit. Existing GC takes its exclusive
counterpart, then rechecks actual own-RLS page/root references before quarantine,
retry or deletion. Retained references protect canceled and failed cohorts too.
Unknown schema, routing, permissions or query results protect the file; absence
of routing proves zero references only with a completed matching deletion receipt
and absent catalog, route and own cohort partitions. Unreferenced staging expires
24 hours after the latest real dependency or deletion receipt. GC performs no
source/owner locking or bitmap scan. Physical cleanup remains separately approved.

Eligibility GET combines bounded current metadata checks in one pass and performs
no file I/O. A detached used source blocks new admission with
`SOURCE_REMOVED_NEW_USE_BLOCKED` in both application currentness and the common
private recording v3 guard. Metadata GET returns blocked, liveSourceLinked=false
and humanLabelWithdrawn=null for that member; byte availability remains unknown.
New detach notices record the same reason. Historical receipts, frozen payloads,
actual-use protection and earlier notices remain unchanged. Receipt replay
reads history and does not grant fresh admission.

## Grid training admission and GPU lease (D-557, TASK-1005)

`training_core/grid_training_admission.py` is neutral: it imports no application,
database or laboratory module and loads `torch` only inside `probe_runtime`. It owns
the versioned presets `grid-only-v1` and `screen-grid-v1`, whose SHA-256 fingerprint
covers every training parameter but not the approval record. `estimate_cohort_cost`
trains boards in grid-only and full photos in screen+grid; the training time is 60 s per
TRAIN photo clamped to 300–1800 s, and the charged run limit is 3600 s.
`evaluate_admission` is pure and lists every blocking reason in a fixed order: preset
approval or fingerprint, cohort mode, empty cohort, cost over budget, GPU, runtime
versions, VRAM, lease and budget. A training run needs an approved preset; a smoke
needs only a known fingerprint.

`RunBudget` is a checksummed envelope of steps, seconds and attempts. Resume increments
only the attempt; a negative or non-finite charge (clock moved back) exhausts it. The
durable record of a run budget belongs to TASK-0996.

`training_core/gpu_lease.py` holds one application GPU lease at
`<artifact_root>/grid-training/gpu-lease.json`. Each read-decide-write runs under a
short `.lock` file lock and replaces the record atomically. A live owner keeps an expired
lease; takeover needs a passed term and a missing process with the recorded PID and
creation time. An unreadable record or an unknown process state blocks and is never
removed automatically. The lease does not control foreign CUDA processes or laboratory
runs. `process_identity` moved here; the laboratory module re-exports it.

The bounded smoke `vision_lab/grid_training_smoke.py` runs in the isolated laboratory
environment on the reference snapshot's `training` role. It takes the lease, passes the
same admission with `purpose=smoke` and stops after 50 steps or 120 training seconds from
the first step; start-up may take 300 s and the whole run 600 s. A stoppable watchdog
thread enforces the three limits plus 30 s even when a batch blocks. It writes no checkpoint,
candidate or export. The read-only `run-preview` route reports presets, cost, cohort
qualification and lease state, and lists GPU, runtime, VRAM and budget as pending worker
checks.

## Durable application grid training (D-558, TASK-0996)

Training runs are `grid_training` jobs in their own execution slot 3 and worker lane
(`--lane grid-training`), so imports in the general lane are never blocked. The lane's
supervisor `images/grid_training_handler.py` runs in the main environment: it renews the
job lease, re-checks the frozen cohort and its D-556 eligibility, the base version's
`training-base`, the preset and the runtime facts from `grid_training_child --probe`, and
calls `evaluate_admission`. It then starts `images/grid_training_child.py` with the CUDA
interpreter from `GAME_PREDICTOR_GRID_TRAINING_PYTHON`. When unset, the shared CLI
factory locates the checkout's existing `.venv-vision-lab` interpreter (TASK-1134),
so correction preflight in the general lane uses the same CUDA runtime as training.
In this CLI factory an explicit path always wins, including when invalid; missing configuration never
falls back to the supervisor's CPU Python. The child opens no database; it
reads the pinned `spec.json`, holds the D-557 GPU lease and stops on a cancel intent, its
time limit or 60 seconds without a supervisor heartbeat.

The legacy PowerShell lane launcher still has its own candidate search: it passes
its resolved override only to grid-training, not general. Custom `-GridTrainingPython`
or User-only/invalid environment overrides are not unified by TASK-1134. The operator's
default checkout environment is covered; unsupported custom combinations fail closed.

The neutral core holds the shared logic: `training_core/neural_grid_network.py` (network,
graphs, losses), `training_core/neural_grid_augmentation.py` (jitter, photometric
augmentation, training items) and `training_core/grid_training.py` (loop, sampler,
checkpoints, early stopping, freezing, weighted node losses, export and parity). The
laboratory re-exports the moved symbols and keeps its results. Every step is a pure
function of `(seed, step)`, so a run resumed from a checkpoint continues with the indices
and seeds of an uninterrupted run; checkpoints are immutable, re-read before the pointer in
`jobs.checkpoint_payload` moves, and a damaged pointed file fails the run without a
candidate. Grid-only trains only the board stage with the detector and BatchNorm frozen and
the visibility loss masked; screen+grid trains the whole network.

The best checkpoint is exported with ONNX parity (D-561: every torch/ONNX output difference
divided by max(1, |torch|) stays within 1e-4, so pixel-space node coordinates are not
rejected for fp32 rounding; a failed check leaves `parity-failed.json` in the run), installed under
`models/grid-engine/<profile>/<version>` with its `training-base` receipt and registered
`not_evaluated` with an identifier derived from the job and checkpoint, so a retry after a
crash restores the same version. Budget, attempt, checkpoint pointer, export and candidate
live in the job payload; a re-claim charges the unconfirmed interval up to the child's
self-stop (at most 100 s); a whole-process watchdog in the child enforces that bound, and
the child publishes a step checkpoint when it is cancelled, out of budget or loses its
supervisor. A re-claim first waits for the previous trainer to end, then charges its time and
reported steps, adopts a newer intact checkpoint and recovers a finished export without new
budget. D-581 separates the immutable optimisation plan/fingerprint from the cumulative execution
allowance: known training presets receive 8000 steps and 7200 charged seconds (minimum),
across all games, while smoke keeps 50 steps/600 seconds. New budgets carry
`limit_policy=grid-training-limits-v2`; absent metadata means historical `preset-v1`.
Explicit admission of a resumed, recognised legacy budget with exact historical ceilings
adopts the shared ceiling once, retaining all consumption, attempts and checkpoints.
The supervisor adopts the ceiling before charging an orphan's final interval, avoiding
clipping consumption to the old ceiling; it records the pre-recovery budget and new
ceilings in history before launch.
Further resumes do not replenish the allowance. Unknown legacy ceilings remain unchanged;
unknown policy tags fail closed. Preview maxSteps/maxRunSeconds use the same execution
ceilings; planned training steps and historical recipe fingerprints remain unchanged.

Steps are reserved in blocks of 200 in the job payload before the trainer may run them
(`allowance.json`) and settled to the confirmed count when the trainer ends. The API `grid-training-runs` creates, lists, reads, cancels and resumes runs.

The child keeps Python stderr, unexpected tracebacks and faults supported by Python's
`faulthandler` in `diagnostic-<attempt>.log` beside the sealed specification. Probe mode
remains JSON-only and creates no diagnostic file. Unexpected Python exceptions inside
training become a failed `GRID_TRAINING_UNEXPECTED_ERROR` result with the last reached
step, written before the lease is released; they never count as a successful export.
Abrupt external termination can still leave no result or useful traceback. In that case
the supervisor keeps the conservative reservation and reports `GRID_TRAINING_CHILD_EXITED`.
Python stderr is line-buffered to retain complete lines before abrupt exit. Native
libraries writing directly to OS descriptor 2 still reach the supervisor's `DEVNULL`;
this log is not a complete capture of CUDA/C++ stderr. Partial Python lines may be lost.

## Per-game candidate evaluation and proof currentness (D-559, TASK-0997)

A registered `not_evaluated` candidate is compared with its base by a
`grid_model_evaluation` job in the general lane (CPU ONNX). The API
`/admin/grid-model-evaluations` queues it only with the candidate's training cohort and
the cohort of every game whose assignment trains in the candidate's family, each frozen,
`eligible` and pinned to the same family and base, and only with a passing candidate
parity. The handler `images/grid_model_evaluation_handler.py` measures one unit per
(game, VALIDATION or REGRESSION): it re-reads the game's snapshot in that game's own
session, runs both bundles on the same decoded frames from the original photo and scores
them with `neural-grid-metrics-v1` through the neutral `training_core/grid_evaluation.py`.
Each unit writes `grid-model-evaluations/<jobId>/<gameId>-<role>.json` atomically and
checkpoints its summary; a restart skips finished units and rebuilds the same canonical
report v2 (`domain/grid_model_evaluation.py`) under the identity `uuid5(jobId)`.

The gate `grid-model-per-game-gate-v1` is one pure function shared by writer and reader:
no regression in complete-correct photos, correct boards, detected boards, false boards,
duplicate detections and image-macro (a missing board costs 1, an unknown value counts as the worst), a strict
improvement of the target metric on the training game's VALIDATION, REGRESSION as the
final non-regression check only, at least five photos per role measured by both models.
The publication reader recomputes every decision and accepts only a v2 `PASS`.

Cross-game currentness never reads a foreign partition. Migration 0166 (manifest v17)
adds `public.grid_model_cohort_notice_marks`, appended only by a `SECURITY DEFINER`
trigger on every `currentness_notice` and read-only for the application role, and the
append-only `public.grid_model_evaluation_cohort_proofs`. `application/grid_model_evaluation.py`
proves one game per transaction: read the notice count, check the exact eligibility,
bind the report with `bind_existing_report` (replay on retry) and append the proof with
the count read first and the game's active storage generation. Publication, activation,
rollback, default and eligibility views of a v2 report require the latest proof of every
cohort to equal today's count and an active store of the same generation
(`GRID_MODEL_EVALUATION_STALE` otherwise, also for a deleted game, whose partitions are
dropped without row triggers but whose storage location is removed); publication also requires every game of the
family. The currentness command repeats the four steps; a withdrawn label is not proven
again.

## Shared candidate of several games (D-560, TASK-1006)

A shared run is a `grid_training` job of kind `grid-shared-training-run-v1`: the primary
game's route pins its cohort and one frozen, eligible cohort of each other game of the same
family, base and mode. `domain/shared_grid_model_candidate.py` holds the pure joint policy
`grid-shared-candidate-v1`: TRAIN and VALIDATION in every cohort, no recording group with two
roles and no TRAIN photo sharing bytes, pixels or recording group with a control photo of
any game. `images/grid_shared_candidate.py` applies it to pinned snapshot metadata; the API
pins the plan SHA and the supervisor recomputes it at every claim. The trainer fine-tunes the
one base on `JointPhotos` with `BalancedSampler` (each round visits every game once, then
recordings in permutations) and stops early on the equal-weight mean of the games'
VALIDATION scores. The candidate keeps the primary `cohortId`, its `snapshotId` is the plan
SHA, and its D-559 evaluation must cover every cohort it trained on.

### Atomowy postęp trenera na Windows

`write_json_atomic` zachowuje fsync i atomową podmianę kompletnego pliku. Krótka blokada współdzielenia Windows (winerror5/32/33) ponawia wyłącznie tę samą podmianę: maksymalnie7prób, opóźnienia10/20/40/80/160/160ms. Inne i trwałe błędy propagują się; poprzedni plik docelowy pozostaje, sprzątany jest tylko własny tempplik. Mechanizm nie zmienia formatu, budżetu, checkpointów ani lease treningu.


## Propozycje w kolejce korekt i kadr podglądu (TASK-1153)

`CorrectionGridProposals` wiąże bieżący `ImageGridReviewItemResponse` z istniejącym
operacyjnym review przez odczyt identyfikatora, importu, gry, SHA źródła i dwóch
rewizji. Montuje wspólne `GridGeometryProposals`; nie tworzy drugiego źródła
propozycji ani endpointu. Klienci bez opcjonalnych metod nadal obsługują korektę
ręczną. Edycja propozycji wyłącza skróty klawiaturowe edytora w tle.

Opcjonalny `viewportControls` w `BoardGeometryCorrectionEditor` zachowuje domyślne
35% u dotychczasowych konsumentów. Kolejka i edycja propozycji wybierają 70% lub
pełny obraz z zakresem wszystkich punktów. Wszystkie operacje centrowania,
przeciągania i zmiany kwalifikacji czytają ten sam wybrany tryb. Punkty pozostają
w oryginalnych współrzędnych. To nie zmienia `board.margin` inferencji.

`scripts/render_grid_correction_comparison.py --directory <katalog>` renderuje
zapisane, przypięte do modeli i sum źródeł wyniki oraz metryki; nie uruchamia
inferencji i nie zapisuje geometrii. Szablon jest w `scripts/templates/`.
Status zastosowania wymaga pasujących ukończonych receiptów; brak dowodu jest
jawny. Test Node uruchamia czystą logikę podglądu w stub DOM, bez przeglądarki
lub sieci. Raport jest snapshotem z chwili zebrania materiału.


Testy renderera nie wchodzą do domyślnego `python:test` (testpaths obejmuje serwisy).
Uruchomienie przy zmianie renderera/szablonu:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s scripts/tests -p test_grid_correction_comparison.py -v
.\.venv\Scripts\python.exe -m mypy scripts/render_grid_correction_comparison.py scripts/tests/test_grid_correction_comparison.py
```

Odrzucenie propozycji odczytuje bieżący kursor kolejki bez utraty historii;
przyjęcie przechodzi do odświeżonego początku. Obie decyzje pozostawiają komunikat
po odczycie. Niezgodna tożsamość daje jawny przycisk odczytu kolejki, a błąd API
osobny retry propozycji; odczyty nigdy nie stosują geometrii.
