# TASK-0857 — Mumie symbol lighting robustness

## Status

done

## Goal

Run one bounded RGB/gray v2 experiment using existing human labels to address
bright-letter/payline failures, qualify it on unchanged validation and inspect
the same exploratory600-photo batch when qualification passes.

## Context

TASK-0856 exposed clear J/K errors under strong yellow lighting and green
payline overlays. The operator requests autonomous fixes until actual labels
or decisions are needed. Do not use model predictions as training targets.

## Dependencies / entry conditions

Completed separately committed TASK-0856, unchanged D-498339-label qualification
and existing v1 durable run artifacts. V2 uses a new isolated run root.

## Recommended execution

gpt-6.1-sol, high. Separately review leakage, augmentation determinism and
backward compatibility. No delegation. No unbounded tuning after this pair.

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/requirements/VISION_LAB.md
- ai_docs/architecture/VISION_LAB.md
- ai_docs/delivery/MUMIE_SYMBOL_ROBUSTNESS_20261005.md
- ai_docs/delivery/MUMIE_SYMBOL_TRAINING_20261005.md
- ai_docs/delivery/MUMIE_SYMBOL_BATCH_20261005.md

## Scope

One deterministic scoped augmentation/version, additive generation2 CLI,
20ep/1800s/10000steps from scratch per variant, validation-only selection and
ONNX parity. Qualified v2 outputs may be explored on identical600-photo sources.

## Out of scope

New label approvals, source-store mutation, final-test claims, Super training,
default activation, DB and deployment. No repeated search over experiments.

## Acceptance criteria

- [x] V1 defaults and deterministic resume behavior preserved.
- [x] V2 augmentation deterministic per sample/epoch, validation untouched.
- [x] Two bounded durable runs finished successfully.
- [x] Each variant retained 83/84 and ONNX parity on all 84 validation crops.
- [x] Qualified inference uses identical 600 sources and crop pixels; calibration uses 84 only.
- [x] Actual evidence and remaining need for human labels reported without fake accuracy.
- [x] Tests, tools, own review, original SHA, Outcome and separate commit recorded.

## Technical notes

Use the accepted plan's exact transform ranges and existing RunManager,
checkpoints, SymbolTrainingAdapter and dataset. Preserve MODELS defaultv1;
new ROBUST_MODELS and optional generation select supported registry pairs.
Train/validation requests remain bound to the same339 human decisions.
Unqualified v2 models never enter the600-photo qualification path.

## Expected files

- Proposed vision_lab/symbol_augmentation.py.
- Existing symbol_models.py/symbol_runs.py/symbol_training.py: optionalv2.
- Existing symbol_batch.py: optional generation pair, unchangedv1.
- Proposed tests/test_vision_lab_symbol_augmentation.py.
- Existing tests/test_vision_lab_symbol_training.py: exact resume for both generations.
- Requirements, architecture, quality report and current state.

## Test cases

Same sample/seed/epoch has exact same augmentation after restart; different
epoch differs; pixel range stays finite. Validation unchanged. V1 request budget
and CLI defaults remain; v2 request/registration/checkpoint binding/addmission
are explicit. Repeat prior run recovery tests, actual GPU budgets and exports.

## Verification

Use absolute paths and existing bounded run_step.py: pytest/Ruff/mypy120s.
Controlled detached training uses the existing1800s watchdog, PID/log/lease,
bounded status reads and no duplicated variant. Batch portions25/120s.

## Risks / open questions

Augmentation may fail to generalize. If qualification or visual improvement
fails, fresh operator labels for difficult appearances are genuinely needed.
The explored600 batch is not a blind final test and never provides accuracy.

## Outcome

- Completed one isolated RGB/gray v2 pair from scratch, 20 epochs/160 steps
  each. Runs e1f1770f06f44d3687e8985f8f9313b4 and 67b60e8b82d847cfb23cc8e320b05b38:
  validation 83/84, development 255/255, 70.63/78.93 seconds. Both ONNX exports
  pass all 84 crops; max absolute error 2.86102294921875e-6.
- Optional generation 2 and deterministic appearance augmentation preserve v1,
  shared budgets, exact resume and HTTP contracts. Proposed 40 epochs rejected
  before admission; no global configuration increase. Qualification rejects NaN.
- Same 600 photos/5396 boards/80940 pixel-identical crops. V2 uncertainty 16024
  versus 15626; disagreement 4047 versus 3494. 1357 class proposals changed.
  Visual improvements and regressions coexist; no demonstrated overall advantage.
  No activation or claimed final-test accuracy.
- Fresh-process replay: 0 processed; 2404 V2 files/737389437 bytes and all V1
  files unchanged. Strict comparison of all geometry/pixel identities passes.
  Original geometry/symbol states and history preserved. All controlled worker,
  driver and timed-out typecheck processes exited; no orphan PID remains.
- 36 pytest, Ruff format/lint and focused strict mypy with silent imported-module
  diagnostics PASS. Wider mypy found unrelated existing board_search_share_queries
  errors and timed out at 120 s; left outside this task. Own review has no P0–P2.
- Quality report: ai_docs/quality/MUMIE_SYMBOL_ROBUSTNESS_20261005.md.
  D-500 and relevant requirements/architecture updated; plan criteria reviewed
  point by point. Operator evidence: 18 exact cases at
  http://127.0.0.1:8108/symbol-review-priority/review.html. Read-only, no new labels.
- Genuine next boundary: human labels and grid confirmation for difficult
  lighting/payline/white-overlay appearances, plus independent references for
  a quality measurement. Existing recording declaration does not need repeating.
- No database writes, Super training, activation, deployment, push or merge.
  Separate commit `v1.7.203`; full hash recorded after commit in Outcome/current state.
