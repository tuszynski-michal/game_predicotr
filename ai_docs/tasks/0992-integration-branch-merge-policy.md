---
title: Integrate the symbol repair and require task integration
status: in_progress
last_updated: 2026-10-14
---

# TASK-0992 — Integration branch merge and completion policy

## Status

`in_progress`

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

- [ ] The integration branch contains repair commit `6e84a1b1d4a9546e1ff9545b039512f6691ec15d` and the new policy commit.
- [ ] `AGENTS.md` names the branch, requires local integration and no longer contradicts itself about automatic merge.
- [ ] All unrelated modified/untracked files remain preserved; unrelated work is not staged or committed.
- [ ] Documentation and whitespace checks pass; previous 43 passing code tests are reused because code is unchanged.
- [ ] Full commit and integration evidence is recorded. TASK-0991 remains in progress until its separately supervised operational run finishes.

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

In progress.

### Verification results

Initial inspection: main is clean apart from pre-existing untracked `worktrees/`; integration worktree contains unrelated work. `git merge-base --is-ancestor v1.1-vision-lab-hybrid-geometry main` succeeded. Exactly v1.7.351/v1.7.352 are ahead of the integration tip.

### Not completed

Commit, protected fast-forward, restoration and final checks remain pending. No push, migrations, data writes or service lifecycle changes.
