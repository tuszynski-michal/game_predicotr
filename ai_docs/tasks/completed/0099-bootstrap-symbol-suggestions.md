---
title: TASK-0099 — Safe bootstrap symbol suggestions
status: done
last_updated: 2026-07-29
---

# TASK-0099 — Safe bootstrap symbol suggestions

## Goal

Use explicitly accepted labels from geometrically approved crops to show
ranked symbol suggestions in the whole-layout review UI, while keeping every
decision manual and auditable.

## Dependency

D-068 accepted v16 geometry, TASK-0060 produced the source-aware split and
TASK-0061 produced the first immutable bootstrap checkpoint. Suggestions must
not run on quarantined geometry or mutate labels automatically.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- D-058–D-062 in `ai_docs/process/DECISION_LOG.md`
- `ai_docs/tasks/0098-local-image-grid-calibration-held-out-gate.md`

## Scope

- deterministic local image features for accepted crop examples,
- ranked top-three nearest reviewed symbols with distance/confidence evidence,
- optional previous-label suggestion linked through stable `observationId`,
- visible uncertain/no-suggestion state,
- keyboard acceptance that still creates a normal explicit review decision,
- no online model mutation and no auto-accept,
- metrics on a disjoint source-image validation subset,
- tests for determinism, label leakage, ties, empty bootstrap and crop drift.

## Acceptance criteria

- [x] Only accepted labels with approved geometry can become references.
- [x] Validation examples never act as their own or same-source references.
- [x] The UI shows up to three ranked suggestions and their evidence.
- [x] No suggestion changes a label until the owner explicitly accepts it.
- [x] A previous crop-version label is visibly distinguished from a current
      geometry prediction.
- [x] Low similarity yields `no suggestion`, not a guessed class.
- [x] The same inputs produce the same rankings.
- [x] Tests, lint, typecheck and UI smoke pass.

## Out of scope

- PyTorch training and ONNX export,
- calibrated auto-accept,
- background retraining after each click,
- geometry correction.

## Outcome

Completed 2026-07-29. The immutable 269-sample training partition is the only
reference index. Targets always exclude self and references from the same
source image. The UI exposes deterministic top-three evidence, an explicit
`no_suggestion` state and a visually separate previous-geometry label.
Suggestions are read-only; Q/W/E or a click still creates a normal explicit
review decision.

The source-disjoint 74-sample validation report records `75.6757%` coverage at
the conservative `0.9975` cosine threshold, `76.7857%` top-one accuracy at
coverage and `94.6429%` top-three accuracy at coverage. Source leakage is zero.
The report SHA-256 is
`7bd77eeade0a5fd68d74c0394520aa2063ab6c2d6f21d7944cb52374eb6b290e`.

Verification:

- 18 focused classifier, suggestion and whole-layout review tests passed,
- Ruff and strict mypy passed for changed Python sources,
- report `--check` reproduced byte-for-byte,
- loopback browser smoke rendered both `no_suggestion` and ranked top-three
  states without changing the accepted-label count.
