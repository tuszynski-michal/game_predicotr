---
title: Jawny protokół większego eksperymentu RGB Mumii
status: done
last_updated: 2026-10-06
---

# TASK-0872 — większy izolowany RGB Mumii

## Status

`done`: the bounded experiment, durable runner and independent verification
are complete. V5 candidate acceptance is REJECTED; TASK-0873 entry is not met.

## Goal

Train one larger RGB candidate from the qualified multi-packet AI assessments
and unchanged human development, using explicit new protocol limits and durable
checkpoint/resume. Evaluate the actual exported model before accepting it.

## Context

The operator requested autonomous larger training and prioritised accuracy.
The original generation4 single-reference protocol remains valid and unchanged.
The new candidate is experimental; AI origin is never human approval.

## Dependencies / entry conditions

- TASK-0871 completed, independently audited and committed separately.
- Bind its immutable qualified-visual pointer, qualification ID and file SHA.
- Preserve R2/V4/human26/human8, human84 validation and diagnostic histories.
- No new recording-origin question: all three existing folders are distinct.

## Recommended execution

gpt-6.1-sol, high. Independent code/data/inference audit: gpt-6.1-sol, high.
Do not retry a rejected variant under another seed or weaken acceptance gates.

## Relevant docs

- AGENTS.md, ai_docs/README.md, ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md, ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/requirements/VISION_LAB.md (D-502–505)
- ai_docs/architecture/VISION_LAB.md (exact feedback and AI adapter)
- ai_docs/delivery/MUMIE_LARGE_TRAINING_EXECUTION_PLAN_20261006.md (stage B)
- ai_docs/quality/MUMIE_AI_ROUND2_20261006.md
- ai_docs/quality/MUMIE_FIRST_HUMAN_CHECK_20261006.md
- ai_docs/quality/MUMIE_RGB_ONLY_DIAGNOSTIC_20261006.md
- TASK-0871 outcome and its new quality report
- ai_docs/quality/MUMIE_LARGE_RGB_EXPERIMENT_20261006.md

## Scope

Introduce a versioned multi-reference manifest and a separate explicitly bounded
RGB protocol. Reuse SymbolTrainingInputs, SymbolDataset, RGB preprocessing,
appearance augmentation, human-feedback weight4/AI weight1 and the existing
fenced RunManager/checkpoint/RNG implementation. Keep old references limited to
100 and old generation4 limits unchanged. New bounds: 20 epochs, 7200 seconds,
50000 steps; one RGB model version and one admitted training run per manifest.

Compose the previously qualified R2 inputs and newly agreed exact crops. Preserve
human origin, feedback IDs and all older cohorts. No duplicate crop pixels, no
test photos or decoded aliases, no first-film development, no Super targets.
Bind every packet/reference/review/source/quad/raster/dictionary and qualification
to its original immutable evidence. Validate the full manifest in a fresh process
and through an independent auditor before admission.

Model selection and calibration use only unchanged human84 validation. Evaluate
human26/human8 after training, with per-class non-regression against R2 RGB and
V4 RGB. Preserve existing human18/human19/diagnostic9 gates and AI audit22.
Report actual counts, steps, epochs, worker PID/checkpoints and elapsed time.
Estimate remaining duration only from actual observed epochs. Verify CPU ONNX
numerics/class parity, checkpoint binding and fresh-process resume behaviour.

## Out of scope

Gray/fusion retraining, seed search/refit, new human approvals, geometry training,
API/UI/schema/DB, migrations/deletion, activation, import/deployment, merge/push.

## Acceptance criteria

- [x] Explicit new protocol, immutable multi-reference inputs and old contracts preserved.
- [x] Fresh-process input validation, negative guards and independent preflight audit.
- [x] One bounded durable RGB run with actual checkpoints and measured progress.
- [x] Validation-only selection/calibration and all required per-class comparisons.
- [x] CPU ONNX parity, restart/resume evidence and independent final audit.
- [x] Focused tests/style/types, documented limits and Outcome/CURRENT_STATE; separate commit recorded below.

Candidate gate: **FAIL** (10/18 human per-class comparisons). Completing the
experiment does not make the candidate eligible for integration or activation.

## Expected files

New versioned multi-reference adapter and RGB runner under
services/worker/src/game_predictor_worker/vision_lab; narrowly scoped reuse hooks
in symbol_runs.py, symbol_training.py and symbol_models.py if required.
Focused tests under services/worker/tests, requirements/architecture/decision
documentation for the explicit protocol, this task, quality report and CURRENT_STATE.
Confirmed implementation files: symbol_large_ai_experiment.py,
symbol_large_rgb_protocol.py, symbol_large_rgb_runs.py; optional BOOT class hook
in symbol_runs.py and explicit new purpose/model branch in symbol_training.py.
Old symbol_models registries and adapter factory remain unchanged. New tests:
test_vision_lab_symbol_large_ai_experiment.py,
test_vision_lab_symbol_large_rgb_runs.py and scoped symbol_training regression.

