---
title: TASK-0101 — Production symbol-aware crops and geometry gate
status: done
last_updated: 2026-07-29
---

# TASK-0101 — Production symbol-aware crops and geometry gate

## Goal

Turn the accepted TASK-0100 spike into immutable full-corpus crop artifacts,
while preserving explicit fallback, provenance and an independent visual gate.

## Context

Frame-only local calibration improved geometry but failed every held-out board.
The symbol-aware spike found 15 reliable centers on all 25 reviewed boards,
reduced held-out median residual from `6.6964 px` to `2.0441 px`, and passed
owner review. Full-corpus validation subsequently rejected propagation of one
exact-image frame correction across all page positions. Production data must
start from each detector board independently, use a new crop namespace and
cannot overwrite v1–v5 artifacts or migrate the existing 56 labels.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- D-058–D-067 in `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/0098-local-image-grid-calibration-held-out-gate.md`
- `ai_docs/tasks/completed/0100-symbol-aware-grid-refinement-spike.md`

## Scope

- apply guarded symbol-aware refinement independently to every detected board,
- create a new immutable crop namespace and record refiner metrics/provenance,
- fail closed to `needs_review` when localization or transform guards fail,
- route only strict fallback boards to exact-observation manual correction,
- regenerate the complete 43-image / 387-board corpus after those corrections,
- create a page-level visual gate before setting `trainingAllowed = true`.

## Out of scope

- symbol class recognition or model training,
- auto-accepting geometry,
- changing OCR or sequence numbers,
- overwriting older crop namespaces,
- migrating old labels to new crop identities.

## Acceptance criteria

- [x] Every detector board is refined independently without cross-position
      propagation of an image-level frame correction.
- [x] Every board records refiner version, center coverage, inliers and
      residuals.
- [x] Any failed guard makes the source image `needs_review`.
- [x] Strict full-corpus benchmark routes 381/387 boards automatically and
      exactly 6 fallbacks to manual review.
- [x] Production-eligible complete corpus is regenerated with 43 images,
      387 boards and 5805 cells after the bounded visual gate.
- [x] Old crop artifacts and 56 decisions remain unchanged.
- [x] Full-page visual review must pass before training is allowed; the first
      v7 review was rejected with 92 explicit bad sequences across 36 images
      plus additional lighter cuts.
- [x] Schemas, tests, Ruff, mypy and deterministic checks pass.
- [x] Documentation records measured production outcome.

## Expected files

