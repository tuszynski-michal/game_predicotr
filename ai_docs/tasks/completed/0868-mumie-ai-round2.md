---
title: Second isolated Mumie RGB/gray experiment with additional blind AI examples
status: done
last_updated: 2026-10-06
---

# TASK-0868 — dodatkowe przykłady i druga para Mumii

## Status

`done`

## Goal

Qualify up to 30 new development crops and evaluate one isolated RGB/gray pair
against frozen human and cross-recording references without operator involvement.

## Context

The operator explicitly requested maximum autonomous progress. The accepted
two-task stage continues after TASK-0867; its optional correction queue is not
a prerequisite. Prior recording-independence confirmations remain authoritative.

## Dependencies / entry conditions

TASK-0867 final audit/commit; strict V3 third-film batch, frozen V4 evidence,
19 approved human feedback decisions and five unreadable history records.
All 26 later human audit rasters and their full photos remain outside development.
One additional pair is authorized; no retry seed search or production activation.

## Recommended execution

gpt-6.1-sol, high. Two independent blind visual reviews and an independent
experiment audit use gpt-6.1-sol, high under the accepted model table.
Input drift blocks the dependent operation; report qualification failure honestly.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/delivery/MUMIE_AUTONOMOUS_CONTINUATION_20261006.md`
- `ai_docs/quality/MUMIE_AUTONOMOUS_AI_AUDIT_20261006.md`
- `ai_docs/quality/MUMIE_HUMAN_AUDIT_20261006.md`

## Scope

Reuse strict AI selection, consensus, freeze, adapter and durable training protocol.
Prepare up to 100 exact cases: human19, old AI development29, old AI audit22 and
up to30 new development cases. Gold-frame observations remain separate.
One additional generation4 pair, named V4-R2, uses a new manifest and run root.
Calibration/best epoch use only the existing human84. Evaluate per-class human
84/18/19/9 gates against V4, frozen human26 and transfer control50/directed10.
Only after passing gates, reclassify the identical first8100 symbol crops in a new
sidecar. Preserve all original models, rasters, histories, results and geometry.

## Out of scope

Application API/UI or schema changes, DB writes/migration/deletion, production
activation, merge/push/deploy, new film requests, Super targets and more than one pair.

## Acceptance criteria

- [x] Exact blind input and two independent reviews; protected human/source isolation.
- [x] Strict cohort with at least20 AI audit targets and AI development greater than29.
- [x] One controlled RGB/gray pair or a documented qualification failure.
- [x] Actual human per-class gates, ONNX parity, human26 and separate AI transfer50/10.
- [x] If eligible, identical8100-crop sidecar; otherwise preserve qualified V4.
- [x] Fresh-process replay, focused tests/style/types and independent audit.
- [x] DoD, Outcome, CURRENT_STATE and separate versioned commit.

## Technical notes

Seed20261005, 20 epochs, batch32, lr0.001, max1800 seconds/10000 steps per branch;
human feedback weight4 and AI weight1. Run one GPU worker at a time. Durable PID,
watchdog, checkpoint/RNG and finite CLI steps remain required.
Human decisions retain priority; AI consensus does not create human approvals.
Whole photos containing the human26 are excluded before new development selection.
The first film and human validation remain out of development.

## Expected files

New local `artifacts/mumie-ai-round2-20261006` helpers, reference, qualified cohort,
runs and evidence. New quality report and task/current updates. No application files.

## Test cases

Strict adapter/consensus/training/sampler/metrics tests. Source, raster, history,
protected-photo, model/ONNX and old-output SHA rejection. Fresh process verifies
immutable results and qualification. Human labels are never fabricated.

## Verification

Absolute PowerShell commands through the existing finite120-second runner.
GPU training is detached, controlled and monitored; each branch has max1800 seconds.
Stop after the accepted stage, after both audited task commits, or a genuine
blocked dependent operation. No new operator permission is needed within this scope.

## Risks / open questions

No blocking operator question. AI agreement can be jointly wrong. Reused84 and
same-film audit do not estimate independent population accuracy.

## Outcome

Commit: `v1.7.216`.

Two independent blind reviews inspected 100 exact PNGs and 20 human anchors.
76 high/high cases qualified; development increased from 312 to 327 unique crops,
including AI29 → AI44. AI audit22, human84/diagnostic9 and all source/history
bindings remained frozen. All human26 source photos and decoded RGB aliases,
and the first film, remained outside development. Gold observations were kept
separate; no human labels or Super targets were fabricated.

Exactly one generation4 RGB/gray pair completed with unchanged seed/budgets:
20 epochs and 280 steps each; RGB 633.279726 seconds/best8, gray
606.188346 seconds/best6. Calibration and best epoch used only human84.
Both owned workers exited. All existing per-class human84/18/19/9 gates passed.
Independent actual checkpoint/CPU-ONNX replay covered 196 rasters with identical
classes and maximum absolute logit difference 3.8147e-6.

Later held human26: RGB improves 25/26 → 26/26; gray and fusion regress
26/26 → 25/26 on the exact Ra → J directed case. Thus the combined R2 pair
is rejected, V4 remains qualified and the R2 RGB artifact is retained without
activation. The first-film AI control47/47 remains unchanged; directed6 yields
RGB6/gray5/fusion5 versus V4 6/5/6. AI agreement is not human accuracy.
No R2 8100-crop sidecar, extra training, seed search or calibration refit occurred.

Qualification digest: `99782f45d000414fd3d9648754db4a7a77b24aaa47dcf736eb26b34ae7488e43`.
Pair proof: `dbe76d867864258a0bfa6d7e4b821717f6fa78f67b92f0241ce465f24407e815`.
Held proof: `2eaefea4470e7b576f5e3d0a05dd834dfa764c32c1d724c670c691765f541820`.
Repeated fresh-process inference reproduces pair/held bytes. Repeated final
replay checks 9332 pins and four negative guards with identical proof bytes;
pinned-set digest `12bc79f5c75f0b71d7d4ded986a53b6ddaa822115a37a2607d69fb47ee66238c`.
Original models, rasters, histories and 61 first-film outputs remain unchanged.

Focused tests: 50 passed and one pre-existing obsolete generation-registry
assertion failed. It expects generation3 rejection despite existing support
for3/4; this unrelated test was not changed or hidden. All 15 local helpers
pass Ruff, formatting and scoped strict mypy. Independent final audit PASS:
documentation and actual artifacts agree; no open P0–P2 findings.

Read-only health confirms eight optional exact corrections, revision0, direct
PNG0.125s/proxy0.094s. No new folder or operator approval was needed. Application
API/UI/schema, DB, production models and geometry remain unchanged. No migration,
deletion, activation, merge, push or deployment was performed.

DoD and accepted plan steps1–5 map to the seven checked criteria above. The
conditional failed-gate preservation path is fulfilled. Detailed evidence:
`ai_docs/quality/MUMIE_AI_ROUND2_20261006.md`.
