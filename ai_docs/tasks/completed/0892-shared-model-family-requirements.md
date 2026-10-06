---
title: TASK-0892 — Shared model families and game creation catalog requirements
status: done
last_updated: 2026-10-07
---

# TASK-0892 — Shared model families and game creation catalog requirements

## Status

`done`

## Goal

Record the accepted Laboratory direction: publish evaluated model versions
for game creation and share one model family across compatible games.

## Context

The user requests that future 777 v3 and 777 v4 games use and improve the
same model, rather than requiring separate training for every game record.
D-526 already records the future main-application Laboratory integration.

## Dependencies / entry conditions

- TASK-0891 is complete at v1.7.233, commit
  c527ced5187b0024a5faff61505433283bafa090, confirmed against branch history.
- Existing grid profiles and per-game symbol iteration/activation contracts
  remain the current implementation. This task records a future extension.
- Assumption: this clarification authorizes documentation of the domain
  direction, without implementing the Laboratory, schema or model activation.
- No blocking product question for documenting this direction.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`. The available model can reconcile domain
requirements with the existing registry and prevent claims of delivered UI.
An implementation or migration request requires a separate execution plan.
No delegation or independent agent review is required for this documentation.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/requirements/APP_V3_FUNCTIONAL_INVENTORY.md` — MODEL-09
- `ai_docs/process/DECISION_LOG.md` — D-526
- `ai_docs/tasks/0673-vision-lab-training-panel.md` — existing separate scope;
  this task does not execute or change that task's status.

## Scope

- Distinguish game records, shared model families and immutable versions.
- Record evaluated model publication to the game creation catalog.
- Allow qualified feedback from compatible member games in a shared cohort.
- Preserve symbol identity mapping, source provenance, protected test data,
  separate geometry/symbol versions and explicit activation.
- Record the domain decision and update requirements, architecture, inventory
  and current state consistently.

## Out of scope

Application code, API changes, database writes/migrations, new training,
model publication/activation, deployment and changes to existing game data.

## Acceptance criteria

- [x] 777 v3 and 777 v4 can share a model family without sharing boards,
  sequence positions or game rules in the documented target.
- [x] A successful training remains a candidate; quality review and explicit
  publication make a compatible version available when creating a game.
- [x] Family feedback is pooled only through verified class/geometry
  compatibility, with auditable per-game origins and protected evaluation.
- [x] Shared development creates immutable versions; activation does not
  change in-flight jobs or human decisions.
- [x] Current per-game implementation and the unimplemented Laboratory
  extension are distinguished, with no contradictory unconditional rule.
- [x] D-527, CURRENT_STATE and Outcome record scope and verification; one
  separate versioned commit contains only this task's changes.

## Technical notes

The model family is the shared learning identity; a version is an immutable
artifact and report. A game is a separate domain record bound to compatible
model versions. Existing static grid profiles are not a dynamic catalog of
all trained symbol models. Do not turn matching game names into compatibility
or combine Mumie and 777 training data implicitly.

## Expected files

- Existing `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md` — per-game
  scope and target extension.
- Existing `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md` — target
  registry, membership, provenance and immutable snapshot responsibilities.
- Existing `ai_docs/requirements/APP_V3_FUNCTIONAL_INVENTORY.md` — MODEL-09,
  new MODEL-10 and Laboratory target description.
- Existing `ai_docs/process/DECISION_LOG.md` and `CURRENT_STATE.md`.
- New `ai_docs/tasks/0892-shared-model-family-requirements.md`, moved to
  `completed/` after acceptance checks.

## Test cases

Documentation review: two compatible 777 games contribute approved examples
to one family's next version; incompatible Mumie data remain separate; a
candidate is not selectable before publication; a running import keeps its
original snapshot after a new activation; labels map to each game's symbols.

## Verification

Read documents from a fresh bounded process; check cross-document consistency,
relative links and `git diff --check`. Before committing, inspect staged check,
statistics and paths. No code tests/build are required for documentation only.

## Risks / open questions

The future execution plan must define schema/API, catalog UI, compatibility
checks and multi-game activation transactions before implementation. This
task is not that plan and does not authorize those data operations.

## Outcome

### Changed

- Recorded shared families, immutable versions, explicit publication to the
  game creation catalog and pooled qualified feedback from compatible games.
- Preserved local symbols, game data, source origins, held-out protection,
  explicit activation and immutable running job snapshots.
- Separated current static grid profiles/per-game symbol runtime from the
  unimplemented dynamic catalog and shared Laboratory extension.

### Verification results

- Read current profile choices in `game-catalog-state.ts` and
  `game-catalog.tsx`; they select frozen grid models rather than a dynamic
  trained-symbol model catalog.
- Fresh-process review of all four domain documents: PASS; relative linked
  requirement/architecture files exist. All acceptance scenarios are covered
  by the documented target, including incompatible families and pinned jobs.
- `git diff --check`: PASS. Staged check, file list and statistics are inspected
  before the separate versioned commit.
- No code tests, lint/typecheck or build; no application code changed.

### Not completed

- Laboratory integration, schema/API, catalog UI and shared training are not
  implemented by this requirements task. No training, data writes, model
  publication/activation or service restart was performed.

### Documentation updates

- Supervised model requirements/architecture, inventory MODEL-09/10, D-527
  and CURRENT_STATE. Existing TASK-0673 remains unchanged.

### Recommended next task

- Prepare a bounded integration plan for the main Laboratory and shared
  registry, using these domain requirements and the existing training jobs.

### Commit

- v1.7.234; full hash recorded after commit.
