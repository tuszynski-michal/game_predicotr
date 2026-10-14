---
title: Resume pending symbol reinference without progress regression
status: in_progress
last_updated: 2026-10-14
---

# TASK-0991 — Resume symbol reinference and scoped operator run

## Status

`in_progress`

## Goal

Resume symbol reinference after process or lease recovery without decreasing durable progress, and execute the operator-authorized one-off run for pending cells below 0.80 in game `777a2`.

## Context

Job `2f807266-ae5f-410d-afae-f33c01580773` failed after four attempts with `JOB_PROGRESS_REGRESSION`, at 6824/341461 boards. Its handler restarted counters at zero and ignored its checkpoint. Active model iteration `747c21d5-8cbb-4ba5-a53c-6a763f79a2b4` was activated on 2026-10-13 and contains all eight game classes.

## Dependencies / entry conditions

The operator approved repair and the previously disclosed 1–2 hour work budget, while requesting no application filter/API change. Existing services are not restarted by the agent. The current main branch begins at v1.7.350 / `6fa55778`; untracked `worktrees/` predates this task.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/API_CONTRACT.md`, pending reinference section
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/archive/CURRENT_STATE_2026Q4.md` (only the insertion boundary when closing the rolling window).

## Scope

- Store a stable source/item key in new checkpoints and continue after that key on recovery.
- Replay historical cursorless checkpoints idempotently with durable progress as a lower bound; do not disable the domain regression guard.
- Preserve total and counters when eligible rows disappear through human decisions.
- Use a separately saved operational runner/manifest for the one-off <0.80 scope; no new application filter, API, UI, migration, training or activation.
- Read-only preview on 2026-10-14: 35122 pending source-available cells below 0.80; no active game job. Approved cells are excluded regardless of confidence.

## Acceptance criteria

- [x] Restart resumes after a durable stable cursor, including when earlier rows disappear.
- [x] Legacy checkpoint recovery and an empty eligible set do not regress counters or total.
- [x] A committed prediction with a lost checkpoint remains idempotent on replay.
- [x] Invalid cursor is refused before inference/writes.
- [x] Focused regression tests, lint, format, typecheck and docs checks pass, or limitations are explicit.
- [ ] Operational manifest freezes only pending cells with confidence strictly below 0.80 in game `6e20a58f-88f3-4a9c-87b5-ae3297ed4fbf`; all eight classes are covered. Revalidate identity/state before write and preserve all non-target predictions and human decisions.
- [ ] Operational result and any remaining work are recorded without claiming completion from process launch alone.

## Technical notes

The existing query sorts by `(source.id, item.created_at, item.id)`. New checkpoint kind v2 stores that key, while retaining runtime schema_version=1. Recovery uses the saved counters and filters by the key rather than a positional offset. Old kind v1 lacks a key: replay current eligible rows with existing model/crop uniqueness protection, keeping the saved progress as a high-water mark until replay catches up. Existing domain progress validation remains intact. A shrinking eligible set can leave completed progress below the original total; do not pretend removed rows were successfully inferred.

## Expected files

- Existing: `services/worker/src/game_predictor_worker/images/pending_symbol_reinference.py`, handler and private checkpoint helpers.
- Existing: `services/worker/tests/test_pending_symbol_reinference.py`.
- Existing: `ai_docs/process/CURRENT_STATE.md`.
- New: this task; an operational result under `ai_docs/quality/` if the run executes.
- Operational runner/manifests/logs: ignored `artifacts/symbol-reinference-20261014/`.

## Verification

Use `.venv/Scripts/python.exe` in the repository root. Every subprocess has an explicit timeout (focused pytest, ruff and mypy at most 120 seconds). The one-off operation runs as a tracked process with an explicit deadline, durable receipts, short status checks and no service lifecycle changes.

## Risks / open questions

The exact lease-loss trigger of the historical job is unproven. A cursorless legacy retry may repeat inference before catching up. Eligibility remains live, as before; this change does not introduce a frozen production cohort. An unchanged model/crop pair cannot receive a duplicate revision. Cross-family review is attempted with the installed Claude CLI, if available; it is not a requirement from a previously accepted execution plan for this standalone bugfix.

