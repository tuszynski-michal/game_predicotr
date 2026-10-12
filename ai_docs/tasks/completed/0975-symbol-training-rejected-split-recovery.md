---
title: Symbol training recovery after a rejected dataset split
status: done
last_updated: 2026-10-12
---

# TASK-0975 — Recover symbol training after a rejected dataset split

## Status

`done`

## Goal

Allow a new symbol-training attempt to use the currently approved examples after an earlier attempt was rejected before training, without inheriting its unusable split.

## Context

Game `6e20a58f-88f3-4a9c-87b5-ae3297ed4fbf` has three rejected iterations. Job `564fbff5-fc29-47c8-a518-627ffa05e049` has no SLIWKA examples in TRAIN because it inherited assignments from earlier pre-training rejections. The job monitor shows completed at 0/45. The operator requested a permanent fix and confirmed neural training with separate Mumie data and weights.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Do not inherit source assignments from terminal iterations that never completed an epoch; retain the latest usable trained reference and its independent evaluation sources.
- A fresh explicit attempt after rejection can create a new immutable iteration on an unchanged cohort. Replaying the same command remains idempotent.
- Report pre-training rejection explicitly in durable job progress and the Admin monitor, including historical completed dataset-build jobs at zero epochs.
- Keep the existing neural architecture (`SpatialSymbolCnn`) shared with Mumie's RGB laboratory trainer, but never share game datasets, class catalogs, weights or activations. Train a fresh candidate of the selected game; existing imports retain pinned versions, and activation remains explicit.

## Acceptance criteria

- [x] The reported current cohort produces a complete deterministic four-way class split in a new process without changing historical iterations.
- [x] Pre-training rejection cannot poison subsequent attempts; valid trained split assignments remain stable.
- [x] Rejected unchanged-cohort retry and command replay work independently.
- [x] Rejection before the first epoch is clearly visible and does not claim successful neural training.
- [x] Focused regression tests, format, lint, type checks and docs checks pass.

## Technical notes

The minimum remains the documented coverage of every active class in four independent whole-photo groups (TRAIN, validation, test, regression). No arbitrary new sample threshold, random split per crop, evaluation leakage, automatic activation, database migration, service lifecycle operation or bulk data change. Insufficient data still fails closed. The current cohort must be checked read-only using the fixed assignment policy. This is a targeted defect repair, not execution of a larger delivery plan.

## Expected files

- `services/api/src/game_predictor_api/storage/symbol_model_iteration_repository.py` — prior split selection and terminal retry.
- `services/worker/src/game_predictor_worker/symbols/training_job.py` — rejected progress checkpoint.
- `apps/admin/src/features/jobs/job-state.ts`, `job-monitor.tsx` — rejection labels.
- Related focused tests, supervised-improvement architecture, current state and generated code map.

## Test cases

- Rejected zero-epoch assignments move all rare-class photos to controls; a fresh split contains all classes in all four groups.
- A trained candidate rejected by quality retains its source assignments.
- Rejected retry with a new command creates a separate iteration; replay returns that same iteration.
- Worker rejection records a durable rejected stage without writing training checkpoints.
- Historical and new rejected job labels differ from successful training; other job consumers retain their labels.

## Outcome

- Implementation commit: **v1.7.317**, `28d48445a16500e3172d38874b8acd6eafc98a3c`.
- The migrated checkout had no Git author configuration. Restored repository-local name/email from its existing commit history; the subsequent commit and a fresh Git process confirm persistence. Global Git settings were not changed.

### Changed

- Terminal attempts with zero completed epochs no longer establish inherited split references. Trained candidates, including quality-rejected ones, keep their evaluation assignments.
- Explicit rejected retries receive a distinct configuration nonce; command replay is resolved before split calculation and retains the original result. A changed configuration under the same command key is rejected.
- Worker checkpoints pre-training rejection explicitly; the monitor also recognizes historical completed dataset-build jobs at zero progress. Quality details identify missing symbols and the whole-photo minimum.
- Verified that production and Mumie laboratory RGB training use the same `SpatialSymbolCnn` architecture. Training starts fresh per game; no Mumie dataset, weights or activation was copied.

### Verification results

- Focused API/storage/worker tests: **20 passed** (including actual neural training, ONNX export, immutable checkpoints, cancellation/resume, pre-training rejection, retry and lost-response replay).
- Admin jobs/model-quality tests: **33 passed**.
- Ruff formatting/check: PASS for four modified Python source/test files. Prettier and ESLint: PASS for six modified Admin source/test files. Admin `tsc --noEmit`: PASS.
- Scoped mypy: PASS for the repository, training handler and repository protocol (`--follow-imports=skip --disable-error-code=unused-ignore`). The broader import traversal was interrupted after no output; this is a scoped check, not a claim of whole-repository type safety.
- Read-only fresh-process check of the reported immutable cohort: **235 samples, 27 source photos**, assignments **17 TRAIN / 4 validation / 3 test / 3 regression**, all eight classes covered in every split.
- Initial sandbox runs could not create pytest temporary folders and stalled in the API test. The isolated test run outside the sandbox revealed Windows path-length errors in the long temporary path. Using a short unique `.venv/t975-*` directory and bounded CPU thread settings made the unchanged tests pass. No user services or models were changed by tests.
- Code map regenerated; decision-link, current-state-window and code-map checks: PASS.
- `claude-audit` created `artifacts/audits/TASK-0975_BRIEF_claude.md`. Neither Claude CLI nor an independent Claude model is available in this session. No auditor ran and no PASS is claimed. This direct repair has no review assignment in an accepted delivery plan; the unavailable optional review remains a limitation.

### Not completed

- No training run, model activation, migration, restart, push or deployment on operator data. The operator can start a fresh training attempt through `Ulepsz rozpoznawanie`.
- The minimum remains every active symbol represented in four independent source-photo groups. Arbitrary numbers of near-duplicate crops do not guarantee an independent evaluation set.

### Documentation updates

- Supervised-improvement architecture, current state, this task and generated code map.

### Recommended next task

- Run a new symbol-training attempt for the reported game and inspect its candidate gate before explicit activation. Reload the worker manually if its process predates the checkpoint-label change; API/Admin hot reload applies the current checkout's changes.
