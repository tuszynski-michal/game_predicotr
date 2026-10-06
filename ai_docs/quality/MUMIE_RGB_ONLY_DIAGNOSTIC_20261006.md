---
title: Separate same-crop Mumie RGB-only diagnostic
status: done
last_updated: 2026-10-06
---

# Scope and frozen eligibility

Artifact root:
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-rgb-only-diagnostic-20261006`.
Eligibility ID:
`5b6af3ef03d77ff7dbc3e7c2f45f0586f92d24088b5871316acc4aadf044ac7c`.

This is a separate RGB-only diagnostic. It does not replace the V4 qualified
pair or override the rejected R2 gray/fusion gates. No new pair, training,
calibration, model registry entry or production activation was created.

All nine frozen R2 RGB versus V4 RGB group/per-class gates pass:
human84, old18, new19, diagnostic9, withheld22, diagnostic4, new control3,
directed5 and combined8. All ten class sample/correct counts are compared,
including absent classes. A better aggregate cannot hide a class regression.
Training-feedback groups and reused validation are not independent test data.

9352 original pins are checked. Eligibility descriptors and temperatures are
semantically rebound to the pinned human8 proof and V4/R2 pair proofs on every
new process. Exactly two actual RGB exports are allowed: V4 RGB and R2 RGB.
Class order, nine metric tables, calibration, model/source/history SHA and
pair status are validated. No gray or fusion inference occurs in this diagnostic.

Decoded whole-photo exclusions cover both actual development312/327 sets.
The independent auditor recomputed their RGB EXIF signatures and checked all
60 first-film photos outside them. First-film data remains outside symbol
development; geometry was previously partly trained on this recording.

# Actual same-crop comparison

Three finite portions of 20 photos completed in 26.20, 20.44 and 24.16 seconds.
Each uses the original source, board/field ordering and lattice quads. Every
RGB96 crop is re-rendered and its decoded pixel SHA compared before inference.
Actual frozen V4 RGB classes reproduce the original V4 proposals.
Outputs live only under the new create-only `rgb-only-diagnostic` sidecar.
Raw logits, probabilities, class/confidence and exact source/raster bindings
are retained for replay. No geometry, old result, atlas or human label is changed.

| Measurement | V4 RGB | R2 RGB |
|---|---|---|
| Source photos | 60 | 60 |
| Exact symbol crops | 8100 | 8100 |
| Class changes relative to V4 RGB | — | 33 |
| Confidence below the original 0.9 threshold | 704 | 490 |
| Whole-recording accuracy | Not measured | Not measured |

There are 214 fewer low-confidence cases on the same 8100 rasters. This is a
change in confidence flags, not proof of improved correctness. The 33 changed
classes are not automatically accepted as labels. The eight new human targets
remain correct for both RGB generations; R2 additionally corrected one earlier
human26 error, giving 34/34 on the two specified later human reference sets.
The 34 examples selected for uncertainty do not estimate population accuracy.

# Durable resume and guards

Existing outputs are read without rerunning inference, but must retain the exact
top-level envelope, experimental=true, accuracy=null, labels_written=0, every
source/quad/pixel binding, two model records and consistent finite logits/scores.
Additional metadata or changed origin/accuracy fields are rejected.
Model descriptors/temperatures and gate tables are linked to authoritative
immutable proofs, so replay cannot silently switch to a different pinned model.

Isolated negative checks cover an actual failed-gate comparison command with
no output writes, mutated envelope fields, changed model descriptor/temperature,
changed quad during resume and modified model/source/history bytes.
These checks alter only detached copies or in-memory data.

Independent audit has reproduced all 60 source photos / 8100 crops and both actual
RGB models, with maximum absolute logit difference 0. It independently confirmed
the 33 changes, 704/490 flags, all 9352 original pins, human8 revision 8 and earlier
human26 revision 27. Both previous 61-output sets are preserved. The original R2
paired sidecar remains absent, its two original run directories remain unchanged
and the combined failed-gate guard still rejects that pair.

Four local helpers pass Ruff, formatting and scoped strict mypy.
Focused inference tests: 17 passed. TASK-0869 separately passed 43 focused tests.
Own complete actual replay also covered all 60 photos / 8100 crops in bounded
portions of 26.38, 33.66 and 45.14 seconds. Its maximum absolute logit difference is 0.
Final replay checks 9474 pinned inputs/outputs, including all 60 per-photo replay
markers. Pinned-set digest:
`b3f13c7812eaea06fb2fdda627c32f4ba02063db2319b871c1702945cfeb6f1f`.
Seven negative-check groups passed. Fresh inference resume in 18.30 seconds validates
all 60 existing outputs and computes zero new photos. Final fresh replay resume
completed in 35.50 seconds with zero new replayed photos. All 60 existing markers,
9474 pins and the pinned-set digest reproduce exactly; replay bytes are identical.

Independent final audit: artifacts, sources, models, replay, fresh resume and
documentation PASS. Both earlier review findings were fixed and checked.
No open P0–P2 findings. All five task criteria and accepted plan 0870 steps 1–4
are covered.

# Limits and next use

This artifact is a diagnostic, with no application/API/UI/schema or database
change, migration/deletion, Super targets, model activation, merge/push/deployment.
The operator's new labels are preserved and need not be repeated.
V4 remains the qualified pair; R2 RGB remains a separately assessed experiment.