- `services/worker/src/game_predictor_worker/images/local_grid_calibration.py`
- `services/worker/src/game_predictor_worker/images/rectification.py`
- `services/worker/src/game_predictor_worker/images/symbol_grid_refinement.py`
- `services/worker/src/game_predictor_worker/images/symbol_grid_overrides.py`
- `services/worker/src/game_predictor_worker/images/safe_context_crops.py`
- `services/worker/src/game_predictor_worker/images/symbol_mesh.py`
- `services/worker/src/game_predictor_worker/images/global_symbol_lattice.py`
- `services/worker/src/game_predictor_worker/images/symbol_lattice_homography.py`
- `services/worker/src/game_predictor_worker/images/projective_lattice_crops.py`
- `services/worker/src/game_predictor_worker/images/source_projective_lattice_crops.py`
- `services/worker/tests/test_local_grid_calibration.py`
- `services/worker/tests/test_symbol_grid_refinement.py`
- `services/worker/tests/test_symbol_lattice_homography.py`
- `services/worker/tests/test_projective_lattice_crops.py`
- `services/worker/tests/test_global_symbol_lattice.py`
- `services/worker/tests/test_source_projective_lattice_crops.py`
- `scripts/build_m5_complete_local_grid_profiles.py`
- `scripts/crop_m5_board_cells_symbol_aware.py`
- `scripts/crop_m5_board_cells_detector_symbol_aware.py`
- `scripts/review_m5_symbol_grid_fallbacks.py`
- `scripts/crop_m5_board_cells_safe_context.py`
- `scripts/build_m5_safe_context_gallery.py`
- `scripts/build_m5_symbol_mesh_spike_gallery.py`
- `scripts/build_m5_symbol_lattice_homography_step2.py`
- `scripts/build_m5_projective_fixed_padding_regression.py`
- `scripts/crop_m5_board_cells_reviewed_symbol_aware.py`
- `services/worker/src/game_predictor_worker/images/symbol_grid_fallback_review.py`
- `ai_docs/quality/m5-full-symbol-grid-refinement-detector-report.json`
- `ai_docs/quality/m5-board-cell-crops-v6-detector-symbol-aware-affine-report.json`
- `ai_docs/quality/m5-board-cell-crops-v7-reviewed-symbol-aware-report.json`
- `ai_docs/quality/m5-board-cell-crops-v7-reviewed-symbol-aware.schema.json`
- `ai_docs/quality/m5-v7-owner-visual-feedback.json`
- `ai_docs/quality/m5-v4-owner-visual-feedback-round1.json`
- `ai_docs/quality/m5-symbol-centered-mesh-v4-full-preflight-report.json`
- `ai_docs/quality/m5-cell-quality-v1-owner-v4-round1-report.json`
- `ai_docs/quality/m5-bright-lattice-v9-round1-report.json`
- `ai_docs/quality/m5-bright-lattice-v9-round1-control-report.json`
- `ai_docs/quality/m5-projective-frame-v11-step1-report.json`
- `ai_docs/quality/m5-symbol-lattice-homography-v12-step2-report.json`
- `ai_docs/quality/m5-projective-fixed-padding-v12-seq29-gate-report.json`
- `ai_docs/quality/m5-projective-fixed-padding-v12-bounded-regression-report.json`

## Outcome

The exact-image calibrated-start v5 route was rejected by page-level visual
inspection because some lower boards included sequence-number/background
pixels. Detector-per-board v6 refined 381/387 boards; 6 strict fallbacks are
isolated as sequences `11`, `33`, `123`, `172`, `266`, `337`. The owner
corrected and accepted all six in the exact-observation editor. Cropper
`board-cell-crops-v7-reviewed-symbol-aware-affine-v1` generated 43 images,
387 boards and 5805 cells with 381 strict refined boards, 6 manual overrides
and 0 `needs_review` pages. The report SHA-256 is
`0950ac493af010d198cace691f78f3aa454100acaff246845a2fca2c5f8d0a55`;
an immediate `--check` rerun reproduced the same bytes. Draft-07 schema
validation, Ruff, mypy and 28 relevant worker tests passed. The owner rejected
the final gallery: 92 unique sequences across 36 images were explicitly listed
as bad and lighter cuts were not exhaustively enumerated. Sequence 316 proves
the failure mode: the detector bounding box contains the full board, but its
red-mask extreme-point quad is too narrow; per-slot localization then fits
already clipped fragments. v7 remains quarantined with
`trainingAllowed = false`. Rework must start from the complete per-board
bounding frame and use a local symbol mesh/per-cell crop rather than another
single global affine grid. The first `local-symbol-mesh-spike-v1` uses robust
row/column center estimates, midpoint cell bounds and a 5 px overlap allowance.
It generated comparison cards for all 92 explicitly rejected sequences with
0 fallbacks. This is a review-only spike and cannot replace v7 until the owner
accepts the rejected-case comparison and a subsequent complete-corpus gate.

The owner subsequently reported that the first mesh gallery still contained
weak sequences, so `local-symbol-mesh-spike-v1` was not accepted. A
conservative expanded-frame experiment preserved complete symbols but its
large overlapping windows also included material parts of neighbouring
symbols; it remains diagnostic and cannot train a classifier. The next
review-only candidate,
`expanded-frame-centered-symbol-mesh-spike-v4`, combines the expanded
detector frame with fixed-size crops centred on a robust local mesh. The top
row is extrapolated from the two more stable lower rows so the red board frame
cannot become its symbol centre.

