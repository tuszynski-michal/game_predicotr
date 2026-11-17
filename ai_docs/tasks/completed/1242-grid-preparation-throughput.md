---
title: Resume-compatible grid cohort materialization throughput
status: done
last_updated: 2026-11-17
---

# TASK-1242 — Resume-compatible grid preparation throughput

## Status

`done`

## Goal

Deliver a verified preparation-throughput repair preserving the active parent,
cohort, physical five-source pages, completed receipts, selection and saved progress.

## Context

Operator authorized this repair and an additional 1–2 hours of implementation,
tests and independent audit. Parent `6ac108a6-7b99-4701-bbf3-b5d78fae3b89`, cohort
`8d571c98-bbcc-5d00-9792-4ec77e53c491`, game
`246a1f54-eee8-49d5-b11a-0fde70e5eecd`. Materialization traverses 25,631 sources
for 503 TRAIN photos/647 boards. Before repair cursor 8520/revision 1834.
Read-only baseline: cohort document 20,981,684 decoded bytes/0.389 s; 1758 prior
page records 1,735,469 bytes/0.107 s; prepared artifact 12,344,909 bytes/0.149 s.
Evidence: root `.runtime/preparation-throughput-baseline.json` and timestamped
`.runtime/preparation-speed-before-20261117T125849.json`.

## Dependencies / entry conditions

