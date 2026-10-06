---
title: Mumie — human-referenced audit of frozen V3 and V4
status: done
last_updated: 2026-10-06
---

# TASK-0865 evidence

The operator completed all26 cases requested at the TASK-0864 boundary. Current
revision27 contains26 latest approvals and one superseded decision. The existing
BatchReviewStore and symbol_feedback prepare/verify_pack qualified the complete
decision/receipt/history chain, dictionary, exact source/quad/PNG/pixel bindings
and current live guards. No agent edited an operator decision or approved geometry.

The26 labels were assigned after the frozen V4 training. None of their exact
rasters entered the312-example development set. Twenty-two cases were explicitly
withheld before training. Their full photos are disjoint from development;
the four previously uncertain cases also happen to have no training-photo overlap,
but remain a separate diagnostic group because selection was different.
No training, epoch selection, calibration or threshold adjustment used these labels.

## Actual inference and human accuracy

All four actual V3/V4 ONNX artifacts were checksum-verified. Existing RGB64/gray3
preprocessing and each pair's original human84-selected temperatures/fusion
weight/0.9 threshold were applied to the exact26 approved PNGs. Every predicted
class matched its previously published source-bound result, and confidence
matched within1e-6. No additional model run was admitted.

| Human group / branch | Qualified V3 | Experimental V4 |
|---|---:|---:|
| Withheld22 RGB | 19/22 | 21/22 |
| Withheld22 gray | 18/22 | 22/22 |
| Withheld22 frozen fusion | 18/22 | 22/22 |
| Diagnostic4 RGB | 4/4 | 4/4 |
| Diagnostic4 gray | 0/4 | 4/4 |
| Diagnostic4 frozen fusion | 2/4 | 4/4 |

The previous22/22 AI agreement is now22/22 against actual operator references
for gray/fusion. All22 human references agree with the independently retained
AI class assessments. This does not turn AI training targets into human approvals.
The single remaining RGB error is A predicted as Faraon, case
`d904ee9fa8637883be09c02ae7bdc452c619beae3f783651bee0836dd7064adb`.
Gray and frozen fusion identify A correctly. No operator change is required.

| Withheld human class | Samples | Correct V4 fusion |
|---|---:|---:|
| 10 | 3 | 3 |
| J | 2 | 2 |
| Q | 2 | 2 |
| K | 2 | 2 |
| A | 5 | 5 |
| Ra | 1 | 1 |
| Sarkofag | 2 | 2 |
| Mumia | 2 | 2 |
| Faraon | 1 | 1 |
| Sfinks | 2 | 2 |

All10 classes are represented, with only1–5 examples per class. These are targeted
photo-held examples from the same third recording as part of development,
not an independent-film or randomly sampled population benchmark. The operator
saw prior V3 suggestions in the editor; annotation was not blinded. Confidence
flags and accuracy of all8100 unlabelled cells remain separate: previous424→454
uncertain cells and37→22 disagreements do not establish full-film correctness.
The reused validation83/84 and limited diagnostic9/9 are unchanged; no new
qualification or production activation is implied by the small perfect audit.

## Preservation, replay and checks

The qualified result pins5771 existing input files, including current human
state/reference/history, exact26 PNGs, complete third-film sources, old cohorts,
actual model/report/run artifacts and the original61 V4 outputs. Those61 hashes
are taken from TASK-0864's original outputs-before-replay snapshot and checked
against its replay output-set digest, not re-frozen from current bytes.
All pins match before and after inference. Human stores and earlier model results
remain untouched.

A fresh process repeated complete pack qualification and actual26-crop inference,
publishing the identical report digest:
`7d3c0e286aac61b60107acf19bdc373f4c45149e73d0d6d00f689b6cdf7b38d9`.
The first qualified evaluation took40.22s and replay43.61s, each with an explicit
120s limit. Create-only output did not duplicate or replace human/model data.
A further fresh process recomputed human reference/metric bindings and5771 hashes.
Four negative checks pass without editing actual data: pixel checksum drift,
decision/receipt mismatch, changed reference quad and wrong model artifact SHA.
No computer reboot was performed; persistence was tested through fresh processes.

Forty-six focused existing feedback/training tests passed. Both standalone
evaluation/verification helpers pass Ruff lint/format and scoped strict mypy
with explicit untyped Torch/ONNX boundaries. No application module/API/UI/schema
changed, so OpenAPI regeneration, frontend build, full unrelated suite and DB
migration were not applicable. Import ordering and the explicit two-logit call
were corrected before final checks; no test or quality gate was weakened.
Independent final audit passes with no unresolved P0–P2. It re-rendered all26
source/quad rasters, checked primary27-record history and class UUID/name binding,
proved absent raster/photo overlap, recomputed all four actual ONNX outputs and
perclass counts, and verified5771 pins, original61 outputs and replay. All7
acceptance criteria, plan steps1–5 and applicable Definition of Done points pass.

## Evidence and next step

Absolute evidence root:
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-human-audit-20261006`.
Use `qualified-evaluation.json`, evaluations, human-packs and replay.json.
An earlier preliminary evaluation is retained create-only; the qualified pointer
above adds the original61-output preservation pins and is the final result.
Human pack:
`9c7f47afa151aad0fa29cfc2dee3e15df588c2b086217dfba08a6d0c59cd7053`.
No runtime switch/restart was necessary. The existing editor retains all26
completed decisions. No repeat annotation of this packet is needed.

Keep these labels as assessment of the frozen candidate; do not immediately
train them away and continue reporting the same score as unseen accuracy.
The next useful stage is a larger human-referenced transfer check on a recording
excluded from V4 training, with exact source-location qualification and a
separate frozen review packet. Existing recordings must be checked before asking
for another folder. Rare-class examples and separately approved Super frame
labels remain distinct needs. This task supplies the actual human result and
stops at its documented evaluation boundary.

Work stays on feat/grid-engine-v3 in the requested worktree. No new training,
calibration, human edits, geometry approvals, Super labels, DB writes/migrations/
deletion, activation, merge/push or deployment occurred. Pre-existing unrelated
metadata edits are excluded from this task's separate commit v1.7.213.