The rejected-case preflight meshed `91/92` explicitly reported sequences and
failed closed on sequence `192`. The complete-corpus preflight meshed
`385/387` layouts and failed closed on sequences `192` and `235`; both
fallbacks are caused by implausible outer-column spacing and are not silently
accepted. Its deterministic report has SHA-256
`6d91b5bec672794c89929d3fb9509ce395c4eb9e88adb3b91dd623d101edc8be`.
Representative engineering inspection of sequences `1`, `64`, `100`, `200`,
`300`, `316`, `379` and `387` found complete, isolated symbols. This is still
not owner acceptance: `trainingAllowed` remains `false`, the full 385-card
gallery awaits review and the two fallbacks need exact-observation correction
before a production namespace can be released. A second full run reproduced
both the expanded-frame SHA-256
`2bfa16f22da264418cf0531241b5740e6f9f832e6c80b4a4549379664e263b26`
and the v4 preflight SHA-256 above. Ruff, mypy, `git diff --check` and 17
targeted worker tests pass; pytest required an explicit repository-local
`--basetemp` because the Windows system pytest directory denied access.

The owner stopped the v4 full review after sequence 30 because the remaining
manual inspection burden was not acceptable. The partial round recorded 16
bad layouts: `4`, `6`, `7`, `8`, `9`, `10`, `12`, `15`, `18`, `21`, `22`,
`24`, `26`, `27`, `29` and `30`, with failures concentrated in columns 1–3
and several edge cells. A crop containing only about 30% of a symbol is not a
valid training observation and cannot be auto-accepted during inference.

Three immutable follow-up spikes clarified the boundary:

- a wider fixed context recovered some clipped symbols but leaked neighbouring
  symbols,
- midpoint partitions removed neighbour leakage but could not recover pixels
  absent from the source frame,
- a wider source frame recovered edge pixels but also exposed navigation
  controls adjacent to or occluding edge symbols; sequence 4 demonstrates
  that geometry alone cannot produce a clean training sample from every cell.

The next production gate must therefore be cell-aware. It must mark complete,
isolated symbols as training-eligible and quarantine clipped, occluded,
interface-contaminated or uncertain cells. Quarantined cells remain visible in
the full-layout review and may receive a manual symbol decision, but their
image crop must not enter classifier training. No experimental v5–v8 spike is
accepted as a production namespace and `trainingAllowed` remains `false`.

The first deterministic pixel-only gate was calibrated against the exact
historical v4 crop identities referenced by the owner's round-1 feedback. It
quarantined `41/55 = 74.55%` explicitly affected cells, but incorrectly left
14 affected cells eligible. It also quarantined `82/185 = 44.32%` cells not
listed as affected inside the same 16 layouts. Those 185 cells are not an
owner-approved positive golden, so the second number is only a conservative
diagnostic. The important blocking result is the 14 false accepts: threshold
tuning cannot make this gate a production acceptance mechanism.

Visual diagnostics showed that the failure begins before the per-cell gate.
On wide frames, the slot-local locator can select the red cabinet frame or a
partial symbol because the real five-column lattice is narrower and shifted
inside the 500 px diagnostic frame. Candidate v9 therefore estimates all five
column centres jointly from compact bright components across the complete
board. It recovered the shifted lattices on all 16 owner-listed layouts and
all 14 round-1 control layouts without fallback; sequence 26 now centres all
five columns on the actual symbols instead of the left red frame.

The v9 calibration policy is deliberately fail-closed. During bootstrap,
columns 1 and 5 are never training-eligible because the navigation controls
can touch or occlude their symbols. Inner-column cells still pass the
independent pixel gate. This retains `108/240` candidate training crops in the
16-layout problem set and `99/210` in the control set while quarantining all
edge cells. These numbers are not owner acceptance. The next gate is a
bounded visual review of the 16 v9 cards; the full 387-board corpus must not be
generated until that review passes. `trainingAllowed` remains `false`.

