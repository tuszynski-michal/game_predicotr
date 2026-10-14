---
title: Persistent Claude Code CLI discovery
status: done
last_updated: 2026-10-14
---

# TASK-1007 — Persistent Claude Code CLI discovery

## Status

`done`

## Goal

Discover the existing Windows-packaged Claude Code CLI without relying on PATH, and retain this knowledge for subsequent agents.

## Context

The operator asked to retain the solution to repeated Claude Code availability failures. PATH lookup fails, although the installed executable runs from the Claude Windows package's LocalCache directory. The process-reported Roaming path is not accessible from this environment.

## Dependencies / entry conditions

Direct operator request. No product implementation plan applies. Existing unrelated changes under worktrees/multi-game-share remain untouched.

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/architecture/CODE_MAP.md
- .codex/skills/claude-audit/SKILL.md

## Scope

- Preserve PATH precedence; add bounded-directory discovery for the native and packaged Claude Code installations.
- Choose the newest numeric installed CLI version, without pinning a version or changing user PATH.
- Add a persistent instruction to AGENTS.md and correct the audit skill's missing-CLI guidance.

## Out of scope

Installation, login, credentials, production services, model calls, full audits and changes to product code.

## Acceptance criteria

- [x] Existing PATH commands retain precedence; unrelated missing tools return null.
- [x] Packaged CLI is found without PATH, including after an installed version changes.
- [x] New-process version probe succeeds with a finite timeout.
- [x] Future agents read the diagnostic rule in AGENTS.md.

## Expected files

- scripts/audit_task.ps1: Resolve-AuditorCli and missing-CLI message.
- AGENTS.md, .codex/skills/claude-audit/SKILL.md.
- This task, CURRENT_STATE.md and its rolling archive.
- New regression test scripts/tests/test_auditor_cli.ps1.

## Verification

Run the resolver regression script in a new PowerShell process (60-second limit), then a real CLI --version probe (15 seconds), npm run docs:check (120 seconds), and git diff --check. No network/model request is required to prove discovery.

## Risks / open questions

Successful discovery is not proof of login or model availability. A future vendor directory layout change requires updating discovery. No cross-family audit is mandated by an accepted plan for this standalone change.

## Outcome

Implementation commit: **v1.7.361 / `baf67dbd0456ede583237c45c3b287e01afe6385`**.

### Changed

- Resolve-AuditorCli preserves PATH precedence, discovers native and Windows-packaged Claude Code, and selects numeric versions without a pinned executable path.
- AGENTS.md and the Claude audit skill retain the diagnosis and clarify discovery versus login/model availability.
- Eight offline regression cases cover missing CLI, packaged discovery, version update, incomplete/invalid versions, Git/Codex isolation, Roaming and native installations, and PATH precedence.

### Verification results

- Windows PowerShell 5.1 regression script: 8 PASS, fresh process, 60-second timeout.
- Real resolver and fresh CLI process: Claude Code 2.1.295, exit 0, 15-second timeout.
- Full audit-script DryRun: resolved Claude Code 2.1.295, exit 0, without a model request (60-second limit).
- npm run docs:check: PASS (544 decision entries, 42 active tasks, 10 done sections; 120-second limit).
- Code map regenerated: no semantic changes. git diff --check: initial trailing blank line corrected; final check PASS.

### Not completed

- No model request, authentication test, independent cross-family audit, reboot, installation or user PATH change. CLI discovery is verified; authenticated audit execution is not.
- Operator accepted the result and explicitly requested main on 2026-10-14. Fast-forward merge from codex/claude-cli-discovery into main completed at v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d`; implementation commit ancestry verified. Existing unrelated worktree changes preserved. No push.

### Documentation updates

- AGENTS.md, audit skill, CURRENT_STATE.md and rolling archive.

### Recommended next task

- Use the resolved CLI for the next authorized audit; report authentication/model failures separately from executable discovery.
