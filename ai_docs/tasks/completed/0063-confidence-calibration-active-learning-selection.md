---
title: TASK-0063 — Confidence calibration and active-learning review selection
status: done
last_updated: 2026-07-29
---

# TASK-0063 — Confidence calibration and active-learning review selection

## Goal

Calibrate the immutable TASK-0062 ONNX classifier on source-disjoint validation
data, measure the resulting policy once on test data and create a deterministic,
versioned selection of pending whole layouts for the next manual-review batch.

## Dependency

TASK-0060 defines the immutable source-aware split. TASK-0061 and TASK-0062
provide the bootstrap checkpoint and verified local ONNX adapter. TASK-0059
defines the accepted and pending samples. TASK-0099 remains a separate
train-only similarity aid and is not a confidence policy.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- D-069–D-072 in `ai_docs/process/DECISION_LOG.md`

## Scope

- validate the exact dataset, split, ONNX report, ONNX bytes and pending
  inventory provenance,
- fit one scalar temperature on validation logits only with a deterministic
  bounded optimizer,
- report validation and one-time test NLL, Brier score, ECE, accuracy,
  reliability bins and per-class metrics before and after calibration,
- measure candidate confidence thresholds without selecting them on test data,
- keep automatic acceptance and rejection disabled unless the explicit
  validation and model-maturity gates pass,
- infer all currently pending cells locally with the verified ONNX model,
- group cells into whole 5 × 3 layouts and select a deterministic review batch
  using uncertainty, prediction-space diversity, source diversity and
  underrepresented predicted classes,
- write immutable logical reports and reproduce them byte-for-byte with
  `--check`.

## Acceptance criteria

- [x] Temperature is fitted only on validation and does not change top-one.
- [x] Test data is used only for final measurement.
- [x] Calibration metrics expose global and per-class weaknesses.
- [x] Auto-accept and automatic rejection have explicit measured gates and
      reason codes.
- [x] The current bootstrap model cannot silently enable auto-accept.
- [x] Pending samples and crop bytes are checksum-verified before inference.
- [x] Active-learning output contains complete whole layouts only.
- [x] Selection is deterministic, source-aware and tied to model/data hashes.
- [x] No prediction mutates `reviewed-cell-labels-v1`.
- [x] Focused tests, Ruff, strict mypy and dependency checks pass.

## Out of scope

- changing classifier weights, split or ONNX graph,
- online learning,
- automatically accepting or rejecting current labels,
- persistent review database/API/UI,
- OCR confidence calibration,
- retraining after the selected review batch.

## Expected files

- `services/worker/src/game_predictor_worker/images/symbol_confidence.py`
- `scripts/calibrate_m6_symbol_confidence.py`
- `services/worker/tests/test_symbol_confidence.py`
- `ai_docs/quality/m6-symbol-confidence-calibration-report.json`
- `ai_docs/quality/m6-symbol-active-learning-selection.json`
- architecture, quality and process documentation

## Verification

All expensive commands use bounded timeouts. Unit tests cover optimizer,
metrics, fail-closed policy gates and deterministic selection. The real-data
script is run once and then repeated in `--check` mode.

## Outcome

Completed 2026-07-29. A deterministic scalar temperature of `1.0338382913`
was fitted on 74 validation samples only. Validation NLL changed from
`0.94285158` to `0.94251763`; the frozen temperature then changed test NLL
from `0.87164029` to `0.87065020` without changing top-one.

The best measured validation threshold, `0.89329293`, produced precision
`1.0` on only 9 samples. It failed the minimum support and all-class gates.
Together with bootstrap model status and the unmet dataset-size target, this
keeps auto-accept disabled with explicit reason codes. Automatic rejection is
also disabled; every current prediction requires a human decision.

All 5389 pending crop bytes were checksum-verified. There are 359 complete
pending boards; four partial boards were excluded. The deterministic selector
created a batch of 30 complete layouts from 30 distinct source images. The
calibration report SHA-256 is
`a2359efed1e2dc2d73fc383d9e260c88f4a19838a74af3dd165362692601bff7`
and the selection report SHA-256 is
`2ab9a79a6d1c81b8d08abe0defc447510f0cfe4df1909c9aa8da77d79e6115d2`.
A second full `--check` reproduced both reports byte-for-byte.

Verification:

- 25 focused confidence, ONNX, classifier and suggestion tests passed,
- Ruff and strict mypy passed for the changed Python sources,
- `pip check`, Prettier and `git diff --check` passed.

The existing upstream PyTorch/PyTree `LeafSpec` FutureWarning remains limited
to ONNX export tests and does not affect calibration or selection.