The owner rejected v9 after comparing sequence 29 with v7. The image contains
a visible perspective outline and the detector preserves it, but the v10
wide-frame calibrator replaces the detector quad with an axis-aligned expanded
bounding box. The mesh then uses axis-aligned cells and synthesises the first
row from rows 2–3. This is a structural geometry error, not a threshold or
OpenCV limitation. V9 must not be tuned further or propagated to the corpus.

## Corrective projective-grid implementation

The accepted correction is split into three bounded steps:

1. **Perspective-preserving frame expansion.** Create a new immutable
   candidate that expands each detector quad in canonical board coordinates
   and maps it back to the source image. It must preserve edge directions,
   perspective and convexity; historical bounding-box variants remain
   unchanged.
2. **Symbol-lattice homography.** Detect symbol-centre candidates globally,
   assign them to the known 5 × 3 lattice and fit a guarded projective
   homography with RANSAC. Derive four virtual grid corners from all inliers
   rather than trusting only four possibly occluded corner symbols.
3. **Fixed-padding regression gate.** Rectify through that homography, apply
   fixed padding in canonical cell coordinates and compare the result first on
   sequence 29, then on `4`, `6`, `7`, `26`, `30` and the clean controls.
   Full-corpus generation remains prohibited until this bounded gate passes.

OpenCV 4.13 already provides the required homography, RANSAC, line detection
and perspective-warp operations. No library change is planned for these three
steps. A learned keypoint detector may be reconsidered only if the guarded
projective approach fails on held-out source images.

Step 1 is implemented as the immutable profile
`expanded-detector-projective-quad-v1` and cropper namespace
`board-cell-crops-v11-projective-frame-preflight-v1`. Expansion happens in
normalised board coordinates and is mapped back through the detector
homography. It never clamps an invalid result: non-finite, non-convex,
non-expanding or out-of-image geometry returns
`PROJECTIVE_FRAME_EXPANSION_INVALID`.

The sequence-29 regression preserves the detector perspective and expands
`[(402,336), (652,328), (645,448), (410,430)]` to
`[(386,329), (679,317), (669,459), (396,436)]`. The diagnostic card has
SHA-256 `e7ce5f70f86fc159d65c38df4f833e60741a87997e946bf9c81d5cfbfd72d2b1`.
Ruff, mypy, `git diff --check` and 10 relevant worker tests pass. This result
accepts only the frame-expansion primitive; the logical 5 × 3 grid shown on
the card is intentionally still provisional and must be replaced by step 2.
No full-corpus v11 artifacts were generated and `trainingAllowed` remains
`false`.

Step 2 is implemented as the independent estimator
`symbol-lattice-homography-ransac-v1`. It collects the 15 row-major centre
candidates from the complete expanded board, filters out candidates below the
existing confidence floor and fits one ideal-to-observed projective transform
for the whole 5 × 3 lattice. RANSAC is followed by a least-squares refit on its
inliers. The result fails closed unless it has at least 10 reliable candidates,
9 inliers, all 3 rows, all 5 columns, inlier P95 at most `10 px`, a convex
virtual grid inside the guarded frame margin and plausible projected row and
column spacing. Historical affine and mesh implementations are unchanged.

On sequence 29 the estimator found `14/15` reliable candidates and retained
13 inliers spanning all rows and columns. It rejected the false centre in the
first row, third column; the remaining low-confidence corner candidate also
does not control the transform. Inlier median residual is `4.6077 px`, P95 is
`7.6869 px`, and the four virtual grid corners derived from all inliers are
`[(1.5127,4.1743), (476.5020,22.3797), (470.9365,287.7535),
(30.8164,309.6661)]` in the expanded 500 × 300 frame. The bounded diagnostic
PNG has SHA-256
`4e4d1f56f13e24458bca6e86c4a05810d30e39c242bc2543c8b196acc76585d4`
and its report reproduces byte for byte.

