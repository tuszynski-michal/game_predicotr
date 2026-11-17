---
title: Per-run progress supervision without a cumulative wall-clock stop
status: done
last_updated: 2026-11-17
---

# TASK-1244 — Progress supervision of the existing correction training run

## Status

`done`

## Goal

Replace the cumulative time stop for the explicitly approved training run with
supervision of completed work, retaining its identity, consumed work and checkpoints.

## Context

The operator explicitly requested supervision rather than a two-hour limit and
approved 1–2 hours of additional implementation, tests and Claude review. Parent
`6ac108a6-7b99-4701-bbf3-b5d78fae3b89`, training child
`6d003b6e-e0c1-4b15-be97-c10cbf92fac0`, cohort
`8d571c98-bbcc-5d00-9792-4ec77e53c491` remain the operational targets.
The current child is alive: native CPU and reads increase, and stack samples
prove transition from TRAIN indexing to VALIDATION indexing. GPU steps were still
zero at 15:02 UTC. Existing code enforces 7200 seconds in supervisor, child control
and independent child watchdog, including startup. No policy has been changed yet.
TASK-1243 is reserved on another branch; this task uses 1244.

## Dependencies / entry conditions

Work from main `041002571fc029eb66c82bae19bcad66ec4bfd63` in the isolated
`codex/grid-progress-supervision` worktree. Preserve the 45 dirty root files.
The running old child cannot safely acquire changed Python code in memory.
Deployment needs a graceful, checkpoint-preserving handoff of the same job and
explicit approval of the finished result and the necessary grid worker restart.
No restart, cancellation, migration, merge or activation is performed by this plan.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/CROSS_AUDIT.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/CODE_MAP.md`

## Scope and technical decisions

- Add an explicit, persisted `operator-progress-supervised-v1` budget policy for
  an approved ordinary correction run only. Existing presets, smoke runs,
  content experiments, optimization steps and quality gates keep their defaults.
- Represent no cumulative time ceiling as JSON null, never infinity or a huge
  substitute number. Continue accumulating finite elapsed seconds; preserve all
  reservations, attempts, checkpoint bindings, recipe, seed and split.
- Extend the existing owner preview/apply tool with an explicit policy option,
  exact SHA approval and row comparison. Apply only to a stopped, unleased run
  with settled consumption and a verified existing checkpoint. Replay is
  idempotent; drift and active jobs are rejected.
- Child and supervisor remove only the cumulative stop for that policy. Keep
  cancellation, supervisor-loss detection, GPU lease protection and step limits.
  Stop with a specific progress-stall error after 300 seconds without completed
  work. A heartbeat, live PID, busy CPU or changing timestamp alone never renews it.
- Publish bounded, attempt-bound activity records after verified snapshot pages,
  completed validation units, optimizer steps and export milestones. Emit at most
  once per second while work advances. New attempts revalidate input and restart
  the stall observation window; consumed training work is never replenished.
- Keep manifest defensive-copy semantics; read one local manifest per metadata
  scan rather than copying the large manifest for every source/target. Verify
  identical dataset rows and train/test boundaries.
- API reports a nullable time ceiling, with generated client/wrapper compatibility
  and an honest existing budget display. Do not add a second start API or automatic
  model activation. No database schema change is required.

## Expected files

Existing: `training_core/grid_training_admission.py` (RunBudget),
`images/grid_training_handler.py`, `images/grid_training_child.py`,
`images/grid_cohort_dataset.py`, `images/grid_training_data.py`,
`images/grid_correction_consistency.py`, `scripts/extend_grid_training_run.py`,
API application/schema `grid_training_runs.py` / `grid_training_cohorts.py`,
Admin budget display, generated OpenAPI/client and scoped tests.
Proposed: `training_core/run_activity.py`,
`training_core/run_progress_supervision.py` and focused tests.
Update requirements, architecture, decision log and generated code maps.

## Acceptance criteria / test cases

- [x] An explicitly approved policy survives serialization and a fresh process;
  elapsed time above 7200 seconds does not exhaust it or replenish steps.
- [x] Legacy budgets and wire identities retain their existing behavior.
- [x] Genuine page/validation/step progress keeps supervision alive; heartbeat-only,
  stale prior-attempt, malformed or replayed activity does not. Stalls, cancel and
  lost supervisor terminate visibly; actual training exceptions remain errors.
- [x] Owner preview/apply preserves identity/state, checks artifact bindings,
  rejects active/drifted jobs and is idempotent, including PostgreSQL validation.
- [x] Metadata indexing remains byte/label/role equivalent and avoids repeated
  full-manifest copies. The current run is monitored throughout the work.
- [x] Backend, OpenAPI, generated client, wrapper and budget display agree on null.
- [x] Scoped tests, lint, types, documentation/maps and Claude audit pass before
  commit. Report exact coverage and any pre-existing unrelated failures.
- [x] Finished result and safe handoff are presented for deployment approval;
  no activation or new training run is created.

## Verification

Use repository Python with worktree API/worker paths on PYTHONPATH. Run focused
pytest paths for budgets/activity, child/watchdog, handler, owner grants and API;
the existing budget-extension PostgreSQL fixture is the integration starting point.
Run scoped ruff/mypy, generated client/OpenAPI check, affected Admin interaction
checks/types, code-map and docs checks. Finite commands have explicit timeouts
at most 120 seconds; Claude audit uses its authorized 1800-second timeout.
No synthetic large benchmark is authorized or planned.

## Risks / open questions

- No optimizer checkpoint existed at admission; do not interrupt the old child
  until a safe checkpoint handoff is available. If it completes first, preserve
  that result and do not restart completed work just to exercise the new policy.
- Deployment/restart approval is separate from the approved implementation cost.
- Current progress observations are authoritative; a live PID alone is insufficient.

## Outcome

Commit: v1.7.667 / `c2b73c987551e2e1957f80faf63359832e286d2e`.

Implementation and scoped quality checks complete; final Claude review PASS.

The explicit owner grant is restricted to an ordinary stopped grid-only correction
run, requires a verified checkpoint, preserves all consumption/input pins and is
idempotent under row CAS. The nullable ceiling survives a fresh Python process.
Supervisor, child controls and watchdog honor the policy while retaining step,
lease, cancellation and 300-second completed-work protections. Verified snapshot
pages, optimizer steps and per-photo correction measurements publish bounded,
attempt-bound activity. The defensive manifest copy is now outside each metadata
scan's source/target loops. API, generated client/wrapper and panel support null.

Verification so far: 95 distinct Python tests PASS (including two PostgreSQL
grant/CAS/replay cases), 62 Admin interaction cases PASS, two client request cases
PASS. The new policy also passed the real tiny CPU training/checkpoint/ONNX-export
test. The real operator checkpoint at step 2400 passed full byte/binding,
early-stopping and baseline-floor validation in a fresh process, read only:
`D:/game_predicotr/.runtime/task1244-checkpoint-validation.json`.
Two new core modules pass scoped mypy with skipped imports; eight changed existing
modules pass with skipped imports and their opaque Any-return / existing unused
ignore diagnostics disabled. No production type error was suppressed.
Scoped ruff/format, Admin ESLint, client/Admin TypeScript checks, OpenAPI/generated
client drift, regenerated code maps and docs checks PASS (startup read 44,679 B).

Initial test attempts hit Windows path length in the packaged temporary directory
and an HTTP test restriction in the default execution context. Short owned test
paths and the permitted native test context resolved them; no test was weakened.
The failed default HTTP group was checked for orphaned processes before rerun.

While this repair was prepared, the same live training completed at 2400 actual
optimizer steps, stopReason=early_stopping, selecting step 1200. The generic job
counter marks the completed plan as 3600/3600; that is not evidence of 3600
executed steps. Candidate `6cc10344-1d69-5765-b8c8-423a0313984a` was registered;
evaluation `19119701-0904-46e0-8426-ba4af72aa567` is processing. No active process
was cancelled/restarted and no grant was applied to the now-completed training.
Its cumulative old-budget consumption was 3165.907 seconds. No activation.
Operational supervision continues until the parent/evaluation reaches a result.

### One correction round after independent review

Round 1 was REVISE (0 P0, 2 P1); preserved report and receipt:
`quality/TASK-1244_AUDIT_ROUND1_claude-opus-5-5.*`, report SHA
`6123730894b73b329a8f4a86bb34f17c3edf10c265d3d4c50323c004276e13c3`,
payload SHA `1f5e751bb2a15538905d8e9c456bd189fc9bf7d1e25ccc7d4567d50a2da345cc`.

- P1-1: validation crop preprocessing now publishes each completed photo. A fake
  monotonic clock proves continued crop work across 600 total seconds renews
  the stall window, while a subsequent 300 seconds without work stalls.
- P1-2: tests verify watchdog stall result publication and exit code 4, explicit
  cancellation, and successive per-photo validation passes renewing observation.
- P2-1: auxiliary publication uses bounded Windows sharing-error backoff up to
  about 0.47 s and can drop a locked update without crashing training. Persistent
  failure still expires observation. Activity is intentionally ephemeral, unlike
  authoritative checkpoint/budget persistence; fsync is not required for it.
- P2-2: game ID is read once per evaluation part and lazily cached for content
  references. Snapshot defensive-copy semantics and default consumers remain.
- P2-3: a stall no longer masks completed no-improvement or real training errors;
  tests cover simultaneous result arrival and a stall. Cancelled/absent results
  retain the explicit stall interpretation.
- P2-4: clock anomalies keep fail-closed behavior, with a Polish label and three
  invalid-delta tests. Residual: an operator must correct a backwards wall clock
  before recovering a crashed attempt; elapsed consumption is never silently reset.
- P2-5: graph/checkpoint publication, raw parity and bundle publication advance
  export milestones. Real tiny CPU training/export passes under both policies.
- P2-6: 15 regenerated files with no semantic diff were byte-compared to HEAD
  after newline normalization and restored; only the intended generated type
  and OpenAPI change remain. Evidence: `quality/TASK-1244_GENERATED_EOL.json`.

Focused correction group: 90 PASS, two pre-existing wiring-fixture failures
(`baseline_floor` / `beats_baseline` missing from a SimpleNamespace). Both were
reproduced using the unchanged HEAD child code in an isolated fresh test process;
the fixture file was not modified and the tests were not skipped or weakened.
Together with the unchanged prior groups this is 126 distinct Python PASS,
including two PostgreSQL tests, plus 62 UI and two client tests. Two baseline
fixture failures remain outside scope. Tiny real training/export policy cases
PASS again (60.64 s supervised, 58.49 s legacy).

### Final acceptance and residual risks

Round 2 PASS, 0 open P0/P1; all original findings closed. Report/receipt:
`quality/TASK-1244_AUDIT_claude-opus-5-5.*`, report SHA
`43c3e49cc12c323b8099c5fe99269fa02aa87dda035cd9229dd9a1645d52bff4`,
payload SHA `ecdecdc375744f64f70871e9c488b59fa7898b018383aadb12e4a77235ce7cd8`.
Observed CLI model claude-opus-5-5; high effort is requested-only evidence.
Accept two residual P2 findings without another review loop:

- P2-7: the two unchanged wiring fixtures lack baseline result fields. They fail
  identically on HEAD; follow-up fixture maintenance is separate, not a suppressed
  regression. All 90 other correction-group cases passed.
- P2-8: an internally generated, SHA-consistent but inconsistent supervision spec
  can fail before result publication and display GRID_TRAINING_CHILD_EXITED. The
  handler generates a consistent spec; failure stays visible and cannot activate
  a candidate. More specific diagnostics are a separate improvement.

Final unique coverage: 126 Python PASS (including two PostgreSQL), 62 UI PASS,
two client request PASS; two known pre-existing fixture failures remain. Changed
code passes lint/format and the documented scoped type checks. OpenAPI/client
drift and documentation/maps checks pass. Acceptance criteria and Definition of
Done are covered; no new migration, data deletion or model activation occurred.

The original parent and evaluation completed with PASS (4/4), confirmed at
16:14:26 UTC. Actual optimization was 2400 steps, selected weights from 1200.
VALIDATION: correct boards 52/60 -> 52/60, normalized error
0.0187900864 -> 0.0186210056, cell-cut-safe boards 40 -> 41. REGRESSION: 17/21 ->
17/21, normalized error 0.0132143222 -> 0.0127910717. This comparison is against
the pinned base 01767a49, not the assigned abe39bce model. Candidate remains
inactive; default revision 5 and assignment revision 6 are unchanged.
Immutable operational proof:
`D:/game_predicotr/.runtime/grid-partial-learning-final-20261117T161807227714Z.json`
(SHA `b4391cd9cb48cd9515145d1410c3abfd12c52349a105d9a43f2c1d81a1f57f69`),
compact receipt `D:/game_predicotr/.runtime/task1244-supervision-final.json`.

Ready for explicit result/merge/deployment approval. The 45 root user changes
are preserved. No active training handoff is needed: the target run completed
before the new policy was ready, so no budget grant or extra training is applied.
Deployment may restart idle API/general/grid-training workers only with explicit
approval; keep image-selection and completed job identities unchanged. Activation
and a fresh comparison with the assigned model remain separate decisions.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1244 | gpt-6.1-sol | high | Scoped durable budget, watchdog and replay changes; escalate on input/checkpoint ambiguity. | claude-opus-5-5, high, read-only CLI; model observed, effort requested-only. |
