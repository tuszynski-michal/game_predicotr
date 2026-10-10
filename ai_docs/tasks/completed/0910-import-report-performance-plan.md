---
title: Audited plan for import report performance and game isolation
status: done
last_updated: 2026-10-07
---

# TASK-0910 — Audited plan for import report performance and game isolation

## Status

`done`

## Goal

Deliver a self-contained implementation proposal, independently reviewed by
gpt-6-astra with high reasoning, for the report delays and growth across folders
and games; make it ready for a second review in Claude Code.

## Context

The user requested a plan after the read-only audit of Show report. Existing
Mumie geometry artifact validation costs 19.870 seconds without SQL. The source
file checks cost another 3.606 seconds. Global staging scans, a singleton lock,
game-wide canonical reads and Python job replay scans add avoidable work.

## Dependencies / entry conditions

- MAIN branch `v1.1-vision-lab-hybrid-geometry`, HEAD v1.7.243,
  `69e7ec937dacb4155c8f32978f45a2b26f090a3b`.
- Read-only audit receipts in the absolute repository artifacts directory.
- Explicit user authorization for Astra/high delegation and saving a plan.
- TASK-0910 and proposed implementation TASK-0911–0918 avoid a concurrent
  owner-lookup repair (TASK-0902). Its files/edits are outside this task.
- Existing API/PostgreSQL unavailable during source measurements; live SQL and
  end-to-end HTTP performance remain unverified.
- Assumption: this request authorizes documentation only. The implementation,
  migrations, projection backfill and rollout remain proposals.

## Recommended execution

gpt-6.1-sol / high for planning and source validation. Independent
gpt-6-astra / high design review is explicitly requested by the user. Escalate
unresolved P0–P2 findings before declaring the plan ready.

## Relevant docs

- `C:/Users/tuszy/Documents/game_predicotr/AGENTS.md`
- `C:/Users/tuszy/Documents/game_predicotr/ai_docs/README.md`
- `C:/Users/tuszy/Documents/game_predicotr/ai_docs/process/CURRENT_STATE.md`
- `C:/Users/tuszy/Documents/game_predicotr/ai_docs/process/PLAN_STANDARD.md`
- `C:/Users/tuszy/Documents/game_predicotr/ai_docs/process/TASK_TEMPLATE.md`
- `C:/Users/tuszy/Documents/game_predicotr/ai_docs/process/DEFINITION_OF_DONE.md`
- `C:/Users/tuszy/Documents/game_predicotr/ai_docs/requirements/IMAGE_INGESTION.md`
- `C:/Users/tuszy/Documents/game_predicotr/ai_docs/architecture/API_CONTRACT.md`
- `C:/Users/tuszy/Documents/game_predicotr/ai_docs/architecture/DATA_MODEL.md`
- `C:/Users/tuszy/Documents/game_predicotr/ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`

## Scope

- Separate measurements, current code facts, proposed design and unknowns.
- Define immutable report indexes, live canonical counts, atomic publication,
  bounded reads, game-scoped catalog, cross-process source locks and recovery.
- Preserve exact import guards, historical pinned preflights and V1.1 workflow.
- Define dependent tasks, model assignments, acceptance tests and rollout gates.
- Record independent Astra findings and their resolution.
- Deliver an absolute file link and copyable review instructions for Claude Code.

## Out of scope

- Product code, dependencies or schema changes.
- Database writes/migrations, model training/activation, cleanup, server restarts,
  production projection rebuild, push, merge or deployment.
- Synthetic load tests or a full copy of the database.

## Acceptance criteria

- [x] Plan follows PLAN_STANDARD and TASK_TEMPLATE; every task has a model row.
- [x] Existing referenced files/symbols are verified; proposed elements are labeled.
- [x] Every finding maps to a concrete task and regression/acceptance criterion.
- [x] Overview cannot authorize import or silently load the full geometry artifact.
- [x] Cross-process race, crash, legacy, partial publication and lost response are covered.
- [x] Astra/high final review has no unresolved P0–P2, or remaining blockers are explicit.
- [x] Plan is usable in a new session and includes instructions for independent Claude review.
- [x] Only this task's documentation enters its commit; existing edits are preserved.

## Technical notes

The recommendation persists immutable source/range metadata at browser finalize
and geometry metadata at worker completion. The UI displays that small overview
then loads live canonical counters independently. Exact preflight/start retain
the existing integrity and atomic job/in_use transaction. No dynamic count cache
or new canonical-report job is introduced. A separate source operation task
replaces the global lock with one bounded, cross-process lock per upload.

## Expected files

- New: `C:/Users/tuszy/Documents/game_predicotr/ai_docs/delivery/IMPORT_REPORT_PERFORMANCE_PLAN_20261007.md`.
- New: `C:/Users/tuszy/Documents/game_predicotr/ai_docs/quality/IMPORT_REPORT_PERFORMANCE_ASTRA_REVIEW_20261007.md`.
- New: this task, moved to completed only after final review.
- Existing: only this task's entry in
  `C:/Users/tuszy/Documents/game_predicotr/ai_docs/process/CURRENT_STATE.md`.

## Test cases

- Verify all linked source paths exist and symbols occur in the stated modules.
- Check eight numbered implementation tasks have eight final model rows.
- Check proposed timing goals are not described as measured HTTP/SQL results.
- Review boundary cases with Astra/high and reconcile all actionable findings.
- Check only documentation is staged and whitespace validation passes.

## Verification

Documentation checks only: scoped Markdown formatting, path/model-table checks,
git diff checks and independent design review. No application tests or build are
required because product code and contracts are unchanged. All finite commands
use a bounded runner with a maximum 120-second timeout.

## Risks / open questions

- Live SQL plans and end-to-end latency are not available; they are future
  implementation acceptance gates, not evidence of current success.
- New API modes, auxiliary metadata and locking protocol are proposed; their
  publication in a plan does not record an accepted architectural decision.

## Outcome

### Changed

- Saved the proposed eight-task implementation plan and copyable Claude Code
  review instructions; no implementation scope was started.
- Incorporated seven Astra/high findings on migration ordering, local source
  locking, canonical owner claims, nullable legacy metadata, field names,
  projection job dispatch/identity and bounded index iteration.
- Kept measured file-only costs separate from proposed HTTP performance targets.

### Verification results

- Independent gpt-6-astra/high final review: no open P0–P2 design findings.
- All 38 linked evidence/source/document paths exist; eight numbered tasks match
  eight explicit model rows; the model assignment is the plan's final section.
- New Markdown documents formatted with an explicit scoped ignore file because
  the repository's normal Prettier configuration excludes ai_docs.
- Scoped formatting, staged whitespace and scope checks passed. The commit
  contains only three new planning documents and this task's CURRENT_STATE hunk.
- Application tests/builds were not run: only documentation changed.

### Not completed

- No implementation, migration, data mutation, service restart, training,
  activation, cleanup, rollout, push or merge.
- Live SQL/HTTP, restart/race tests and implementation review remain future
  acceptance gates. No benchmark was performed in this planning task.

### Documentation updates

- Proposed plan, independent design review, this completed task and its own
  CURRENT_STATE entry. No accepted requirements/architecture/decision was changed.
- Initial documentation commit: `v1.7.245 / de62ef98ff5131102b417afdd3cd2564d7526ecc`.
- Documentation follow-up v1.7.246 corrects proposed task numbering to
  TASK-0911–0918 after concurrent task reservation.
  Commit: `192c57ea9a94f3a80aa4193e83d1fc2bda468a1a`.

### Recommended next task

- Independent Claude Code review of the proposed plan, then user acceptance.
