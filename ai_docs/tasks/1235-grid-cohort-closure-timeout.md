---
title: Grid cohort registration timeout repair
status: in_progress
last_updated: 2026-11-16
---

# TASK-1235 — Grid cohort registration timeout repair

## Status

in_progress

## Goal

Complete preserved cohort registration within the existing 300-second statement
budget while retaining all currentness, ownership and split-evidence checks.

## Context / authorization

Operator explicitly approved the additional repair and cost, tests, independent
Claude review and resuming the same learning. Parent `42f30e0e-9707-4cf9-aaf6-10482f6e9d60`
failed at 15:35:08 Europe/Warsaw on attempt 5264 after manifest repair TASK-1234.
It passed artifact/member validation, then timed out in
`public.recording_cohort_command_v10` / `register_cohort_use`.
No lock wait was observed. Cohort `19a52a6c-99ea-56ba-b713-c918338db415`
remains ready_to_freeze, revision 5257, with the same immutable manifest.

The 25,631-source plan contains 428 TRAIN, 41 VALIDATION, 13 REGRESSION,
402 BUFFER and 24,747 unassigned sources. All sources must retain their
registry proof validation, including those not used for training.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/CROSS_AUDIT.md`

## Scope

- Diagnose the expensive registration reads using bounded read-only samples.
- Remove the measured query bottleneck without skipping protected sources,
  changing receipt/proof JSON or increasing stall/statement/GPU budgets.
- Apply database changes only through Alembic, including startup schema readiness.
- Test actual PostgreSQL semantics, stale inputs, role/alias conflicts, permissions,
  immutable replay and a fresh connection; run scoped lint/types/docs/maps.
- Obtain independent Claude review before commit.
- Deploy only within the operator's operational authorization and resume the
  existing parent; no new start key, cohort, workflow or activation.

## Acceptance criteria

- [x] Measured bottleneck and resulting fix are documented.
- [x] Existing source/currentness/protected-role/purpose guards remain effective.
- [x] Targeted unit/PostgreSQL regressions, scoped quality and audit completed.
- [x] Database upgrade/downgrade and existing function security are verified.
- [ ] Same parent proceeds past registration, or a concrete remaining blocker is recorded.

## Expected files

- Existing: `storage/schema_readiness.py`, schema readiness tests, architecture,
  code maps, this task and current state.
- Proposed: migration 0191 and focused PostgreSQL regression tests; exact SQL
  changes will follow the measured bottleneck rather than a broad registry rewrite.

## Technical notes

Limited real-data reads confirmed per-source registry context work (16 sources
0.1389 s), rather than a missing pixel index. Existing indexes are used. Registration
currently invokes the full context separately for every source, even when the
source has no registry links. The repair will preserve byte-identical context JSON:

- In context v3, classify at most 200 input sources by all initial byte/pixel
  registry links, own historical uses and nullable identities. Connected/nullable
  sources retain the original transitive closure and label logic. Disconnected
  sources use the mathematically empty closure, with actual diagnostic evidence;
  empty group proof is evaluated once for the statement snapshot.
- In cohort v4, read contexts in pages of 200 and retain separate cache keys for
  preview=true/false. Every source still passes its original identity, member,
  registry proof, role/purpose and exclusion checks before any registry insert.
- Preserve function OIDs/signatures, capability ownership, SECURITY DEFINER,
  search_path, grants, receipt shape, advisory locks and transaction boundaries.
- Migration 0191 preflights exact old fragments of both function definitions before
  replacing either; downgrade removes only these transformations. No data deletion.
- Add differential PostgreSQL tests against the original definitions for connected,
  disconnected, alias, diagnostic, nullable and mixed preview cases, plus migration
  permissions/rollback and existing role/currentness regressions. Existing data
  diagnostics remain read-only; full live registration is only retried after review.

## Risks / open questions

- Main contains unrelated uncommitted work; implementation is isolated in
  `codex/grid-cohort-closure-timeout` from `656a966b`.
- Existing historical/currentness fixtures have documented baseline failures.
- No live registration retry or operator-data write during diagnosis.

## Outcome

Implementation prepared; existing SQL function definitions captured read-only under
`.runtime/task1235-baseline`. No operator database schema or workflow state changed.

### Changed

- Context v3 uses a bounded page classification and an exact empty-closure branch;
  connected and nullable sources retain their original closure/label code.
- Cohort v4 caches at most 200 contexts per page, keyed separately by source and
  preview mode. All per-source identity/member/proof/role/purpose checks remain.
- Reversible Alembic 0191 transforms both existing definitions only after full
  preflight; OIDs, ACLs, ownership, security, search_path and proof JSON are preserved.
- Startup head guard updated with its graph regression. No API or client changes.
- Current-state header shortened by referring to the existing close-task procedure,
  retaining the required format and leaving room for the active repair pointer.

### Verification results

- Unit/schema tests: 35 PASS. Scoped ruff lint/format PASS; strict scoped mypy
  with silent imports PASS (3 source/migration files).
- Dedicated disposable PostgreSQL test PASS (205 sources, two pages): original/new
  context JSON equal for both preview modes, connected/unconnected sources, own
  history and nonempty labels, cross-game pixel alias, recording component, nullable
  identity, validation A/B, diagnostic evidence, page-two role conflict and stale
  proof. Failed closures insert no use. Restricted-role permissions, fresh-connection
  validation, migration downgrade/upgrade and unchanged function OIDs/ACLs verified.
- Existing effective-material test FAIL at its historical function-text assertion.
  The identical failure was reproduced on main/0190: it expects a 5000-source cap
  removed by 0189. Photo cohort v3 is untouched by this repair. This baseline failure
  was not weakened or included as a passing regression; its later cases did not run.
- Read-only real-data comparison, 200 sources, no function publication: byte-identical
  PostgreSQL JSON text/proof hashes for preview=false and true. Baseline 0.9474/1.1147 s;
  new read 0.3434/0.3955 s. Limited sample, not a whole-cohort completion forecast.
  Evidence: `.runtime/task1235-baseline/read-parity.json`.
- Docs/window/startup/mirrored-skill checks PASS; regenerated code maps and
  `code-map:check` PASS. `git diff --check` PASS.

### Not completed

- Commit, approved database cutover and same-parent resume.
- Live full-cohort registration within 300 seconds remains to be verified after
  migration. Original parent/cohort/command/artifact identities remain preserved.

### Independent review

- Claude Opus 5.5, requested effort high, CLI round 1: PASS, 0 P0 / 0 P1.
  Report: `../quality/TASK-1235_AUDIT_claude-opus-5-5.md`; adjacent receipt
  validates the report and frozen payload SHA
  `960675034f23080ba28146b971ad14a7f87b287e55356aca8f536532551be255`.
- P2-1 retained: the historical effective-material assertion blocks its later
  cases. Dedicated parity/registration tests cover both preview modes and page
  boundaries, but not all later negative admission/release cases independently.
- P2-2 retained: an absent page-cache entry would yield NULL; current identity
  validation and matching ID/preview arrays make this unreachable. Page prefetch
  can change precedence between two invalid-input errors, without admitting input.
- P2-3 retained: training-scope and validation-fence calls remain per source;
  connected sources retain their full closure. The read-only 200-source speedup
  is not evidence that the complete registration fits 300 seconds. Verify the
  preserved live parent after cutover; retain any remaining concrete blocker.
