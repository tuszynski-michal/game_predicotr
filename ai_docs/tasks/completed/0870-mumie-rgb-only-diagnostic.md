---
title: Conditional same-crop Mumie RGB-only diagnostic
status: done
last_updated: 2026-10-06
---

# TASK-0870 — izolowana diagnostyka RGB Mumii

## Status

`done`

## Goal

Either replay eligible RGB-only inference on the existing 8100 exact crops,
or document a failed per-class gate without creating classifier outputs.

## Context

R2 gray/fusion remains rejected. RGB-only is a separate experimental diagnostic,
not a replacement pair, qualification override or production activation.

## Dependencies / entry conditions

TASK-0869 independently audited and committed; frozen new8 and old human reports.
Every R2 RGB versus V4 RGB comparison by class and group must not regress.

## Recommended execution

gpt-6.1-sol, high. Independent artifact/replay audit gpt-6.1-sol, high.
Any input drift or failed gate blocks inference; never relax eligibility.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/delivery/MUMIE_FIRST_HUMAN_CONTINUATION_20261006.md`
- `ai_docs/quality/MUMIE_FIRST_HUMAN_CHECK_20261006.md`
- `ai_docs/quality/MUMIE_AI_ROUND2_20261006.md`

## Scope

Freeze eligibility 84/18/19/9/22/4/new8 gates by class. If passed, actual RGB only
on 60 existing photos / 8100 unchanged quads/rasters, max 20 photos per finite step.
Create-only standalone sidecar and summary; exact re-render/fresh-process replay.
Otherwise publish rejected eligibility and guard proof, preserving all artifacts.

## Out of scope

New pair, training/refitting, qualification bypass, changes to existing R2 guards,
human labels, original geometry/results, API/UI/schema/DB, Super, activation/deploy.

## Acceptance criteria

- [x] Frozen group/class eligibility with explicit failed-gate behavior.
- [x] Conditional 8100 actual RGB sidecar or audited rejection with zero outputs.
- [x] Exact source/quad/pixel/model/old-output preservation and bounded resume.
- [x] Fresh replay, meaningful negative guards, style/types and independent audit.
- [x] DoD, Outcome, CURRENT_STATE and separate v1.7.218 commit.

## Technical notes

Reuse frozen preprocess, source rendering, live SHA checks and checked_publish.
No model registry or application response changes. Accuracy of 8100 remains null.
Experimental model branch is explicit, without synthetic gray/fusion proposals.
New root is proposed `artifacts/mumie-rgb-only-diagnostic-20261006`.

## Expected files

Proposed local diagnostic helpers/sidecars/report; quality/task/current updates.

## Test cases

Perclass regression despite aggregate improvement; source/model/history drift;
resume preserves existing bytes; unchanged raster SHA; failed gate writes no crops.

## Verification

Existing finite 120-second runner, portions of max 20 photos, fresh-process replay.
Stop after both stage tasks, their audits and separate commits.

## Risks / open questions

No blocking question. Unlabelled change counts/flags are not accuracy.
This stage does not qualify production or geometry.

## Outcome

Commit: `v1.7.218`.

All nine R2 RGB versus V4 RGB comparisons by class and group pass; original human84,
old18, new19, diagnostic9, held22/diagnostic4 and new control3/directed5/all8.
Eligibility `5b6af3ef03d77ff7dbc3e7c2f45f0586f92d24088b5871316acc4aadf044ac7c`
pins 9352 original inputs and binds exactly two model descriptors/temperatures
and all nine metric tables back to authoritative V4/R2/human proofs.

Actual V4 RGB and R2 RGB ran on 60 source photos and 8100 unchanged RGB96 crops.
Three bounded portions of 20 photos completed in 26.20 / 20.44 / 24.16 s.
Source/quad/pixel SHA and old V4 RGB classes reproduce exactly.
Standalone create-only outputs contain no gray or fusion inference.
There are 33 class changes; confidence flags below 0.9 decrease from 704 to 490.
These are unlabelled diagnostic counts, not whole-film accuracy or approvals.

Actual fresh source/CNN replay also covered all 60 photos / 8100 crops in three bounded portions:
26.38 / 33.66 / 45.14 s, maximum absolute logit difference 0. Seven detached guard
groups passed, covering failed-gate command/no writes, envelope fields, model
descriptor/temperature, quad, model/source/history bytes. Existing-output
resume validates exact top-level fields, model records and source/pixel binding;
replay markers bind original outputs and exact schema with finite delta<=1e-6.

Replay 9474 pins/set digest:
`b3f13c7812eaea06fb2fdda627c32f4ba02063db2319b871c1702945cfeb6f1f`.
Fresh comparison resume in 18.30 s calculates zero new photos. Final replay resume
in 35.50 s replays zero new photos, validates all 60 markers and 9474 pins, and retains
the identical pinned-set digest and replay bytes. Independent final audit of actual
inference, sources, models, replay, resume and documentation PASS; both earlier
findings fixed and checked, with no open P0–P2.

17 focused inference tests passed; four helpers Ruff/format/scoped strict mypy
PASS. TASK-0869 separately passed 43 tests. Human8 revision 8, human26 revision 27,
both original 61-output sets and all models remain preserved. Original paired
R2 sidecar remains absent, combined gate remains false and V4 stays qualified.

No training/refit/activation, API/UI/schema/DB, migration/deletion, Super targets,
geometry approval, model registry change, merge/push/deployment. The whole first
film remains symbol-development-excluded; geometry was partly trained there.
DoD, all five task criteria and accepted plan 0870 steps 1–4 are fulfilled.
Report: `ai_docs/quality/MUMIE_RGB_ONLY_DIAGNOSTIC_20261006.md`.
The accepted two-task stage is complete with its final audit and separate commits.
