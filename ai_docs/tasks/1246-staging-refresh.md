---
title: Activate trained Mumie A2 grid model and process two staged folders
status: in_progress
last_updated: 2026-11-17
---

# TASK-1246 — Refresh staging with trained Mumie A2 model

## Status

in_progress — operator approved the additional repair, tests, review and processing cost.

## Goal

Activate the already trained candidate and process both explicitly selected staging
folders into grids and pending symbol verification, preserving existing human work.

## Context

The operator explicitly requested activation and processing of staging 40ceb31e
(2778 photos) and 2e027bed (2789 photos). This authorizes these existing data
operations, not another training run, source deletion or unrelated model changes.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`

## Scope

- Verify ownership, immutable staging manifests and absence of previous imports.
- Recheck existing evaluation currentness; publish and activate candidate
  6cc10344-1d69-5765-b8c8-423a0313984a through owner API/CAS commands.
- Preserve model default and symbol-model assignment; activate only Mumie A2 grid model.
- Create new geometry preflights pinned to this candidate for both folders.
- Use existing import/crop workflow to expose pending symbols for human verification.
- Verify actual model pins, source/board/cell counts, completion and review readiness.
- Repair explicit browser preflight creation to resolve current assignment when
  the staging has no human detection bindings. Keep frozen import/resume and
  binding-backed requests unchanged; existing service callers retain defaults.

## Acceptance criteria

Code acceptance is reviewed before deployment; the live-data checkboxes below
remain pending until the reviewed fix is deployed and those operations complete.

- [x] Existing browser request selects current assignment without an API change.
- [x] Repeated request after new service creation returns the same persisted job.
- [x] A different active version cannot reuse old-model geometry entries.
- [x] Legacy service consumers, saved binding identity and frozen imports stay intact.

- [x] New grid model is assigned to Mumie A2 with a durable activation receipt.
- [ ] Both new preflights pin that exact model and retain old artifacts/corrections.
- [ ] Both imports complete and pending symbol crops are accessible in Symbol Verification.
- [ ] Missing/unbound/blocked sources are explicitly reported; no guessed sequence binding.
- [ ] Fresh-process read confirms persistent results and unchanged original staged files.

## Expected files

`application/jobs.py` (`create_page_geometry_preflight_job`,
`_neural_preflight_snapshot`), `api/image_imports.py`
(`start_browser_page_geometry_preflight`), focused API regression tests,
IMAGE_INGESTION and ITERATIVE_IMAGE_IMPORT docs, generated code maps, this task,
CURRENT_STATE/archive and quality evidence. HTTP request/response stays unchanged;
there is no schema migration or new dependency. Root's 45 existing changes stay separate.

## Verification

Bounded local owner API reads/writes with stable command keys, recorded job IDs,
SHA checks and fresh-process final reads. Inspect actual jobs and symbol review
projection; no synthetic benchmark, GPU training or broad test suite is needed.
Focused regression tests cover new-model selection, lost-response replay in a new
service, rejection of old-model entry reuse, saved detection bindings and old frozen
import pins. Run changed Python lint/format/types, code-map/docs/OpenAPI checks and
the approved independent Claude review before the code commit/deployment.

## Risks / open questions

- Current report's 25 cohort notices were proven current before activation.
- Unbound source skipping needs explicit operator confirmation of the actual count.
- Protected existing human corrections and source bytes must remain intact.
- Root checkout has 45 operator modifications; documentation work is isolated.

## Outcome

Initial inspection confirms both folders belong to Mumie A2, are ready and have no
prior imports. Stable commands/receipts: `.runtime/new-model-stagings-state.json`.
Initial publication with an evaluation job ID was rejected without mutation;
the supported command uses report ID e74c552e-25e3-55dd-884f-3d0a4feb0c8e.
The supported currentness recheck finished successfully: noticeCount=25,
provenNoticeCount=25, proof time 2026-11-17T18:12:31.937305Z. Its HTTP response
was lost, but fresh API reads confirmed the committed proof before activation.
Publication revision 1 and Mumie A2 assignment revision 7 succeeded through
the supported owner endpoints. Global default remains 01767a49, revision 5.

The first geometry-preflight request also lost its HTTP response. A fresh job-list
read recovered job b568b69f-6bdd-4bce-b1fc-d7a994c5ea9b for staging 2e027bed,
created 2026-11-17T18:18:07.682316Z. Its actual frozen model is OLD abe39bce,
despite the game already being assigned to NEW 6cc10344. The API implementation
`JobService._neural_preflight_snapshot` reuses a completed staging snapshot before
resolving current game assignment. A second request would reproduce the same issue.
No import/crop job was started and no old result or human correction was deleted.
The first preflight is allowed to finish harmlessly; it is not accepted as a result
of the requested new-model processing.

The operator was asked once to approve 45–90 minutes of additional repair,
targeted tests and independent review, followed by the requested processing.
The operator answered "Tak, napraw i przetwórz oba stagingi", approving that cost.
Implementation is restricted to the existing browser-preflight operation. The
internal optional `use_current_model` flag defaults false for existing consumers;
the new-staging browser action sets true; managed-source requests retain false.
Without local human detection bindings it
resolves the active assignment rather than searching old completed jobs. Local
saved bindings keep their exact frozen proposal because detection IDs cannot be
transferred between models. Neither selected staging has such bindings. Existing
manual quads, old manifests/imports and resume commands remain immutable.
Evidence: `.runtime/new-model-stagings-state.json`,
`.runtime/new-model-stagings-active-assignment.json`,
`.runtime/new-model-stagings-activation-and-blocker.json`.

### Repair validation before independent review

- The new HTTP regression failed against unmodified HEAD at the expected model
  comparison: legacy v1 staging snapshot instead of the current v2 catalogue snapshot.
- After the 9-line production change: 119 tests PASS in 105.99 s across
  `test_browser_preflight_current_model.py` (8 cases), `test_neural_page_geometry_api.py`,
  `test_jobs_domain.py` and `test_image_imports_api.py`.
- Scoped ruff check/format PASS for both production files and the regression test.
- OpenAPI export `--check` PASS: request/response and generated client are unchanged.
- Import-isolated mypy has the exact same 36 messages on HEAD and repaired code;
  with its pre-existing import artifacts (`no-any-return`, `misc`) disabled, both
  changed modules PASS. Evidence: root `.runtime/task1246-typecheck.json`.
  A full-import attempt timed out at 115 s; no remaining process was found. Full
  project typecheck is not claimed. No tests were skipped or weakened.
- Code maps regenerated; map freshness, docs/window/startup budgets and diff checks PASS
  (startup read 44,719 bytes). Independent audit is pending.
- Data work remains pending: do not treat old-model job b568b69f as new-model success.

### One correction round after independent review

Round 1 returned REVISE (0 P0, 1 P1). Its report and receipt remain byte-for-byte
in `ai_docs/quality/TASK-1246_AUDIT_ROUND1_claude-opus-5-5.*`.

- P1-1: the browser opt-in is now `managed_source_job_id is None`. Two HTTP
  regressions prove managed-source preparation retains the old model after assignment
  changes, including manual-quads-only and source-exclusion-only corrections.
- P2-1: the previous model's job is completed with a real SHA-bound, valid manifest
  before switching assignment. The test first proves that artifact can be reused
  under its own model, then proves it is absent as a base for the next model.
- Final code: 121 tests PASS in 83.91 s across the same four files. All 10 focused
  cases and the existing 111 regressions pass; no baseline failures or skips.
- Scope remains unchanged: only new, unimported staging preparation follows the
  active model; existing managed-source operations preserve their previous choice.
- Read-only preservation preview retains 45 root changes; only generated maps and
  CURRENT_STATE overlap. The merged startup-budget preview passes. The own prior
  P2 pointer is shortened; the earlier operational note remains in its task file.
- The task filename was shortened to `1246-staging-refresh.md` for that startup
  budget; task identity, code and original audit evidence are unchanged.
- Focused round-2 audit PASS, 0 P0/P1/P2; both earlier findings closed. Main report:
  `ai_docs/quality/TASK-1246_AUDIT_claude-opus-5-5.md` and its validated receipt.
  Payload SHA `afabebcb7ed998b3d1ba65afa8a60bc91a9beb16d38f1d6d4652ac5ec50dc899`,
  report SHA `1c3f94a90803c70d091002eb94efd356e706bf635f62caf4df10a63179f792eb`.
- Final scoped format/lint/types, docs and code-map freshness PASS. No further code
  change after the audit. Full project typecheck is not claimed (scope above).
- All 5567 staged source-file byte checksums match their existing manifests;
  immutable baseline `.runtime/new-model-stagings-source-baseline.json` is preserved.
  Filename-attested ranges: 40ceb31e = 373591–398592 (25002 positions),
  2e027bed = 398584–423684 (25101 positions). They overlap in 9 positions;
  import will use canonical ownership, without inventing or overwriting sequences.
- No deployment/merge or import has been performed; model activation is already done.

## Repair execution

1. Add the internal opt-in and bind the existing browser action to it; no new API field.
2. Reproduce the old-model regression and verify fresh-process replay and protected bindings.
3. Run scoped checks and Claude read-only audit; commit the reviewed repair while
   the operational task remains in progress.
4. Present the concrete code result for integration/deployment approval required by
   the repo. Then create both correctly pinned preflights, import and verify pending
   symbol crops. Close the task only after its live operations finish; final evidence
   commits and cleanup stay in this same approved integration scope.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1246 | gpt-6.2-sol | high | Wąska poprawka istniejącego wyboru modelu oraz kontrolowane operacje na dwóch stagingach; rozszerzenie ochrony danych wymaga ponownej analizy. | claude-opus-5-5, high; kod i regresje, tylko odczyt |
