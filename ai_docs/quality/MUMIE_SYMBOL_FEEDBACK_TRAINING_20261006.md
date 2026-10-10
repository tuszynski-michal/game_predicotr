---
title: Mumie — completed generation 3 feedback evaluation
status: done
last_updated: 2026-10-06
---

# TASK-0861 evidence

The single RGB/gray generation-3 pair completed twenty epochs from scratch.
Qualified manifest `0cff2a15ea44aeb2fc77311845ae6d3190060891d65ef1549c4fd5e6d01e3de4`
and its original labels/split stayed unchanged. TASK-0862 restored exact source
reads through a persisted location, with all 2,052 original filenames/SHA.

## Actual outcomes

| Branch | Existing validation | Training feedback regression | Limited diagnostic |
|---|---|---|---|
| rgb | 83/84 | 18/18 | 9/9 |
| gray | 83/84 | 18/18 | 9/9 |
| fusion | 83/84 | 18/18 | 9/9 |

| Class | Validation samples | RGB correct | Gray correct | Fusion correct |
|---|---|---|---|---|
| 10 | 12 | 12 | 12 | 12 |
| J | 4 | 4 | 4 | 4 |
| Q | 10 | 10 | 10 | 10 |
| K | 9 | 8 | 8 | 8 |
| A | 11 | 11 | 11 | 11 |
| Ra | 5 | 5 | 5 | 5 |
| Sarkofag | 12 | 12 | 12 | 12 |
| Mumia | 8 | 8 | 8 | 8 |
| Faraon | 9 | 9 | 9 | 9 |
| Sfinks | 4 | 4 | 4 | 4 |

All branches were checked against the frozen V1 predictions on the identical
84 sample IDs/labels/classes. Qualification: rgb=True, gray=True, fusion=True; pair qualified:
True. Selection/calibration used validation only. Temperatures:
RGB 1.2000000000000002, gray 1.15;
fusion RGB weight 0.3.
No reference was rewritten. Remaining fusion reference conflicts:

- `02626455caaec09f2e86c54225ce1b77a6ac7461eba818c91c1245eb752f38c4`: reference K, prediction Q.

This is the previously observed K/Q reference conflict, retained for a human
reference review. Validation is reused for epoch selection and calibration;
83/84 does not estimate accuracy on the new film. The 18 corrected crops are
development training targets, never an independent test. The nine diagnostic
targets were excluded from this generation's training and evaluated after model
selection, but cover only Mumia/Sfinks and were seen by the older generations.
Their outcome is not population accuracy or a blind old-model comparison.

## Controlled execution and real export

RGB run `8da05da671d645dd9688c217ef094ce9`, attempt2, and gray run
`dc8642f0015a42bcb3b0aef35a590162`, attempt1, succeeded. Each completed200
optimizer steps and20 epochs within its original1800s/10000step limit.
Best epochs: 11 / 11.
Worker training seconds: 290.953 /
274.234. CPU Torch/ONNX Runtime parity
passed on all84 validation rasters per branch; maximum absolute errors:
2.86102295e-06 /
3.81469727e-06, tolerance1e-4, identical argmax.

Weighted replacement sampling uses feedback weight4,318 draws per epoch and
264 unique development crops. Metrics count each unique crop once. Validation84
and diagnostic9 never enter the sampler. Each run has persisted identity,
budgets, fencing, checkpoint/RNG/optimizer and selected best-weight artifacts.

Attempt1 of the same RGB run had failed before checkpoint0/optimization when
the old source path disappeared; its31.549s budget charge/history remain.
The different-byte non-cut directory was not substituted. RUN_BUSY rejected
an early gray admission; no second gray run existed. Admission succeeded only
after RGB status succeeded and owner PID9408 had exited. Completion was later
confirmed for both workers. No random rerun or additional model was admitted.

## Reproducibility, checks and scope

Evaluation artifact: `C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-symbol-feedback-20261005\evaluation-e3d948f8852fa5287dbfee15501b4c8c8c7626ac932df495f8d3fe813792e2f9.json`. Independent fresh processes reproduce the
same evidence digest and comparison bytes. Evaluation checks complete live
input SHA, immutable reports, original V1 calibration, unique264/84/9, explicit
18 sample IDs, effective318 draws, epochs and actual parity. The original
339-label manifest, original stores, earlier models and reports remain pinned.

The implementation checkpoint v1.7.207 passed43 focused pytest tests, including
exact interrupted/resumed training for generations1/2/3, sampler-generator
continuation and frozen diagnostic calibration. Ruff format/lint and scoped
mypy passed with explicit Torch/ONNX dependency typing boundaries. TASK-0862
subsequently passed29 source-feedback and28 original training regressions,
plus real new-process verification and identical relocation retry.

Separate final review has no unresolved P0–P2. Every task acceptance criterion
is met: one bounded pair, unchanged exact inputs, correct sampling/unique
counts, post-selection diagnostics, real parity, per-class baseline gate and
fresh-process replay. Documentation-only completion adds no HTTP/UI change;
OpenAPI generation/build are not applicable. Commit v1.7.209 records completion
after implementation checkpoint v1.7.207 and relocation v1.7.208.

The new recording inventory contains2,844 files with no byte duplicates or
training-source overlap; sixty evenly spaced photos are selected for the next
separate TASK-0863. That task will use the qualified V3 pair when its gate passes,
otherwise the previously qualified V2 pair. It will prepare real crop-review
cases, without human labels, guessed accuracy, Super labels or activation.
No database writes/migrations/deletions, merge/push or production deployment.
