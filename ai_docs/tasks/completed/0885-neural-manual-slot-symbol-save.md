# TASK-0885 — Save symbols on an operator-approved neural slot

## Status

`done`

## Goal

Save an explicitly selected symbol on a corrected neural board while sibling slots still await geometry review.

## Context

The operator's board 1405 failed with IMAGE_GRID_REVIEW_SYMBOL_CELL_UNAVAILABLE for cell 4. Read-only SQL confirms the entire transaction rolled back: the slot is pending, with no board or cells. All 24 proposed nodes are inside the 1520×1054 source. D-484 withholds the new projection because another slot is pending, despite the operator's explicit board geometry save. D-521's individual neural correction workflow and D-488 symbol save require a narrow exception.

## Dependencies / entry conditions

MAIN v1.7.226 /4e73b92cd3b135496b42a836edeb1f979e8de46a, branch v1.1-vision-lab-hybrid-geometry. Existing metadata edits and .claude files are excluded. Prior authorization covers correcting and running the Mumie workflow. No production data surgery is necessary.

## Recommended execution

gpt-6.1-sol, high. One bounded transaction/gate regression; perform the implementation and self-review in the current task. Escalate a missing provenance or contract decision instead of weakening crop checks. No delegated work.

## Relevant docs

- AGENTS.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/DECISION_LOG.md: D-484, D-488, D-521, D-522
- ai_docs/requirements/ADMIN_APP.md: correction grid
- ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/architecture/API_CONTRACT.md: D-488
- ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md

## Scope

- Admit only the current explicitly human-approved manual lattice of a bound neural slot to its cell projection. Sibling slots and the source's incomplete status remain unchanged.
- Classify visibility from the exact lattice used for rendering.
- Preserve transactional symbol assignment, crop identity, CAS and idempotent replay.
- Verify fresh-process runtime and deploy the backend fix using owned-process guards.

## Out of scope

Legacy 777 behavior, source-wide implicit exception, migration, cleanup, reimport, training, model activation, Super, push.

## Acceptance criteria

- [x] A complete manual neural lattice in an incomplete source creates its 15 current cells and approves only the operator-selected symbol.
- [x] Unapproved proposals, stale approvals, legacy corner grids and other pending slots retain D-484 fencing.
- [x] Outside cells cannot be approved; exact interior nodes determine visibility.
- [x] The HTTP transaction survives a fresh app/session and an identical retry without duplicate events.
- [x] Production board 1405 is inspected without fabricating an operator label; the live API runs the fixed code.

## Technical notes

The explicit Save authorizes geometry for one board. It is not approval of the full source or all predicted symbols. D-522 records this interpretation of the operator's existing request. An optional domain gate input defaults false, supplied only for a current human-approved manual_v1 lattice retaining a neural proposal checksum. The correction transaction may use this board's exact current cells while the game projection is rebuilding without an error; general symbol mutation and failed projection gates remain unchanged. All provenance, render, source availability and mutation validations remain. API payloads and cellSymbols are unchanged. No user decision blocks this repair.

## Expected files

- services/api/src/game_predictor_api/domain/image_geometry_completeness.py: geometry_gate_withholds_board
- services/api/src/game_predictor_api/storage/image_geometry_completeness_state_repository.py: withheld_review_item_ids
- services/api/src/game_predictor_api/storage/image_symbol_review_repository.py: correction-specific current-board readiness
- services/api/src/game_predictor_api/storage/symbol_cell_source_visibility.py: current_source_visibilities
- services/api/tests/test_image_geometry_completeness_domain.py
- services/api/tests/test_symbol_cell_source_visibility.py
- New services/api/tests/integration/test_neural_manual_slot_symbols_postgres.py
- ai_docs/process/CURRENT_STATE.md, DECISION_LOG.md and the relevant correction documentation

## Test cases

Real renderer and isolated PostgreSQL: two deferred slots, incomplete source, manual lattice, cell 4 selection → selected approval only, sibling pending, source still incomplete. Fresh HTTP app and repeated key → same revision/events. Default four-corner gate and absent/stale approval → still withheld. Exact lattice visibility and truly outside cells → fail closed.

## Verification

Use the repository finite runner (120 seconds each) with pytest for scoped domain/visibility and guarded PostgreSQL tests, followed by Ruff/format and scoped mypy. PostgreSQL fixture must create only its uniquely named *_test database and tear it down. The live check is read-only; API restart requires fresh identity, health and no active jobs. Planned checks are not execution results.

## Risks / open questions

No blocking product question. The operator's unsaved browser choice is not available in this session; retain it and never invent a replacement label. The completion version is v1.7.227 based on actual MAIN history.

## Outcome

Implemented and deployed in MAIN on v1.1-vision-lab-hybrid-geometry. Completion version v1.7.227; full commit hash recorded after commit.

- Reproduced the actual cell-4 error with a real renderer and isolated PostgreSQL before applying the fix. The initial projection fix exposed the additional rebuilding-state gate; both causes are covered by the final regression.
- Scoped domain/visibility/virtual geometry checks: 143 passed. Real PostgreSQL HTTP regression: passed, including 15 current cells, one selected human approval, sibling/source fencing, fresh-app idempotent replay, outside-cell rollback and visible partial-cell success. Only the fixture's uniquely named disposable *_test database was created and removed.
- Ruff lint and formatting: passed for all seven owned files. Strict scoped mypy with normal owned imports: passed; only third-party Torch/torchvision/ONNX modules were skipped through the existing scoped configuration.
- Broader projection/virtual/grid/API suite: 84 passed, one unrelated failure in test_list_endpoint_uses_keyset_cursors_without_duplicates. Its old expected list timeout is 5000 ms, while the existing configuration applies 20000 ms and 15000 ms for counts. The test was not weakened or changed.
- Read-only live SQL confirmed board 1405's rolled-back save and intact bound source. No production label was guessed or submitted. A fresh pre-restart preview confirmed no active import, training or lifecycle job. Exact process identities were checked before stopping the owned API pair.
- API root 46320 / listener 47872 started at 19:17:51 UTC with the fixed MAIN code. The launch helper's initial 10-second readiness window expired; subsequent bounded checks confirmed the same existing process listening on 8000, successful startup and healthy API. No second API instance was launched. Admin, Reviewer and workers were preserved.
- Evidence: artifacts/mumie-main-app-pilot-20261006/board-1405-readonly.json and 0885-live-verification.json; finite check receipts in artifacts/grid-v3-deployment-20261004/0885-*.json. No API contract change, frontend build, migration, training, model activation, data cleanup or push.
- Definition of Done and this task's acceptance criteria reviewed individually. The remaining operator action is to retry their selected symbol save on 1405; the operator's browser choice was not available for an automated production submission.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0885 | gpt-6.1-sol | high | Bounded gate and transaction regression with crop provenance protection. | Self-review; no delegation. |
