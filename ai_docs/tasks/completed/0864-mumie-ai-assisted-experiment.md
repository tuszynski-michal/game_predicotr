# TASK-0864 — AI review and isolated Mumie experiment

## Status

done

## Goal

Deliver a bounded experimentally trained pair using separately attributed AI
visual assessments, with unchanged human labels and measured regression gates.

## Context

The operator explicitly requested autonomous overnight training and internal AI
inspection on2026-10-06. This authorizes an experimental AI-origin cohort,
superseding the previous stage's stop at missing new human labels.

## Dependencies / entry conditions

Qualified V3 evaluation and completed60-photo third-recording batch exist.
The user already declared each genuinely new folder an independent film.
The operator subsequently completed24 decisions:19 approve and5 unreadable,
revision24. Consume its exact immutable pack without mutating the human store.
Human targets override AI, unreadable decisions exclude those exact rasters.

## Recommended execution

gpt-6.1-sol, high. Independent visual reviewers and implementation audit use
gpt-6.1-sol, high, under the user's explicit internal-AI request. Escalate
unresolved P0–P2 or data provenance conflicts; do not manufacture human labels.

## Relevant docs

- AGENTS.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/DECISION_LOG.md (D-502 through D-505)
- ai_docs/requirements/VISION_LAB.md
- ai_docs/architecture/VISION_LAB.md
- ai_docs/delivery/MUMIE_AI_OVERNIGHT_20261006.md
- ai_docs/quality/MUMIE_AI_OVERNIGHT_20261006.md
- ai_docs/tasks/completed/0863-mumie-third-recording-diagnostic.md

## Scope

Two blind AI assessments of up to100 source-bound exact crops; conservative
consensus; isolated local generation4 and one bounded RGB/gray pair; honest
human validation and AI agreement report; durable artifacts and replay.
After successful human gates, reclassify the existing8100 source-bound rasters
in bounded20-photo portions with unchanged geometry and accuracy=null.

## Out of scope

Human store writes, Super target training, geometry approvals, database writes,
activation, merge/push/deployment and paid external APIs.

## Acceptance criteria

- [x] Two recorded raster-bound reviews, class anchors, disagreements and exclusions.
- [x] Newhuman19 are qualified with current history;5 unreadable excluded.
- [x] Human stores, original manifests and frozen validation remain identical after this snapshot.
- [x] Consensus-only AI targets retain ai_visual_assessment origin and full provenance.
- [x] At least20 withheld examples/photo isolation before training; same-film limitation explicit.
- [x] One RGB/gray pair finishes or reports a concrete quality/runtime failure.
- [x] Human84/18/9, all-class regression and ONNX parity reported separately from AI agreement.
- [x] Fresh process verify/retry, focused tests, lint/typecheck, independent audit and own commit.
- [x] On passed gates, bounded same-crop8100 comparison/replay; otherwise explicit skip reason.

## Technical notes

Follow the accepted overnight plan in full. A new explicit adapter/format may
compose existing SymbolTrainingInputs; never forge SymbolLabelStore decisions.
Old generation and default adapter behavior stays strict. AI labels are
experimental development targets only. Existing human18 and newhuman19 retain sampling4;
AI targets use1. Withheld AI images are excluded from all draws and selection.

## Expected files

- Proposed: vision_lab/symbol_ai_experiment.py and focused tests.
- Existing: symbol_feedback.training_adapter, symbol_models.model_pair,
  symbol_runs.build_manager/CLI, symbol_training.train/training_loader.
- Relevant requirements/architecture/decision log, this task and CURRENT_STATE.

## Test cases

Origin/consensus mismatch; unknown/duplicate cases; exact render and source drift;
held photo leakage; old-format rejection; sampling replay; default generation
regressions and all original input SHA unchanged after real runs.

## Verification

Use the absolute existing120s runner, main .venv pytest/Ruff/mypy and bounded
vision-lab GPU workers. Run focused tests before lint/typecheck, then relevant
existing feedback/run regressions. Verify artifacts in a new process.

## Risks / open questions

AI consensus is fallible and same-model review is not statistically independent.
No blocking operator question remains within this authorized local experiment.

