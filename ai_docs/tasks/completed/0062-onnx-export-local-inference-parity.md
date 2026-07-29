---
title: TASK-0062 — ONNX export and local inference parity
status: done
last_updated: 2026-07-29
---

# TASK-0062 — ONNX export and local inference parity

## Goal

Export the exact immutable TASK-0061 bootstrap checkpoint to a versioned ONNX
artifact and provide a local CPU inference adapter whose outputs remain within
an explicit tolerance of PyTorch.

## Dependency

TASK-0061 produced the immutable PyTorch checkpoint and training report.
TASK-0060 produced the source-aware split. TASK-0099 may continue using
PyTorch embeddings, but this task must establish the production inference
boundary without changing model weights, preprocessing or class order.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- D-069–D-071 in `ai_docs/process/DECISION_LOG.md`

## Scope

- pin mutually compatible ONNX, ONNX Script and ONNX Runtime CPU dependencies,
- validate the exact dataset, split, PyTorch report and checkpoint provenance,
- export fixed model semantics with dynamic batch only:
  `N × 3 × 64 × 64 -> N × 8 logits`,
- run ONNX structural validation before publication,
- create a local adapter that verifies model bytes, class order, tensor shape
  and finite outputs,
- compare PyTorch and ONNX logits, probabilities and top-one class on all 416
  accepted samples,
- record provider/runtime versions, timing, tolerance and artifact checksums,
- reproduce the ONNX artifact and report byte-for-byte where supported by the
  selected exporter.

## Acceptance criteria

- [x] The ONNX artifact is derived from the exact TASK-0061 checkpoint.
- [x] Preprocessing and class order match the PyTorch report.
- [x] The adapter uses only a local verified artifact and CPU provider.
- [x] Dynamic batch sizes work without dynamic image dimensions.
- [x] All 416 approved samples preserve top-one class.
- [x] Maximum absolute logits and probability drift stay below an explicit,
      measured tolerance.
- [x] Invalid checksum, input shape, class contract and non-finite output fail
      with stable codes.
- [x] A second export/check reproduces the committed logical result.
- [x] Tests, Ruff, strict mypy and dependency checks pass.

## Out of scope

- confidence calibration or auto-accept thresholds,
- active-learning selection,
- quantization,
- mobile integration,
- retraining or model architecture changes.

## Expected files

- `services/worker/src/game_predictor_worker/images/symbol_onnx.py`
- `scripts/export_m6_symbol_classifier_onnx.py`
- `services/worker/tests/test_symbol_onnx.py`
- `ai_docs/quality/m6-symbol-classifier-onnx-report.json`
- dependency and architecture/process documentation

## Verification

All long-running commands must use bounded timeouts. The parity report is
generated once and then verified with `--check`; focused tests cover both
successful inference and fail-closed contracts.

## Outcome

Completed 2026-07-29. The current `torch.export`-based exporter produced a
115,133-byte opset 18 model with SHA-256
`e03f66f2ab092b6049920fee6fb2839900a95eb94af42fbd5ef7e35c473b5fb8`.
The local adapter verifies that artifact, fixed image/class dimensions and the
CPU-only provider before inference.

Parity covered all 416 approved train/validation/test samples. Top-one
mismatch count is zero, maximum absolute logits error is `2.861e-6` and
maximum absolute probability error is `4.172e-7`, both below the accepted
`1e-5` tolerance. The deterministic report SHA-256 is
`6f4596ae8ae938b7e9e89dac05e1a888ac4e53fe1d780dcc9325abfac33ad98c`.

Verification:

- 19 focused ONNX, classifier and suggestion tests passed,
- Ruff and strict mypy passed for the changed Python sources,
- `pip check` passed,
- a second full `--check` reproduced the ONNX bytes, parity result and report.

The exporter currently emits a harmless upstream PyTorch/PyTree FutureWarning
about `LeafSpec`; it does not affect the graph, parity or reproducibility.
