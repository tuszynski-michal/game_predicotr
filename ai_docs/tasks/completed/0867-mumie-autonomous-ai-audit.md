---
title: Autonomous blind AI audit of frozen Mumie cross-recording cases
status: done
last_updated: 2026-10-06
---

# TASK-0867 — dalszy blind AI audit Mumii

## Status

`done`

## Goal

Ocenić60 dokładnych cropów dwoma blind AI review, policzyć frozen-model
agreement osobno50/10 i przekazać jedynie niejednoznaczne przypadki do priorytetu.

## Context / entry conditions

Operator wyraźnie zlecił autonomiczne dokończenie maksymalnego zakresu po0866.
Raw60 packet pozostaje trainable=false. Pierwszy film nie wchodzi do treningu.
Przed przygotowaniem ocen zweryfikować saved replay/actual source/model SHA.

## Recommended execution

gpt-6.1-sol, high. Dwa blind visual reviews i osobny audit gpt-6.1-sol, high
według zaakceptowanego planu; drift blokuje zależny fragment.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/delivery/MUMIE_AUTONOMOUS_CONTINUATION_20261006.md`
- `ai_docs/quality/MUMIE_CROSS_RECORDING_20261006.md`

## Scope / technical notes

Reuse `symbol_ai_experiment.review_items/consensus`, `BatchReviewStore`,
`symbol_batch_labels.prepare/publish_portal`. Blinded manifest has60 PNGs,
20 existing human training anchors, no CNN labels/groups or human queue state.
Two exact assessments produce AI-only targets for evaluation. Operator retains
truth priority; no store writes. Gold frame is observation only. Separate
create-only proof and priority packet; first film stays development-excluded.

## Out of scope

Training in this task, base data changes, production activation, Super targets,
new API/UI, DB/deletion/migration/merge/push/deploy.

## Acceptance criteria

- [x] 60 exact bound rasters and20 anchors,2 independent blind reviews.
- [x] Perclass AI agreement50/10,uncertainty and separate gold-frame observations.
- [x] Frozen SHA/history/first-film exclusion and zero AI human approvals.
- [x] Ready priority of unresolved cases with prior60 and26 decisions preserved.
- [x] Fresh-process replay,focused tests/style/types and independent audit.
- [x] DoD,Outcome,CURRENT_STATE,own commit; continue0868 without operator.

## Expected files

Proposed local `artifacts/mumie-autonomous-ai-audit-20261006` helpers/reviews/
evaluation/priority. Proposed quality report, current block and completed task.
Existing lab saved runtime only if safe priority switch preserves operator state.

## Test cases / verification

Existing consensus and batch-label tests, exact review hashes, stale source/
review/pixel rejection. Absolute finite runner120s; read-only API checks.

## Risks / open questions

No blocking operator question. AI agreement does not replace human accuracy.
Pending60 human reference is not a reason to stop independent training.

## Outcome

### Changed

Two independent blind reviews of 60 PNGs and 20 human anchors accepted 53
AI proposals and left seven unresolved. Immutable per-class control50/directed10
agreement proof; eight exact priority crops and saved runtime with previous backup.
Human histories, original60 and prior26 approvals were preserved.

### Verification results

Thirty consensus/batch-label pytest passed. Six helper Ruff/format and scoped strict
mypy passed. Fresh-process replay verified 8,748 SHA pins and four negative guards.
Direct/proxy exact8 PNG checks passed at revision0 in 0.297/0.266 seconds.
Controlled API2740/UI26388 restart; editor/portal/original gallery200.
Independent artifact audit completed with no open P0–P2 findings.
DoD, six acceptance criteria and plan steps1–3 checked individually.

### Not completed

No human labels fabricated, first-film training, Super targets, DB operations,
production activation, merge/push or deployment. AI agreement is not human accuracy.

### Documentation updates

Accepted continuation plan, MUMIE_AUTONOMOUS_AI_AUDIT_20261006.md and CURRENT_STATE.
Commit `v1.7.215`; full hash recorded after commit.

### Recommended next task

Continue TASK-0868 automatically; eight optional corrections do not block training.