## Outcome

Implemented the explicit D-505 experimental adapter/format and generation4,
optional dispatch/model registry, photo-isolated audit, human-priority exact
feedback pack and sampling1/4 with durable RNG/optimizer/budget resume. Previous
adapters and generations retain strict default behavior. No HTTP/schema/UI change.

Both reviewers actually inspected79 exact crops and20 human class anchors.
All24 human-assessed rasters override AI;19 approvals are used with their original
history,5 unreadable cases excluded.29 high/high AI development targets and22
photo-disjoint same-film audit targets are separately attributed. The312 unique
development examples produce423 draws/epoch; no audit target enters sampling,
selection or calibration. No agent wrote human decisions.

Real runs5e6a8f93524b4c1bbbe1d28fce0eaf51/e95d860b154f46cca2325e97caae8224
finished attempt1,20epochs/280steps, best8/6,535.908s/604.668s. Workers exited.
RGB/gray/fusion83/84 reused validation,18/18 earlier corrections,19/19 new
training corrections and9/9 limited diagnostics. All per-class human gates pass
against actual V3;84-raster ONNX parity passes per branch, maxabs2.861e-6.
Before this training V3 scored15/4/10 of19 new human cases. AI22 agreement is
21/22 RGB,22/22 gray/fusion versus V3 19/18/18. These are AI agreement and
training-regression measurements, not independent human accuracy.

The passed human gates permitted3 bounded20-photo portions over identical
8100 crops/540 boards.39 class proposals changed. Low confidence424→454,
RGB/gray disagreements37→22, accuracy=null. No overall improvement or activation
is inferred. A new-process retry processed0 and reproduced61 byte-identical
outputs;5673 original input files remained unchanged. Pair evaluation also
reproduced the identical digest in a new process.

Verification: pytest experimental module16, training module17, existing feedback/
training-manifest/batch-input modules52:85 distinct tests passed. Ruff format/check
passes on7 files; scoped strict mypy passes on5 source modules.14 artifact-level
positive/negative checks pass, including pooled score concealing per-class loss,
geometry/count/order/crop/human-approval drift. Bounded120s command statuses are
persisted under artifacts/grid-v3-deployment-20261004 (ai-input-protection-final,
ai-experiment-focused3, ai-regressions, ai-lint-final, ai-format-final,
ai-library-types-final, overnight-pair-qualification/replay, overnight-same-cells
portions1–3/replay, overnight-replay-preservation). No frontend build/OpenAPI or
DB migration is applicable. No unrelated full suite/load benchmark was run.

Independent code/data audit closed two P2 helper findings by adding all three
human regression gates and full invariants for reused/summarized results.
Separate final same-cell output audit passes: all8100 real crops re-rendered
pixel-identically, geometry and ordering unchanged, actual counts and all5673/61
file hashes match. No unresolved P0–P2 remains. All9 acceptance criteria,
plan steps1–7 and applicable DoD points are fulfilled, with honest limitations.
API/schema/frontend/sequence/target changes are not part of this task.

Ready human boundary:26 pending crops (22 withheld plus4 uncertain), editor
http://127.0.0.1:3102/symbols/batch and portal
http://127.0.0.1:8108/overnight-symbol-review/review.html. Saved reference/labels,
runtime backup, controlled lab restart, read-only HTTP and fresh-process
ownership/readiness checks pass. Original24 decisions are unchanged. No new
folder or30-per-class selection is required now.

Evidence root: C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-ai-experiment-20261006.
Manifest aff9c65ac61fac6c1873d1eff44d0ac17f204476cd8cb6c65b3e1d9e05b02ad8;
pair proof1a7fa49bb2ea991e06d3037686c57f4c4a4d5a6d4710bd397677ddc08f4d7ffb.
Report: ai_docs/quality/MUMIE_AI_OVERNIGHT_20261006.md.

Commit: `v1.7.212`, based on verified HEADv1.7.211. Pre-existing
unrelated metadata edits are excluded. No DB writes/migrations/deletion,
Super targets, geometry approvals, activation, merge/push or production deployment.
