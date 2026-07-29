---
title: TASK-0061 — Versioned batch symbol classifier baseline
status: done
last_updated: 2026-07-29
---

# TASK-0061 — Versioned batch symbol classifier baseline

## Status

`done`

## Goal

Train and persist a deterministic local PyTorch baseline for the eight reviewed
symbols, tied to the immutable TASK-0060 split and accompanied by held-out
metrics per symbol.

## Context

TASK-0060 produced a source-disjoint `269/74/73` train/validation/test split.
Every split contains all eight classes, but all classes remain below the
approximate 100-sample target. The first model is therefore a bootstrap
baseline, not an accepted production classifier.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- D-059, D-068 and D-069 in `ai_docs/process/DECISION_LOG.md`

## Scope

- pin a Windows/Python 3.12-compatible CPU PyTorch and torchvision pair,
- validate the exact dataset and split checksums before loading any image,
- define a small versioned CNN baseline suitable for 90 × 90 symbol crops,
- use deterministic seeds, fixed preprocessing and batch training,
- select the checkpoint only by validation metrics,
- evaluate test exactly once after checkpoint selection,
- persist configuration, class mapping, state dict checksum and metrics,
- report accuracy, macro recall, confusion matrix and per-symbol metrics,
- keep model artifacts local and never download weights at runtime.

## Out of scope

- pretrained weights or network access during training,
- ONNX export and runtime parity,
- calibrated confidence or auto-accept,
- active-learning selection and review UI integration,
- additional labeling or geometry changes.

## Acceptance criteria

- [x] Training consumes only sample IDs assigned to train.
- [x] Validation chooses the checkpoint and test does not influence training.
- [x] The run verifies the exact TASK-0060 report and dataset checksum.
- [x] Class order, preprocessing, seed and hyperparameters are versioned.
- [x] The saved state dict and report have SHA-256 checksums.
- [x] Metrics include every symbol and a complete confusion matrix.
- [x] Repeating the same CPU run produces the same logical result.
- [x] Tests, Ruff and mypy pass for the changed scope.

## Technical notes

- Use a small custom CNN without pretrained weights.
- CPU is the reference device for deterministic baseline generation.
- The first model is explicitly `bootstrap`; no acceptance threshold is
  invented in this task.
- Commands must have bounded timeouts and work in Windows PowerShell.

## Expected files

- `services/worker/src/game_predictor_worker/images/symbol_classifier.py`
- `services/worker/tests/test_symbol_classifier.py`
- `scripts/train_m6_symbol_classifier.py`
- `ai_docs/quality/m6-symbol-classifier-baseline-report.json`
- local ignored model artifact under `artifacts/`
- `pyproject.toml`
- `package.json`

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_symbol_classifier.py
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images/symbol_classifier.py services/worker/tests/test_symbol_classifier.py scripts/train_m6_symbol_classifier.py
.\.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/images/symbol_classifier.py scripts/train_m6_symbol_classifier.py
.\.venv\Scripts\python.exe scripts/train_m6_symbol_classifier.py --check
```

## Risks / open questions

- Small and imbalanced bootstrap data may produce weak held-out metrics.
- Strict byte-identical weight files are not assumed across different PyTorch
  releases; the pinned local CPU environment is the reference.

## Outcome

### Changed

- pinned PyTorch `2.12.1` and torchvision `0.27.1` CPU,
- added strict immutable dataset/split/asset validation,
- added the 24,104-parameter `small-symbol-cnn-v1`,
- added deterministic train/validation checkpoint selection and held-out test,
- persisted a local `.pt` artifact and a versioned quality report,
- added stable CLI error codes and the root `m6:symbols:train` command.

### Verification results

- 24 related dataset/classifier tests passed,
- Ruff passed,
- strict mypy passed,
- `pip check` reports no broken requirements,
- a second 40-epoch `--check` run reproduced the logical checkpoint and report,
- best epoch: `22`,
- validation accuracy/macro-recall: `59.4595% / 61.4469%`,
- test accuracy/macro-recall: `63.0137% / 62.7128%`,
- logical state SHA-256:
  `0edab6bbb738d908c4e902a347c982407549c159829c80fc3010c314a6c1aea2`,
- report SHA-256:
  `9098dcbcad4698a9f95910e09f19d05fae9edcad4957a15c56fef9e0efaa4e55`.

### Not completed

- No ONNX artifact or parity test was produced.
- No confidence threshold or auto-accept policy was defined.
- Weak held-out classes remain `star`, `watermelon` and `plum`.

### Documentation updates

- pinned the training libraries in `TECH_STACK.md`,
- added the baseline boundary to `SYSTEM_ARCHITECTURE.md`,
- added D-070 and updated M6/current-state sequencing.

### Recommended next task

- TASK-0099 — Safe bootstrap symbol suggestions.
