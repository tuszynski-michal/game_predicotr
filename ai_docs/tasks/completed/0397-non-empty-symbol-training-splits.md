---
title: Non-empty symbol training evaluation splits
status: done
owner: codex
last_updated: 2026-09-02
---

# TASK-0397 — Non-empty symbol training evaluation splits

## Context

An individual-cell training cohort contained 885 approved crops from 14 source
families, but its persisted `sourceAssignments` was empty. Hash fallback put
all families into train, validation, and test, leaving regression empty. The
job therefore trained for 40 epochs and failed during candidate evaluation.

## Scope

- derive source families from both legacy board items and individual approved
  cohort cells;
- repair a historical assignment only when it cannot populate every required
  split;
- reject an empty required split before training;
- cover the regression with focused API-storage and worker tests.

## Relevant docs

- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Definition of Done

- A new-game individual-cell cohort with at least four source families persists
  non-empty train, validation, test, and regression assignments.
- An incomplete historical assignment cannot cause a late candidate-gate
  failure.
- A malformed configuration fails before the first training epoch with a
  stable error code.
- Focused tests, lint, and typecheck pass.

## Outcome

- Iteration creation now gathers source checksums from legacy cohort boards and
  from individual-cell cohorts joined through `source_image_id`.
- Broken historical assignments are deterministically rebuilt only when their
  remaining sources cannot fill every missing required split.
- The worker validates train, validation, test, and regression immediately
  after dataset preparation and fails before epoch one with
  `TRAINING_DATASET_REQUIRED_SPLIT_EMPTY` if the invariant is violated.
- The real 885-crop cohort for game `b73c7a42-dfce-498c-be26-0df015721990`
  resolves 14 source families and now produces `11/1/1/1` source assignments.
- Verification: 15 focused tests passed; Ruff passed; mypy passed for the three
  changed production modules.