Four new tests cover two corrupted corner observations, missing column
coverage, an implausible virtual grid, deterministic rerun and the real
sequence-29 regression. This accepts only homography estimation. It does not
yet rectify or publish cells: the lower-left virtual corner extends about
`10.7 px` beyond the diagnostic frame, so step 3 must prove that fixed canonical
padding uses only supported source pixels. The selected failures and clean
controls remain the next bounded gate. Full-corpus generation and training
remain prohibited. The final bounded gate passed 10 relevant tests, Ruff
format/check, mypy, deterministic report `--check` and `git diff --check`.

Step 3 is implemented as the non-production candidate
`board-cell-crops-v12-projective-lattice-fixed-padding-preflight-v1`.
It warps the expanded board through the fitted homography, applies an immutable
`10 px` inset in every canonical 100 × 100 cell and resizes the supported
80 × 80 interior to 90 × 90. A separately warped support mask and the projected
four corners of every padded crop both have to remain inside the real expanded
frame. Missing support returns a stable fallback instead of border replication
or a black training pixel.

The required execution order was preserved. Sequence 29 ran first and passed
independently: `15/15` cells have support fraction `1.0`; its deterministic
report SHA-256 is
`3593ffabd587db86c58a251f3bbf0567a6149a86c746f22ac04e82a3c173a579`.
Only then did the bounded gate run on `4`, `6`, `7`, `26`, `30` and the
14 controls from `m5-v4-round1-clean-control-sequences.json`.

The bounded gate failed. It created fully supported cells for `13/20` boards
and stopped fail-closed on seven:

- reported failures `7` (`SYMBOL_LATTICE_INLIER_COVERAGE_INSUFFICIENT`) and
  `30` (`SYMBOL_LATTICE_INSUFFICIENT_INLIERS`),
- controls `3` and `11` (`SYMBOL_LATTICE_INSUFFICIENT_INLIERS`),
  `16` and `28` (`SYMBOL_LATTICE_VIRTUAL_GRID_IMPLAUSIBLE`) and
  `17` (`SYMBOL_LATTICE_RESIDUAL_TOO_HIGH`).

The final report SHA-256 is
`57fc69a64a4223fe5815978a1c803024217a96c2879f68fe3b69d9545d56b378`;
an immediate `--check` reproduced all cards and report bytes, while
`--require-pass` correctly returned exit code `1`. Engineering inspection also
rejects the technically routed sequences `4` and `26`: their first-column
symbols remain visibly clipped. The guard verifies source-pixel support, not
that the proposed centre belongs to the symbol. The current row-major
slot-local candidate locator can consistently select a frame or fragment for
an entire edge column; a homography fitted after that incorrect assignment
cannot repair it.

Therefore step 3 is rejected as a production geometry gate. The test harness,
cards and fail-closed cropper remain diagnostic evidence, but no v12 dataset
namespace is published. The next correction must replace slot-local centre
proposal with global symbol-component/keypoint candidates and explicit robust
assignment to the 5 × 3 lattice, then rerun exactly this bounded gate.
Full-corpus generation and training remain prohibited.

## Global assignment and source-aware v13 regression

The corrective candidate is versioned independently as:

- locator `global-bright-component-lattice-assignment-v1`,
- homography `symbol-lattice-homography-ransac-v2-global-assignment-v1`,
- cropper
  `board-cell-crops-v13-global-lattice-source-aware-fixed-padding-preflight-v1`.

The locator extracts compact bright components from the complete 500 × 300
analysis board. It fits five column bases and three row bases globally, assigns
at most one component to each logical slot and refines a centre only inside an
adaptive window around that lattice. A slot without component support cannot
become a reliable homography observation merely because a local patch contains
the red frame. The RANSAC point-count, coverage, inlier and residual gates
remain unchanged.

The regression exposed that the 500 × 300 expanded board is an analysis plane,
not the boundary of the original photograph. On sequence 29 the correct
lower-left virtual corner is approximately `(42.84, 329.41)` in that plane.
Rejecting or moving the symbol to keep that point below `y = 300` recreated
the original clipping. V13 therefore composes
`ideal -> analysis -> normalized source` and samples the final fixed-padding
cells directly from the normalized source image. A warped source-support mask
and every projected crop corner must still prove support fraction `1.0`; no
border replication or synthetic black training pixels are permitted. The
source-aware geometry guard allows bounded extrapolation outside the
intermediate analysis plane, while final real-source bounds replace that
intermediate-frame assumption.

