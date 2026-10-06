---
title: Frozen Mumie models against eight new first-film human references
status: done
last_updated: 2026-10-06
---

# Exact human evidence

Artifact root:
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-first-human-check-20261006`.
Immutable proof:
`9d02a5d0b8f4ecb039e586f2aadc1f72ceee151cc3012445a4c4aec3903c5833`.

The operator approved all eight priority cases, revision8. Existing
symbol_feedback.prepare/verify_pack retains full original decisions, history,
receipts, dictionary and source-bound PNGs. Every exact quad is re-rendered.
These are operator-origin references, trainable=false, with no fabricated
labels, geometry approvals or Super targets.

The priority reference has distinct case IDs because its presentation category
differs from the original60 reference. The evaluator joins uniquely through
complete source metadata, board, field, quad, PNG byte SHA and decoded pixel SHA.
Every other case field must be identical. Current human case_id and immutable
previous_case_id are both preserved; presentation identity never replaces
raster identity. A changed quad cannot join an otherwise identical case.

All eight are outside both V4 development312 and R2 development327 by exact
source and raster identity. The entire first film remains outside symbol
development. Existing whole-film/alias exclusion evidence is pinned. Geometry
was partly trained on this film, so this is not a blind geometry benchmark.

# Actual frozen-model results

Six actual CPU ONNX exports were verified and run with their frozen RGB/gray
preprocessing and original validation-only temperatures/fusion settings.
All three generations reproduce their previous class proposals and confidence
within1e-6 on these exact rasters. No epoch/model/temperature/probability threshold
was selected or refitted using the eight new labels.

| Human group | Count | V3 RGB / gray / fusion | V4 RGB / gray / fusion | R2 RGB / gray / fusion |
|---|---|---|---|---|
| Previous control50 subset | 3 | 3/3 / 3/3 / 3/3 | 3/3 / 3/3 / 3/3 | 3/3 / 3/3 / 3/3 |
| Previous directed10 subset | 5 | 5/5 / 2/5 / 2/5 | 5/5 / 3/5 / 5/5 | 5/5 / 3/5 / 4/5 |
| All eight | 8 | 8/8 / 5/8 / 5/8 | 8/8 / 6/8 / 8/8 | 8/8 / 6/8 / 7/8 |

Every new R2 RGB versus V4 RGB per-class/group gate passes. V4 and R2 gray miss
two operator references in this group; R2 fusion has one additional error compared
with V4. Per-class confusion matrices and exact error IDs are in the proof.

The earlier separate human26 evaluation had V4 RGB25/26 and R2 RGB26/26.
Together R2 RGB is34/34 on the two specified later human sets. This is a count
on selected references, not measured accuracy of a whole folder or population.

# AI separation and preservation

Seven previously unresolved AI cases now have human truth; the remaining case
already had accepted AI consensus. There are zero conflicts between accepted
AI consensus and the new human references. The other52 cases remain AI-only.
The immutable AI60 report is preserved; neither it nor any human store is
rewritten to hide the original provenance.

V4 remains the qualified pair. The rejected R2 combined human gate remains
false. A possible RGB-only diagnostic under TASK-0870 has separate explicit
eligibility and cannot alter those facts or create a new pair.

# Verification

9349 source/model/history/input/output pins, the earlier human26 approvals and
both previous61-output sets are checked before and after inference.
Focused feedback and batch-label tests:43 passed (one dependency deprecation
warning). Two local helpers pass Ruff, formatting and scoped strict mypy.

Initial actual inference completed in75.09seconds. Fresh-process actual
inference completed in81.67seconds and reused byte-identical proof/pointer.
Exact source replay completed in11.86seconds, covering all8 rasters and five
isolated guards: modified history/source/PNG/quad and per-class regression
despite an improved aggregate score. Pinned-set digest:
`d715e61b4c6740399d15c5b618d44cf2def622bfe17f1776e4d9cf80a2da9d51`.

Repeated fresh source replay11.38seconds reused identical proof bytes.
Independent final audit PASS, no open P0–P2: the auditor checked all9349 pins,
decoded whole-photo isolation, eight source renders, six actual ONNX outputs,
per-class matrices and preservation. No new training, refit, application/API/schema
change, database write, migration, deletion, activation, merge, push or deployment.
The operator need not repeat these eight labels or supply another film.
All six task criteria and accepted plan0869 steps1–4 are covered.
