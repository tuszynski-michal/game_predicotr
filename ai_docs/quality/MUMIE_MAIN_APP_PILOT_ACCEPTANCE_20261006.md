---
title: Mumie — main application pilot acceptance
status: accepted
last_updated: 2026-10-06
---

# Scope and result

TASK-0884 operational acceptance passed on the real MAIN application. The
operator approved the concrete deployment, migrations, candidate activation,
service restart and first100 images. MAIN is
C:\Users\tuszy\Documents\game_predicotr, branch
v1.1-vision-lab-hybrid-geometry. The implementation branch ends at
v1.7.225 /820083aed4b3d2dda048c938bd2f3ed410132d95; both branch histories
and independent RGB0878 changes are retained in the merge.

The pilot is ready for human correction. This is an operational result, not
an estimate of population symbol accuracy or automatic geometry qualification.

| Actual result | Evidence |
|---|---|
|100 exact retained originals,31,167,375B, three recordings34/33/33 | Frozen inventory and100 actual managed SHA checks |
|99 bound pipeline sources,891 pending boards | Frozen source bindings match exact source/slot counts |
|One unbound source,seq_499996-500004.jpg | Original range exceeds500000; no invented board/sequence/target |
|One importjob f3ff4258-e561-4031-bc04-227c9dbf51b6 | Attempt3,waiting_for_review,199/199,99review,0failed |
|99 exact checkpoints at manual_review | waiting_for_review,retry1; all297 earlier stages retain timestamp/payload digest |
|Mumie candidate active | Iterationfd5b15b6-e335-410d-9720-5f2d3bd6ec43; activationfa00eaa1-5f19-4675-8102-3f40e042ff7c |
|No invented supervision |0 human approvals,0 approved geometry,0 cohorts,0 symbol_training jobs |
|777 preserved | All preexisting registry columns equal baseline SHA a99a7e1fb1f53fb277788707d71540df8ac84be0e0e80b1eb8954d49869f6994; activationd5b3e588-f2f2-4d4b-b2fb-9b5a72a6d52b |

Cold acceptance audit aafa8cf7-ca6b-4897-8bbb-9727c5b3b6fa at18:26:00Z
passed every check. Independent gpt-6.1-sol/high SQL/code review passed with
zero openP0–P2. Fresh processes import the actual MAIN modules, not worktree
modules. Root did not save a human geometry/symbol decision during UI QA.

# Runtime and actual UI

Final identity/readiness at18:25:43Z: MAIN API29756/listener30308,
Admin45912 on3000, Reviewer48888 on3001, general worker38536/48684.
AllHTTP checks200. API has no reload; MAIN UI processes were verified and
adopted after external restarts. No duplicate UI process was launched.
Vision Lab3102 and independent RGB processes were not stopped.

The actual Reviewer import URL is:
http://127.0.0.1:3001/?mode=local&gameId=fea55cc1-ebf4-4cee-b3ab-a520017ed1be&importJobId=f3ff4258-e561-4031-bc04-227c9dbf51b6.
queue=grid-audit is a different historical list and is not this pilot queue.

Actual board sequence10 opens with24 editable nodes and15/15 source-direct
cell previews, model suggestions and all10 catalog keyboard choices. Changing
a cell symbol works without touching the grid or requesting a new preview.
The unsaved choice survives a browser reload; the root removed only its own
trial selection afterwards. No save/approve operation was performed.
Screen proof: C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-main-app-pilot-20261006\0884-main-reviewer-live.jpg.

Existing import requires a rules version. An otherwise empty3×5 draft was
created through the existing API, id96d15e0e-fe88-4acc-a1a1-866ae341d455.
spinCost0 is an unused explicit placeholder, not a payout/free-spin rule.
No publication, paylines, payouts or target calculation were performed.

# Deployment and recovery

The full custom/zstd archive has13,604,719,372B and173TABLE DATA entries.
SHA: caa6dbce9803d35a250ab71ec66c442d9a6e226680d398cab25e61e139242a53.
An isolated retained *_test restore completed exit0 at0143,173tables, exact777
registry and0Mumie sources; database size46,971,090,623B. The3739.9s receipt
measures elapsed time since supervision adoption, not total restore duration.

The restore filled C sufficiently to hit the application's30GiB reserve.
This was the root's deployment error. The initial staging409 occurred before
upload creation. The verified archive was reversibly moved to
D:\game_predictor_backups\mumie-main-app-pilot-20261006\game_predictor_0143_20261006T153523Z.dump.
Both complete byte hashes were verified before releasing its C copy. The
backup pointer and crash reconciliation are durable. No database deletion or
reserve reduction was performed. The *_test database and initial incomplete
2.65GB partial remain retained; the partial is not a recovery archive.

