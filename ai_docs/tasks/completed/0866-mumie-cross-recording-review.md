---
title: Mumie cross-recording inference and human reference packet
status: done
last_updated: 2026-10-06
---

# TASK-0866 — większy test transferu i gotowa kolejka referencji

## Status

`done`

## Goal

Porównać frozen V3/V4 na 60 eligible zdjęciach pierwszego filmu i udostępnić
gotowy pakiet50 kontroli oraz10 kierowanych przypadków w istniejącym edytorze.

## Context

Operator dostarczył trzy niezależne filmy i zlecił samodzielną kontynuację.
TASK-0865 dał 22/22 human audit V4 w częściowo trenowanym filmie. Nowa próba
sprawdza transfer symboli na filmie bez development targetów. Nie potrzeba
ponownej zgody na analizę ani kolejnego katalogu.

## Dependencies / entry conditions

- Frozen qualified V3 oraz experimental V4, ukończony TASK-0865.
- Weryfikacja pierwszego katalogu przez strict V3 exclusions i V4 development
  source/photo-pixel checks; nie wolno polegać tylko na nazwie katalogu.
- Część filmu wykorzystano do geometrii; wynik nie ocenia jej niezależności.

## Recommended execution

gpt-6.1-sol, high. Review gpt-6.1-sol, high według końcowej tabeli planu.
Drift lub technical overlap blokuje zależny fragment; bez omijania walidacji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/VISION_LAB.md` — D-502–D-505
- `ai_docs/architecture/VISION_LAB.md` — feedback/experimental symbol cohorts
- `ai_docs/delivery/MUMIE_CROSS_RECORDING_REVIEW_20261006.md`
- `ai_docs/delivery/MUMIE_AI_OVERNIGHT_20261006.md`
- `ai_docs/delivery/MUMIE_HUMAN_AUDIT_20261006.md`

## Scope

Inventory/source qualification, frozen60-photo batch, identical-crop V4,
predeclared50 controls and separate10 directed cases, immutable evidence,
existing human editor runtime, bounded restart/replay and independent audit.

## Out of scope

Training/calibration, production activation, geometry approval, Super labels,
DB/migration/deletion, merge/push/deployment and new API/UI contracts.

## Acceptance criteria

- [x] 60 qualified real photos with filenames, SHA/exclusions and V4 isolation.
- [x] V3/V4 use identical geometry/order/pixel SHA; metrics remain proposals.
- [x] Control selection does not depend on predictions; directed group separate.
- [x] Ready packet has exact rasters, zero human decisions and trainable=false.
- [x] Saved runtime/read-only API/new process replay work; previous data preserved.
- [x] Focused tests, lint/format/types, negative drift checks and independent audit.
- [x] DoD, plan, Outcome, CURRENT_STATE and separate numbered commit agree.

## Technical notes

Use existing `symbol_batch.freeze/run`, `reclassify_photo`, `classify_logits`,
`symbol_batch_labels.prepare`, `BatchReviewStore`, `publish_portal`. Qualified
V3 remains batch provenance; V4 is explicitly separate experimental sidecar.
Create-only results and exact SHA drift checks. Do not inject V4 into old
generation adapter. Runtime backup before pointing at new packet. Preserved
human26 decisions remain withheld and are not used for new training.

## Expected files

- Existing: `ai_docs/process/CURRENT_STATE.md` — new task block only.
- Proposed: delivery plan, task, `ai_docs/quality/MUMIE_CROSS_RECORDING_20261006.md`.
- Proposed local artifacts: `artifacts/mumie-cross-recording-20261006` helpers,
  inventory, frozen comparison/selection/packet evidence and runtime backup.
- Proposed gallery batch: `artifacts/mumie-folder-test-20261005/first-v3-60`.
- Existing saved runtime: `artifacts/mumie-symbol-dataset-version-20261005/runtime.json`.

## Test cases

Frozen source/pixel/geometry mismatch rejects; exact retry creates no new
result; missing crop recorded; filename caps/clipped cells preserved; old
human store and model state unchanged; new queue revision0 and exact PNG.

## Verification

Existing absolute `run_step.py --timeout120 --cwd <worktree>` for all finite
steps. Focused `test_symbol_batch*` and feedback tests, Ruff/format/scoped
mypy on helpers; controlled lab launcher and read-only queue request.

## Risks / open questions

No blocking operator question. No human ground truth yet for the new packet.
The50 controls are a bounded conditional crop test, not population accuracy.

## Outcome

### Changed

- Qualified all three supplied folders (2580/2052/2844 photos), actual V4
  development 312 and zero first-film source overlap. Strict exclusions retain
  2508 eligible of 2580 after 6 duplicates and 66 protected sources. Frozen
  60 evenly spaced photos pass stronger whole-photo pixel exclusions.
- V3 and experimental V4 produced symbol proposals on identical 8100 available
  rasters / 540 boards, respecting filename cap. 100 classes differ;
  disagreements 89→54 and low confidence 461→472. Accuracy remains null.
- Prepared exact 50 predeclared controls plus 10 separate directed cases, no
  missing controls, on 60 distinct photos. Review reference
  `4af496199720988f7d90da00bb892d2de1a66684ca89d401ed41de9b037f9d91`,
  revision 0, trainable=false, zero human decisions. Category shows no class.
- Existing editor/runtime points at the packet with a durable byte backup.
  Prior 26 decisions / revision 27, models, runs and original 61 outputs are
  unchanged. API/UI identity-owned restart, read-only queue and PNG checks pass.
- Commit `v1.7.214`; actual history before completion confirmed v1.7.213
  e3d074239fdd27a3b0101dbdc0fac78f31e0abc6. Separate task commit, baseline
  historical metadata excluded from staged scope.

### Verification results

- 71 focused batch / batch-inputs / batch-labels / feedback tests PASS, 51.13s.
  Ruff / format / scoped strict mypy PASS on seven diagnostic helpers.
- Fresh-process V4 retry processed 0; preparation retry reproduces the exact
  packet. Replay 29.08s: 8539 input pins and 372 output files byte-identical,
  8100 rerenders, actual four ONNX models on 60 PNGs, four negative checks PASS.
- Independent read-only artifact audit PASS, no open P0–P2, reproducing all
  rasters / actual ONNX / selection / input-output hashes and current histories.
- Direct API / UI proxy returned 60 exact PNGs in 0.516 / 0.297s; all editor and
  gallery routes returned 200. Saved API 23640 / UI 35108 identity-owned and ready.
- Every finite step bounded by 120s runner. No timeout or orphan process.
  All seven criteria / accepted plan steps 1–5 / relevant DoD points satisfied.

### Not completed

- New human reference is intentionally pending operator annotation. No claim
  of unlabeled-film accuracy. Geometry partially trained on this film;
  independent grid evaluation and Super reference are outside this task.
- No training, calibration, model activation, DB/migration/deletion,
  application/API contract change, merge/push or production deployment.

### Documentation updates

- MUMIE_CROSS_RECORDING_REVIEW_20261006.md, quality acceptance report,
  CURRENT_STATE and completed task. Runtime backup and durable local artifacts.

### Recommended next task

- Operator labels the 60 exact crops at `http://127.0.0.1:3102/symbols/batch`.
  Measure frozen V3/V4 against latest human history, control50 and directed10
  separately. Keep this first-film packet out of development; do not train on
  it and continue reporting it as unseen evaluation.
