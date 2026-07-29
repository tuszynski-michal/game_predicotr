---
title: TASK-0099 — Safe bootstrap symbol suggestions
status: todo
last_updated: 2026-07-28
---

# TASK-0099 — Safe bootstrap symbol suggestions

## Goal

Use explicitly accepted labels from geometrically approved crops to show
ranked symbol suggestions in the whole-layout review UI, while keeping every
decision manual and auditable.

## Dependency

TASK-0098 must produce a passed local-geometry inventory. Suggestions must not
run on quarantined or unreviewed geometry.

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

- [ ] Only accepted labels with approved geometry can become references.
- [ ] Validation examples never act as their own or same-source references.
- [ ] The UI shows up to three ranked suggestions and their evidence.
- [ ] No suggestion changes a label until the owner explicitly accepts it.
- [ ] A previous crop-version label is visibly distinguished from a current
      geometry prediction.
- [ ] Low similarity yields `no suggestion`, not a guessed class.
- [ ] The same inputs produce the same rankings.
- [ ] Tests, lint, typecheck and UI smoke pass.

## Out of scope

- PyTorch training and ONNX export,
- calibrated auto-accept,
- background retraining after each click,
- geometry correction.

## Outcome

Not started. Reserved after TASK-0098.
