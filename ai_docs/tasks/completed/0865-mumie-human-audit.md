# TASK-0865 — Human-referenced audit of frozen Mumie models

## Status

done

## Goal

Replace the AI-only audit statistic with an exact human-referenced comparison
of the frozen V3/V4 pair on22 preselected withheld crops and4 separate diagnostics.

## Context

The operator completed the requested26-case packet. Current store revision27
contains26 latest approvals and one superseded decision. This resumes the
explicitly authorized autonomous Mumie work at its completed human boundary.

## Dependencies / entry conditions

TASK-0864 committed asv1.7.212/e6ed2d7211ceb396e208993840b568070f6b1d57.
No new training or production activation was performed. Exact source-bound
V3 batch, V4 ONNX/report/evaluation and pretraining withheld assignments exist.

## Recommended execution

gpt-6.1-sol, high. Independent data/result audit usesgpt-6.1-sol, high under the
existing explicit internal-AI authorization. Stop on unresolved source/history
drift or P0–P2 findings; never rewrite operator decisions to match AI.

## Relevant docs

- AGENTS.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/DECISION_LOG.md (D-502 through D-505)
- ai_docs/requirements/VISION_LAB.md (exact feedback and isolated experiment)
- ai_docs/architecture/VISION_LAB.md (exact feedback/experimental adapter)
- ai_docs/delivery/MUMIE_HUMAN_AUDIT_20261006.md
- ai_docs/quality/MUMIE_AI_OVERNIGHT_20261006.md
- ai_docs/tasks/completed/0864-mumie-ai-assisted-experiment.md

## Scope

Immutable latest human pack; qualification against frozen model/sample bindings;
actual ONNX inference and human accuracy per class, separate22/4 groups;
input preservation/replay, independent audit and documented next boundary.

## Out of scope

Training/calibration/threshold changes, human writes, new API/UI/schema,
Super targets, whole-grid approvals, database mutation, activation/deployment.

## Acceptance criteria

- [x] All26 latest approvals and27 history records qualified with exact rasters.
- [x]22 audit IDs/photo isolation and4 diagnostic IDs explicitly proven.
- [x] Existing actual ONNX/preprocessing/calibration retained; source results agree.
- [x] RGB/gray/fusion human counts/perclass/errors and AI conflicts reported.
- [x] No target from26 entered training; same-recording/selection limits explicit.
- [x] Fresh process retry reproduces report and inputs remain unchanged.
- [x] Focused verification, independent audit, DoD, Outcome/state and own commit.

## Technical notes

Reuse symbol_feedback.prepare/verify_pack and BatchReviewStore for current
receipts/history/live checks; raw decisions remain trainable=false. Frozen
SymbolAiExperimentAdapter verifies the existing cohort. Existing
symbol_batch.preprocess/classify_logits and run_files.verify_artifact apply
actual ONNX on approved PNGs. No recalibration or new CNN selection.
Compute aggregate and perclass metrics from actual named predictions.
Validate exact source/cell/quad/pixel bindings against V3 and experimental
same-cells results. New output is create-only and checksum-bound; input drift
blocks replay rather than creating silently different evidence.

## Expected files

- Proposed: artifacts/mumie-human-audit-20261006 local evaluation/evidence.
- Proposed: ai_docs/quality/MUMIE_HUMAN_AUDIT_20261006.md.
- This task, accepted audit plan and CURRENT_STATE.md.
- Existing runtime/source code is reused; no source change is expected.

## Test cases

Current versus superseded decision; wrong case/pixel/quad; unexpected cohort
membership/photo leakage; frozen model artifact drift; identical new-process
retry and unchanged human state/run/models; same-film limitation.

## Verification

Use the existing absolute120s run_step.py with worktree PYTHONPATH and main
.venv Python. Focused existing feedback/models tests before execution; report
and immutable pack qualification in separate processes. Validate failure on
altered binding without editing actual data. No load benchmark or synthetic
large fixture is needed.

## Risks / open questions

No blocking operator question.22 samples are chosen from the same film as
development, even though their photos/rasters are withheld. Human judgments
may still be ambiguous; report actual conflicts rather than correcting them.

## Outcome

### Changed

Published an immutable latest-human pack for26 approvals/revision27, keeping
the one superseded decision only as history. Reused existing current guard,
exact raster and receipt qualification; raw trainable=false flags and human
stores remain unchanged. Created a separate actual-ONNX comparison against
primary human labels, with frozen preprocessing/calibration and22/4 separation.
No application source/API/UI/schema or runtime configuration changed.

### Verification results

- Human22 withheld: V3 RGB19/22, gray18/22, fusion18/22; V4 RGB21/22,
  gray22/22, fusion22/22. All10 classes present (1–5 examples each).
- Diagnostic4: V3 RGB4/4, gray0/4, fusion2/4; V4 all4/4. None of26 exact
  rasters or full-photo SHA belongs to development312. No AI/human conflict.
- One RGB error A→Faraon remains, corrected by frozen gray/fusion. Target
  accuracy is human-referenced but not representative independent-film accuracy.
- Actual ONNX classes agree with prior source-bound results and confidence
  within1e-6; no refit or calibration/threshold/epoch selection on new labels.
- Qualified evaluation40.22s, fresh-process full replay43.61s, same immutable
  digest7d3c0e286aac61b60107acf19bdc373f4c45149e73d0d6d00f689b6cdf7b38d9.
-5771 original pins match, including original61 V4 output hashes from the old
  snapshot/replay digest, latest history/source/crop/model/report/run metadata.
- Four negative checks pass without edits: pixel drift, receipt mismatch,
  reference-quad drift and model SHA mismatch. Primary label/count checks pass.
-46 feedback/training pytest pass; standalone helper Ruff lint/format and
  scoped strict mypy pass for2 files. All commands use absolute120s runner.
  Statuses persisted in artifacts/grid-v3-deployment-20261004/human-audit-*.
- Independent audit re-rendered26 crops and recomputed actual ONNX/metrics,
  isolation and5771/61 SHA. No unresolved P0–P2. All7 acceptance criteria,
  accepted plan1–5 and applicable DoD points fulfilled.

### Not completed

No new training, calibration, human edits, whole-grid approval, Super targets,
DB mutation/migration/deletion, activation, merge/push or deployment. No build/
OpenAPI/full unrelated suite is applicable. No computer reboot was performed.

### Documentation updates

Accepted MUMIE_HUMAN_AUDIT_20261006.md, matching quality report and CURRENT_STATE.
Evidence under C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-human-audit-20261006;
final pointer qualified-evaluation.json, immutable evaluations, human-packs/replay.
Human pack9c7f47afa151aad0fa29cfc2dee3e15df588c2b086217dfba08a6d0c59cd7053.
Preliminary evidence remains create-only; final pointer includes the original
output preservation pins. Commit `v1.7.213`, after verified HEADv1.7.212.
Prior unrelated metadata edits are preserved and excluded.

### Recommended next task

Larger human-referenced transfer check on an existing recording excluded from
V4 training, after full source-location qualification. Keep current26 for frozen
assessment; avoid training them then reporting unchanged unseen accuracy.
No repeated annotation of this packet or additional folder is required now.
