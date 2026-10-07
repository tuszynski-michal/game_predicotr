---
title: TASK-0903 — restore manual API and Admin process control
status: done
last_updated: 2026-10-07
---

# TASK-0903 — restore manual API and Admin process control

## Status

`done`

## Goal

Release the API port occupied by this chat and persist the user's exclusive
manual control of API and Admin service lifecycle.

## Context

The previous import diagnosis left a hidden API launcher/server (15980/29900)
on port 8000. The user explicitly rejects agents starting or restarting API
or Admin and wants to run them in their own terminals.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`
- `ai_docs/requirements/ADMIN_APP.md` — local application form
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md` — local service boundaries

## Scope

- Stop only the verified API instance launched by this chat; verify port 8000.
- Add the manual-control rule to AGENTS.md and link it from the operation guide.
- Record verification and leave API/Admin startup to the user.

## Out of scope

Starting or restarting any service, stopping Admin or workers, changing ports,
application code, imports, data, migrations, autostart configuration or plans.

## Expected files

- `AGENTS.md` — new local service control rule.
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md` — operator-owned startup.
- `ai_docs/process/CURRENT_STATE.md` — operational outcome.
- New task document `ai_docs/tasks/0903-user-controlled-api-admin.md`.

## Acceptance criteria

- [x] The verified API launcher/server from this chat are absent and port 8000
  is free, or an unrelated owner is identified and left untouched.
- [x] A durable instruction prohibits agent API/Admin lifecycle operations
  without a separate explicit current request.
- [x] User commands remain unchanged; no service is started for verification.
- [x] Documentation is committed separately, preserving unrelated changes.

## Verification

Bounded process identity and listener checks, reread the saved instructions,
check documented commands against package.json, and scoped Git diff checks.
No application tests or live HTTP startup are needed for a process-policy edit.

## Outcome

Verified launcher 15980 and child server 29900, exact executable/command line,
parent relation and port ownership. Stopped only those two processes. Both
are absent and port 8000 was confirmed free. Admin and workers were untouched.

The new AGENTS.md section persists the user's rule for future sessions. The
operation guide links the rule and shows unchanged package.json commands in
user-owned PowerShell terminals. Product requirements, architecture, code,
API contract, data and service configuration are unchanged.

Verification: bounded process/listener checks, instruction reread, command
mapping checks, task Markdown format check and scoped Git diff checks. No
application tests, service startup, import retry, push or merge were performed.
The remaining unspecified application error was not diagnosed in this task;
the user can now start API manually and obtain its actual error output.

DoD: every applicable criterion is satisfied by the saved policy and observed
process cleanup. No accepted implementation plan applies to this operational
instruction change. Completion v1.7.247; full commit hash recorded after commit.
