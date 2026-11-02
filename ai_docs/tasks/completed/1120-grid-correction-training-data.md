---
title: Dane z korekt i trwały podział
status: done
last_updated: 2026-11-02
---

# TASK-1120 — Dane z korekt i trwały podział

## Status

`done`

## Goal

Wykonać T1 zaakceptowanego planu uczenia wspólnego modelu siatek z zapisanych korekt.

## Context

Operator ma ponad 100 poprawionych plansz Mumie A2 i potrzebuje uczenia bez ręcznej rejestracji nagrań. Liczba jest deklaracją, nie pomiarem kwalifikujących się danych.

## Dependencies / entry conditions

READ-ONLY preflight przed kodem; raport liczby human approvals, zdjęć, atestów, aliasów i możliwości splitu. Brak splitu zgłosić przed implementacją; nie rozluźniać minimów.

## Recommended execution

gpt-6-astra/high, według tabeli planu. Obowiązkowy niezależny audyt Claude Code claude-opus-5-5/high przed commitem; P0/P1 blokują commit. Niedostępność przypisanego modelu wymaga jawnej aktualizacji, bez niejawnej zamiany.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- [Plan i pełny zakres T1](../../delivery/GRID_CORRECTIONS_LEARNING_PLAN_20261102.md)
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`, `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/VISION_LAB.md`, `ai_docs/architecture/CODE_MAP.md`
- [D-554](../../process/decisions/DECISION_LOG_2026.md#d-554--nagrania-i-ochrona-danych-kontrolnych-geometrii-v3)
- [D-556](../../process/decisions/DECISION_LOG_2026.md#d-556--niezmienne-kohorty-geometrii-v3-i-aktualność-dowodów)
- [D-559](../../process/decisions/DECISION_LOG_2026.md#d-559--ocena-kandydata-geometrii-v3-per-gra-i-most-aktualności-dowodów)

## Scope

Pełna sekcja T1 planu; zasady i minima z planu są obowiązujące.

## Out of scope

Trening na danych operatora, zmiana defaultu lub przypisań, migracja bazy operatora, restart usług, merge/push; klasyfikator symboli i uczenie detektora całego ekranu.

## Acceptance criteria

- [x] Korekty bez resave; tylko geometrie human-approved24; wiarygodne atesty i kopie; trwałe role/bufory po freeze; provisional preview bez trwałego użycia.
- [x] Właściwe testy, lint/typecheck i dokumentacja.
- [x] Audyt Opus 5.5/high bez otwartych P0/P1.
- [x] Outcome, task-close, osobny wersjonowany commit i record-hash.

## Technical notes

Przed kodowaniem ponownie odczytać ten task i sekcję T1 planu. Chronić istniejące polityki/snapshoty/raporty; nowe reguły wersjonowane. API zmieniać jednym pionem. Mutacje operatora wyłącznie z osobną zgodą. Podgląd nie tworzy dowodu faktycznego użycia danych.

## Expected files

Istniejące moduły wejściowe (ścieżki usług względem ich katalogów src): storage/grid_training_cohort_evidence.py; domain/grid_training_cohorts.py; storage/source_recording_groups.py. Nowe pliki wskazać w Outcome przed audytem.

## Test cases

Scenariusze T1 i T4 w planie: minima, brak danych, nowe/stare polityki, aliasy, restart, utracona odpowiedź, konflikty rewizji; zakres testów odpowiedni do zmienionego pionu.

## Verification

Polecenia ustalić z package.json/pyproject i istniejących testów. Każda skończona komenda z timeout <=120 s; build po uprzedzeniu, audyt <=600 s zgodnie ze skillem. Nie uruchamiać szerokich benchmarków.

## Risks / open questions

Preflight i rzeczywista kwalifikacja danych mogą zatrzymać implementację przed błędną obietnicą użycia korekt. Wynik pomiaru należy zapisać w Outcome.

## Outcome

Commit: v1.7.517 / `e1fcae27dace97c5dea102a05c512b9bf77ec94c`.

### Wynik niezależnego audytu i pozostałe ryzyka

Claude Code `claude-opus-5-5/high`, runda 2: **PASS**, bez P0/P1.
Raport: `ai_docs/quality/TASK-1120_AUDIT_claude-opus-5-5.md`.
Runda 1 zachowana w `artifacts/audits/`. Jedna runda poprawek zakończona.
Pozostałe P2 nie blokują tego taska: historyczne kohorty i poprawne dopuszczenie
oceny nowej polityki (P2-5/P2-7) należą do TASK-1121; pełny mypy i dokończenie
starszych ścieżek integration (P2-6/P2-8) do TASK-1123. Koszt nakładki
legacy (P2-9) pozostaje jawnym ryzykiem do kontroli w T4, bez deklaracji
wydajności ani zlecania nieautoryzowanych benchmarków.

### Focused independent recheck request

Koordynator zleca rundę 2 w Claude Code claude-opus-5-5/high wyłącznie dla
zamknięcia findings z raportu `ai_docs/quality/TASK-1120_AUDIT_claude-opus-5-5.md`
po jednej rundzie poprawek zmieniających zachowanie objęte P1. Nie jest to
nowa implementacja ani nieograniczona pętla audytów. Raport powinien oznaczyć
`Runda: 2` i zweryfikować dyspozycję P1-1/P1-2 oraz P2-1–P2-6 z tego Outcome.
Wyniki wcześniejszych testów ograniczonych środowiskiem nie są deklarowane
jako pełne PASS. Pełna bramka mypy pozostaje w T4 przed integracją.

### Changed

- D-577 records the operator-approved verified-attestation fallback. The existing
  cohort service now accepts explicit `application-grid-corrections-v1`, grid-only,
  whole-import selection; legacy defaults and policies remain unchanged.
- Pure bounded deterministic solver considers one to three consecutive role blocks
  per ordered import, all permutations, alias/session constraints, ten-photo buffers,
  minima and the 70/15/15 objective. Work limits return explicit errors, not partial optima.
- Metadata adapter reads genuine existing human proofs without resaving corrections,
  pins all selected sources and revisions, counts partial controls, deduplicates exact
  copies and checks population/registry/label drift before materialization and freeze.
- Alembic 0170 extends the existing private recording capability with immutable
  photo uses and BUFFER reservations. Freeze registers them atomically; known aliases,
  sessions, protected uses and legacy cohort consumers share the protection.
- Backend/OpenAPI/generated client/wrapper/request test form one opt-in API change.
  No service, operator migration, training, model activation or push was performed.

### Files for review

- New: `services/api/src/game_predictor_api/domain/grid_correction_split.py`;
  `storage/grid_correction_split.py`, `storage/source_recording_sql_v4.py`,
  `storage/source_recording_permissions_v4.py` under the same package;
  `services/api/alembic/versions/0170_grid_correction_photo_roles.py`.
- Cohort integration: `application/grid_training_cohort_commands.py`,
  `application/grid_training_cohort_freeze.py`, `domain/grid_training_cohorts.py`,
  `storage/grid_training_cohort_{currentness,evidence,repository}.py`,
  `storage/database_roles.py`, `schemas/grid_training_cohorts.py`,
  `api/grid_training_cohorts.py` under `game_predictor_api`.
- Tests: `services/api/tests/test_grid_correction_{split,split_adapter,cohort_contract}.py`
  and `services/api/tests/integration/test_grid_correction_registry_postgres.py`.
- Client: `packages/admin-api-client/{openapi/openapi.json,src/generated/types.gen.ts,
  src/index.ts,test/grid-training-cohort-request.test.mjs}`.
- Documentation: plan, D-577/index rollover, VISION_LAB requirements/architecture,
  generated CODE_MAP/SYMBOLS, this task and CURRENT_STATE. Earlier preflight report
  remains historical evidence of the blocker resolved by the operator's decision.

### Verification results

- Preflight: actual `mumie-aktu2` has 117 current human-corrected 24-node boards on
  89 photos; 788 original files and verified attestations exist. Logical import names
  are managed SHA paths. The similarly named `mumie-a2` has no photos.
- Core legacy suite: 48 PASS. Existing HTTP plus new policy contract: 18 PASS.
  Adapter, storage and solver suites: 38 PASS (including 17 pure solver cases).
- Disposable PostgreSQL migration/application-role test: PASS (final rerun 34.68 s); atomic rollback,
  durable new-session READ ONLY validation, cross-game byte-alias buffer protection,
  RLS scope and private privileges. Fixtures contain metadata, not fabricated human proofs.
- Final adapter/contract check after label-count fencing: 7 PASS (3.31 s).
- OpenAPI export, generated client, TypeScript client typecheck and request test: PASS.
- Ruff check and format: PASS for all 18 changed/new Python files.
- Mypy `--follow-imports=silent`: PASS for all 13 changed production modules.
  Generated-client drift check: PASS. Code map regenerated; all four docs:check
  components PASS (startup 44261/45000 bytes; state window 15348 bytes).
- Commands use `D:/game_predicotr/.venv/Scripts/python.exe`, explicit worktree
  PYTHONPATH and bounded subprocess timeouts (110 s). Restricted Windows TestClient
  stalled; the same bounded test with normal dependency access passed. Broad mypy
  initially timed out; `--follow-imports=skip` is not a valid substitute (dependency
  Any errors), so it is not claimed as a passing check.

### Not completed

- Required independent Claude Code Opus 5.5/high audit, findings disposition,
  task-close, versioned commit and record-hash remain the coordinator's next gate.
- Worker training/evaluation/report consumers are TASK-1121. They intentionally
  reject the new policy until that task supplies the complete versioned contract.
- No operator dataset was frozen or used for training. Unknown session/history
  evidence remains an explicit photo-only limitation; buffer separation is not proof
  of independent capture sessions.

### Documentation updates

D-577, requirements, architecture, plan clarification and code map describe the final
implementation. Decision and migration number collision checks covered local branches.

### Recommended next task

Audit TASK-1120 before commit; then TASK-1121, within the accepted whole-plan scope.

### Audit disposition — one correction round

Read the complete `quality/TASK-1120_AUDIT_claude-opus-5-5.md` (Opus 5.5/high,
REVISE: two P1 and six P2). No second audit or commit was started by the executor.

- P1-1 addressed: the legacy wrapper checks only `photoRoles` from immutable
  `recording_photo_uses`, including byte/pixel/component aliases. It delegates all
  earlier role-head/holdout/ancestor semantics to the original family-aware function.
  Legacy storage regression freezes and validates REGRESSION with `final_test`
  and VALIDATION with an unused TRAIN head in a different family.
- P1-2 addressed in code/tests: label-count drift rejects capture before publication;
  registry proof drift rolls back without partial reservations. The PostgreSQL
  service workflow covers prepare, capture, materialize, freeze, fresh-session
  replay of prepare/pages/freeze and stale CAS. Its explicit substitutes are at
  human-proof and image boundaries; it does not claim fabricated metadata is a
  human approval. The separate genuine-label legacy e2e remains required evidence.
  New guards reject legacy TRAIN against control/buffer/unlabelled reservations.
- P2-1 addressed: all assigned sources, including unlabelled and duplicate sources,
  receive immutable reservations. `used_in_cohort` preserves the distinction from
  actual examples; snapshots retain metadata, and only 20 used examples copy bytes
  in the 41-source regression. Used-role minima remain based only on actual examples.
- P2-2 addressed: adapter failures preserve available photo/board counts in the
  existing error message contract; a minima regression verifies the values.
- P2-3 addressed: the population fingerprint pins source identity and attestation
  facts/bindings plus attestation validity, not revision UUID or unrelated status.
  An unchanged attestation on a new active revision preserves the fingerprint;
  reverted evidence, changed bindings and removed membership invalidate it.
- P2-4 addressed: single-run preview and shared planning reject the new policy with
  `GRID_RUN_POLICY_UNSUPPORTED` before a job can be created. Unit/API regressions pass.
- P2-5 explicitly retained as a delivery dependency: D-577 and the plan assign
  historical/shared-base cohort composition to TASK-1121's existing shared-candidate
  service and worker reader. T1 provides immutable versioned input, not a claim
  that base-cohort composition is already implemented. The API gate stays closed.
- P2-6 deferred explicitly to the TASK-1123 pre-merge full Python typecheck gate.
  Targeted `--follow-imports=silent` checks pass; full strict check is not claimed.

Correction-round validation: Ruff 22 Python files PASS; targeted mypy 15 production
modules PASS; 17 adapter/contract/run-preview tests PASS; schema-head regression
17 PASS. Alembic 0170 uses exact existing capability column grants, without broad
SELECT grants. `schema_readiness` and its explicit-head test now require 0170.

Required PostgreSQL suites, each bounded independently to 110 seconds:

| Suite | Result |
|---|---|
| `test_grid_correction_registry_postgres.py` | PASS, 43.76 s; registry drift, reservations, legacy guards and complete service replay/CAS |
| `test_grid_training_cohort_storage_postgres.py` | 2 PASS, 63.77 s; migration down/up, old family-aware semantics, fresh READ ONLY validation |
| `test_grid_model_evaluation_bridge_postgres.py` | BLOCKED by pre-existing hardcoded head `0168_source_crop_runs`, 24.71 s. HEAD already contains 0169 and the same stale assertion; unrelated test left unchanged. |
| `test_grid_model_evaluation_e2e_postgres.py` | BLOCKED at unchanged worker `_write_atomic` after successful freeze/evaluation queue, 100.79 s: FileNotFoundError on a long worktree artifact path. No worker change in T1. |
| `test_grid_training_cohort_e2e_postgres.py` | TIMEOUT at outer 110 s after successful `frozen_committed` (97.344 s) and `restart_replay_eligible` (100.125 s); child dataset/final checks not completed. No orphan test process. Exact owned database/OID and two marked roles cleaned with existing ownership helper. |
| `test_recording_migration_lifecycle_postgres.py` | 5 PASS in two bounded invocations: empty down/up/reprovision 24.00 s; four remaining cases 64.56 s. |

The coordinator owns focused Opus recheck of the P1 correction and its final disposition;
open P0/P1 still block task close and commit. No unrelated baseline fixes were added.

Final correction-round notes: `schema_readiness` mypy PASS separately (16 production
modules checked in total); its 17 unit tests PASS. The evaluation fixture constructs
its artifact path from the test file's repository root, ignoring pytest basetemp;
no repeat with an ineffective shorter basetemp or worker change was made. The code
head is updated for 0170 as part of migration delivery, not a baseline test workaround.
All five audit-requested legacy PostgreSQL suites were attempted and their actual
limits/errors are above; no full-suite PASS is claimed. P1 disposition awaits the
coordinator's focused review of the stable correction diff.
