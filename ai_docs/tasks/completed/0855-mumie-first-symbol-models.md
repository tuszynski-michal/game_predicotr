---
title: TASK-0855 — Mumie first RGB/gray symbol models
status: done
last_updated: 2026-10-05
---

# TASK-0855 — first fresh symbol models

## Status

`done`

## Goal

Train and evaluate two bounded, from-scratch symbol classifiers on the qualified
fresh Mumie cohort. Preserve labels and every production model/service.

## Context / dependencies

TASK-0854 is committed as v1.7.200. Operator confirmed independent recordings and
authorized autonomous work using current labels, including fewer than30 Mumii.
Manifest d5dc865287ca2d4583b450ccdca84f6186e16ac86922dc6f95ebea3930151589:
255 development/84 validation,10 classes. No final_test or Super labels.

## Recommended execution

gpt-6.1-sol high, self review. No delegation or production activation.

## Relevant docs

- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/delivery/MUMIE_SYMBOL_TRAINING_20261005.md` (TASK-0855)
- `ai_docs/process/PLAN_STANDARD.md`, `TASK_TEMPLATE.md`, `CURRENT_STATE.md`
- `ai_docs/tasks/0672-vision-lab-t07-train-symbol-models.md`
- `ai_docs/quality/MUMIE_SYMBOL_QUALIFICATION_20261005.md`

## Scope

Reuse SpatialSymbolCnn, deterministic augmentation, neutral v2 checkpoints and
the existing durable RunManager through a separate local symbol manager/worker.
RGB/gray3channel,20 epochs each, batch32, seed20261005, AdamWlr.001/wd.0001,
max1800s/10000steps each. Existing CUDA runtime only. One train per variant per
cohort; retry preserves budget/RNG/optimizer/best/history. Validate inputs at
start/checkpoint/finish. Best epoch by validation macro accuracy/loss/earlier.
Validation-only temperature calibration/fusion, confusion/per-class/logloss,
review disagreements and coverage. ONNX/parity if available within run budget.

## Out of scope

DB, original labels, geometry model/splits, Super recognition without labels,
production registry/API/UI, activation, deployment, push/merge and other games.

## Acceptance criteria

- [x] Two20-epoch from-scratch models, exact cohort binding and saved best weights.
- [x] Durable admission, restart/lost response/resume and non-refundable limits.
- [x] Class metrics, confusion, calibration/fusion and human-review evidence.
- [x] Candidate export/parity result or explicit availability limitation.
- [x] Tests/lint/types, original SHA unchanged, own review and separate commit.

## Expected files

New `symbol_models.py`, `symbol_training.py`, `symbol_runs.py`, scoped tests,
quality report and current state; reuse existing neutral training/run modules.

## Test cases / verification

Scoped unit/resume/run regression tests (120s), Ruff/format(60s), mypy(120s).
Actual workers detached with persistent PID/settings/log and watchdog1800s;
readiness/status reads bounded. No repeated training run outside admission.

## Risks / open questions

Validation has J/Sfinks4. All selection/calibration uses this same small part;
report preliminary evidence, not independent final accuracy. No operator input
required to complete this task. Fewer Mumia labels are accepted for first run.

## Outcome

Both20-epoch models completed, with83/84 validation (98.81%) and Mumia8/8.
RGB best14, gray11; calibration/fusion completed, full84-case ONNX parity PASS.
Suspected human K/Q conflict and uncertain Faraon saved for later review;
original decisions unchanged. Validation is small, reused for selection/calibration.
Existing durable run protocol retained. RGB resumed after unsupported CUDA pool
from epoch0, same budget; equivalent fixed pooling regression added. Actual
new-process replay created no duplicate.11 new tests +14 run regressions, Ruff,
format and scopedMypy PASS. Original SHA unchanged. Own review against every
criterion and accepted plan: no unresolved P0–P2. Report:
`ai_docs/quality/MUMIE_SYMBOL_MODELS_20261005.md`. Separate commit `v1.7.201`,
hash recorded after commit. No activation/DB/deployment or Super training.
