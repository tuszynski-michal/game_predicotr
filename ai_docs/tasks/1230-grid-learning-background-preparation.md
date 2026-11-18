---
title: Durable background preparation of grid correction learning
status: in_progress
last_updated: 2026-11-17
---

# TASK-1230 — Background preparation and supervised detector training

## Status

in_progress — original training/evaluation complete; authorized partial-correction run is preparing/training; separate background-feature source integration remains pending.

## Goal

Queue correction preparation immediately, show persisted progress, and train/evaluate a
screen+grid candidate for Mumie a2 without a total preparation timeout.

## Context

Operator authorized repair and actual training in the current conversation. Read-only
preview of all 11 own correction imports (25,631 photos) returned GRID_COHORT_TIMEOUT
after 302 seconds. No new learning job had been created. GPU training/evaluation
budgets and quality gates remain unchanged; ready means a verified candidate, not
automatic activation.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`

## Scope

- Add opt-in background preparation to the existing learning start operation and job type.
- Preserve legacy requests, idempotency, ownership, protected splits and default-version fences.
- Preparation-only jobs pause for review; explicit resume authorizes training.
- Persist phase, actual units, last progress, heartbeat and immutable prepared artifacts.
- Keep 300-second stall/single-statement protection, renew only on actual progress.
- On restart, revalidate unfinished preparation; reuse completed immutable artifacts and child IDs.
- Use background preparation in Admin and resolve saved start requests by their stable key.
- Verify changed code, restart/deploy only within operator authorization, then supervise real training.

## Acceptance criteria

- [x] Start returns an existing/new durable job without running the expensive split in HTTP.
- [x] Lost-response replay never creates another workflow; another active workflow blocks duplicates.
- [x] Preparation progressing beyond 300 seconds succeeds; a stalled unit fails visibly.
- [x] Prepared state survives a fresh worker/service instance; changed input/default fails closed.
- [x] Preparation-only cannot train without explicit resume.
- [x] Admin shows preparation progress and recovers a saved command without a new key.
- [x] API/OpenAPI/generated client/wrapper/request tests agree.
- [x] Actual screen+grid candidate has training and evaluation evidence; no automatic activation.

## Expected files

Existing: correction-learning application/schema/router/panel/state, correction split,
cohort prepare commands and worker handler. New: preparation progress and background
admission modules, targeted regression tests. Documentation and generated API/code maps.

## Verification

Run API/worker regression tests for changed workflow, scoped ruff/mypy, Admin tests,
typecheck/lint, OpenAPI/code-map/docs checks. Check live API job IDs, progress,
training artifacts and per-game gate before reporting ready.

## Risks / open questions

- Git metadata write denied by host during worktree creation; protect existing user changes.
- Preparation may discover missing data or a quality rejection; never weaken gates for success.
- Completed preparation is immutable; interrupted preparation restarts with current proofs.

## Outcome

### Authorized partial-correction training — 2026-11-17

The operator explicitly selected "Nowy trening na poprawkach" after disclosure
of one new run with at most 7200 seconds of GPU training and quality evaluation
before activation. No model activation or service restart is authorized.
The TASK-1240 starter was used with explicit grid-only mode and a separate
absolute command file `.runtime/grid-partial-learning-20261117.json`.
New parent: `6ac108a6-7b99-4701-bbf3-b5d78fae3b89`, command key
`90eb8e9b-bbcc-4cf3-b8f5-bf19c45262bf`, created 2026-11-17 09:32:51 UTC.
Base/default remains `01767a49` revision 5; game assignment remains `abe39bce`
revision 6. The original completed screen+grid parent and saved command remain
unchanged. Preview from TASK-1240 qualified 503 TRAIN photos/647 boards, including
493 partial photos; actual new frozen counts must be verified after preparation.
At 09:33:41 UTC preparation was recording context at 13,800/25,631 sources,
with a fresh progress heartbeat and no error. GPU start is not yet claimed.
Live operational evidence: `.runtime/grid-partial-learning-20261117-status.json`
and `.runtime/grid-partial-learning-20261117-observations.jsonl`.

The persisted preparation artifact was read from a fresh process and verified
against its content-addressed SHA `3ff414c8a823b3b8f8bce1a21a2ec582861ff7a7a495d55d3838a9e4b1581bc9`.
It confirms TRAIN 503 photos/647 boards, VALIDATION 19/60, REGRESSION 13/21,
canStart true and no blockers. Its accounting reports 128 new TRAIN photos/135
boards and 375 previously used TRAIN photos/512 boards. Planned optimisation:
3600 steps, six evaluations; estimated run time 2580 seconds, not a guarantee.
The actual frozen cohort and GPU start remain to be verified. Summary:
`.runtime/grid-partial-learning-20261117-prepared-summary.json`.

At 09:42:00 UTC the same parent was processing `cohort_capture`, 283/25,631
sources, with a current heartbeat and no error. New cohort
`8d571c98-bbcc-5d00-9792-4ec77e53c491` is preparing in grid-only mode. The start
request returned and its shell exited successfully; the existing general worker
owns continued preparation. The persisted command has preparationOnly=false, so
the existing workflow will create the GPU child and evaluate it after successful
capture/freeze. At this checkpoint no GPU child or new candidate exists yet.
The start request is fulfilled; completion and activation are not claimed.

Manifest, registration and recovery repairs are deployed and pushed. The original
workflow completed training and evaluation with PASS; candidate remains inactive.
Operational history below retains earlier failures and approvals.
Background job `42f30e0e-9707-4cf9-aaf6-10482f6e9d60` created
2026-11-16 00:46 Europe/Warsaw for Mumie a2
`246a1f54-eee8-49d5-b11a-0fde70e5eecd`, screen+grid/v4, full default scope,
no exclusions. Base `01767a49-980e-5ab6-962e-e22d8414a93e`, default revision 5.
Exact command key `e23a470b-b401-473b-b3a9-37bb3f0c3344` is persisted in
`.runtime/grid-detector-learning-246a1f54-eee8-49d5-b11a-0fde70e5eecd.json`.
Supervisor: `scripts/Start-GridCorrectionLearning.ps1 -GameId
246a1f54-eee8-49d5-b11a-0fde70e5eecd -Wait -MaxHours 6`. Replays the same key;
never create a new command merely because a tool/session disconnects.

### Continued supervision and explicit progress-policy approval — 2026-11-17

The operator requested supervision based on actual work rather than a two-hour
deadline, explicitly approved replacing that ceiling for this run, then approved
1–2 hours of additional implementation/tests/Claude review. The implementation is
isolated in `codex/grid-progress-supervision` (TASK-1245, originally TASK-1244). No policy grant has yet
been applied and no service was cancelled/restarted by this follow-up.

Read-only native stack/CPU/I/O observations proved transition from TRAIN metadata
indexing to VALIDATION indexing. At 15:08:26 UTC the same child
`6d003b6e-e0c1-4b15-be97-c10cbf92fac0` had 477 GPU steps, 62% sampled GPU use and
2089 MiB allocated. Later checkpoints at 600, 1200, 1800 and 2400 were observed.
The actual training finished with stopReason=early_stopping after 2400 optimizer
steps, selecting the best step-1200 weights. Its old-budget consumption was
3165.907 seconds; the cumulative time ceiling did not end this run. The generic
completed job shows 3600/3600 planned units, which must not be mistaken for 3600
executed optimizer steps.

Candidate `6cc10344-1d69-5765-b8c8-423a0313984a` was registered. The same parent
created evaluation `19119701-0904-46e0-8426-ba4af72aa567`, report ID
`e74c552e-25e3-55dd-884f-3d0a4feb0c8e`. At 15:46:44 UTC evaluation was processing,
without error; native sampling confirmed metadata indexing in worker general.
Supervision continues through the evaluation result. Candidate is inactive.
Read-only checkpoint byte/binding, early-stopping and baseline-floor validation
passed in a fresh process: `.runtime/task1244-checkpoint-validation.json`.
Samples and stack evidence remain under `.runtime/task1243-*` / `task1244-*`.

At 16:14:26 UTC the same parent and evaluation were completed, 4/4, verdict PASS
(per-game gate v6, photo-only evidence). Candidate `6cc10344` remains inactive;
default/base 01767a49 revision 5 and assigned abe39bce revision 6 are unchanged.
The old 7200-second ceiling did not end training; no policy grant was applied
to the completed job and no extra training or restart was performed by supervision.
Against the pinned base: VALIDATION correct boards stay 52/60, normalized error
0.0187900864 -> 0.0186210056, cell-cut-safe boards 40 -> 41; REGRESSION stays
17/21, normalized error 0.0132143222 -> 0.0127910717. This is a small improvement
against that base, not a comparison with the assigned model.
Immutable final API/result evidence:
`.runtime/grid-partial-learning-final-20261117T161807227714Z.json`, SHA
`b4391cd9cb48cd9515145d1410c3abfd12c52349a105d9a43f2c1d81a1f57f69`;
compact summary `.runtime/task1244-supervision-final.json`.
Supervision of this run is complete. Broader feature source integration remains
separate. TASK-1245 progress-policy implementation has final Claude PASS (0 P0/P1).
After explicit result/merge/deployment approval it was integrated and pushed at
`9cd972aa4b6c06436286beca8f903b427432b7b0` (v1.7.667–670). The original task number
1244 was renamed to 1245 after a parallel calculation task reached main; raw audit
evidence retains its original identity and hashes. Both histories are preserved.
All 45 tracked local changes were restored and byte-verified, with recovery stash
`86709232ca55933f606ded7707b138e89cbd14b1` retained. Root docs checks PASS.
API is healthy in a new process; general worker 28044 and grid-training worker
34316 are running. Image-selection worker 17788 was preserved. The fresh-process
policy round trip and live nullable-budget/background contract both PASS after
removing the owned worktree and branch. No grant was applied to completed training,
no additional training was created and no model was activated. Deployment evidence:
`.runtime/task1245-health.json`, `.runtime/task1245-cleanup.json` and
`.runtime/task1245-deployment.json`; raw audit evidence remains in
`.runtime/task1245-evidence/`.

### Preparation throughput repair deployed — 2026-11-17

The operator approved the finished TASK-1242 result (85 targeted tests and Claude
PASS, no open P0/P1), merge/push/cleanup and a brief restart of API and only the
general worker. This later approval permits those two restarts; image-selection
and grid-training workers were preserved. Activation remains a separate decision.

Main and origin/main are `041002571fc029eb66c82bae19bcad66ec4bfd63`, containing
v1.7.665 (`cd83092bf0f9354ee4f1fe996f1d4a32d9b94c53`) and v1.7.666. The owned
`codex/grid-preparation-throughput` branch and worktree were removed. All 45
pre-existing tracked modifications and untracked user files were preserved;
the index stayed empty. Recovery stash `a343dd0d94b5261665ab3649fbf7168cf01e4350`
and `.runtime/task1242-cutover-backup/` remain available. No migration was needed.

The same parent `6ac108a6-7b99-4701-bbf3-b5d78fae3b89`, cohort
`8d571c98-bbcc-5d00-9792-4ec77e53c491` and command key
`90eb8e9b-bbcc-4cf3-b8f5-bf19c45262bf` resumed from cursor 15,770. No new start
command, discarded page or changed split/recipe was introduced. Full post-freeze
verification checked all 5,127 physical page hashes, including every retained
page, and passed comparison with the stopped-run snapshot. Evidence:
`.runtime/task1242-run-preservation-20261117T143247772023Z.json`.

Observed throughput increased from 99.46 to 893.40 sources/minute (8.98x) over a
186.70-second interval on this same run; this is an interval measurement, not a
guarantee for every source. Evidence: `.runtime/task1242-speed-after.json`.
Materialization completed all 25,631 source records around 14:25:32 UTC; cohort
freeze was confirmed at 14:31:18 UTC, revision 5258, manifest SHA-256
`7e10799ffc29e5bcc8fdeb9e08878d098f220a5b218a329dc9c93c73ad46f2a5`.

| Frozen role | Photos | Boards |
| --- | ---: | ---: |
| TRAIN | 503 (493 partial) | 647 |
| VALIDATION | 19 | 60 |
| REGRESSION | 13 | 21 |

The existing parent automatically created training child
`6d003b6e-e0c1-4b15-be97-c10cbf92fac0` at 14:32:44 UTC. By 14:41:38 UTC it was
processing, admitted with maxSeconds=7200 and plannedSteps=3600, with its native
trainer running. First GPU allocation/optimization step was not yet observed;
progress was 0/3600 during input loading and verification. This is not a claim
that a new model has been trained. Base/default revision 5 and game assignment
revision 6 remain unchanged; no activation was performed. Final deployment and
live-state receipts: `.runtime/task1242-deployment.json` and
`.runtime/grid-partial-learning-20261117-status.json`.

The generic parent preparation checkpoint can still show the pre-restart cursor
15,770 while the cohort is frozen. Cohort status and immutable page verification
are authoritative for completion; this pre-existing display issue was not changed
by the throughput repair. The broader background feature and its source changes
remain a separate active task.

### Changed

- Existing start supports durable preparation; lightweight GET avoids whole-population work on reload.
- Immutable prepared artifact, progress/cancellation/lease fencing, same-job explicit training resume.
- Data preparation/cohort pages/freeze use progress-bounded deadlines; legacy requests retain budgets.
- A registered updated worker capability gates new payloads during deployment.
- Admin starts preparation in background and reconciles accepted saved commands by key.
- No activation, destructive migration, external push or merge.

### Verification results

- API/request/progress/worker targeted command: 41 PASS; expanded progress/worker: 6 PASS.
- PostgreSQL: background admission/replay/restart/resume, legacy parent and freeze-lock selection PASS.
- Admin interactions 64 PASS; saved-command utilities 3 PASS; TypeScript, scoped eslint, production build PASS.
- Scoped Python lint/mypy PASS (including the final preparation/cohort/worker files).
- OpenAPI current; docs checks PASS (startup 44985 B); generated code map updated.
- RTX 4050, torch 2.12.1+cu130, CUDA available in the configured training interpreter.
- Baseline-only failure confirmed in unchanged `split_mapping`: old contract test fixture omits
  `schemaVersion` and raises KeyError. Baseline AST and behavior are identical; not changed for green.

### Not completed

- Operational training/evaluation acceptance is complete; final evidence is below.
- Review/commit/integration of the pre-existing background-feature source changes
  is separate from repair tasks 1234/1235/1237. Do not automatically commit the
  existing 45 local changes, which also include unrelated selector work.
- No model activation is authorized. The earlier Git metadata denial was resolved
  through host-approved operations; unrelated configuration/worktrees remain intact.


### Operational preparation evidence

At 00:51 Europe/Warsaw the first prepared artifact passed with no blockers:
TRAIN 10 complete photos/90 boards, VALIDATION A 5 complete photos/45 boards,
REGRESSION 13 photos/21 labelled boards; 561 annotated photos/758 labelled boards
in the available population. Partial photos remain excluded from screen TRAIN/A
by the existing policy, not by a new cap. Planned training: 1200 steps, 600 train
seconds, estimated total run 1020 seconds. A new general process (PID 39440)
registered `worker-v10-general-grid-preparation-v1`. Cohort preparation is running
with continued progress beyond the former total 300-second deadline.

### Notification/supervision handoff

The foreground PowerShell supervisor is still running (exec session 38796) and
polls the existing job. A hosted condition-watch could not execute in the local
environment (first recorded run failed without a result), so it was disabled.
A local Codex heartbeat was then rejected by automatic approval review: persistent
hourly automation and sharing project paths/API identifiers/idempotency information
with that destination lacked explicit user authorization. No active scheduled
notification has been established. Do not bypass that rejection. Obtain explicit
authorization for the local Codex notification before retrying, and minimize the
prompt metadata (the idempotency key need not be transmitted). This does not stop
the actual learning job or its own checkpoint/heartbeat/recovery mechanism.

Latest acceptance: scoped mypy 6 files PASS after the typing correction; latest
PostgreSQL background workflow test PASS including no GPU probe before preparation-only
review and explicit resume before runtime admission. Freeze selection/locking PASS.

### Generic Jobs monitor compatibility

Fixed the generic Jobs response schema for background preparation: pins are
optional only with the explicit background flag; legacy payloads still require
pins. This resolves the list/detail HTTP 500 caused by the new durable payload.
Targeted Jobs response tests: 11 PASS. Live unfiltered list returned 50 jobs,
including the active learning exactly once; detail returned processing with a
fresh heartbeat. The running job was not restarted or replaced.

### Old worker consumed a background step (2026-11-16)

At 01:39 Europe/Warsaw the parent failed with KeyError on attempt 53.
The persisted claiming worker was `worker-v10-general` (without preparation
capability), while the registered lane advertises the new version. HEAD's
legacy advance directly reads payload["pins"], absent from background inputs.
The old heartbeat thread logged that it was fenced but its polling loop used
`should_stop=lambda: False`, so the obsolete process kept claiming work.

9800/25631 captured sources remain durable. A bounded replay of the next 200
sources, full advance and current handler all passed; the latter two used an
outer transaction that was explicitly rolled back. No job state was changed.
The parent is still failed; no training run or candidate exists.

Repair files: worker lane heartbeat/CLI, job-store capability filter and their
regression tests. A fenced heartbeat now stops future claims; incompatible
versions skip background inputs both in candidate selection and under row lock.
These source changes cannot affect already loaded old Python processes. Before
resuming the same parent through its existing resume endpoint, stop all obsolete
general workers on the host and restart the general lane. Never fabricate pins
or mutate the immutable job input to accommodate obsolete code.

Regression verification: heartbeat/CLI 8 PASS; disposable PostgreSQL background
workflow 1 PASS including an incompatible worker leaving the parent unclaimed.
Host process visibility is unavailable in this command sandbox (no host Python
processes are listed). No live restart or resume was performed. Do not report
the source repair as deployed; the failed parent remains preserved.

Final scoped ruff and docs checks PASS (startup 44990 B); maps regenerated.
Unrestricted scoped mypy followed imports and reported unrelated existing
source-lattice/replacement/geometry errors plus a boolean SQL expression in this
change. The latter was corrected to literal(bool) and the PostgreSQL regression
rerun passed. The follow-imports-silent retry produced no output for over 60 s
and was interrupted; no complete mypy PASS is claimed for this operational fix.

### Authorized restart and resume (2026-11-16 02:17 Europe/Warsaw)

Operator confirmed all workers stopped and authorized continuation. API confirmed
all three lanes stopped. Manager detached launches did not survive command end;
status was verified stale and DB still stopped before any replacement launch.
Current workers run in separately controlled exec sessions: general 77059,
grid-training 36557 (CUDA interpreter .venv-vision-lab), image-selection 35846.
All three registered and heartbeat with grid-preparation-v1. Keep these sessions
running; they are not the stale PIDs in the manager's initial launch report.

POST resume reused parent 42f30e0e and cohort 19a52a6c. Attempt 54 on the updated
worker passed the former failing boundary and committed capture cursor 10000.
At 02:19 capture continued at 10174/25631 with a fresh heartbeat and no error.
Foreground supervisor is now exec session 78324 (-Wait -MaxHours 6), replacing
the older ended watcher. No scheduled notification or automatic activation.

### Health check 2026-11-16 02:46 Europe/Warsaw

Not healthy: all three lane registrations are stopped (last heartbeat 02:36:22).
Parent still displays processing, but its last heartbeat is 02:36:17 and lease
expired 02:37:17. Cohort revision 70 has durable capture cursor 13800/25631.
No new error or training run. The supervisor status file last changed 02:36:18;
its previous exec session is no longer accessible. Thus the previous agent-session
launch did not provide lasting supervision. Exact shutdown cause is not logged.

Do not keep relaunching temporary agent-session workers as a permanent fix.
Run the existing manager in the operator's native Windows PowerShell:
`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/manage_worker_lanes.ps1
-Action Start -Lane all -GeneralThreadBudget 7`. The updated store recovers the
expired lease and continues the same parent; no fresh command key is needed.
Then verify actual cursor movement and fresh heartbeats. A separate native
PowerShell can run Start-GridCorrectionLearning.ps1 with the same game, -Wait
and -MaxHours 6. Ready still requires trained/evaluated candidate evidence.

### Continued supervision request 2026-11-16 03:00 Europe/Warsaw

Operator requested monitoring through training/evaluation completion. All three
lanes now running again with updated capability and fresh heartbeats. The same
parent recovered its expired lease (attempt 75); capture advanced from 13800
to 14200, with no error. Full screen+grid workflow remains authorized and will
automatically advance to training/evaluation after preparation, without activation.

Codex thread heartbeat creation returned a generic app-tool request failure,
without any automation confirmation. No retry or duplicate local heartbeat was
created. The existing hosted watch was inspected: prior recorded attempt failed
without output; inherited environment details remain unavailable, which is not
proof of the exact failure cause. On the renewed direct monitoring request,
the existing watch Automation_ce043113f97481919e1e5e67b4e44300 was re-enabled
with a minimized prompt, hourly COUNT=12, Europe/Warsaw. API confirmed enabled,
next check 03:03:13. Check its actual first recorded result before claiming
successful future access; schedule registration alone does not prove execution.
Its instructions require a concrete critical blocker for inaccessible local
runtime, suppress healthy-progress notices, require completed/PASS/artifacts
before ready notification, and disable the watch after resolution.

At 03:04 the parent still has fresh advancing heartbeats and no error; capture
had reached 14800. Hosted watch remains enabled, but peek still shows only the
old failed run and no result for the new schedule yet. Do not confuse successful
schedule update with verified execution or guaranteed notification delivery.

### One-shot registration collision 2026-11-16 03:08 Europe/Warsaw

Operator requested a 15-minute agent monitor and technical repair of failures.
The scheduler supports at most hourly checks; no unsupported 15-minute schedule
was submitted and the existing hourly watch remains unchanged.

Live DB proved the general lane was overwritten by worker_id task1231-oneshot,
worker-v10-general, PID 20692, started 03:07:49 and stopped in the same second.
The actual manager general worker logged that it was fenced at 03:07:16; an
earlier manager process has the same fenced log at 03:04:03. Other lanes remain
healthy. Parent has no error and committed capture cursor 15200, but is queued
waiting_for_dependency while general is stopped. No training run exists.

CLI now registers the persistent lane heartbeat only for --poll. One-shot
claims retain their job lease/heartbeat but cannot replace or stop the lane's
registered polling owner. Updated CLI tests require no registration for general
or image-selection one-shot calls and retain registration/fencing for --poll.
This cannot patch an already loaded process or a custom one-shot helper from
an older worktree. Stop using global lane registration in such helpers and
restart the native general worker after deploying the updated root code.

CLI/heartbeat regressions 8 PASS, scoped ruff PASS, scoped mypy with silent
imports PASS for cli.py. Maps and docs checks PASS. Native general still needs
restart; do not claim current queued job is actively processing without a fresh
worker heartbeat and advancing capture cursor. Agent-session launch is not a
durable replacement for the native operator-managed process.

Final recheck: capture cursor 15400. The global lane was overwritten again by
task1231-oneshot / worker-v10-general, started 03:10:12 and stopped 03:10:16.
This confirms the obsolete/custom helper remains an operational blocker despite
the fixed root CLI. Disable that helper's lane registration before restarting
the native general worker; repeating temporary launches will not solve it.

### Materialization completed, freeze blocked — 2026-11-16 14:34 Europe/Warsaw

Fresh local API: the same parent failed at 13:41:35 Europe/Warsaw with
`GRID_COHORT_METADATA_TOO_LARGE` / `Metadata page exceeds its bound.` The cohort
is `ready_to_freeze`, revision 5257, with no remaining materialization cursor.
TRAIN, validation and quality policy were not changed. No trainingRunId,
candidateVersionId, evaluationId, reportId or verdict exists; GPU training has
not started. Worker lanes have current heartbeats; restarting them alone does
not remove the artifact-reader failure.

Root cause verified against the stored artifact and current code:

- Manifest SHA-256:
  `d2c9c9c552fcaf3ff89c5acb6803ab9f6061ad67c962b487bddd4a35d4f22620`.
- Stored at `artifacts/data/grid-training-cohorts/`
  `246a1f54-eee8-49d5-b11a-0fde70e5eecd/`
  `19a52a6c-99ea-56ba-b713-c918338db415/pages/<SHA>.json`.
- File size 21,181,768 bytes / 20.20 MiB; streamed SHA-256 matches its filename
  and the manifest SHA returned by the cohort API.
- `GridCohortArtifactStore.read_json` in
  `services/api/src/game_predictor_api/storage/grid_training_cohort_artifacts.py:83`
  rejects any JSON larger than 16 MiB. The writer publishes the root including
  full `photoSplit` in `application/grid_training_cohort_commands.py:492`;
  freeze reads that same root through the bounded reader at
  `application/grid_training_cohort_freeze.py:144`.

Required repair: reconcile manifest publication and bounded reading for large
populations, keeping checksum verification, split evidence and quality gates.
Cover writer/reader compatibility and frozen-currentness on an isolated copy,
then resume the existing failed parent with the existing resume operation.
Do not create another learning, replace immutable artifacts, reset the cohort
or blindly retry the unchanged reader. Stored cohort pages and manifest remain.
Code changes require the separate worktree requested by the operator; this
session previously could not create its Git ref, and the required Claude audit
is blocked by CLI OAuth (TASK-1233). No code patch, API/Admin/worker restart,
requeue, new training, activation, push or merge was performed for this check.

### Large-manifest repair prepared — 2026-11-16

The independent compatibility repair TASK-1234 is committed in the separate
`worktrees/grid-cohort-large-manifest` / `codex/grid-cohort-large-manifest`,
v1.7.649 / `a79b12aba25192a02276d670f31d85f0278505ed`.
Git writes and the Claude CLI audit succeeded in this session; earlier blockers
do not describe the repair's current state. Claude Opus 5.5 PASS, 0 P0/P1.

Publication, API/preparation/freeze and training snapshot readers now share
a 64 MiB JSON budget. The API verifies SHA-256 over the same bounded bytes it
decodes. Oversized publication fails before creating an unreadable immutable file.
The preserved 21,181,768-byte manifest and 5,127-page index passed API/training
reads on isolated storage and in a fresh process. Corrupted copies fail SHA-256.
No production artifact was overwritten.

Verification: 79 PASS, 6 baseline unit failures reproduced against HEAD;
scoped lint/format/mypy and docs/maps PASS. Disposable PostgreSQL verified freeze,
restart/replay and a fresh-process 120-target dataset; the later stale-input case
hit its existing 105-second soft deadline, so the entire E2E is not a PASS.
P2 risks retained in TASK-1234: portable comparison export's separate 16 MiB
limit, incomplete stale-input E2E coverage and decoded-object memory overhead.

Not deployed or resumed: result acceptance and merge authorization plus fresh
API/general/grid-training processes are required before calling the existing
resume endpoint for parent `42f30e0e-9707-4cf9-aaf6-10482f6e9d60`.
The local API still confirmed this same failed parent/cohort and no training
or candidate IDs. No new command key, workflow, activation, service restart,
merge or push was performed. TASK-1230 remains blocked on operational handoff.

### Authorized merge, restart and same-parent resume — 2026-11-16

Operator explicitly accepted merge/push/cleanup, deployment, API/worker restart
and resuming the same parent. Fast-forward and push completed:
`main` = `origin/main` = `656a966b5342d47254865849980c407f71c014aa`, containing
repair `a79b12aba25192a02276d670f31d85f0278505ed`. No migration was required.
Version labels 1.7.649 and 1.7.650 also occur on the separate efficiency-plan
branch; existing history was retained and commits are identified by hash.

Existing tracked work was captured in a recovery stash and a byte/hash backup
under `.runtime/task1234-cutover-backup`, then restored and verified (45 files;
two process/architecture documents combined with the accepted incoming changes).
No pre-existing changes were added to the repair commits. The merged worktree
and local `codex/grid-cohort-large-manifest` branch were removed after detaching
their `.venv` junction; main dependencies and other worktrees remain intact.

All old API/general/image-selection/grid-training processes were stopped.
The first worker-stop status finalization exceeded 10 seconds; process inventory
confirmed no orphan general worker, and the remaining stops succeeded with a
30-second status limit. API restarted with its original `--reload` mode, PID
7372 (`.runtime/api-task1234.pid.json`). New worker PIDs: general 13176,
image-selection 14364, grid-training 18008; budgets 7/5/1 and existing
`.venv-vision-lab` CUDA interpreter retained. Fresh API health and all three
`grid-preparation-v1` lane heartbeats were verified after the launch calls ended.

POST to the existing `/42f30e0e-9707-4cf9-aaf6-10482f6e9d60/resume` succeeded
at approximately 15:26 Europe/Warsaw. Learning ID, cohort `19a52a6c`, base,
default revision and original command key were preserved. No new start command
or workflow was created. Parent is processing at attempt 5264, with renewed
heartbeat/lease and no error. Training/candidate IDs were still null at that
observation; actual GPU training and candidate readiness are not yet claimed.

### Subsequent SQL closure timeout — 2026-11-16 15:35:08 Europe/Warsaw

The same resumed parent failed on attempt 5264 at `2026-11-16T14:35:08.273507Z`
with `GRID_COHORT_TIMEOUT` / `The metadata closure exceeded its bounded lock budget.`
The large manifest and materialization pages were successfully read; execution
passed population/member validation and reached `register_cohort_use` in
`application/grid_training_cohort_freeze.py` before the frozen status commit.

Read-only PostgreSQL activity showed an active
`SELECT public.recording_cohort_command_v10(...)` query, with no lock wait event.
Its final statement reached the existing 300-second budget. This is a subsequent
SQL closure/performance blocker, not the manifest-size error. The last persisted
progress sample was 25,400/25,631 due to checkpoint throttling; the SQL call follows
the complete member loop. No restart/retry of the unchanged closure was attempted.

Post-failure proof: cohort remains `ready_to_freeze`, revision 5257, identical
manifest SHA-256; learning/cohort/base/default/command identities are unchanged.
No trainingRunId or candidateVersionId exists. The closure transaction did not
publish frozen state; PostgreSQL activity afterwards showed no remaining active
query. API and all three native worker lanes remain healthy with fresh heartbeats.
Full response evidence: `.runtime/task1234-post-resume-failure.json`.

The authorized manifest fix, merge/push/cleanup, deployment, restart and same-parent
resume are complete. Actual training is still blocked. Repairing registration
performance is a larger follow-up: inspect the private SQL closure and its input
proofs, preserve transactional/currentness fences, add targeted regressions, use
Alembic for any function changes, and obtain the required independent review.
Do not simply remove the 300-second guard or launch another workflow. Further
costly implementation requires the operator's explicit cost/scope approval.

### Additional repair authorized and prepared — 2026-11-16

Operator explicitly approved the additional timeout repair and cost, tests,
independent review and same-parent resume. TASK-1235 is isolated in
`worktrees/grid-cohort-closure-timeout` / `codex/grid-cohort-closure-timeout`.
It batches context reads at 200 sources and derives equivalent empty contexts
only for sources with no registry/history links; connected or nullable sources
retain the original closure. Registry proofs and all admission checks remain.

Prepared Alembic migration: `0191_grid_cohort_linear_closure`, replacing bodies
of context v3 and cohort v4 while preserving signatures, security and ownership.
35 unit/schema tests and a dedicated PostgreSQL differential/registration test
passed, including two pages, roles/purposes, aliases, diagnostic flags, stale
proofs, fresh connection and upgrade/downgrade. A historical test failure was
reproduced unchanged on main. Read-only comparison on 200 actual sources returned
identical PostgreSQL JSON text/hashes; sample context time fell from
0.9474/1.1147 s to 0.3434/0.3955 s for the two preview modes.

At this checkpoint the independent Claude review is pending. The operator DB
is still on 0190; no new migration, service restart, workflow start or live
registration retry was performed during this repair. Parent 42f30e0e remains
preserved after its last SQL timeout; ready/trained status is not claimed.

### Reviewed SQL repair deployed and same parent resumed — 2026-11-16

Claude Opus 5.5 CLI review round 1: PASS, 0 P0 / 0 P1. Report and validated
receipt: `ai_docs/quality/TASK-1235_AUDIT_claude-opus-5-5.md`. Three P2 limitations
are recorded in TASK-1235, including the lack of a whole-cohort time forecast.
Operator explicitly accepted the reviewed result, merge/push, migration, restart
and same-parent resume. Implementation commit `v1.7.651`,
`4dbb57b5ecae9d966f86957fafbfe27d76e048f4`, is in main and origin/main.

With API and all three worker lanes stopped, Alembic upgraded 0190 to
`0191_grid_cohort_linear_closure`. Fresh-connection SHA checks matched both
function bodies to the approved preview exactly. No table/data deletion.
45 pre-existing tracked dirty files were backed up and restored; untouched files
were byte-verified, overlapping docs merged, maps regenerated from combined
sources. Recovery stash `7400d55fbdbb168f61b80bc2350214153aa25e8e` is retained.

API PID 32188 and all lanes restarted; general/image/GPU budgets remain 7/5/1,
GPU trainer uses `.venv-vision-lab/Scripts/python.exe`. At 16:15:01 UTC the same
parent was resumed exactly once through its resume endpoint, retaining cohort,
manifest, original command key, base and default revision. Attempt 5265 entered
processing with a fresh heartbeat. At this checkpoint full registration and
GPU training are still being observed; neither is claimed complete.

The full retry subsequently failed again with `GRID_COHORT_TIMEOUT`, attempt
5265, at the preserved 300-second SQL statement budget. No training/candidate
was created. A bounded read-only probe identified the remaining header cost:
32 accesses to mode through the 22,235,980-byte JSON document took 1.428059 s;
32 accesses to the scalar extracted once took 0.000081 s. These document
accesses remain inside the per-source loop in the original SQL body. Evidence:
`.runtime/task1235-header-probe.json`. No additional schema change or retry was
performed during this diagnosis. Approval requested before further costly
implementation/tests/audit; the original data and workflow are preserved.

Operator subsequently approved the header-read continuation and its deployment
after successful checks. Migration 0192 is prepared on the repair branch.
39 unit/schema tests PASS; expanded disposable PostgreSQL test PASS (84.86 s),
including both modes, admission guards, reservation releases, exact 0191 rollback,
permissions and a fresh connection. Scoped lint/format/types/docs/maps PASS.
Actual header projection is byte/field-equivalent and avoids repeated document
access; no operator schema change or resume has occurred for 0192 yet.

Focused Claude round 2 returned a report, but its list formatting failed validation
(`Finding cannot be both open and closed`): a closed-item explanation referenced
another open item. This is not PASS. Request/diagnostics are retained; explicit
permission was requested for one format-correct repeat, without automatic retry.

### Header repair verified and original workflow advanced — 2026-11-16

Operator approved the single audit repeat. Focused Claude round 2 passed with
0 P0 / 0 P1; validated report/receipt are in `ai_docs/quality/`. One local transport
preflight stopped without starting Claude; the approved paid repeat succeeded.
Implementation `v1.7.652` / `7c833c7c6555ae8f841a2a5cbe3f438341b51fde`
is in main and origin. Alembic 0191 -> 0192 was applied with API/lanes stopped.
Fresh-connection definition SHA matched the approved preview, with unchanged
function identity/permissions/security and unchanged context function.

API PID 36176 and all three lanes restarted; budgets and CUDA interpreter stayed
7/5/1 and `.venv-vision-lab/Scripts/python.exe`. Resume at 17:32:11 UTC retained
the original parent/cohort/base/default/command/manifest identities (attempt 5266).
Fresh read at 17:39 UTC confirmed cohort frozen/revision 5258, 25,631 plan sources,
884 registry uses (428 TRAIN, 41 VALIDATION, 13 REGRESSION, 402 BUFFER), zero releases,
unchanged manifest/split hashes, and disk SHA verified. The registry timeout is fixed.
Evidence: `.runtime/task1235-live-verified.json` and observation history.

The same parent advanced to attempt 5267 and created training run/job
`c489f65f-8272-412b-aaf1-f86bac000856`. It is processing, stage training, attempt 1,
planned 1200 steps, with a fresh heartbeat. At 17:46 UTC progress was still 0/1200
and GPU memory/utilization were zero, so actual GPU compute and a trained candidate
are not yet claimed. Training/evaluation remain in this original workflow; no
automatic activation or new workflow was requested.

At 17:50:55 UTC the same training run advanced to 6/1200, with no error; the
CUDA child process is PID 5712 under the unchanged grid-training worker.
RTX 4050 memory allocation reached 5609 MiB (previously zero). Actual GPU
training has now started. This is progress, not a completed or accepted model.
Parent remains waiting_for_dependency on this exact child; no new parent,
cohort, command key, candidate activation or training budget was introduced.

TASK-1235 was closed using `close_task.py`: closing commit `v1.7.653` /
`3c1e143d22a3a449f161dd9da5ca8667a165c94a`; hash record `v1.7.654` /
`498ccebf9a63e68145361785860cdbc07eb47a08`. Main equals origin/main at that
tip. Final docs/window/startup checks PASS (44,876 bytes); 45 operator tracked
files preserved/restored, recovery stash `9f1a6cbff114fe7fb6662fc047d6f4c5585eb6ce`
retained. API-only final documentation restart left worker/GPU child running;
new API PID 24736 is healthy. The fully merged repair worktree and local branch
were removed after detaching its .venv junction; root dependencies remain.

### Completion supervision and measured budget risk — 2026-11-16

Operator requested completing the same training/evaluation, rather than stopping
after resume. Existing parent, cohort, run, seed, recipe, splits and quality gates
remain pinned. No activation is authorized by this completion request.

At 18:18:58 UTC the same run was processing at step 208/1200 with no error.
Child progress reported 8.3744 mean seconds/step; at that observed rate the
remaining 992 steps need about 8307 seconds (138 minutes), versus 4997 seconds
(83 minutes) remaining in the existing cumulative 7200-second budget.
This is an estimate, not a completion-time guarantee. Read-only proposal:
`.runtime/task1230-budget-extension-preview.json` (no state changes applied).

Code confirms `ChildControl.check` and the supervisor enforce the time ceiling;
an exhausted budget stops without a candidate, and the normal resume operation
never replenishes consumed seconds. The live spec also pins its current limit.
No code, envelope, immutable spec, allowance, step count or limit was edited.

Requested explicit approval for a controlled limit increase of this run alone
from 2 to 4 hours and checkpoint-safe resume if needed, preserving consumed
budget and the full 1200-step plan. Proposed additional implementation/test/review
scope may cost 30–60 minutes; it has not started pending that approval. Training
continues under the already-approved 2-hour ceiling in the meantime.

### Resumed supervision and cancellation gate — 2026-11-16

Operator requested resuming work. Read-only API/native inspection found that the
old CUDA child PID 5712 had ended, with its last progress at step 235 and no
checkpoint. A new native grid worker (PID 21088, started 21:10:42 UTC) automatically
reclaimed this same job, charged prior work and entered attempt 2. New child PID
3248 uses the same run/spec path. No new run or cohort was created by this agent.
The API's old step 234 and progress file attempt 1 are not a recovered weight state;
attempt 2 has no resume checkpoint. The 235 steps cannot be claimed as preserved.

The agent proposed holding the recovered job while preparing the previously
described per-run 4-hour limit. Automatic approval review rejected the cancellation
before execution: the user's resume/complete instruction did not explicitly
authorize cancelling active training, which may irreversibly discard progress.
No cancellation, indirect stop, budget write or workaround was performed.
Explicit consent was requested for controlled cancellation/resume and the scoped
4-hour change, including the earlier 30–60-minute implementation/test/audit cost.

Unchanged live facts: same parent/run/cohort/base/seed/recipe/1200-step plan;
maximum 7200 seconds, cumulative use 2785.562 seconds at the last observation,
reserved steps 600, no candidate. Training continues while the question is pending.
The related isolation/progress work TASK-1236 already exists on
`codex/grid-learning-efficiency-20261116` (`ec94a340`); it was inspected only by
commit summary and was not merged or modified. Avoid reusing that task number.

### Approved per-run recovery — 2026-11-17

The operator explicitly approved the proposed controlled cancellation if needed,
four-hour cumulative ceiling, checkpoint-safe resume and the stated repair cost.
Before any mutation, attempt 2 stopped naturally at the original 7200-second limit.
An immutable SHA-verified checkpoint at step 575 remained, although the database
pointer was null. No cancellation was performed and no completed data was deleted.

TASK-1237 implements a preview-SHA-bound owner operation for this run only. Claude
round 1 PASS (0 P0/P1), both P2 observations corrected; 14 unit and one disposable
PostgreSQL test, scoped lint/types/maps/docs passed. Implementation commit:
`5e82a06a4e66ca3e500ceecb2924ebf6f9437054` (v1.7.655), separate working branch.

The exact preview `8eed026132ba1f7a14d154bc0cfa968892d25bc1a615f04f178848785da75ef8`
was applied once. A fresh database connection confirmed the complete intended
state: max_seconds 14400, used_seconds 7200, 1200 reserved steps, two attempts,
checkpoint step 575; original input and stopped status unchanged. Evidence:
`.runtime/task1237-after-apply.json`. Ordinary parent resume returned the same
parent/run/cohort/command key at 00:21:10 UTC; no start command or new run was used.
At 00:23:49 UTC the existing worker entered attempt 3 with resume.step=575 and
7200 remaining seconds in its sealed spec. The saved limit survives a new worker
load. New runtime consumption/reservations accrue normally. Training and quality
evaluation are still pending; activation remains unauthorized.

At 00:32:08 UTC the new GPU process advanced to step 580/1200 from the recovered
575 checkpoint, no error. This verifies real continuation, beyond an API requeue.

### Training completed and recovery repair integrated — 2026-11-17

At 01:46:13 UTC the same training run was completed at 1200/1200, attempt 3,
without error. Final checkpoint SHA:
`daf8162186e8e07e75c788bc467557e6b2bfd5790d09d6167dd312e57b093593`.
The unchanged selection rule chose the step-600 weights: VALIDATION photo/board
correct rates 1.0, normalized error 0.003329573948229276. These are training
selection metrics, not a completed independent quality-gate verdict.
Candidate version: `0b37cba4-972f-555e-8049-a272dbe5b285`; weights SHA
`cba246394c7f8b914e6ab210ea76391e1fbb2f705a65cccaf0a7101325a4c896`.
Cumulative time 12158.938/14400 seconds; reserved steps 1825/8000.
Export/result: `artifacts/grid-training/runs/c489f65f-8272-412b-aaf1-f86bac000856/result-3.json`.

The original parent created evaluation `b2c81908-9cda-417b-8122-e6815b718795`,
report `8ac52d4e-3483-5ec0-8350-0933a7d45836`. It is processing on the general
worker with regular heartbeats; no activation/default assignment was performed.

Operator accepted TASK-1237's tested/audited result and integration. Its commits
v1.7.655–657 are now in main and origin/main at
`477419902ba6957492f8b870088b84d9e1c78f4e`. Closing commit v1.7.656:
`8137a4349048a4754e89484cc8a2eed3f4d41d07`. No new schema migration required.
Root docs/window/maps checks PASS (startup 44897 bytes). All 45 existing tracked
files were preserved/restored, with exact original bytes or verified merged
contents; index empty. Recovery stash `79779aef5db5dc5995ada111447338048adac409`
and byte backups in `.runtime/task1237-cutover-backup` retained. One mapped reader
prevented truncation of a document; atomic replacement retained an extra old-file
backup and passed exact SHA checks. API restarted successfully (PID 21740), while
workers and evaluation continued. Audit history retained in
`.runtime/task1237-audit-history`; the fully merged worktree and local branch were
removed after nonrecursive .venv junction detachment. Root dependencies remain.

During cutover an unrelated board-search branch was initially fast-forwarded by
mistake. It was restored by compare-and-swap to its exact prior 498ccebf pointer
before main was switched/merged; no foreign commit was removed. A later observation
found it at the integrated tip in a new separate worktree; no further changes to
that branch were made by this repair. Other worktrees/branches were preserved.

### Final operational acceptance — 2026-11-17 02:23:37 UTC

The original parent `42f30e0e-9707-4cf9-aaf6-10482f6e9d60` is completed, with the
same command key/cohort/run. Training is completed at 1200/1200; evaluation
`b2c81908-9cda-417b-8122-e6815b718795` is completed at 4/4 with PASS.
Report `8ac52d4e-3483-5ec0-8350-0933a7d45836` uses unchanged per-game gate v3
and has current cohort evidence (noticeCount=provenNoticeCount=0).

| Frozen control role | Photos | Base correct boards | Candidate correct boards | Base normalized error | Candidate normalized error |
| --- | ---: | ---: | ---: | ---: | ---: |
| VALIDATION A | 5 full photos | 44/45 | 45/45 | 0.004801590354916779 | 0.0033295605128300467 |
| REGRESSION | 13 partial photos | 17/21 | 21/21 | 0.01321432218495999 | 0.0060306537011477705 |

Validation complete photos improved 4/5 -> 5/5; false boards and duplicates remain
zero. Both validation/regression decisions pass, coverage complete, no reasons.
Regression measures labelled targets only, not unlabelled detections. Evidence is
photo-only: session independence/unknown ancestor use are not proven, and product
improvement gates are not a statistical significance claim. No policy was weakened.
The existing checkpoint selection chose the better step-600 weights after all
1200 planned steps were executed.

Candidate `0b37cba4-972f-555e-8049-a272dbe5b285` is neither default nor assigned
to the game. No activation, new training or artifact cleanup was performed.
Evidence: `.runtime/task1237-quality-latest.json`, immutable final acceptance
receipt, `.runtime/task1237-quality-summary.json` and the API report above.
Fresh API health is OK and all three worker lanes are running. Repairs main and
origin/main remain `477419902ba6957492f8b870088b84d9e1c78f4e`; own worktree and
branch are removed. Operational scope is finished; the broader pre-existing
background-feature task remains active only for its separate source integration.
