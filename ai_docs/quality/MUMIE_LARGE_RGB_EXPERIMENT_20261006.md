---
title: Mumie — larger RGB experiment and rejection evidence
status: final
last_updated: 2026-10-06
---

# Result

TASK-0872 completed its bounded experiment and technical verification.
The candidate `mumie-symbol-rgb-v5-large-ai` is **REJECTED**: 10 of 18
human per-class comparisons fail. Technical run success is not model acceptance.
TASK-0873 entry condition is not met. No model was activated or deployed.

Human26 plus human8: V5 RGB **29/34**, R2 RGB **34/34**, V4 RGB **33/34**.
These are selected regression controls, not an independent population estimate.
The larger training set did not improve these controls. More epochs did not
improve human84 validation; the selected checkpoint is epoch1 of20.

## Frozen inputs and origin

- Qualification: `8a57f640f741be76259ec0cd5f7f8a384638754910b94fd004ca2807b40b8ac8`;
  file SHA `c48ba7af2689aa972aa97cfd18082c5c034392a854113b9e7bfeeec0808c5b20`.
- Larger manifest: `58a0646f48a6b51485c3f386ec3b35a14cfc4e07907ebd1b332999bed53ed36b`;
  file SHA `f9a25894d37228c30a15ff86f348b16a90194c3e61ef36d6ba6b1fcd074436f0`.
- R2 base: `8adaaaf621e5506c5618559ec433f06f4eed13b75465d394ae2af0be3717f40d`;
  its exact qualification receipt remains pinned.
- Development2053 = human283 + AI1770. The original R2 development327 is
  preserved and1726 new high/high AI cases are added. New Mumia cases109.
  New cases come from41 photos of the third recording; unique rasters do not
  imply independent scenes. AI agreement never becomes human approval.
- Human84 validation, diagnostic9, AI audit22, human26/human8 histories,
  dictionary order and37 human-feedback IDs remain unchanged. Whole protected
  photos, decoded aliases, excluded first-film development and duplicate pixels
  are rejected. No Super targets or human-label writes.
- The manifest binds11474 original live pins and2168 PNGs. Every original
  source/quad/native raster is independently checked. Freeze93.78s;
  fresh-process full verification70.81s. Publication is immutable/create-only.

## Protocol and actual execution

One admitted run: `5302ac7d5fd74eba9a37faf2813b8093`.
Protocol digest: `0f506f82d1301889d065dac568fb144a0c99123b0f51eea39376f51903bce532`.
Model RGB64, seed20261005, batch32, learning rate0.001, at most20 epochs,
7200 accounted seconds and50000 steps. Human-feedback weight4/AI weight1.
There is no automatic seed search or refit. Old generation1–4/API limits remain
unchanged; this is a separate local request/state/runner contract (D-506).

The larger weighted loader draws2164 cases per epoch,68 steps per epoch.
The actual GPU run completed20 epochs and1360 steps. Best epoch1:
human84=83/84, macro accuracy0.9888889; development2042/2053.
Calibration temperature0.95 was selected using only human84 validation.
Human26/human8 were evaluated after training and were not used for epoch or
temperature selection. AI training agreement1762/1770 and AI audit19/22
are agreement with AI targets, not human-ground-truth accuracy.

First worker PID44912,631.2108 accounted seconds. A cancellation request made
when checkpoint9 existed exposed a delayed stop in the old shared trainer;
the worker completed epoch20 and exports before its neutral finish observed
the request. The new local runner now honours cancellation at the next batch
heartbeat, with a focused regression test. The old runners remain unchanged.
Do not describe this as stopping at epoch9 or as a tested process crash.

Fresh-process resume used the same run, request, manifest and cumulative budget,
new fence/lease, worker PID7892 and checkpoint20. It executed zero additional
training steps, restored optimiser/RNG/best state and re-exported the model.
Final technical status succeeded; cumulative695.9628s,1360 steps unchanged.
Both workers exited. No CNN is still running.

## Export and restoration evidence

- Actual checkpoint9 SHA:
  `42d6d5f3012fb9c4a8bcdbc9bbd2b4fabb32a846fd96ff1e2178793b5b2feb51`.
- Actual checkpoint20 SHA:
  `b65ddcbce00c50fe0f9595b26003c59d68fb332327d70b656718eb9f0b475fa0`.
- Best weights SHA:
  `61b52b330565e614efbeaadd32b12e84bcdbbe6b4cc4a05ef91452a00cae49ba`.
- ONNX SHA:
  `099779f2191fd40bad9e1f977606688a58345d68740377f46751d30930e6ed41`.
- First and resumed best weights/ONNX are byte-identical. CPU Torch versus
  CPU ONNX max absolute logit error2.86102294921875e-6 on84 validation samples;
  predictions identical,83/84. This compares actual exported tensors/models.
