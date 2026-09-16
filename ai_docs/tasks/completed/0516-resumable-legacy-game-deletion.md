---
title: TASK-0516 — Resumable legacy game deletion
status: done
last_updated: 2026-09-08
---

# TASK-0516 — Rzeczywiście porcjowane i wznawialne usuwanie starej gry

## Status

`done` — implementation only; data execution remains separately gated.

## Goal

Replace the single-transaction legacy purge with bounded, independently committed
deletion, durable progress and deferred asset references; do not execute deletion.

## Context and accepted plan

The accepted 2026-09-08 partitioned game storage plan contains TASK-0516–0526.
Sequence: resumable deletion (0516), confirmed old-game removal (0517), v2
schema (0518), routing/write fence (0519), current cells (0520), reads (0521),
counts (0522), partition lifecycle (0523), migration rehearsal (0524), confirmed
new-siedem migration (0525), acceptance/retention/default (0526).

This task implements only 0516. The next destructive step requires preview and
separate confirmation. Existing 0504 preservation rules are superseded for the
new command: retain only the existing local chat-search SQLite archive, not
the legacy operational game or its PostgreSQL archive.

## Dependencies / entry conditions

- Legacy UUID: `80f3c7ec-6110-4e20-a263-2675ee5b15d6`, code `777`, name `777 v0.1`.
- Protected UUID: `03d64bfe-4d29-47dd-9153-76bd99b3b5d9`, code `new-siedem`.
- Read-only inspection confirmed database head 0102 and no created/processing
  jobs on 2026-09-08. Recheck these conditions at execution, not only now.
- Record the already-applied 0102 FK index separately before adding a successor.
- Preserve all other pre-existing dirty work, including old cleanup scripts.

## Recommended execution

`gpt-6-astra high`; independent `gpt-6-astra high` review is required for graph,
triggers, ownership, concurrency and checkpoint semantics. Escalate any unknown
dependency or unsafe shared-resource ownership rather than broadening deletion.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`

## Scope / technical notes

- Default 2000-row batches; bounded metadata; no global list of row IDs.
- Each transaction commits delete + asset-reference journal + receipt together.
- Receipt must survive game deletion and process restart. Progress reports actual
  committed counts and stage; unknown totals have no invented percentage.
- Lock timeout 2 s, statement timeout 15 s; shrink retry batch and stop after
  three failures, keeping committed progress and a concrete diagnostic.
- Parent ownership rows remain until children are gone. Self references and
  trigger-owned queue projections require explicit handling.
- The queue deletion trigger needs queue items and states alive and updates jobs.
  Generic child-first deletion is insufficient (independent design audit).
- Global executions/stage results/terminal manifests are not exclusively owned.
  Journal execution keys and leave them for reference-aware GC in 0517.
- Persist a write fence that survives restart, covers OLD/NEW owners and nested
  trigger writes, and does not freeze the protected game.
- Schema preflight includes ownership, FK indexes and trigger definitions.

## Expected files

- Existing: `storage/models.py` FK index declaration (prerequisite only).
- New: versioned ownership policy, deletion repository/CLI, Alembic migration,
  unit and isolated PostgreSQL tests, operational documentation.
- Do not introduce runtime imports of untracked maintenance scripts.

## Out of scope

Actual deletion, migrations on the application database, file GC, service restart,
new-siedem migration, partition rollout, and all access to `Documents/777`.

## Acceptance criteria / test cases

- Restart and lost response preserve committed batches and do not count twice.
- Failure before commit changes neither domain rows nor checkpoint/journal.
- No delete crosses game ownership or removes shared execution data.
- Queue trigger behavior remains valid throughout deletion.
- New/updated child rows cannot enter or leave a fenced game unnoticed.
- Scope, archive, schema/index drift and active jobs block unsafe execution.
- Metadata is bounded and oversized rows produce explicit errors.
- Only the operator command with matching confirmation can start deletion.

## Verification

Focused pytest and PostgreSQL tests on an isolated temporary test database;
Ruff, scoped mypy and formatting. Each command is supervised by a subprocess
timeout of at most 120 s. Review precedes the completion commit. No application
database mutation is authorized by test execution.

## Outcome

### Changed

Implemented the pinned deletion policy, grouped hierarchical keyset cursor,
independent transactions, durable receipt/journal, explicit queue-trigger
handling, reference preservation, exact SQLite preservation proof and CLI.
Added unapplied 0103/0104 migrations for the receipt/fence and missing access
paths. No imports from pre-existing untracked cleanup scripts.

### Verification results

Eight distinct focused tests passed (PostgreSQL integration, six policy tests,
prerequisite index). Ruff, scoped mypy and changed-file formatting passed.
Independent `gpt-6-astra high` review has no remaining P0/P1 after corrections.
Real read-only archive comparison matched 414705 layouts and the symbol catalog.
See `ai_docs/quality/TASK_0516_RESUMABLE_DELETION_REVIEW.md` for evidence and limits.

### Not completed

Application-database migration, deletion, physical GC and all subsequent tasks
have not run. Large-data performance and index disk cost are not established;
the small isolated fixture is not a throughput benchmark. Full application/web
tests were not needed for this maintenance-only change and were not run.

### Recommended next task

TASK-0517 only after completion and explicit confirmation of a current preview.
