---
title: Mumie cross-recording frozen comparison and ready human packet
status: done
last_updated: 2026-10-06
---

# TASK-0866 — evidence and acceptance

This stage follows the operator's autonomous-continuation instruction. All
three supplied folders were located under `C:/Users/tuszy/Documents/mumie`:
2580 first-film, 2052 second-film and 2844 third-film photos. The operator's
distinct-recording declarations are already recorded; no new folder or
repeat confirmation was requested.

## Source qualification and selection

- All 2580 first-film byte sources have zero overlap with the actual 312 V4
  development samples. Strict generation3 batch qualification retains full
  merged graph/protected-source exclusions: 6 duplicates, 66 excluded sources,
  2508 eligible, 60 evenly spaced selected. The decoded-photo guard combines
  all V3 protected photo groups and all 60 photos from the third-film selector.
  All selected 60 pass. The earlier 5771 pins, including the original 61 experimental
  output hashes and latest 26 human decisions at revision 27, remain protected.
- `control-selection.json` was published before the first result. Source SHA
  plus seed 20261006 selects board/field in 50 evenly spaced selected photos.
  These cases do not depend on predictions. No missing or duplicate control
  raster required replacement. Ten directed cases are separate, on the ten
  other selected photos, chosen by class changes/disagreements/confidence.
- Frozen geometry uses the previous trained iteration3 export. Part of this
  film supported its training. This is symbol transfer evidence, never an
  independently referenced geometry evaluation. Earlier diagnostic9 labels
  from this recording were inspected for regression after model selection;
  the first film is excluded from development but not a never-inspected film.

## Actual inference

| Property | Qualified V3 | Experimental V4 |
|---|---:|---:|
| Photos |60|60|
| Selected boards / filename expected |540 /540|540 /540|
| Exact available cells |8100|8100|
| Unavailable cells |0|0|
| RGB/gray disagreements |89|54|
| Low fused confidence, frozen threshold0.9 |461|472|

Class proposals change in 100 cells. Fewer disagreements do not establish
accuracy; increased low-confidence count is also reported. Accuracy is null.
Actual ONNX and each generation's frozen temperature/fusion weight are used,
with unchanged raster rendering/preprocess. No new training, model selection,
threshold fitting or production registration took place. Every geometry,
source, crop pixel, board/cell index/order and non-symbol reason is preserved.

## Ready human workflow

Reference ID:
`4af496199720988f7d90da00bb892d2de1a66684ca89d401ed41de9b037f9d91`.
Strict existing `symbol_batch_labels.prepare` derives the packet from the
qualified V3 batch. Separate immutable selection pins both V3/V4 proposals
and the control50/directed10 groups. Experimental V4 is not inserted into the
old batch adapter. No class proposal appears in a case category.

The exact 60 rasters are available at `http://127.0.0.1:3102/symbols/batch` and
`http://127.0.0.1:8108/cross-recording-review/review.html`. The packet is
`trainable=false`, revision 0 with zero decisions. Corrections use the existing
symbol editor without altering correct geometry. Human unreadable/grid_issue
remain available. Control proposals cover all 10 classes; this is not truth.

The saved runtime points to the new reference/labels, with the original bytes
in `artifacts/mumie-cross-recording-20261006/runtime.before-cross-review.json`.
The previous 26 approvals at revision 27 and original queue remain unchanged.
Identity-owned API 23640 / UI 35108 were restarted and independently reported
ready. Direct and UI-proxy read-only queue requests returned all 60 exact PNG
checksums in 0.516s and 0.297s; all three editor/gallery routes returned 200.
Production API 8000 was not restarted or reconfigured.

## Verification performed

- 71 existing focused batch/batch-inputs/batch-labels/feedback tests PASS
  (51.13s, one existing AnyIO deprecation warning).
- Seven diagnostic helpers: Ruff,format and scoped strict mypy PASS.
- Initial exact-render check regenerated 8100 pixel hashes and actual four
  ONNX predictions on all 60 review rasters. Four detached-copy negatives
  reject source,quad,pixel and order drift. No operator files were modified.
- Fresh process V4 retry processed 0 photos, complete 60. Fresh packet retry
  reproduced the same reference/groups with zero writes to human decisions.
- Output capture pins 372 files; selection pins 8539 inputs. Final new-process
  verification passed in 29.08s with identical input/output hashes, all 8100
  rerendered crops and 60 actual ONNX cases.
- Independent final audit PASS, no P0–P2 findings: all 8100 source rasters,
  actual four ONNX models, exact selection of 50 controls plus 10 directed
  cases on 60 distinct photos, all input/output pins, original 61 output SHA,
  human 26 / revision 27 preservation and all 60 API/proxy PNGs reproduced.

Every finite step used the saved absolute runner with a 120-second timeout.
V3 portions took23.34/27.39/27.75s; V4 portions19.97/21.20/25.06s.
Qualification91.12s printed its intermediate phase. Preparation56.70s and
retry60.30s completed normally; no orphan training process or extra server
copy was created. New replay helpers emit progress while validating rasters.

## Acceptance / DoD mapping

1. Source/recording qualification → inventory,whole-source/decoded-pixel
   isolation and retained authoritative exclusions.
2. Identical V3/V4 cells →8100 rerenders,strict same-cells guards and source
   model/report pinnings; no fabricated boards beyond filename cap.
3. Prediction-independent controls → pre-inference50 identity schedule,
   separately represented10 directed cases and no silent replacements.
4. Exact human packet →60 checked PNGs,zero decisions,trainable=false,
   original dictionary provenance and protected current histories.
5. Durable workflow → saved runtime backup, controlled restart/read-only HTTP
   and create-only retries. Final 372-file replay confirmed byte identity.
6. Quality → 71 focused tests, seven helper style/type checks, four negatives;
   independent final artifact audit PASS, no open P0–P2.
7. Documentation/commit → plan, completed task, Outcome and CURRENT_STATE
   reflect actual scope; own versioned commit follows the separate audit.

No DB writes,migration,deletion,Super target,automatic model activation,
merge,push or deployment. No application/API/UI contract changed.
Human reference is the next required interaction. Do not train on this
packet and continue presenting it as unseen evaluation; measure the frozen
pair on control50 and directed10 separately after operator decisions.