## Outcome

### Changed

Repair commit: **v1.7.351 / `6e84a1b1d4a9546e1ff9545b039512f6691ec15d`**. This commits the tested code; the task remains in progress until the supervised operational run and verification finish.

Operator-requested integration completed on 2026-10-14: `v1.1-vision-lab-hybrid-geometry` fast-forwarded through policy commit v1.7.353 / `14aeb0c02b03b60480f3447545c0a17e13bb835b`, including the repair and its v1.7.352 documentation record. Unrelated dirty multi-game work was preserved. No push or service restart. Subsequent completion commits must follow the new `AGENTS.md` integration rule.

The handler persists a stable cursor and resumes with durable counters. Historical cursorless retries replay idempotently while keeping the durable progress floor; an empty or shortened eligible set retains prior totals. Cursor timestamps require a timezone. The domain regression guard is unchanged. No API, generated client, UI or migration changes.

### Verification results

- Initial operator-database read only: 35122 pending cells below 0.80; eight classes; no created/processing game jobs.
- Focused worker tests plus three domain fencing/regression tests: 17 passed, 2.06 seconds, new process.
- Complete worker test module and jobs-domain module: 43 passed, 2.33 seconds, new process outside the Windows filesystem sandbox. Initial sandbox attempts failed creating temporary directories or resolving their paths; no application test assertions failed for the changed module.
- Ruff format and lint passed for both changed Python files. Targeted mypy (`--follow-imports=silent` on the changed handler) passed: one source file, no issues. Documentation checks and code-map freshness passed; no module/public symbol changed.
- `claude-audit`: brief created at `artifacts/audits/TASK-0991_BRIEF_claude.md`; Claude CLI was not installed, so no independent cross-family audit occurred. This is an explicit review limitation, not a PASS verdict.
- Operational manifest: 35122 cells on 24309 boards, SHA-256 `dbec7abccf16f9be88854622c5dae804a47170ec069583f9b3a2118951f1f0d6`. Three separate processes resumed the same receipts. Previously inferred exact model/crop pairs are recorded as already processed; only remaining target pixels enter inference. Mixed board revisions retain original values and origin revision IDs for other cells; transactions assert their full prediction/human fields are preserved, excluding system revision references. No result is declared complete before all receipts are verified.

### Not completed

Operational completion, commit and final closure remain pending. Existing poll worker has not been restarted; future jobs need the operator to reload its code. The one-off runner uses the fresh process directly. No push, merge, API/Admin restart, training, activation, schema migration or destructive data operations.

### Operational recovery

The first long runner stopped when Windows briefly refused atomic replacement of its auxiliary status file. All committed board revisions had synchronized receipts. The runner now retries that specific sharing violation at most twenty times (0.1 seconds apart). The previous process was confirmed absent before starting the next; the new process resumed the same frozen scope and receipts. Prior stdout/stderr are preserved. No service was restarted and no completed inference was discarded.

### Continued supervision

At 2584/24309 boards, the resumed process had inferred 3383 target cells and recorded 255 boards previously inferred by the exact same model/crop snapshot. No new stderr or protection assertion failures. The operator requested supervision; a five-minute heartbeat in this same chat was created as `doko-cz-rozpoznawanie-777-a2-poni-ej-80`. It remains quiet during normal progress, verifies completion from a fresh read-only process, resumes only after the previous bounded process has exited, and stops for a new failure or when the operational time budget is exhausted. The heartbeat must complete the task documentation and final result commit after verification, then disable itself. Current runner parent PID 43444 / actual PID 35388; authoritative live state is in `status.json`, not this historical PID record.

### Operator reload for future normal jobs

The repair is on disk, but the existing poll worker was deliberately not restarted. After the one-off operation completes, the operator can reload only the general lane from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/manage_worker_lanes.ps1 -Action Stop -Lane general -TimeoutSeconds 10
npm run workers:start
```

This is an instruction for the operator, not an authorization for the heartbeat to restart services. The one-off operation already uses a fresh process and does not require this reload.