Frozen qualification: 8a57f640f741be76259ec0cd5f7f8a384638754910b94fd004ca2807b40b8ac8,
file SHA c48ba7af2689aa972aa97cfd18082c5c034392a854113b9e7bfeeec0808c5b20,
pointer SHA 1e9c841315217bcce7d55ba8ec75ed33ce4ac1d421bb203428e8f501307c3a32.
Qualified AI cases: 1726, including Mumia109. Preserve the 327-development R2
base and its unchanged validation/diagnostic/AI-audit cohorts.

Implementation decision D-506: local request/state/configuration and a distinct
symbol_protocol_digest, while protocol_digest remains None. canonical_request
already includes the new local field in checkpoint/input fingerprints, avoiding
the unrelated HYBRID branch. One immutable run root is stored in the manifest.
The local runner additionally requires valid best epoch, best_weights and actual
CPU ONNX passed before success. No blocking operator question or API extension.

## Verification

Each finite step has an explicit timeout at most 120 seconds. The controlled
training worker has a persisted PID/lease and the new 7200-second deadline.
Check focused regressions first; do not change an obsolete unrelated test to
make a broader suite green. Never mutate original labels or proof histories.

## Risks / open questions

AI agreement is fallible and does not establish population accuracy. Qualification
count alone does not guarantee improvement. Regression blocks candidate acceptance.
No operator action is required for preparation or this isolated training.

## Outcome

Implemented D-506 as three isolated modules, two narrow reuse hooks and focused
tests. Public/API and generation1–4 contracts remain unchanged. No model registry
or adapter-factory change. Immutable manifest58a064…d36b contains2053 development
cases (human283/AI1770), preserves R2 and adds1726 qualified new AI cases.
Freeze93.78s and fresh-process verification70.81s passed; independent full input
preflight passed. Two initial120s freeze attempts published nothing and left no
worker. Source decode caching and shared-ancestor checks removed their cause
without weakening exact source/quad/pixel/SHA validation.

One actual RGB run5302ac…8093 completed20 epochs/1360 steps on RTX4050 Laptop;
first PID44912 used631.21s, best epoch1, human84=83/84. Calibration temperature
0.95 used only human84. Cancellation revealed a delayed stop; the new local
heartbeat now honours it at the next batch and has a regression test. The
original observed cancellation completed epoch20 before neutral finish. It is
not reported as an epoch9 stop or a process-crash test.

Fresh-process resume of actual checkpoint20 used PID7892, new lease/fence and
the same run/request/budget. Zero new steps; cumulative695.96s/1360 steps.
Weights and ONNX exports are byte-identical across attempts. Actual CPU
Torch/ONNX parity passed on84 cases, max error2.861e-6, identical classes83/84.
Two further detached processes replayed one real batch32 from checkpoint9
(globalStep612), with identical images/logits/optimiser/model/RNG and unchanged
ledger. Proof1d4b43…06d9 and frozen exact source are preserved. The independent
auditor reproduced the sampler/augmentation/labels/RNG in a new process and
verified both proofs, checkpoint and ledger. No new run/model write occurred.

Evaluation efcdc9…5ee rejects V5: human34=29/34 versus R2 RGB34/34 and V4 RGB33/34;
new19=16/19, withheld22=19/22, human8=6/8. Old18=18/18, diagnostic9=9/9,
human84=83/84. Ten of18 per-class comparisons fail. Separate AI audit19/22
and training agreement1762/1770 are not human accuracy. Independent actual
CPU inference of V5 and both baselines,34 native crop rerenders and11480 pins
reproduced all18 gates. Code/data/model/evaluation/replay audits passed with no
open P0–P2. Technical success is separate from rejected candidate eligibility.

Verification:42 focused adapter/runner/legacy-AI tests passed;18 numerical
training/resume tests passed across generations1–5;15 local-runner tests passed
after the cancellation fix. These suites overlap. Final Ruff lint/format passed
for five source modules and three tests. Strict scoped mypy passed for the three
new modules (22.70s); external Torch/Torchvision imports were skipped, local and
Pydantic code remained typed. Full repository tests/build/typecheck were not run.
Exact R2 receipt, re-signed drift, protected groups, cache rechecks, restart,
lost responses, cumulative budgets/fencing and Windows reparse/case-alias guards
are covered. All task criteria and accepted stageB requirements were checked.

Quality report: ai_docs/quality/MUMIE_LARGE_RGB_EXPERIMENT_20261006.md.
Own commit: `v1.7.220`; full hash is added after commit. Older dirty completion
metadata is excluded from this commit.

Not performed: DB/schema/migrations/deletion, human-label/Super writes, geometry
training, gray/fusion refit, seed search, API/UI, activation, import/deployment,
merge or push. Earlier models/evidence remain intact. TASK-0873 is not started
because its PASS-candidate entry condition fails. A separately specified next
experiment should test human/AI and photo exposure: feedback draw share fell
from33.79% to6.84% despite unchanged weight4. This is a hypothesis, not a proven
cause; no new folder or human correction is required to diagnose it.
