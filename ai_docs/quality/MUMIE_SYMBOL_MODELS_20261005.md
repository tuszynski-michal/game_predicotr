# Mumie first symbol models — 2026-10-05

TASK-0855, D-498. Both models trained from scratch on the current fresh labels;
255 development samples and84 validation samples from separate recordings.
All10 classes occur in both parts. The cohort uses13 photos, with only2 selected
photos from the validation recording. This is preliminary validation, not an
independent final test. Epoch selection and temperature calibration reuse it.

## Measured results

| Model | Epochs / selected | Development | Validation | Macro accuracy | Budget used |
|---|---|---|---|---|---|
| RGB | 20 /14 | 255/255 | 83/84 (98.81%) | 98.89% | 55.36s /1800s |
| Gray3 | 20 /11 | 255/255 | 83/84 (98.81%) | 98.89% | 49.35s /1800s |

The development–validation gap is1.19 percentage points for both. Validation
Mumia8/8, Sarkofag12/12, Faraon9/9, Sfinks4/4, Ra5/5, 10:12/12, J4/4,
Q10/10, A11/11, K8/9. J/Sfinks counts are too small for a general accuracy claim.

RGB temperature1.05/logloss0.07563; gray1.25/0.08886. The prescribed fusion
weights0/.1/.2/.3 all give83/84; .3RGB/.7gray has the lowest fused logloss0.08320.
Fusion does not improve measured accuracy and has worse logloss than RGB alone.
No disagreement between model labels. At agreement plus confidence>=.9,83/84
would pass,82/83 agree with human reference. This policy can miss a confident
reference conflict; it is measured evidence, not a production activation.

## Cases for later human review

- Human K, both models Q, confidence98.82%: decision
  `02626455caaec09f2e86c54225ce1b77a6ac7461eba818c91c1245eb752f38c4`.
  Source `15a358e1ac08a23e9ab1cc9a1d7ad5f3e997055ce0fb97000eb57caa87c9a245`,
  board_index7/cell_index8 (zero based). Crop visibly contains Q on agent inspection.
  Treat as suspected reference mislabel, without rewriting the human decision or
  adjusting83/84 retrospectively. Pixel remains bound to the same geometry.
- Faraon, both models Faraon, confidence87.45%: decision
  `d3bb7a5272d5528021187e4b527f6523862b90ebf13105b03b77468ef8a3dc5c`,
  same source, board_index2/cell_index1. Small/blurred crop; retains review flag.

The evaluation report separately flags model uncertainty and disagreement with
the existing reference. Ground-truth conflicts are never silently relabeled.

## Durable execution and exports

Existing CUDA runtime torch2.12.1+cu130, torchvision0.27.1+cu130, CUDA13.0;
RTX4050Laptop. Seed20261005, batch32, AdamWlr.001/wd.0001, deterministic bounded
augmentation only on development. No old weights or older labels were used.

RGB run `06e7a4616c7349858b4e623a1dc0080b`, gray
`5a950cb00e3e4df3a69f37eeb93b6e8a`. Durable run settings, claim/PID/creation time,
fencing, watchdog, budgets, epoch checkpoints and best states all persisted.
First RGB attempt failed at adaptive average-pool CUDA backward. For fixed64
inputs, equivalent non-overlapping4x4 average pooling replaced the adaptive
operation in the local instance only. Forward/gradient equivalence test PASS.
Resume used the same run, epoch0 checkpoint and non-refundable8.04s/1step;
final reserved steps161. Gray160steps. Separate process start replay returned
the same succeeded RGB run while gray was running; no extra launch.

Both ONNX exports passed parity on all84 validation examples with maximum
absolute logit error3.8147e-6 and identical argmax. Best weights and ONNX are
checksum-bound fenced artifacts under
`C:/Users/tuszy/Documents/game_predicotr/artifacts/mumie-symbol-training-20261005/runs`.
Full confusion, history, logits, bindings and artifacts are in each final report;
`comparison-review.json` records calibration, fusion and84 review rows.

A separate new-process check also compared ONNX CPU outputs with the recorded
CUDA logits: class labels match84/84 for each model, while raw logit differences
reach0.0013864RGB/0.0006695gray. These are not bit-exact GPU/CPU results and do
not pass a1e-4 cross-device logit bound. The original strict CPU-Torch/ORT parity
check remains unchanged; selection/calibration still uses the recorded CUDA
validation logits. Retain this precision distinction for any later activation.

## Verification / scope

11 new tests plus14 durable-run regressions PASS. Tests include exact interrupted
epoch continuation (optimizer/RNG/history/best), consumed steps, lost responses,
duplicate admission, calibration, class metrics, reference conflict and pooling.
Ruff/format/scopedMypy PASS. Own separate review checked every task criterion
against the accepted plan: no unresolved P0–P2. Original geometry SHA
`06870eb890ad41947d05d0e0a4da1f0c6d7cac31a797ba196971a72ec1ee9f43` and symbol SHA
`fa518e34b5547eec3b09e7158126a3c01b976bc989b472fa0c21ac54cb046e02` unchanged.
Live source/ref/catalog bindings and immutable preparation also verify unchanged.

No DB writes/migrations, original label edits, production registration, activation,
deployment, merge/push or API/UI restart. No Super attribute labels exist, so
these models recognize underlying symbols, not gold-frame state. Next scope:
an independent larger inference batch, followed by targeted review; activation
and a new cohort after corrections require their separate authorized task.
