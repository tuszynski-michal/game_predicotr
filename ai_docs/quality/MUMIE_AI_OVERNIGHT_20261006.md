---
title: Mumie — isolated AI review and actual overnight experiment
status: done
last_updated: 2026-10-06
---

# TASK-0864 evidence

The operator explicitly authorized autonomous overnight training and internal
AI visual inspection. D-505 allows a separate experimental AI-origin cohort
without manufacturing human approvals. The subsequent human batch contained
24 decisions at revision24:19 approved and5 unreadable. Their exact original
history, dictionary, rasters and immutable pack were qualified before use.
No agent wrote human decisions.

## Blind visual assessments and immutable cohort

Two separately tasked reviewers each inspected20 human-approved class anchors
and all79 source-bound RGB96 rasters from the existing third-recording batch.
Neither received CNN predictions. Reviews retain model/reviewer identity,
case/source/quad/PNG/pixel SHA, class or unreadable, confidence, reason and
a separate frame observation. Only readable matching high/high class votes
qualify. These reviewers use the same model and are not statistically independent.

All24 human-assessed rasters override AI. Five unreadable cases are excluded;
19 new human targets preserve their actual decisions. One AI/human disagreement
on a blurred A remains recorded, with the human target retained. Ten agreeing
gold-frame observations are diagnostic only:0 Super training targets.

The isolated manifest contains29 AI development targets and22 AI audit targets
with `ai_visual_assessment` origin and `human_approved=false`. Whole photos are
disjoint between these sets. The audit assignment was made before training
using photo index modulo3, excluding complete photos with new human training
targets. The22 samples come from the same third film; they are not an independent
recording or a human-referenced test. Four remaining uncertain cases stay pending.

Original264 human development,84 validation and9 diagnostic samples remain
unchanged. The resulting development set has312 unique examples:
246 original human,37 human feedback and29 AI. Human feedback has sampling
weight4; AI and other human examples have weight1. Each epoch draws423 examples,
with14 optimizer steps. Withheld AI never enters sampling, epoch selection,
calibration or augmentation selection. Human84 alone selects and calibrates.

The new adapter checks the complete qualified base, current human history,
relocated sources, full2,844-photo third-film inventory, authoritative batch
exclusions and exact re-rendered crops. Source aliases/duplicates, changed
reviews, changed decisions or unsafe output overlap fail. Original strict
adapters reject the experimental format. Generation4 is explicit and local;
default generations retain their existing behavior and durable run protocol.

## Actual bounded training and human gates

One RGB and one gray run trained from scratch, sequentially, with seed20261005,
20 epochs, batch32, learning rate0.001 and the existing appearance augmentation.
Each request retained its1800s/10000-step budget, checkpoint RNG, optimizer,
sampler, admission and watchdog. Both finished in attempt1 with280 steps.
Recorded workers32836/4076 exited; no orphan or second copy remained.

| Evidence | RGB | Gray | Frozen fusion |
|---|---:|---:|---:|
| Human84 reused validation | 83/84 | 83/84 | 83/84 |
| Previous18 training corrections | 18/18 | 18/18 | 18/18 |
| New19 before training, qualified V3 | 15/19 | 4/19 | 10/19 |
| New19 after training, this experiment | 19/19 | 19/19 | 19/19 |
| Limited diagnostic9, evaluated after selection | 9/9 | 9/9 | 9/9 |
| AI29 training agreement | 28/29 | 27/29 | 28/29 |
| AI22 withheld agreement | 21/22 | 22/22 | 22/22 |
| Same AI22, prior V3 proposals | 19/22 | 18/22 | 18/22 |

All human gates pass per class against actual V3 reference results, including
old18, new19 and diagnostic9; pooled accuracy cannot conceal a lost class.
Every evaluation uses identical sample IDs, expected classes and source-bound
rasters. Both baseline reports are checksum-pinned. CPU Torch/ORT parity passed
on84 rasters per branch, maximum absolute error2.861e-6. Best epochs8/6;
recorded cumulative time535.908s/604.668s. No additional seed/run was tried.

The original K/Q human-reference conflict remains. Reused human84 is a small
selection/calibration set, not a new independent test. Perfect19/19 measures
training regression, not transfer. AI agreement can reproduce shared AI mistakes.
No accuracy claim is made for the full unlabelled third film.

## Same-cell comparison and durable replay

The completed60-photo comparison uses actual parity-checked ONNX, existing preprocess/classify_logits and
reclassify_photo, fixed validation calibration, and portions of at most20
existing photos with120s limits. It may change only symbol proposals.
New/reused/summary paths validate the original top-level geometry and every
non-symbol cell field, exact crop SHA, order, indices and geometry reasons.
All8100 crops and540 boards retain their original geometry and source identity.

| Same unlabelled rasters | V3 | Experimental V4 |
|---|---:|---:|
| Compared cells | 8100 | 8100 |
| Low-confidence proposals | 424 | 454 |
| RGB/gray disagreements | 37 | 22 |
| Requires review | 424 | 454 |