The mandatory execution order was preserved. Sequence 29 passed first with
`15/15` cells and support fraction `1.0`; its deterministic report SHA-256 is
`22ac9ab8d31a355e4b5b36f39c2b33f777a5efe258e1c042ed77b5273ce17ea1`.
The bounded run then produced supported cells for `18/20` boards. All reported
failures `4`, `6`, `7`, `26`, `30` passed, and engineering inspection of their
cards confirms that the previously clipped edge columns are now fully routed.
Controls `3` and `11` remain fail-closed:

- `3`: `GLOBAL_SYMBOL_LATTICE_AXIS_ASSIGNMENT_FAILED`,
- `11`: `GLOBAL_SYMBOL_LATTICE_INSUFFICIENT_ASSIGNMENTS`.

A bounded second analysis-frame expansion did not safely recover either
control: it still lacked a complete, consistent candidate lattice or failed
the existing inlier/coverage guards. They were not forced through by lowering
RANSAC thresholds. The bounded report SHA-256 is
`210b8d93c254be6c14d7bafcf7869ee1806f51ec92cabc7c11f66234ac2540f7`
and both v13 reports reproduce byte for byte. Historical v12 reports also
still reproduce with their original checksums.

Eleven focused tests pass together with Ruff and mypy. The v13 bounded gate is
still formally failed because it is `18/20`, so no full 387-board generation,
dataset publication or training is authorised. The next bounded correction is
limited to a second candidate modality or exact-observation geometry path for
controls `3` and `11`, followed by the same regression and owner review.

## Guarded bounding-box analysis fallback v14

The two remaining controls showed a bad detector projective quad rather than a
bad final homography. Sequence 3 had one detector side only about half the
length of the opposite side, and its analysis plane cut away the left part of
the symbol lattice. Sequence 11 exposed the same failure as only eight bright
assignments. Increasing the same projective quad did not recover either board.

V14 adds one bounded retry:
`board-cell-crops-v14-global-lattice-source-aware-bbox-analysis-fallback-v1`.
It is allowed only after one of the three global-locator failures:

- `GLOBAL_SYMBOL_LATTICE_INSUFFICIENT_COMPONENTS`,
- `GLOBAL_SYMBOL_LATTICE_AXIS_ASSIGNMENT_FAILED`,
- `GLOBAL_SYMBOL_LATTICE_INSUFFICIENT_ASSIGNMENTS`.

The retry uses the detector bounding box with `6%` horizontal and `4%` vertical
analysis padding. The rectangle is not accepted as final cell geometry. The
same global component assignment, RANSAC coverage/inlier/residual gates,
source-composed homography and `1.0` support preflight all run again. Any other
primary failure remains fail-closed and cannot select this retry.

The required regression now passes technically for `20/20`. Only controls
`3` and `11` used the fallback analysis frame; both retained 12 inliers,
respectively P95 `4.3133 px` and `4.3328 px`, and all 15 cells have real-source
support fraction `1.0`. Every other card checksum is identical to v13, proving
that the retry did not change already accepted routes. Engineering inspection
accepts the recovered symbols on `3` and `11`, but the controls are explicitly
not owner-approved, so the report remains `waiting_for_owner_review`.

The deterministic sequence-29 report SHA-256 is
`545b81c00224aa59f263c17da6ff633ad59e2381048592f875f87a587ba29682`;
the bounded `20/20` report SHA-256 is
`13dfac7e47a200f3a7aec237f4b71ed0032d0a3e969698e6e68239fb20baf1cb`.
Both reproduce byte for byte with `--check --require-pass`. Twelve focused
tests, Ruff, mypy and diff check pass. Full-corpus generation and training
remain prohibited until the owner accepts the bounded v14 gallery.

## Owner acceptance and full-corpus v14 preflight

