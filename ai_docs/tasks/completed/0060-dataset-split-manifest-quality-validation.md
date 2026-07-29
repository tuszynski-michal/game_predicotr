---
title: TASK-0060 — Dataset split, manifest and quality validation
status: done
last_updated: 2026-07-29
---

# TASK-0060 — Dataset split, manifest and quality validation

## Status

`done`

## Goal

Create a deterministic train/validation/test split of the accepted labeled
symbol dataset by source image and issue an auditable quality manifest.

## Context

TASK-0059 exported 416 explicitly accepted v16 samples from 18 source images.
Before training or bootstrap suggestions, the dataset needs a disjoint
source-image split so that crops from the same photograph cannot leak into
held-out evaluation.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- D-059, D-062 and D-068 in `ai_docs/process/DECISION_LOG.md`

## Scope

- validate the labeled dataset identity and single-game symbol catalog,
- group samples by source-image checksum,
- create a deterministic 70/15/15 train/validation/test assignment,
- require at least two source images and every labeled symbol in each split,
- reject source-image and identical-asset leakage between splits,
- report sample, source and unique-asset counts per split and symbol,
- preserve ordered sample identifiers in a versioned manifest,
- report the approximate 100-samples-per-symbol bootstrap target separately
  from the structural split gate.

## Out of scope

- PyTorch training,
- ONNX export or inference,
- symbol suggestions and auto-accept,
- additional manual labeling,
- geometry correction.

## Acceptance criteria

- [x] No source-image checksum occurs in more than one split.
- [x] No crop checksum occurs in more than one split.
- [x] Every known symbol occurs in train, validation and test.
- [x] Each split contains at least two distinct source images.
- [x] The same input and seed produce byte-identical output.
- [x] Counts and source coverage are reported per symbol and split.
- [x] Missing classes or invalid provenance fail with a stable error code.
- [x] Tests, Ruff and mypy pass for the changed Python scope.

## Technical notes

- Split ratios are `train=0.70`, `validation=0.15`, `test=0.15`.
- The seed is a stable text value, not process-global random state.
- Assignment is performed on complete source-image groups.
- The current dataset has fewer than approximately 100 samples for every
  symbol. The manifest must expose this as an advisory rather than hiding it.
- TASK-0099 remains after the first model and must use the held-out boundary.

## Expected files

- `services/worker/src/game_predictor_worker/images/dataset_split.py`
- `services/worker/tests/test_symbol_dataset_split.py`
- `scripts/split_m6_symbol_dataset.py`
- `ai_docs/quality/m6-symbol-dataset-split-report.json`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_symbol_dataset_split.py
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images/dataset_split.py services/worker/tests/test_symbol_dataset_split.py scripts/split_m6_symbol_dataset.py
.\.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/images/dataset_split.py scripts/split_m6_symbol_dataset.py
.\.venv\Scripts\python.exe scripts/split_m6_symbol_dataset.py --check --require-pass
```

## Risks / open questions

- The dataset is structurally suitable for a source-aware split, but its
  per-symbol counts remain below the approximate target of 100.

## Outcome

### Changed

- added deterministic source-group assignment with a stable seed,
- added strict dataset, symbol, source and duplicate-asset validation,
- added a Windows-compatible CLI and package command,
- issued a manifest with `269/74/73` samples from `10/4/4` source images,
- recorded per-symbol counts and the unmet approximate bootstrap target.

### Verification results

- 5 focused tests passed,
- Ruff passed,
- strict mypy passed,
- generation and immediate `--check --require-pass` reproduced the report,
- report SHA-256:
  `214bb9eeddfc996e47a9582c0e582a098b865aff430d14102e28e0c4e5ab2ec0`.

### Not completed

- No model was trained.
- No additional labels were created.
- The approximate 100 reviewed samples per symbol target remains unmet.

### Documentation updates

- added D-069,
- updated M6 execution status and `CURRENT_STATE.md`.

### Recommended next task

- TASK-0061 — Versioned batch symbol classifier baseline, using the immutable
  source-aware split manifest.
