---
title: Mumie — generation 3 implementation and missing-source stop
status: blocked
last_updated: 2026-10-06
---

# TASK-0861 evidence

Generation 3 is implemented and tested, but the real pair is not trained.
During the RGB worker's initial checkpoint validation, the complete source
folder disappeared. The qualified manifest now fails its source-integrity
gate. No validation accuracy, diagnostic score or new candidate is available.

## Implemented behavior

Models `mumie-symbol-rgb-v3` and `mumie-symbol-gray-v3` reuse the existing CNN,
RGB64/gray3 preprocessing and deterministic appearance augmentation. The
registry requires generation 3 and a D-502 classifier feedback cohort together.
Generations 1 and 2 keep their previous behavior and resume tests.

The weighted replacement sampler gives each of the 18 corrected crops weight
4 and the remaining 246 development crops weight 1. It draws 318 samples per
epoch while evaluation counts only 264 unique crops. Its generator is the same
checkpointed generator used by the loader. Exact interrupted/resumed CPU runs
match uninterrupted histories, weights, RNG, optimizer progression and best
epoch for all three generations.

The final report separately records training feedback regression and nine
diagnostic labels after epoch selection. Diagnostic fusion applies fixed
validation temperatures and fusion weight. It cannot fit held-out labels.
The artifact-only evaluation script compares every validation class with V1
and keeps the original 84 sample IDs/labels, old models and reports intact.

## Real attempt and blocker

Artifact root:
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-symbol-feedback-20261005`.
Run ID: `8da05da671d645dd9688c217ef094ce9`, RGB, attempt 1, PID 41612.
It failed before the initial checkpoint and before any optimizer step:
checkpoint_epoch=0, reserved_steps=0, used_seconds=31.5494.
The controlled worker exited; a subsequent process lookup found no owner PID.
The gray variant has not been admitted. No extra or random training was started.

Missing input:
`C:\Users\tuszy\Documents\mumie wybrane\481537- 500000 cut`.
The directory had passed real prepare/freeze/verify/retry earlier in this turn.
A fresh verify now fails on the missing directory. No file removal or move was
performed by this task, and the origin of the filesystem change is unknown.

The existing `481537- 500000` folder contains the same 2,052 names, but all
2,052 byte hashes differ from the frozen source inventory. It cannot replace
the reviewed images. `source-location-proof.json` records the comparison.
Exact labels/history and all 18 PNG rasters remain intact in pack
`c1392fb1954543a2d7b2aeb9c6fb9f5ccd093a1d20b7262a389fcf9c473f8b60`.
No relabeling is needed. Restoring the exact sources or locating their exact
copies is required before the integrity gate can pass and this run can resume.

## Verification and review

The full changed qualification/training/augmentation suites pass 43 pytest
tests, including frozen diagnostic calibration and all three exact resumes.
Ruff lint/format checks pass. Scoped mypy checks pass for the changed modules;
Torch/ONNX dependency analysis is explicitly excluded. For the Torch dataset
boundary, subclassing-Any and unused external-call ignore diagnostics are
excluded, while remaining strict checks stay enabled. This is not a claim
that all Torch library internals were typechecked.

The negative real-input check reproduces the failure in a new process. The
failed attempt, raw decisions, immutable pack and qualified manifest are
preserved. No database changes, model activation, merge/push or deployment.

Separate review found no unresolved implementation P0–P2. Definition of Done
and the plan remain incomplete: actual RGB/gray training, ONNX parity, real
per-class evaluation and conditional diagnostic inference await valid source
files. After restoration, run a fresh integrity verification, resume the same
RGB run (do not admit another RGB run), then execute the single gray run and
the frozen evaluation. Do not report the code checkpoint as task completion.