On 2026-07-29 the owner accepted the bounded v14 gallery. Some crops were
slightly clipped but all reviewed symbols remained readable. This authorises
the full preflight, not training or automatic label migration.

The full runner processed all 43 images and 387 boards in 5 minutes 13 seconds.
It writes immutable per-cell, board and review-card artifacts and groups the
gallery by source image. The run produced:

- 373 cropped boards,
- 5595 immutable cells with source support fraction `1.0`,
- 14 fail-closed boards,
- 25 boards that entered the bounded-box analysis path,
- report SHA-256
  `026e12ac32802c1561552b338ddb80df51a00088a7e6c1cd57b2652a756d97a5`.

The 14 rejected sequences are `33`, `38`, `123`, `163`, `203`, `237`, `254`,
`255`, `325`, `333`, `334`, `335`, `346` and `379`. They cover five distinct
failure families: invalid projective-frame expansion, failed global axis
assignment even after bounded retry, insufficient inliers, incomplete inlier
coverage and implausible virtual-grid geometry. No threshold was lowered and
no synthetic pixels were introduced.

The full v14 report is intentionally `failed`; `5805/5805` is required before
the production corpus can be declared complete. The next correction is bounded
to a diagnostic gallery and explicit geometry path for these 14 sequences.
Existing 373 boards remain immutable evidence but are not training-eligible.

The owner reviewed the first several dozen successful full-preflight cards and
reported that they look correct. This is positive partial page-level evidence,
not acceptance of all 373 routed boards.

Failure diagnostics v3 contains the 14 rejected sequences and 22 unique direct
neighbours. Each regular card compares historical v7 crops, the current
analysis plane, the rectified result and the fail-closed state. Sequence 33
uses a dedicated comparison with the raw detector quad because projective
expansion fails before homography estimation. The gallery contains 36 cards,
reproduces byte for byte and has report SHA-256
`2aeb17991e7b7fc207de097db4d893e69a093ccfc759b1ec25eb251c1526f256`.
It remains review-only and does not authorise training.

The owner chose exact-observation correction for all 14 remaining fallbacks.
`v14-projective-fallback-review-v1` reuses the perspective editor but selects
only those immutable source-image/position identities. It starts from each
board's detector quad, stores decisions separately from the six historical v7
overrides and requires inspection of all 15 live crop previews before
acceptance. The prepared queue has `0/14` accepted and sequences `33`, `38`,
`123`, `163`, `203`, `237`, `254`, `255`, `325`, `333`, `334`, `335`, `346`,
`379`. One focused test, Ruff format/check and mypy pass. Training remains
blocked until the queue reaches `14/14` and the accepted quads pass a new full
preflight.

The owner accepted all 14 exact-observation quads. The first recomputed v15
namespace reached `387/387`, but its immediate reproducibility check detected
an immutable card collision on automatically routed sequence `49`; v15 was
rejected and its generated namespace/report were removed. The correction does
not rerun stochastic geometry for already accepted boards. V16 verifies and
reuses the exact immutable v14 bytes for 373 accepted boards, then generates
only the 14 manually reviewed boards with source-aware fixed padding and
support fraction `1.0`.

`board-cell-crops-v16-reviewed-v14-merge-v1` now contains 43 images, 387
boards and 5805 cells with 373 checksum-verified v14 routes, 14 reviewed source
quads and zero fallbacks. The immediate `--check --require-pass` rerun
reproduced every artifact and report byte. Report SHA-256 is
`c336a872388d35a4bb28a15626565906cd105345577919f0c6a3b251841ac5b9`.
Nine focused tests, Ruff and mypy pass. The technical corpus gate is complete;
`trainingAllowed` remains `false` until the owner accepts the final full-page
gallery.

The owner authorised continuation with the complete v16 corpus on 2026-07-29.
The separate owner-acceptance record binds that decision to the exact full
report SHA-256, `387/387` boards, `5805/5805` cells, 14 reviewed overrides and
zero fallbacks. TASK-0101 is complete. Downstream training data may use v16
only through that accepted checksum chain; no old label is migrated
automatically.
