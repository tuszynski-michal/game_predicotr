---
title: Jawny protokół większego eksperymentu RGB Mumii
status: todo
last_updated: 2026-10-06
---

# TASK-0872 — większy izolowany RGB Mumii

## Status

`todo`: the accepted execution plan authorises continuation after TASK-0871.
No implementation or CNN admission before its final qualification and audit.

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

- [ ] Explicit new protocol, immutable multi-reference inputs and old contracts preserved.
- [ ] Fresh-process input validation, negative guards and independent preflight audit.
- [ ] One bounded durable RGB run with actual checkpoints and measured progress.
- [ ] Validation-only selection/calibration and all required per-class comparisons.
- [ ] CPU ONNX parity, restart/resume evidence and independent final audit.
- [ ] Focused tests/style/types, documented limits, Outcome/CURRENT_STATE and own commit.

## Expected files

New versioned multi-reference adapter and RGB runner under
services/worker/src/game_predictor_worker/vision_lab; narrowly scoped reuse hooks
in symbol_runs.py, symbol_training.py and symbol_models.py if required.
Focused tests under services/worker/tests, requirements/architecture/decision
documentation for the explicit protocol, this task, quality report and CURRENT_STATE.
Exact files and frozen qualification binding must be confirmed before coding.

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

Not started. TASK-0871 visual reviews are still running. No CNN was admitted.