Isolated branch `codex/grid-preparation-throughput`, based on main `8c1d2f00`.
Protect 45 existing dirty files and all other worktrees. TASK-1230 background
support exists only in the operator checkout; do not include that feature in this
commit. Apply only independent repair hunks when deploying. The running worker
continues unchanged during development. Merge/deployment/restart require approval
of the completed result. No new training, activation or budget extension.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`.
- `ai_docs/process/PLAN_STANDARD.md`, `TASK_TEMPLATE.md`, `DEFINITION_OF_DONE.md`.
- `ai_docs/process/CROSS_AUDIT.md`, `ai_docs/quality/AUDIT_REPORT_TEMPLATE.md`.
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`.
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`, `CODE_MAP.md`.
- `ai_docs/tasks/1230-grid-learning-background-preparation.md` (operational context).

## Scope and technical notes

1. Add an internal bounded materialization group to the existing cohort command;
   public HTTP commands retain one five-source page. The parent uses at most 20
   physical pages per command and a two-second monotonic time slice. Preserve each page
   index, bytes, source order, currentness/deletion fences, final root/index format,
   optimistic revision and immutable command replay. One bounded group is atomic;
   failure leaves prior committed pages untouched. Do not skip population evidence.
2. Store rebuildable per-role materialized counts in the existing summary JSON,
   with a version and exact cursor fence. Bootstrap old cohorts from their already
   committed pages. Invalid/stale counters fall back to authoritative page records.
   Advance counts with page/revision in the same transaction. No schema migration.
3. Compare old/new outputs and bounded costs using existing data, without mutating
   operator records. Test restart, response loss/replay, rollback, partial last page,
   legacy cohorts, stale counters and unchanged ordinary command behavior.
4. Commit tested/audited repair. Prepare deployment with copies of prior receipts
   and identities, request completed-result acceptance and restart authorization,
   then verify this exact parent resumes from a nondecreasing committed cursor.

Assumption: five-source physical pages and immutable artifacts are authoritative;
grouping and derived counts are execution details, not changed labels or splits.
Do not change GPU settings, training plan, selection or safety limits.

## Expected files

- Existing `application/grid_training_cohort_commands.py`: `_materialize`, `execute`.
- Existing `application/grid_training_cohorts.py`: `GridTrainingCohortService.command`.
- Existing `application/grid_correction_learning.py`: cohort-command dispatch.
- Existing `storage/grid_training_cohort_repository.py`: `summary_view` and count updates.
- Proposed `storage/grid_cohort_materialization_progress.py`: bounded derived counts.
- Proposed `services/api/tests/test_grid_preparation_throughput.py` and focused PostgreSQL test.
- Relevant architecture, maps, task and state window; generated audit evidence.

## Acceptance criteria

- [x] Old completed pages/receipts and their bytes remain valid; ordinary requests unchanged.
- [x] Same cohort continues at its saved cursor after a fresh process; no duplicate committed work (disposable PostgreSQL proof).
- [x] Bounded grouping reduces full header/prepared reads and receipts per processed source.
- [x] Derived counters equal authoritative full-page aggregation, including old cohorts/restarts.
- [x] Rollback, stale revisions, response loss and changed/deleted input retain existing guards.
- [x] Targeted tests, scoped lint/typecheck, maps/docs and independent Claude review pass.
- [x] Tested repair is reviewable; deployment and same-parent verification reported separately.

## Verification

Windows PowerShell, root of worktree, finite commands <=120 s:
`.venv/Scripts/python.exe -m pytest services/api/tests/test_grid_preparation_throughput.py services/api/tests/test_grid_training_cohort_core.py services/api/tests/test_grid_training_cohort_requests.py`.
PostgreSQL uses an exact-owned disposable database, never operator writes.
Scoped ruff/format/mypy, `npm.cmd run docs:check`, `npm.cmd run code-map:check`.
Audit CLI timeout 1800 s/idle60 s; do not automatically retry transport failures.

## Risks / open questions

- Concurrent main changes and existing background hunks require preservation verification.
- A bounded group can redo only its uncommitted final work after interruption.
- Actual speedup requires measurement; currentness checks and selected-image copies remain.

## Outcome

Commit: v1.7.665 / `cd83092bf0f9354ee4f1fe996f1d4a32d9b94c53`.

### Changed

The parent requests internal groups up to 20 physical pages. Each physical page
still uses the same implementation, CAS revision, currentness checks and immutable
publication. A group is bounded by page count and a two-second slice checked
between pages; a currently executing page retains the normal command deadline.
Public requests default to one page. One group commits one receipt; interruption
rolls back the whole unfinished group, preserving all prior committed work.

Existing summary JSON now holds revision/cursor-fenced derived counters. They are
bootstrapped from prior pages once, excluding the just-inserted page to avoid
double counting. Counter assignment follows page flush; the header update and
revision then commit together, respecting PostgreSQL immutable-history triggers.
No schema, HTTP shape, original input, budget, label or split changes.

### Verification results

- New focused unit suite: 23 PASS (within the final 40-case run), including grouped/ordinary byte parity
  for selected JPEGs, target nodes, physical pages and final root manifest; final
  short page, stale/malformed counters, old receipts, ordinary one-page default,
  group limit and time-slice yielding.
- HTTP cohort requests and four relevant core regressions: 17 PASS; combined
  with the new suite, 40 PASS (5.60 s).
- Parent handler/API regressions: 38 PASS (5.84 s).
- Exact-owned disposable PostgreSQL: 1 PASS (29.45 s). An old page at cursor 5
  survives a failing group and rollback. Successful group advances to cursor 25;
  lost-response replay returns the identical receipt. New interpreter then
  continues that exact cohort from revision 13/cursor 25 to revision 14/cursor 30.
  Immutable-history triggers remain enabled.
- Combined operator source compatibility: patch applies cleanly to the 45-dirty-
  file checkout; tested only on a source copy with TASK-1230 hooks. Six background
  preparation/progress/response regressions PASS (11.98 s after correction), no live file mutation.
- Total distinct passing tests: 85. Operator database was never written by tests.
- Read-only parity on 2057 existing operator pages (cursor 10285) matches exactly.
  Derived summary uses zero page scans versus one full scan per old summary call.
  In-memory metadata aggregation took 0.002118 s vs 0.0001075 s; this excludes SQL
  and is not an end-to-end speedup claim. Prepared reads and command receipts
  occur once per group instead of once per physical page (up to 20x fewer).
  Full header loads are bounded per advance, with revision-only per-page locking.
- Scoped ruff and format PASS. New count module strict mypy PASS with skipped
  imports. Four existing modules pass scoped mypy with skipped imports and only
  no-any-return disabled because imported SQLAlchemy/other return types are opaque.
  Following imports silently exceeded 100 s; no orphaned mypy remained.
- Maps regenerated; docs:check and code-map:check PASS (startup 44552 B); diff check PASS.

### Known baseline / scope limits

Full existing core suite is not claimed green. Its currentness fixture lacks
artifact_root, reproduced from unmodified HEAD (2.20 s), outside this repair.
The changed excluded-source fixture was completed with already-required
policyVersion/recording metadata and the new repository method; all original
no-pixels/no-negative-label assertions remain. No test weakened or removed.
An initial broad core run timed out after 110 s; own-process inspection confirmed
no orphan before the targeted runs. Tests were then scoped to this changed flow.

### Not completed

Completed-result acceptance and live deployment remain pending.
No live file changes, worker/API restart, new parent, GPU budget change or activation
has been performed by this repair. Live deployment needs explicit restart consent
and a fresh committed-cursor/artifact comparison before and after cutover.

### Independent review and one correction round

Round 1 report/receipt are preserved byte-for-byte as
`quality/TASK-1242_AUDIT_ROUND1_claude-opus-5-5.*`; report SHA
`043a6677000b3cc3edb410d96be0e2a7de5bc9b1f392236cb095f1986d9cfbdc`,
payload SHA `9fc801759f1da37c9d200a2feb73eddf196a831d745e68a76a66985d85679679`.
REVISE: 0 P0/1 P1. Transport 1 hit the five-hour account limit; operator authorized
one actual retry. Technical attempt 2 failed before launch (no CLI/PID selected);
attempt 3 executed that authorized retry. All attempts remain in the receipt history.

One correction round addresses all findings:
- P1-1: materialization now locks a revision-only projection with FOR NO KEY UPDATE.
  Keys/document cannot change under the existing immutable-history trigger; CAS
  still checks both DB and in-memory revisions. This lock serializes header writers
  and allows concurrent FK KEY SHARE for correction-notice events. Other cohort
  locks remain unchanged. The group slice is reduced to two seconds between pages;
  the existing individual page deadline remains applicable. This reduces added
  fence-hold time; no strict maximum shorter than the slowest single page is claimed.
  PostgreSQL proves a second transaction can insert a currentness-notice event
  with lock_timeout=5s while the materializing transaction still holds its lock.
- P2-1: the per-page row lock no longer reloads/decodes the immutable document.
  Corrected performance description: prepared-artifact reads and receipts are once
  per group. Full header loads remain bounded per parent advance (up to three
  before the physical-page loop), plus revision-only locking per physical page.
  This is structural reduction, not a measured 20x live speedup.
- P2-2: PostgreSQL fixture now has nonzero prior-page counts (6 boards, 2 photos,
  1 full photo), checked against full-page aggregation and after restart. It is
  metadata-test evidence, not a human-label or trainability certificate.
- P2-3: four parent-dispatch tests cover preparing, preview_ready, materializing
  and ready_to_freeze; only materialization receives materialization_pages=20.

Updated focused regressions: 40 PASS (5.60 s); PostgreSQL concurrency/rollback/
nonzero-counter/restart test PASS (29.45 s). With unchanged 38 parent/API and six
background-compatibility cases this is 85 distinct tests. Refreshed compatibility,
scoped types/lint, maps and docs checks PASS.

Focused review round 2: PASS, 0 open P0/P1, all four original findings closed.
Report/receipt: `quality/TASK-1242_AUDIT_claude-opus-5-5.*`, payload SHA
`c5aa481aff6c02984bd454bc3256e9ace5a2c5d32ad40e124232d2242d2818bc`,
report SHA `37288b96b76800a3b813d4ac6c1d59d80d076f5408e07b8b2534c8caab4f6076`.
Observed CLI model claude-opus-5-5; effort high is requested-only evidence.
Residual P2-4 accepted: a manually created/malformed cohort with summary={} may
still fail metadata display; all normal creators initialize roles, and this
operator cohort has roles. No further review loop. Additional fence-hold time
can be up to two seconds plus the existing individual-page duration.

Live preservation evidence (read only, still pre-deployment): 2469 pages/cursor
12345 were SHA-verified, then 2838 pages/cursor 14190 passed comparison with every
earlier page and unchanged parent, command, cohort and document identity. Root
`.runtime/task1242-run-preservation-20261117T133426695527Z.json` and
`.runtime/task1242-run-preservation-20261117T135149292159Z.json`.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1242 | gpt-6.1-sol | high | Scoped repair with transaction and replay compatibility; stop for a domain contradiction. | claude-opus-5-5, high, read-only CLI; availability confirmed by transport result. |
