---
title: TASK-0895 — Clear the symbol target on each save
status: done
last_updated: 2026-10-07
---

# TASK-0895 — Clear the symbol target on each save

## Status

`done`

## Goal

Every valid save-and-approve submission clears the target selector and requires
a fresh choice before the next submission.

## Context

The user requests clearing `Symbol do zatwierdzenia` when clicking `Zapisz i
zatwierdź`, to prevent accidentally reusing the preceding label.

## Dependencies / entry conditions

- TASK-0894 delivered the unified action on MAIN, v1.7.237,
  `4dfab94aae706905b95eb25cf94a2ab8374d987e`; next version v1.7.238 if HEAD
  remains unchanged.
- Existing `previewOperation` captures `targetSymbolId` before constructing
  either the direct decision or bulk preview command. Keyboard uses it too.
- Interpretation: clear immediately on a valid save invocation, including
  blurry/outside saves and bulk preview. A canceled/failed attempt still
  requires a new selection. Pending/preview commands retain their captured
  target. Other quality/reference actions are outside this request.
- Code is initially clean; old completion receipts and unrelated folders are
  pre-existing changes. No blocking question or API expansion.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`, matching the appended plan task. Inspect
target capture and asynchronous transitions; no delegation. Escalate only
for a discovered mutation-contract conflict.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — unified save and keyboard
- `ai_docs/architecture/API_CONTRACT.md` — existing direct/bulk decisions
- `ai_docs/delivery/SYMBOL_REVIEW_UNIFIED_SAVE_EXECUTION_PLAN.md`
- `ai_docs/guides/MUMIE_MAIN_APP_OPERATOR_GUIDE_20261006.md`

## Scope / out of scope

Reset only the local target for the unified save, preserve captured commands,
and cover repeated, failed and bulk saves. No API/schema/backend changes,
user-data decisions, migration, training, deployment, push or merge.

## Acceptance criteria

- [x] Direct, same-label, corrected, blurry, outside and Enter submissions
  clear the target immediately; the submitted decision still has its target.
- [x] After selecting another crop, save stays disabled and Enter sends
  nothing until the operator explicitly chooses a target again.
- [x] Bulk preview clears the target but captured preview/start commands
  retain it; cancel/failure do not restore the old selector value.
- [x] Frozen bulk cards, current filters and other actions remain unchanged.
- [x] Focused interactions/contracts, scoped format/lint/types and Admin
  build pass. Documentation, Outcome, CURRENT_STATE and commit complete.

## Technical notes / expected files

Existing `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx`,
`previewOperation`: capture the current target, then clear local state for
`reassign`, before either asynchronous branch. Never build a request from
the cleared state or clear again when a late response/job finishes.
Existing `apps/admin/test-interactions/symbol-review-partial.test.mjs`: verify
selector state and recorded commands, including a second selection and
Enter without a new target. Existing requirements, operator guide, plan
and CURRENT_STATE need short behavioral updates. New file is this task.

## Test cases / verification

Same label and another label: submitted target preserved, selector blank.
Select another crop: disabled save; Enter makes no request; choose target
and save: second explicit decision. Blurry/outside: same reset.
Bulk: blank immediately on preview, same target on execution; cancellation
requires a new target. Direct error: target remains blank and no guessed
success. Tests use the existing in-memory client, never MAIN data.

Use the existing absolute `run_step.py` runner with 120 s bounds: tsx
interaction file, Node focused contracts/helpers, scoped Prettier/ESLint,
TypeScript and Admin production build. No browser save on real user crops.

## Risks / open questions

Clearing state before capturing a command would lose the label. Clearing on
a delayed result could overwrite a newer operator choice. Both are avoided
by clearing synchronously after capture. No layout or contract change.

## Outcome

### Changed

- `previewOperation` captures the chosen target, then clears the local
  selector synchronously for `reassign`. Direct, bulk, blurry/outside and
  keyboard saves share this entry. No delayed reset overwrites a newer choice.
- Captured direct/preview/job commands retain their real target. Each new
  submission requires fresh selection. Errors/cancel leave the selector blank;
  reference-image and separate quality actions remain unchanged.

### Verification results

- Fresh-process Admin interactions 13/13 PASS, focused contracts/helpers
  40/40 PASS. Tested repeated saves, Enter with/without a new target, same and
  corrected labels, pending/lost-response error, canceled and completed bulk
  preview, blurry/outside, cold mount and existing frozen-page protections.
- Scoped Prettier/ESLint and TypeScript PASS. Admin production build PASS in
  20.17 s. All steps bounded to 120 s. Diff and acceptance criteria audited.
- No layout/DOM control changes; only existing selector state changes. The
  interaction tests simulate UI events without submitting MAIN decisions.

### Not completed

No task blocker. No real user-data decision, API/schema/backend change,
migration, training, model activation, service restart, deployment, push or
merge. No physical Android-device test for this state-only change.

### Documentation updates

Admin requirements, Mumie operator guide, D-528 follow-up, accepted plan and
CURRENT_STATE describe the reset. Pre-existing receipts are excluded from
the commit. Completion version v1.7.238; hash recorded after commit.

### Recommended next task

No additional implementation is required for this request. Refresh the Admin
page if an existing tab retains the preceding bundle.