The live database was observed at0143 before integration and at0145 just
before the explicit migration CLI. That CLI succeeded as a no-op. The earlier
0143→0145 executor is not attributable from the available logs. Isolated actual
Alembic migration tests passed; live current/head is
0145_neural_page_geometry_binding and the exact777 registry fence passes.

Actual deployment found four integration defects, fixed in MAIN:

- Controlled API readiness could accept an orphan listener's health. It now
  rejects occupied ports, verifies owned listener PIDs and clears health after
  ownership-query failures; fresh-process regression tests cover these cases.
- Lab VALIDATE checkpoints omitted schema_version. Version1 initial/resumed
  envelopes are validated through the real LocalJobWorker/domain contracts.
- Job HTTP snapshots omitted lab cropSize96. The optional strict DTO now
  carries96 while inputSize stays64; OpenAPI/SDK and start/replay/get/list plus
  wrapper request tests cover the complete contract.
- Manual board_crops copied estimatorFailureReason from a deferred proposal.
  The producer now emits the existing deferred position/reason/sequence
  contract. Stage validation was kept intact; neural and legacy tests validate
  the actual downstream payloads.

The failed import was resumed through the existing per-file retry API in
20/20/20/20/19 steps while the general worker was stopped. The same99 keys,
order and checkpoints were retained; the same job completed processing after
worker restart. The earlier generic job retry did not reset the failed file
associations; its receipt remains historical evidence. There was no second
import, staging, duplicate iteration, destructive checkpoint reset or new image.

# Verification

- MAIN install, Admin/Reviewer builds, focused API/client/UI regression
  checks, lint/types and generated Admin/VisionLab contracts passed.
- Additional readiness3, real lab worker2, catalog/query22, lab/legacy HTTP
  start-replay-get-list2 and deferred neural/legacy pipeline5 tests passed.
  Test groups overlap earlier broader suites; do not sum them as unique tests.
- Generated client build and88 tests passed; OpenAPI generation/check passed.
  Final changed Python files passed Ruff/format and runtime DTO/producer Mypy.
- Real405 cells from three photos retain0 pixel/class drift; input max7.153e-7,
  logit max1.907e-6. New process protected-controls install retry created0files.
- Live100-source audit, managed original hashes, post-retention source correction,
  exact frozen model/snapshot/manifest, same-job recovery and777 fences passed.
- UI real first-open/choose-symbol/reload flow passed without human approval.
  Earlier0882 mobile390/360×844 interactions passed; physical Android remains
  untested. No full-repository unrelated test expansion or load benchmark.

All execution receipts are retained under
C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-main-app-pilot-20261006.
They include backup/restore/relocation, merge provenance, models/control install,
operator-state exact requests/responses, audit-retry-before.json,
100-photo-acceptance-readonly.json, final-service-readiness.json and UI proof.
0884-final-proof.json collects27 successful final command receipts and the
actual acceptance/service/recovery identities; earlier failures remain retained.

# Definition of Done and accepted-plan comparison

| TASK-0884 acceptance item | Result |
|---|---|
|Preserve both branches and current independent work | PASS: merge provenance, two document conflicts resolved preserving both histories |
|Backup/schema/preview before writes | PASS: full verified archive, completed isolated restore, approved preview; migration chronology recorded honestly |
|Main services and models ready | PASS: exact process/port identities, actual render/logit parity, fresh MAIN imports |
|Only Mumie activation and100 pilot sources | PASS: one lab import/activation,100 retained originals,99 bound sources;777 unchanged |
|Recovery preserves source/decision/history | PASS: cold checkpoint/HTTP tests plus actual exact99-file resume and unchanged297 prior stages |
|No push or interruption of active writes | PASS: fresh no-active-job guards, owned process stop, RGB/Vision Lab retained; no push |

No new requirement/architecture change was introduced by these integration
fixes. Optional API contract regeneration is complete; operator documentation
is updated. Versioned completion is v1.7.226; its full hash is recorded in the
task Outcome and CURRENT_STATE after commit.

# Remaining operator work and limits

The next step is human review of the existing pilot. Larger500/2000 batches
follow operator acceptance, not another model installation. Symbol training
uses pooled human corrections and protected-source gates; uploads perform
inference, not a new training run. Automatic neural-grid retraining for every
new game is not implemented; its24-node snapshot remains a separate iteration.
34/34 selected controls do not measure an entire movie's accuracy. RGB+gray R2
and V5 remain rejected. Manual Super selection/session rules remain a separate
task. The unbound ending source needs human range/binding review. No TRAIN,
automatic promotion, target calculation, data cleanup or push in0884.