- Two separate GPU processes restored the real checkpoint9/globalStep612 and
  replayed one weighted batch32 on actual development2053. Images, labels,
  logits, loss, optimiser, model update and generator state are identical.
  This is a detached in-memory probe; no second run or canonical weight update.
  Ledger SHA is unchanged. Exact executed source bytes are preserved.
- Batch digest `3bd0b2bdbde6eed3f4530fe9b6b5aa948e38ca58a94d38e2eaf96a5b7efb7ea3`;
  combined proof `1d4b43e97d8598c7f43022ba7e157fa20dc4b9b2d11b58d24b359ce0533906d9`
  in `C:/Users/tuszy/Documents/game_predicotr/artifacts/mumie-large-rgb-experiment-20261006/resume-evidence/replay-qualified.json`.

## Human comparisons

Each row compares every represented class against each baseline, not merely
the total correct count. Rows overlap; never sum them as independent examples.

| Group | V5 RGB | R2 RGB | V4 RGB | Per-class gates versus R2 / V4 |
|---|---:|---:|---:|---|
| human84 | 83/84 | 83/84 | 83/84 | PASS / PASS |
| old18 feedback | 18/18 | 18/18 | 18/18 | PASS / PASS |
| new19 feedback | 16/19 | 19/19 | 19/19 | FAIL / FAIL |
| diagnostic9 | 9/9 | 9/9 | 9/9 | PASS / PASS |
| withheld22 | 19/22 | 22/22 | 21/22 | FAIL / FAIL |
| diagnostic4 | 4/4 | 4/4 | 4/4 | PASS / PASS |
| control3 | 2/3 | 3/3 | 3/3 | FAIL / FAIL |
| directed5 | 4/5 | 5/5 | 5/5 | FAIL / FAIL |
| all8 | 6/8 | 8/8 | 8/8 | FAIL / FAIL |

Five mistakes on34 held human controls: three A→Faraon, one Faraon→K and
one K→Faraon. Independent CPU inference reproduced V5 on84 validation,
37 feedback,9 diagnostics,22 AI-audit and34 exact native held crops. The auditor
also ran V4/R2 RGB on those34, rerendered their source quads, checked11480
evaluation pins and recomputed all18 per-class gates. Evaluation correctness
passes; candidate acceptance fails. No gates or human histories were weakened.

Evaluation ID:
`efcdc9e0407df7e00760fedd7473a41437d713d1ab6b2c35471500efd658c5ee`,
under `C:/Users/tuszy/Documents/game_predicotr/artifacts/mumie-large-rgb-experiment-20261006/evaluation/`.

## Verification and limitations

- 42 focused new-adapter/runner/legacy-AI tests passed (58.91s).
- 18 numerical training/resume tests passed for generations1–5.
- 15 local-runner tests passed after adding next-batch cancellation coverage.
  These suites overlap; their counts are not an aggregate unique-test count.
- Final Ruff lint and format checks passed for5 source modules and3 tests.
  Strict scoped mypy passed for the3 new modules in22.70s; heavyweight external
  Torch/Torchvision imports were skipped, local code and Pydantic remained typed.
  This is not a claim that the entire repository typecheck ran.
- Exact R2 receipt, drift after re-signing, protected source groups, defensive
  cache rechecks, Windows reparse ancestors and conflicting case-alias pins,
  restart, lost response, cumulative budgets and stale fences are covered.
- Independent code/data preflight and actual model/evaluation audits passed.
  Final checkpoint replay audit passed: the auditor separately reproduced the
  checkpoint9 sampler/augmentation/images/labels/generator in a fresh process,
  verified both saved batch proofs and their frozen source, and confirmed the
  ledger/checkpoints remained unchanged. No open P0–P2 findings remain.
- Two initial120s freeze attempts timed out before publication; source decoding
  per composition and shared-ancestor inspection were corrected without
  weakening exact raster or SHA guards. No abandoned worker remained.

The changed sampling exposure is a concrete follow-up hypothesis: the37 feedback
cases still have weight4, but their draw share fell from148/438=33.79% to
148/2164=6.84%; total human share fell from394/438=89.95% to394/2164=18.21%.
AI draw share rose to81.79%. This is an observed dilution, not proof that AI
labels alone caused the regression. A separately specified follow-up should
control human/AI and photo exposure before asking for more labels or increasing
epochs. Preserve the rejected result and earlier candidate; do not refit this
version, select a seed from held controls or start TASK-0873 with V5.

No API/UI/schema changes, DB writes/migrations/deletions, geometry training,
Super detector training, import, activation, merge, push or deployment were
performed. Symbol classification does not establish grid-cutting accuracy.
