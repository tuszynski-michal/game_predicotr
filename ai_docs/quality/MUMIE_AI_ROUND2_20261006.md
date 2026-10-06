---
title: Second isolated Mumie AI-assisted RGB/gray experiment
status: done
last_updated: 2026-10-06
---

# Qualified inputs

Artifact root:
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-ai-round2-20261006`.
The authoritative qualification is `qualified-frozen.json`; its SHA is
`3b8a8a9676729b5f7473470159500777135bf9a36e8489c4d7eab2670f4a9d0e`.
Manifest `8adaaaf621e5506c5618559ec433f06f4eed13b75465d394ae2af0be3717f40d`.

Two independent blind reviewers inspected 100 exact PNGs and 20 human training
anchors. No predictions, selection groups, other reviews or human queue state
were available to them. Their exact-bound high/high consensus accepted 76 cases.

| Cohort | Selected | Accepted by AI | Use |
|---|---|---|---|
| Prior human feedback | 19 | 10 | All 19 human decisions retain priority |
| Previous AI development | 29 | 29 | AI-origin training, weight 1 |
| Previous AI audit | 22 | 22 | Never trained; later human references remain separate |
| New development candidates | 30 | 15 | AI-origin training, weight 1 |

Actual development is 327 unique crops: 283 human and 44 AI, compared with
312/29 in V4. The 37 human feedback crops retain weight 4; 438 draws and 14 steps
per epoch. Validation84 and diagnostic9 identities, pixels and human classes
are identical to V4. No AI approval was inserted into a human label store.

All 26 human audit rasters, whole source photos and their decoded RGB aliases
are excluded from development. Base authoritative photo partitions are also
disjoint. The first film remains development-excluded. Human19 and all five
unreadable history records retain original bindings and receipts.

Gold observations: 11 present, 73 absent, 11 disputed and five uncertain.
These are not Super training labels. New accepted15 are primarily card symbols;
the blurred new graphic-symbol candidates did not meet the strict consensus gate.

# Frozen protocol and checks

Exactly one additional RGB/gray pair uses generation4 architecture and a separate
run root. Seed20261005, 20epochs, batch32, lr0.001, 1800seconds/10000steps per branch.
One active worker at a time; durable checkpoints/RNG/PID/watchdog. The
`run-authorization.json` binds qualification SHA before either run.

V4 pair, human26 and first-film AI60 proof paths, digest IDs, byte SHA and pointer
SHA are frozen before training. Later helpers reject drift rather than silently
reading a new baseline. Calibration and best epoch use only the same human84.
Human per-class gates compare against V4; human26 and transfer50/10 are assessed
after training without refitting. Whole8100-crop inference requires passed gates.

Pretraining independent audit PASS. Fresh-process qualification replay32.27seconds:
all9323 pins, full strict adapter and three detached negative checks passed.
The real protected source re-encoded as PNG has different byte SHA but identical
RGB signature and is rejected. A per-class regression and modified frozen proof
are rejected. Helper Ruff/format/scoped strict mypy passed.

Focused tests: 50 passed. One existing augmentation registry assertion fails because
it expects generation3 to be invalid, while the existing registry supports3 and4.
This pre-existing test mismatch is outside this artifact-only change; it was
not hidden, weakened or committed. There are no application/API/schema changes.

# Model results

RGB run `693ca3da3187493487ba684ef2e6a529` succeeded: 20 epochs, 280 steps,
633.279726 seconds, best epoch 8. Actual export parity passed; report
`8dcc58f9233cd8af659ff9e0aad6fd00844a9667698657e58ca1c83fb380193d`.
Gray run `c981933519174b429e3341e216008994` succeeded: 20 epochs, 280 steps,
606.188346 seconds, best epoch 6. It started only after RGB completion.
Both workers exited; an independent CIM check confirmed neither PID remains.
There were no extra training runs, resumes, seed searches or post-audit refits.

The immutable pair proof is
`dbe76d867864258a0bfa6d7e4b821717f6fa78f67b92f0241ce465f24407e815`.
All existing human per-class gates passed:

| Evaluation | RGB | Gray | Fusion | Comparison |
|---|---|---|---|---|
| Reused human validation84 | 83/84 | 83/84 | 83/84 | Same as V4; existing K/Q conflict retained |
| Previous human feedback18 | 18/18 | 18/18 | 18/18 | No class regression |
| New human feedback19 | 19/19 | 19/19 | 19/19 | No class regression |
| Existing diagnostic9 | 9/9 | 9/9 | 9/9 | No class regression |
| AI audit22 | 22/22 | 22/22 | 22/22 | AI agreement, never training data |
| AI development44 | 44/44 | 44/44 | 44/44 | Training agreement, not accuracy |

Independent checkpoint-to-CPU-ONNX replay covered all 196 evaluation rasters:
84 + 37 + 9 + 44 + 22. Maximum absolute logit difference was 3.8147e-6;
classes matched the actual GPU reports. This includes both branches and is
separate from the trainer's actual export parity checks.

# Separate human and transfer evaluation

Held proof:
`2eaefea4470e7b576f5e3d0a05dd834dfa764c32c1d724c670c691765f541820`.
The 26 later human references were excluded from training and calibration.

| Human reference group | V4 RGB → R2 RGB | V4 gray → R2 gray | V4 fusion → R2 fusion |
|---|---|---|---|
| Withheld22 | 21/22 → 22/22 | 22/22 → 22/22 | 22/22 → 22/22 |
| Separate directed diagnostic4 | 4/4 → 4/4 | 4/4 → 3/4 | 4/4 → 3/4 |
| Combined26 | 25/26 → 26/26 | 26/26 → 25/26 | 26/26 → 25/26 |

R2 RGB passes every human per-class gate and fixes the previous A → Faraon
withheld error. However, the gray branch and fusion newly classify Ra as J:
case `5bfef56b2732704cd716dc9decda744696597694eb9a00c2407db1e6234bb047`,
source `C:\Users\tuszy\Documents\mumie\24517 - 50112 cut\seq_27118-27126.jpg`,
board 4, field 11. Exact pixel SHA:
`802857280d0b7e32890d141577c10956db9a31bb56618207a6474eee648154e4`.
The exact PNG was visually inspected. Its blur and partial overlay describe
the input; they do not establish a causal explanation or change human truth.

First-film transfer remains a separate AI agreement measurement:

| AI reference group | V4 RGB / gray / fusion | R2 RGB / gray / fusion |
|---|---|---|
| Control50: 47 accepted, 3 unresolved | 47/47 / 47/47 / 47/47 | 47/47 / 47/47 / 47/47 |
| Directed10: 6 accepted, 4 unresolved | 6/6 / 5/6 / 6/6 | 6/6 / 5/6 / 5/6 |

R2 fusion additionally changes K → A on AI case
`861effcdfcaa4442ecf802948fcf3beb2c8b2b7acb8ea8e09777443ba25cdd82`.
This is AI agreement, not a new human approval or independent population accuracy.

# Decision, preservation and replay

The combined R2 human gate fails. V4 remains the qualified pair; the improved
R2 RGB artifact is retained as experimental evidence, without activation or
creation of a new hybrid pair. No 8100-crop R2 sidecar is generated. The actual
comparison command with max-photos1 rejects before inference with
`MUMIE_R2_HUMAN_GATES_BLOCK_SIDECAR`; no output directory is created.
All previous models, exact rasters, human histories and 61 first-film outputs
remain byte-identical. There are no application, database or runtime-model changes.

Fresh-process pair inference (28.48 seconds) and held inference (11.34 seconds)
reproduced the identical proof IDs and bytes. Final replay checks 9332 pinned
inputs/outputs and strict cohort validation. Its pinned-set digest is
`12bc79f5c75f0b71d7d4ded986a53b6ddaa822115a37a2607d69fb47ee66238c`.
Four negative checks passed: decoded-photo re-encoding, per-class regression,
modified frozen proof bytes and failed-human-gate sidecar rejection.
The final replay was repeated in another fresh process and reused identical
`replay-final.json` bytes. All 15 local helpers pass Ruff, formatting and
scoped strict mypy.

Read-only review health: eight exact cases remain available at
`http://127.0.0.1:3102/symbols/batch`, revision0. Exact PNG access took
0.125 seconds directly and 0.094 seconds through the UI proxy. The previous
raw60 queue and all 26 human approvals remain preserved. These eight optional
corrections did not block either experiment task.

Independent final experiment audit PASS: documentation and actual artifacts
agree; there are no open P0–P2 findings. The auditor independently verified
actual checkpoint/ONNX inference, 86 source-rendered V4/R2 evaluation rasters,
all 9332 pins, both previous 61-output sets and human26/revision27 preservation.
All seven TASK-0868 criteria and accepted plan steps 1–5 are covered; the
conditional failed-gate path is a completed rejection, not an unfinished run.
No new folder, recording-origin answer or operator approval was required.
