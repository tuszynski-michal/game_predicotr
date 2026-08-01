---
title: TASK-0148 model registry and controlled activation
status: todo
last_updated: 2026-08-01
---

# TASK-0148 — Model registry and controlled activation

## Status

`todo`

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

- [ ] Każda gra ma najwyżej jedną skuteczną aktywną wersję modelu.
- [ ] Tylko kandydat z kompletnym manifestem i przejściem bramki może być
      aktywowany.
- [ ] Aktywacja oraz rollback zapisują aktora, czas, poprzednią i nową wersję.
- [ ] Job utworzony przed aktywacją kończy pracę na poprzedniej przypiętej
      wersji.
- [ ] Job utworzony po aktywacji używa nowej wersji i potwierdza checksumę
      artefaktu przed inferencją.
- [ ] Brak lub uszkodzenie artefaktu zatrzymuje nowy job ze stabilnym błędem,
      bez cichego fallbacku do innego modelu.
- [ ] Aktywacja i rollback nie modyfikują decyzji review ani predykcji.

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

Do uzupełnienia po realizacji.
