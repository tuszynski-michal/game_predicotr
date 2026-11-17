---
title: Use partial grid corrections and compare historical models fairly
status: done
last_updated: 2026-11-17
---

# TASK-1240 — Partial grid corrections and historical model comparison

## Status

`done`

## Goal

Ensure the operator's valid partial corrections reach the existing grid-training
path and compare candidate 0b37cba4 with historical alternatives on identical photos.

## Context

Operator approved implementation, tests, Claude audit and existing-model CPU
comparison after the 1–3 hour implementation / 30–90 minute measurement warning.
New GPU training and model activation are explicitly outside that approval.
The c489f65f screen+grid run completed using only 10 full TRAIN photos/90 boards;
the frozen photo split has 428 TRAIN assignments. The operator script in the live
checkout hardcodes screen+grid. Existing ready recommendation preserves partial
corrections by choosing grid-only; a new mixed-head policy is unnecessary here.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/CROSS_AUDIT.md`
- `ai_docs/delivery/GRID_LEARNING_EFFICIENCY_AND_DATA_PLAN_20261116.md` (P5 context only)
- D-602, D-612 and D-613 in `ai_docs/process/decisions/DECISION_LOG_2026.md`
- `ai_docs/tasks/1230-grid-learning-background-preparation.md` (live untracked history only)

## Scope

- Trace the frozen data funnel and record distinct counts/reasons for omissions.
- Adopt the existing operator starter as a tracked, tested command: default to
  grid-only, require an explicit screen+grid selection, refuse a saved-mode
  mismatch before POST, preserve exact saved keys and requests on replay.
- Preserve source ownership, human-only labels, partial target masks and protected
  TRAIN/VALIDATION/REGRESSION roles; no false detector background labels.
- Read-only CPU comparison of already exported models using identical frozen
  photos, target matching and preprocessing. Define historical selection explicitly;
  never call an incomparable historical score the best score on the current set.
- Targeted tests and quality checks, independent Claude review before commit.

## Out of scope

New training, activation, changing frozen cohorts/labels, loosening quality gates,
new mixed-head recipes, unrelated local feature changes, service restarts, deployment.
Merge/push remain subject to acceptance of the finished result for this task.

## Acceptance criteria

- [x] Exact frozen counts explain the 10-photo result and unused valid corrections.
- [x] Fresh default commands select grid-only; explicit detector mode still works.
- [x] Old saved commands are not rewritten; mismatched options fail without a POST.
- [x] Corrected/partial targets remain usable in the existing grid-only consumer;
  unlabelled boards are never negative detector supervision or test leakage.
- [x] Candidate and historical models have checksum-bound comparable evidence on
  the same frozen control photos; selection and evidence limits are disclosed.
- [x] Targeted tests/lint/types/docs/maps and Claude audit pass.

## Technical notes

Worktree starts at main 2b4537e5; protect all pre-existing live checkout changes.
The live starter is the baseline source for the new tracked script; copy it before
editing, preserve its existing replay behavior, and retain the root copy unchanged
until a separately approved integration. Use a new explicit command file to create
a future run; this task never invokes a real training POST.

Freeze comparison identities before inference. Prefer historical reports for
shortlisting and VALIDATION A for any ranking; REGRESSION is confirmation, not
training or parameter tuning. Reuse existing assessment engines/matching rules.
Saved production cohorts and models are read-only. Comparison artifacts go into
this worktree, with an input manifest and checksums, and will be retained.

## Expected files

- Existing live `scripts/Start-GridCorrectionLearning.ps1` (currently untracked): adopt and fix.
- New focused starter regression tests and a read-only comparison/diagnostic tool.
- Relevant operator documentation, generated code maps and this task/current state.

## Verification

Use PowerShell fake-API tests to verify payload/replay without real jobs; existing
dataset tests for labelled partial targets and source-role isolation; scoped Python
quality and documentation checks. CPU comparison uses only existing real photos.

## Outcome

Commit: v1.7.663 / `049c485507bb0d89e347ddcf9d903da3191d3a59`.

Implementation and measurements complete. Claude focused round 2 PASS, 0 P0/P1.

### Changed

- Adopted the live starter without changing that original file: grid-only default,
  explicit detector mode, immutable saved-command replay, mode/key checks before
  POST, separate future command/status files. Unsupported background API fails
  before POST based on the server OpenAPI contract. No backend/API change.
- Read-only selection benchmark and historical comparison tool reuse the existing
  data adapters, assessment engines and metric definitions. No training or model
  mutation. Input and result artifacts have SHA receipts; code used by the actual
  comparison was frozen before later type/counter-name corrections.
- Requirements/architecture and human/machine-readable quality reports updated.

### Verification results

- 12 new focused regressions PASS (8.51 s), including real PowerShell with fake
  API, explicit/default mode, byte-identical replay, mismatch/no POST, separate
  command files, API contract check, historical ranking without REG input and
  bounded exact inference cache, cross-game command rejection and source-bound
  funnel receipts. The final correction round reran these tests.
- Existing dataset regressions: 7 PASS (1.53 s). Existing preview/recommendation
  regressions: 5 PASS (4.26 s). Partial/deformed target nodes and weights preserved;
  partial sources remain forbidden as full detector supervision. Total 24 tests.
- Strict scoped mypy (silent imports) PASS, two source files. Scoped ruff/format PASS.
- Actual database READ ONLY grid-only preview: canStart true, no blockers,
  TRAIN 503 photos / 647 boards, including 493 partial TRAIN photos; VALIDATION
  19/60, REGRESSION 13/21. Qualified total 561/758. Old screen snapshot: 10/90.
- All nine exported models measured on identical frozen VALIDATION photos. Best
  older from A only: 9992a316. It and candidate 0b37cba4 have 45/45 VALIDATION and
  21/21 REG correct boards. Candidate has slightly lower mean geometry error;
  boards within cells are 42 vs 43 on A and 18 vs 17 on REG, same total 60.
  Immediate base 01767a49 exactly reproduces the old report (44/45 and 17/21).
- Details/limits: `ai_docs/quality/PARTIAL_GRID_CORRECTIONS_COMPARISON_20261117.md`
  and `TASK-1240_COMPARISON_EVIDENCE.json`. Raw data/receipts remain in this
  worktree artifacts and must be retained before approved cleanup.

### Not completed

- Integration result acceptance and authorized deployment remain pending.
- Acceptance/merge/push/deployment are not assumed from cost approval. The live
  starter remains unchanged until separately approved integration.
- New GPU training, model activation and the separate Task-1230 feature integration
  are outside scope. Background API capability is an explicit starter prerequisite;
  the current live checkout has it, a base-only installation fails closed.

### Independent review and administrative renumbering

Main concurrently assigned TASK-1239 to board-search refinements. This isolated
task was renumbered to TASK-1240 and fast-forwarded to main 68ac66e7 before commit.
No inference rerun or model changes. The original round-1 report/receipt remain
byte-identical under `TASK-1240_AUDIT_ROUND1_AS_TASK1239_claude-opus-5-5.*`.
Their original task identity is TASK-1239, payload SHA
19d5ea523555bb732980a656d6182da94678f854fdae7f92ba7234615d2d61ef;
report SHA 60405dea125eebce3de18361c10fac68bcdd69fb737c55e3876b9f658218ecf9.
REVISE: 0 P0, 1 P1, 3 P2. One correction round:

- P1-1: exact TRAIN partition now proves 428 = 49 aliases + 367 partial + 2 empty
  pending corrections + 10 full; both reconciliation flags true. Detailed per-label
  rejection reasons are not stored in the manifest, explicitly recorded rather
  than inferred. Buffer flags are a separate non-additive population count.
- P2-1: sidecar binds game, key and raw-command SHA before network access; immutable
  create-new files and disk flush precede POST. Old named default files keep replay
  compatibility; an unbound existing custom file fails closed. Tests cover a second
  game and an orphaned custom file, without real requests.
- P2-2: `data-funnel-v3.json` has a new receipt, SHA of the producing source and
  its frozen source copy; v1/v2 evidence is retained. Machine summary pins v3.
- P2-3 accepted limitation: scripts/tests is not collected by the general quality
  command. Run these Windows regressions explicitly:
  `.\.venv\Scripts\python.exe -m pytest scripts/tests/test_partial_grid_learning_starter.py scripts/tests/test_grid_historical_comparison.py`.
  This command is required for subsequent starter/comparison changes; no expansion
  of the global test suite is hidden in this task.

Focused round 2 reviewed these corrections as TASK-1240, referencing the
preserved former-identifier report. PASS, 0 open P0/P1; original four findings
closed. Report/receipt: `TASK-1240_AUDIT_claude-opus-5-5.*`, payload SHA
b1b8342f334bdb4c6bb41225688383f8a144779be09c76a9dfcc952284387116,
report SHA e4d77dc7e4176e086329d5877cac840ec23f6c975ea8893f8a963eb79ebaed2b.

Accepted residual P2-4/P2-5: use an absolute -CommandFile path, because .NET's
relative base may differ from PowerShell $PWD. An interruption between creation
of a custom command and its sidecar fails closed on replay; preserve the command
and recover its metadata, never silently reset the key. No POST occurs in that
window. These risks do not affect the stable default path or successful/lost-
response replay after both files were durably written. No further audit loop.
