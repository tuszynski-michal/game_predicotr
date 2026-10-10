---
title: Większa seria wycinków Mumii do niezależnej oceny AI
status: done
last_updated: 2026-10-06
---

# TASK-0871 — większy zbiór symboli Mumii

## Status

`done`

## Goal

Prepare and independently assess a larger deterministic exact-raster candidate
series without changing human labels, test partitions or active models.

## Context

The operator requested larger autonomous training and prioritised accuracy.
No new CNN started after TASK-0870. Existing generation4 runs both succeeded.
The 2000–3000 target is an aspiration, not a count of qualified examples.

## Dependencies / entry conditions

TASK-0870 done, HEAD v1.7.218. Preserve R2/V4/human26/human8 proofs and histories.
Existing third-film batch and quads. First film remains excluded from development.
No blocking recording-origin question; the three folders are distinct recordings.

## Recommended execution

gpt-6.1-sol, high. Two independent visual reviewers and one independent artifact
auditor: gpt-6.1-sol, high. Stop on input drift, protected-source overlap or a
P0–P2 finding after two correction cycles.

## Relevant docs

- AGENTS.md, ai_docs/README.md, ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md, ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/requirements/VISION_LAB.md (D-502–505)
- ai_docs/architecture/VISION_LAB.md (exact feedback and AI adapter)
- ai_docs/delivery/MUMIE_LARGE_TRAINING_EXECUTION_PLAN_20261006.md
- ai_docs/quality/MUMIE_AI_ROUND2_20261006.md
- ai_docs/quality/MUMIE_FIRST_HUMAN_CHECK_20261006.md
- ai_docs/quality/MUMIE_RGB_ONLY_DIAGNOSTIC_20261006.md

## Scope

Pin the existing third-film batch, human proofs, old AI development/audit and
source/photo groups. Select at most 2000 new unique exact rasters, cycling
proposed classes/photos with a cap of 80 per photo. Exclude all human-reviewed
rasters, prior AI rasters, withheld photos and whole human26/test photo groups.
Split into existing references of at most 100 cases using the existing prepare
function. Proposals determine sampling only and remain hidden from visual review.
Two actual visual reviews and high/high consensus retain AI origin and no Super
targets. Report exact progress and accepted class counts; no qualification shortcut.

## Out of scope

CNN launch, multi-reference training adapter, changed limits in old consumers,
API/UI/schema/DB, migration/deletion, human approvals, model activation or deployment.

## Acceptance criteria

- [x] Deterministic selection and explicit source/decoded-photo/pixel exclusions.
- [x] Existing references of at most 100 cases, exact crop hashes and dictionary.
- [x] Two visual reviews, conservative consensus and no invented human truth.
- [x] Fresh-process replay, drift checks, focused tests and independent audit.
- [x] Accurate counters, Outcome and CURRENT_STATE; separate commit recorded below.

## Expected files

Proposed local helpers and review artifacts under the new
C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-large-training-20261006.
Task, accepted plan, quality report and only this task's CURRENT_STATE block.
No application source changes in this task.

## Verification

Each finite command has at most 120 seconds; preparation advances one packet
per bounded step. Existing outputs are validated and reused after a restart.
Meaningful guards cover model/source/history/protected photo drift and duplicate
raster selection. Tests and reviews are planned until their actual results exist.

## Risks / open questions

No required operator interaction yet. Lack of per-class candidates or readable
consensus must be reported. Training data are not qualified by selection or a
reference alone. A target count cannot override visual evidence.

## Outcome

Preparation and qualification finished. Selected and rendered 2000 exact unique
crops from 41 photos in 20 references of 100. The controlled worker completed in
916.50 seconds and exited. Selection ID:
12645e8fdf7657c696035ddf77a750b7acfaf6e198a9265a16a1166789d769ff.
Both actual blind reviews assessed all 2000 rasters and completed fresh own-report
verification. High/high consensus accepts 1726 and rejects 274; Mumia has 109 cases.
Other
class counts are in MUMIE_LARGE_SYMBOL_CANDIDATES_20261006.md.

Qualification ID:
8a57f640f741be76259ec0cd5f7f8a384638754910b94fd004ca2807b40b8ac8.
File SHA:
c48ba7af2689aa972aa97cfd18082c5c034392a854113b9e7bfeeec0808c5b20.
All 11472 pins, human/test proofs and 526 forbidden pixels are preserved. No human
labels, Super targets, CNN, app/API/UI/schema/DB, activation, merge, push or
deployment changes.

Fresh selection took 47.06 s and packet0 replay 36.62 s. Aggregate took 13.39 s;
fresh replay reproduced the same ID, pointer and bytes in 14.86 s. All 12 focused
tests pass. Ruff/format pass for four helpers; mypy passes for three executable
helpers. Independent audit of the original 2000 renders, 40 reviews, 20 consensus
proofs, 11472 pins, protected photos and 14 detached negative
guards PASS. The independent final audit passes with no open P0–P2.
Commit version `v1.7.219` is prepared; its actual hash is recorded after committing.
DoD and the five acceptance criteria are checked against stage A of the accepted
plan; no count is presented as population accuracy. Continue to 0872 after commit.
