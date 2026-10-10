# TASK-0856 — Independent Mumie symbol batch

## Status

done

## Goal

Run frozen geometry and RGB/gray symbol models on 600 independent real photos,
fix technical failures and provide persistent, inspectable review evidence.

## Context

The operator requests autonomous continuation until human labels or an actual
decision are required. TASK-0855's 84-cell validation is insufficient evidence
for unseen photos. The previously supplied second cut folder has 2052 images.

## Dependencies / entry conditions

- TASK-0854 D-498 qualified manifest and TASK-0855 succeeded RGB/gray ONNX.
- Frozen geometry iteration03 export and operator-authorized source folder.
- Original annotation/symbol stores are read-only. No final-test accuracy claim.

## Recommended execution

gpt-6.1-sol, high. Review preprocessing, transitive exclusions and recovery
separately. No delegation. Stop dependent work only for actual missing human
labels, contradictory evidence or unresolved integrity errors.

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/requirements/VISION_LAB.md
- ai_docs/architecture/VISION_LAB.md
- ai_docs/delivery/MUMIE_SYMBOL_BATCH_20261005.md
- ai_docs/delivery/MUMIE_SYMBOL_TRAINING_20261005.md

## Scope

- Checksummed immutable batch selection, full-component exclusions, model bindings.
- Bounded resumable inference with exact training preprocessing and cell rendering.
- Filename board-count bound, partial/outside-cell review, no invented sequence.
- Static indexed photo/cell review, statistics and visual inspection of failures.

## Out of scope

DB, source-store mutation, human approvals, model activation, Super training,
retraining with model labels, production deployment and changing HTTP contracts.

## Acceptance criteria

- [x] 600 evenly distributed, deduplicated eligible photos processed persistently.
- [x] No protected or training/validation source pixels are decoded for inference.
- [x] Source/model drift or corrupt result fails explicitly; restart never duplicates.
- [x] Count5 draws at most5; missing boards and outside cells remain review cases.
- [x] Preprocessing equals RGB/gray training; probabilities use frozen calibration.
- [x] Review contains full images, real crop atlases and per-cell proposals/reasons.
- [x] Tests, lint, format, types and own review pass; original checksums unchanged.
- [x] Documentation, Outcome and separate versioned commit complete.

## Technical notes

The accepted plan is the implementation contract. Reuse neutral geometry and
lab artifact publication; avoid a parallel production endpoint. Hold a bounded
root lock per operation. Publish dependent visual artifacts before the per-photo
commit marker. Check all manifest bindings and existing result assets on retry.
Proposals never become labels. An uncertain geometry is never silently accepted.

## Expected files

- Proposed vision_lab/symbol_batch.py: freeze, verify, process and resume.
- Proposed vision_lab/symbol_batch_review.py: gallery and aggregate evidence.
- Proposed tests/test_vision_lab_symbol_batch.py: meaningful recovery/regressions.
- Documentation: plan, VISION_LAB requirements/architecture, quality report/current state.

## Test cases

Count excess/missing, outside crop, reading order, full-component exclusion,
RGB/gray preprocessing parity, calibrated disagreement, corrupt source/asset,
retry in a fresh process after published result and unchanged original stores.

## Verification

Each Python/pytest/Ruff/mypy command uses the existing bounded run_step.py
runner and absolute worktree paths, timeout120s. Real inference runs in portions
of at most25 photos with a persistent result marker per photo. Final verification
in another process must preserve every result SHA and original store SHA.

## Risks / open questions

No human reference exists for this batch: report model agreement and review
coverage, never accuracy. Independent validation labels may be the final human
interaction. Gold-frame Super has no labels and remains untrained.

## Outcome

### Changed

Frozen/read-only inference600 photos,5396 bounded boards and80940 proposals;
full-component exclusion and exact RGB/gray preprocessing. Static full-photo/
cell review. Fixed last-file499996–500004 exceeding folder end500000:5boards,
one excess detection omitted, explicit conflict, no source edits or sequence.

### Verification results

17 new tests +11 symbol regressions:28 PASS. Ruff/lint/format/mypy PASS.
Real batch and fresh-process replay of all2404 result/gallery files PASS,
737005906 bytes unchanged, no repeated inference. Original geometry/symbol/
run-state SHAs unchanged. HTTP200/browser index smoke and contact-sheet
inspection PASS. Driver/launcher exited without orphan. Separate own review
against all criteria and plan: no unresolved P0–P2.

### Not completed

No accuracy claim on unlabelled600;15626 model-uncertain cases and3494
disagreements. No new human approvals, DB, model activation or deployment.

### Documentation updates

D-499, requirements/architecture, accepted plan and quality report
`ai_docs/quality/MUMIE_SYMBOL_BATCH_20261005.md`. Commit `v1.7.202`, full hash
recorded after commit in this Outcome and CURRENT_STATE.

### Recommended next task

Continue TASK-0857 autonomously: one bounded robustness experiment for clear
bright J/K/payline failures, unchanged human labels and validation. No need
for another routine user confirmation.