Thirty-nine proposed classes changed. Disagreements declined while uncertainty
increased, so these numbers do not establish an overall improvement or justify
activation. Confidence thresholds remain unchanged. Some photos contributed
development targets; full-film accuracy remains null. No geometry or human
approval was changed. Original overlays/atlases are not regenerated as new
human truth.

The three portions processed20/20/20 photos in37.39/37.83/41.67 seconds, each
within its explicit120s limit. A new process processed0 photos, verified every
reused result and reproduced the exact summary. All61 output files (60 results
and summary) remained byte-identical. Summary digest:
`aaaaca5cdf6af68e63d8346ebb5679adfab1ee7f671d2c6dcbc9f70791c4eee3`.

Pair evaluation was independently recomputed in a fresh process and reproduced
the identical digest `1a7fa49bb2ea991e06d3037686c57f4c4a4d5a6d4710bd397677ddc08f4d7ffb`.
Separate audit verified2684 pinned input hashes with0 mismatches.
The broader input snapshot covers5673 files, including all third-film sources
and original batch artifacts. The post-replay check confirmed all5673 original
input files remained identical, including old label stores, histories, sources,
manifests, model reports and batch artifacts. Input/output replay checks are
persisted as checksummed evidence/replay.json. No computer reboot was performed;
fresh-process revalidation and create-only publication establish restart/retry
durability.

## Ready human review and saved configuration

A separate immutable packet has26 pending exact crops:22 withheld AI cases
and4 unresolved cases. The earlier24 decisions remain at their original store.
The packet is still a proposal requiring human assessment; no AI target was
written as a human approval. Choose the visible symbol, or mark unreadable/grid
issue where appropriate. Correcting a symbol requires no grid movement.

- Editor: http://127.0.0.1:3102/symbols/batch
- Direct case portal: http://127.0.0.1:8108/overnight-symbol-review/review.html
- Reference: `3d05434abb05efc2c7b62b98f441ad41ffd62900be4b283858349fe4e8ef68c9`.

Saved runtime.json points to both the new reference and matching label root.
The previous runtime is backed up. The existing PowerShell7 launcher restarted
only its recorded, identity-matching lab API/UI processes, hidden; production
services were untouched. API45388/UI36508 own the saved runtime. Read-only HTTP
checks return200, exact26 pending cases/revision0 and matching reference:
backend0.297s, UI proxy0.156s in a local smoke check. A later fresh-process launcher
Status confirmed both recorded process identities and ready ports. These timings
are not an SLA.

No additional folder or30-per-class selection is needed for the current boundary.
The next operator action is assessment of these26 examples, enabling a human
check of the fixed experiment on its withheld photos. Further independent-film
accuracy requires human ground truth from a recording not used for training.

## Verification and limits

85 focused tests passed:16 experimental qualification checks,17 trainer/run
checks and52 existing feedback/manifest/batch-input regressions. Tests include
origin/consensus drift, unknown/duplicate classes, current history, human priority,
unreadable exclusion, source/render drift, authoritative exclusion recomputation,
protected output directories, old-adapter rejection, no audit sampling and exact
RNG/optimizer/best/budget resume for generation4 as well as previous generations.
Ruff format/check passes for all7 changed source/test files; scoped strict mypy
passes for5 modules with explicit third-party Torch/ONNX boundaries.

Fourteen artifact-level positive/negative checks also pass on real frozen data,
including cell count/order/quad/SHA/human approval/geometry-reason drift and
pooled improvement concealing class regression. Separate code/data audit has
no unresolved P0–P2 after tightening human gates and result-reuse validation.
Final same-cell output audit also passes: an independent fresh process re-rendered
all8100 crops from60 real source photos and checked every pixel SHA against both
results, all540 board geometries,135 ordered fields/photo, indices and geometry
reasons. Independently recomputed class/review counts match the summary, all10
class names are valid, and all5673 input/61 output hashes and replay set digests
match. No unresolved P0–P2 remains. No HTTP/schema/frontend change;
build/OpenAPI regeneration and migration are not applicable. No full unrelated
suite or load benchmark was needed. No computer reboot was performed.

Evidence is under the absolute root
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-ai-experiment-20261006`:
reviews, human-feedback-packs, evidence, cohort, runs, evaluation, same-cells and
next-review. Manifest:
`aff9c65ac61fac6c1873d1eff44d0ac17f204476cd8cb6c65b3e1d9e05b02ad8`.
Actual RGB/gray run IDs:
`5e6a8f93524b4c1bbbe1d28fce0eaf51` / `e95d860b154f46cca2325e97caae8224`.

The result is an experimental candidate. No database writes/migrations/deletion,
Super-target training, geometry approvals, production model activation,
merge/push or production deployment occurred. Work remains on feat/grid-engine-v3
in the requested worktree. Pre-existing unrelated worktree metadata edits are
excluded from this task's commit v1.7.212. All applicable Definition of Done
checks and plan steps1–7 are fulfilled: real qualified reviews, exact human
priority, isolated training/audit, bounded pair/evaluation, same-cell replay,
tests, independent audits, documented operator boundary and separate commit.
