---
title: TASK-0888 — Analyse current Mumie symbol corrections
status: done
last_updated: 2026-10-06
---

# TASK-0888 — Analyse current Mumie symbol corrections

## Status

`done`

## Goal

Quantify the operator's current symbol corrections, verify the active neural
classifier and recommend a concrete next training route without changing data.

## Context

The operator corrected symbols in MAIN after TASK-0887 and asks whether the
recognizer uses a neural network and whether these corrections can improve it.
This request is an analysis, not activation of a new model or a cleanup signal.

## Dependencies / entry conditions

MAIN branch v1.1-vision-lab-hybrid-geometry, HEAD v1.7.229 /
5130cbc80c676560a6ec6c5f77828c48074ff462. Existing post-commit receipts and
unrelated dirty folders remain outside this task's commit. The current Mumie
game is fea55cc1-ebf4-4cee-b3ab-a520017ed1be.

## Recommended execution

Current agent gpt-6.1-sol / high; bounded read-only analysis and self-review.
No delegation or separate implementation plan is required for this analysis.
An independently evaluated candidate is required before any future activation.

## Relevant docs

- AGENTS.md; ai_docs/README.md; ai_docs/process/CURRENT_STATE.md
- ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/requirements/VISION_LAB.md, symbol provenance and training sections
- ai_docs/architecture/VISION_LAB.md, symbol models and snapshot sections
- ai_docs/guides/MUMIE_MAIN_APP_OPERATOR_GUIDE_20261006.md
- ai_docs/process/PLAN_STANDARD.md; TASK_TEMPLATE.md; DEFINITION_OF_DONE.md

## Scope

- Current owner-bound approvals, coverage, disagreement pairs and crop identity.
- Existing GET model-quality preview and active registry/ONNX verification.
- Small visual sample and checksums of the existing R2 lab crop bundle.
- Save a durable analysis with the recommendation and remaining limitations.

## Out of scope

Training, cohort freeze, model registration/activation, reinference, migrations,
777 operations, cleanup, new upload, API/UI changes and merging lab annotations
into DB approvals. AI observations do not become human labels.

## Acceptance criteria

- [x] Current approved coverage and corrected prediction pairs recorded.
- [x] Existing active model demonstrably contains neural convolution layers.
- [x] Exact current/approved crop identities and read-only training preview checked.
- [x] Earlier human training assets checked without copying source folders.
- [x] Recommendation distinguishes new DB corrections from earlier lab labels,
      preserves held-out sources and avoids a population-accuracy claim.
- [x] Outcome and CURRENT_STATE updated; one versioned documentation commit.

## Technical notes

Read-only queries join image_board_search_fast_documents on game, sequence
and review_item_id. Old superseded owners cannot inflate counts. All queries
are scoped to Mumie, with connection5s, statement10s and lock2s limits.
GET model-quality uses45s; the finite runner uses120s. Fourteen current
checksum-bound preview GETs use5s each. Store evidence under
artifacts/mumie-feedback-analysis-20261006; do not write live ORM state.

## Expected files

- New ai_docs/quality/MUMIE_SYMBOL_FEEDBACK_ANALYSIS_20261006.md.
- Existing ai_docs/process/CURRENT_STATE.md, new TASK-0888 entry only.
- This task, moved to completed after analysis.

## Verification

Existing bounded run_step.py with MAIN Python: inspect_feedback.py,
preview_quality.py, visual_sample.py and verify_existing_inputs.py in the
task's ignored evidence folder. Check saved counts and manifest/model hashes.
Verify the final Git diff and preserve unrelated dirty files. No application
test/build is required because no application code or runtime behaviour changes.

## Risks / open questions

The edited sample is deliberately selected and cannot measure full-film
accuracy. The DB cohort has whole-photo splits but no persistent recording ID.
Combining historical lab and MAIN feedback needs source-role and class mapping
checks; a stored old qualification is not proof of a newly composed dataset.

## Outcome

### Changed

- Saved the factual analysis and recommended next candidate path. MAIN code,
  database state, model activation and runtime remain unchanged.
- CURRENT_STATE updated with counts, preserved old corpus and limitations.

### Verification results

- Bounded read-only inspection PASS:126 current approved,34 source photos,
  122 disagreements; all126 crop/render approval identity fields match.
- Existing model-quality GET PASS:81 selected samples,30 photos,7/10 classes.
  No grid/unreadable/stale/missing-asset exclusions. Missing class/source
  coverage recorded before any cohort/job write.
- Fourteen checksum-bound asset GETs and visual inspection completed.
- R2 corpus/model SHA checks PASS:443 files/6,637,811 bytes; actual active
  ONNX contains3 Conv layers and10 classes. Historical human development283
  and validation84 distinguished from AI origins and control roles.
- Focused Git documentation checks PASS. No application tests/build run:
  there is no application-code or behaviour change in this task.
- Commit: v1.7.230; full hash recorded after commit.

### Not completed

- No new training, cohort freeze, activation, reinference, cleanup, migration,
  merge/push, DB/lab label promotion or code/API/UI changes.
- No claim of full-folder accuracy or a qualified combined dataset. Earlier
  source roles and overlap must be rechecked before a new run. The null
  activeModel quality projection is documented, not fixed in this analysis.

### Documentation updates

MUMIE_SYMBOL_FEEDBACK_ANALYSIS_20261006.md, this task and CURRENT_STATE.

### Recommended next task

Qualify a combined lab candidate from exact current MAIN human corrections
and existing human corpus. Use source/recording roles, mapping and checksum
guards; do not request the same annotation work again or train a partial
7-class DB-only cohort. Then train/evaluate separately before activation.
