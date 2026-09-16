---
title: TASK-0374 — Read-only row-first OCR v5 acceptance
status: done
version: 0.10
---

# TASK-0374 — Read-only row-first OCR v5 acceptance

## Goal

Provide a checksum-bound, read-only acceptance harness for
`semi-automatic-range-only-ocr-v5-row-first-v1` and evaluate it without
changing the default recognizer.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md` (D-290–D-293)
- `ai_docs/quality/SEMI_AUTOMATIC_SELECTION_RANGE_OCR_V4_ACCEPTANCE.md`

## Scope

- Add a separately versioned v5 acceptance harness that reads source files and
  immutable, human-labelled manifests without modifying sources, staging, jobs
  or database state.
- Measure source-local exact/unknown results, grouping and selection using the
  v5 runtime, and write a checksum-bound report with timing and OCR-batch
  diagnostics.
- Reuse only human labels from the existing frozen manifests; they are an
  unseen holdout for v5 and must not tune its locator, proof or runtime policy.
- Add tests proving manifest checksum validation, exact/unknown quality metrics,
  selected-review completeness and v5-only runtime selection.
- Run the existing frozen golden and challenge only if their sources remain
  available and their checksums still match. Keep v5 disabled regardless of the
  measured result.

## Out of scope

- Any change to v1–v4.1 behaviour or their reports.
- Tuning the v5 locator, proof, preprocessing, confidence thresholds or batch
  policy based on frozen labels.
- Default activation, API/UI changes, database writes, staging, image import,
  board geometry, cropper, symbol inference, model training or data cleanup.
- Large 1,000-source performance runs: they require a separate explicit task
  after the quality gate and manual review protocol are available.

## Acceptance criteria

- [x] V5 harness resolves only `exact`/`unknown` with the v5 fingerprint and
  never invokes board geometry, board/cell crop or symbol inference paths.
- [x] All source cases are checksum-bound and source names/indexes do not
  supply expected ranges.
- [x] Quality metrics classify exact output on unreadable/ambiguous labels as a
  false exact; selected-range gates require complete manual review.
- [x] Existing v4.1 script, contracts and reports remain unchanged.
- [x] V5 remains non-default regardless of report outcome.

## Expected files

- `scripts/run_row_first_range_ocr_v5_acceptance.py`
- `services/worker/tests/test_row_first_range_ocr_v5_acceptance.py`
- `ai_docs/quality/row-first-range-ocr-v5-*.json`
- `ai_docs/quality/SEMI_AUTOMATIC_SELECTION_RANGE_OCR_V5_ACCEPTANCE.md`

## Outcome

Completed as a safe negative acceptance. The checksum-bound challenge (`19`)
and frozen golden (`100`) were available and matched their manifests. Both
returned zero exact observations, zero false exact and zero selected ranges;
the coverage and group-capture gates therefore failed. The dominant reason was
`COMPLETE_ROW_UNVERIFIED` (`19/19` challenge and `85/100` golden). No tuning,
default activation, database write or source mutation was performed. V5 stays
non-default; a future improvement must use a new fingerprint and a separate
tuning/holdout protocol.
