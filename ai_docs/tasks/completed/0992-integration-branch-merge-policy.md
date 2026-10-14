---
title: Integrate the symbol repair and require task integration
status: done
last_updated: 2026-10-14
---

# TASK-0992 — Integration branch merge and completion policy

## Status

`done`

## Goal

Make the committed symbol reinference repair available on `v1.1-vision-lab-hybrid-geometry` and require local integration after future completed tasks.

## Context

The operator explicitly requested integration of v1.7.351/v1.7.352 and an `AGENTS.md` rule making integration part of completion. The integration branch is checked out at `worktrees/multi-game-share`, with unrelated uncommitted tracked and untracked work. Its committed tip v1.7.350 is an ancestor of main; main contains only the two requested repair/documentation commits beyond it.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/AI_DRIVEN_DEVELOPMENT.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/tasks/0991-symbol-reinference-resume.md`
- `ai_docs/archive/CURRENT_STATE_2026Q4.md` (rolling-window insertion boundary only).

## Scope

- Add the default integration branch and the post-verification/commit local merge rule to `AGENTS.md`; remove the contradictory blanket ban on automatic merge.
- Preserve all existing migration, data-operation, review and service lifecycle gates; no push or service restart.
- Record this task and integrate the repair plus this policy with a fast-forward in the existing integration worktree.
- Snapshot unrelated dirty files and temporarily protect only colliding `CURRENT_STATE.md` changes if necessary. Restore that work without committing it.

## Acceptance criteria

- [x] The integration branch contains repair commit `6e84a1b1d4a9546e1ff9545b039512f6691ec15d` and the new policy commit.
- [x] `AGENTS.md` names the branch, requires local integration and no longer contradicts itself about automatic merge.
- [x] All unrelated modified/untracked files remain preserved; unrelated work is not staged or committed.
- [x] Documentation and whitespace checks pass; previous 43 passing code tests are reused because code is unchanged.
- [x] Full commit and integration evidence is recorded. TASK-0991 remains in progress until its separately supervised operational run finishes.

## Expected files

- `AGENTS.md`
- This task, moved to `ai_docs/tasks/completed/0992-integration-branch-merge-policy.md` on completion.
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/archive/CURRENT_STATE_2026Q4.md` (oldest done section, unchanged).
- `ai_docs/tasks/0991-symbol-reinference-resume.md` (integration evidence only).

## Verification

Use bounded Git commands (15–30 seconds), documentation checks (30 seconds each), exact branch containment and dirty-file SHA-256 comparisons. Store protective snapshots under ignored `artifacts/integration-20261014/`. No new code tests or independent model audit is needed for this documentation-only policy and fast-forward of already-tested code.

## Outcome

### Changed

Policy commit: **v1.7.353 / `14aeb0c02b03b60480f3447545c0a17e13bb835b`**. `AGENTS.md` now requires local integration into `v1.1-vision-lab-hybrid-geometry` after required verification, review and the task commit. It preserves migration, data, service and push gates and removes the contradictory blanket merge ban.

The integration worktree fast-forwarded from v1.7.350 / `6fa5577802738f3614fc21e4abc2873990f8536d` to this policy commit, also incorporating the two symbol-repair commits. No migration-dependent changes from the unrelated multi-game feature were committed or merged from its dirty working tree.

### Verification results

- Initial ancestry and committed-scope checks passed. The repair and policy commits are ancestors of the integration branch after the fast-forward.
- All 52 unrelated modified/untracked files retained their SHA-256 values. The colliding `CURRENT_STATE.md` retained all 33 added/changed foreign lines; the single add/add conflict retained both task sections. No foreign staging or unresolved conflicts remain.
- Protective snapshots, patch and verification JSON: ignored `artifacts/integration-20261014/`. The state-only protective stash `85a5e03f1d796634d4d762bfeda028835c3a103a` remains available; no other stash was dropped or applied.
- Documentation checks and `git diff --check` passed before commit; final documentation bookkeeping is checked and fast-forwarded as part of closure. The existing 43 passing symbol/job tests, ruff and targeted mypy are reused; no code changed in this task.
- Main acquired concurrent V3 plan changes in README, requirements, CURRENT_STATE and untracked `ai_docs/delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md`. They were preserved outside this task's commits; the mixed CURRENT_STATE was staged by owned hunks only.

### Not completed

No push, migrations, data writes or service lifecycle changes. No new model audit or broad tests for this documentation-only change. The independent symbol-inference operation remains active under TASK-0991 and its existing heartbeat; this policy task does not declare that run complete.
