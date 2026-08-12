---
title: TASK-0148 model registry and controlled activation
status: done
last_updated: 2026-08-01
---

# TASK-0148 — Model registry and controlled activation

## Status

`done`

## Goal

Dodać niezmienny rejestr wersji modelu per gra oraz jawną, audytowalną
aktywację i rollback kandydata, bez zmiany trwających importów.

## Context

Produkcja obecnie wskazuje stały bootstrapowy artefakt. Iteracyjne uczenie
wymaga aktywnego wskaźnika per gra i przypięcia dokładnej wersji do joba.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/MILESTONE_06_6_EXECUTION_PLAN.md`
- `ai_docs/tasks/0147-candidate-onnx-calibration-and-regression-gate.md`

## Scope

- dodać migrację rejestru iteracji i historii aktywacji per gra,
- wyprowadzić aktywny model z danych zamiast stałej ścieżki w workflow,
- dodać preview i jawne potwierdzenie aktywacji tylko `candidate_ready`,
- dodać kontrolowany rollback do wcześniej poprawnej wersji,
- atomowo aktualizować wskaźnik oraz zdarzenie audytowe,
- przypinać identyfikator, manifest SHA-256 i fingerprint modelu podczas
  tworzenia image import joba,
- pokazać aktywny model, historię i wynik operacji w Adminie.

## Out of scope

- automatyczna promocja po treningu,
- przełączanie modelu w już trwającym jobie,
- przeliczanie istniejących oczekujących elementów.

## Acceptance criteria

- [x] Każda gra ma najwyżej jedną skuteczną aktywną wersję modelu.
- [x] Tylko kandydat z kompletnym manifestem i przejściem bramki może być
      aktywowany.
- [x] Aktywacja oraz rollback zapisują aktora, czas, poprzednią i nową wersję.
- [x] Job utworzony przed aktywacją kończy pracę na poprzedniej przypiętej
      wersji.
- [x] Job utworzony po aktywacji używa nowej wersji i potwierdza checksumę
      artefaktu przed inferencją.
- [x] Brak lub uszkodzenie artefaktu zatrzymuje nowy job ze stabilnym błędem,
      bez cichego fallbacku do innego modelu.
- [x] Aktywacja i rollback nie modyfikują decyzji review ani predykcji.

## Technical notes

Aktualny model bootstrapowy powinien zostać zarejestrowany jako jawna wersja
bazowa przez migrację danych lub kontrolowany bootstrap, aby nie było dwóch
równoległych mechanizmów wyboru modelu.

## Expected files

- `services/api/alembic/versions/*_symbol_model_registry.py`
- `services/api/src/game_predictor_api/`
- `services/api/tests/`
- `services/worker/src/game_predictor_worker/images/production_workflow.py`
- `services/worker/src/game_predictor_worker/`
- `services/worker/tests/`
- `apps/admin/src/features/model-quality/`
- `packages/admin-api-client/`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
python -m pytest services/api/tests -q
python -m pytest services/worker/tests -q
npm.cmd run openapi:check
npm.cmd test --workspace @game-predictor/admin
```

## Risks / open questions

- Migracja bootstrapowego modelu musi zachować obecne fingerprinty pipeline'u
  dla historycznych jobów.

## Outcome

Migracja `0037_symbol_model_registry` dodaje append-only historię aktywacji z
monotonicznym `activation_number`, idempotencją i checksumą komendy. Preview,
aktywacja, rollback i bounded historia mają typowany kontrakt OpenAPI oraz UI w
sekcji jakości modelu. Resolver przypina nowemu image importowi pełny,
checksum-bound snapshot aktywnego modelu; import historyczny zachowuje jawny
bootstrap. Efektywny fingerprint pipeline'u obejmuje model, więc predykcje nie
przechodzą z cache między wersjami.

Weryfikacja 2026-08-08:

- API rejestru, snapshotu, jobów, importów i migracji: 62/62 passed przed
  doprecyzowaniem porządku; finalna regresja rejestru/migracji: 34/34 passed,
- worker workflow, pinning, drift i bramka: 19/19 passed,
- Admin: 176/176 passed; typecheck i skupiony ESLint: passed,
- Ruff API/workera/skryptów i aktualność OpenAPI/generowanego klienta: passed.

Lokalna baza pozostaje na 0035 do kontrolowanego zakończenia bieżącej selekcji;
nie jest to obejście implementacji. Przed użyciem endpointów rejestru operator
wykonuje standardowe `npm run db:migrate` przy zatrzymanych workerach.
