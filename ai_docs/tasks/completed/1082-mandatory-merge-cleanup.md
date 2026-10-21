---
title: TASK-1082 — Mandatory cleanup after merging to main
status: done
last_updated: 2026-10-21
---

# TASK-1082 — Mandatory cleanup after merging to main

## Status

`done`

## Goal

Make removal of the merged worktree and local branch a required part of
merging to main, without another cleanup permission request.

## Context

The operator explicitly requested automatic cleanup after every merge.
The existing merge skill still requires a separate cleanup authorization.

## Relevant docs

- `AGENTS.md` — integration and protection of unrelated changes.
- `.claude/skills/merge-to-main/SKILL.md` and its `.agents/skills/` mirror.
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope / expected files

Update the integration rule in AGENTS.md, align the merge skill and mirror,
and close this documentation task through task-close. Keep AGENTS.md within
its existing startup-read budget without weakening any requirement.

## Acceptance criteria

- [x] Merge approval includes required removal of the merged worktree, when
      present, and its local branch, without another permission question.
- [x] Cleanup verifies that commits are in main, detaches junctions safely,
      and preserves unrelated local changes and unmerged work.
- [x] Skill and mirror agree; docs checks and whitespace checks pass.

## Out of scope

Application changes, deletion of other worktrees, remote branch deletion,
service restarts, automatic merge or push of this documentation change.

## Verification

Run `npm run docs:check`, `git diff --check` and the skill-creator validator
with a 120-second subprocess timeout. No application tests are needed for
this documentation-only change. Compare the unrelated diff checksum before
and after the task.

## Outcome

Commit: v1.7.458 (hash dopisuje kolejny commit).

### Changed

- AGENTS.md makes worktree and local branch cleanup mandatory after merge and
  push. The existing merge approval covers cleanup without another question.
- Merge skill and Codex mirror use the same rule and retain commit, junction
  and unrelated-change checks. Absence of a worktree means branch-only cleanup.
- The integration paragraph was tightened to retain the enforced 14000-byte
  AGENTS.md budget without changing other rules.
- Converted the existing skill description to folded YAML: its unquoted colon
  prevented the skill-creator validator from parsing the original frontmatter.

### Verification results

- docs:check passed, including enforced startup budgets and skill mirrors.
- skill-creator quick_validate.py passed; git diff --check passed.
- No application tests: this change only updates workflow documentation.
- Final unrelated-change checksum and status checked after local commits.

### Not completed

- This documentation change has not been merged or pushed; acceptance of the
  earlier board preview fix is separate from approval of this new change.
- No other worktree, branch, user data or service was changed.

### Recommended next task

Accept the rule change for integration to main; cleanup is then part of that
merge approval.
