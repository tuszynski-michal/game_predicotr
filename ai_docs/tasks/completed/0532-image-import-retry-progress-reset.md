---
title: TASK-0532 — Świeży postęp przy ponowieniu importu zdjęć
status: done
last_updated: 2026-09-14
---

# TASK-0532 — Świeży postęp przy ponowieniu importu zdjęć

## Status

`done`

## Goal

Ponowienie nieudanego importu `image_directory` zachowuje trwałe checkpointy
plików, lecz rozpoczyna agregację joba od zera, aby odtworzony stan nie wywołał
fałszywego `JOB_PROGRESS_REGRESSION`.

## Context

Po ponowieniu 143 błędnych plików job zachował wcześniejsze agregaty
`2343/4400`. Worker poprawnie odczytał mniejszy stan terminalny z asocjacji
plików V2, ale monotoniczna ochrona postępu uznała go za cofnięcie.

## Dependencies / entry conditions

- TASK-0529, TASK-0530 i TASK-0531 naprawiły zapis V2, projekcję plansz oraz
  operacje retry plików.
- Powiązania plików są trwałym źródłem prawdy o etapach; agregaty joba są
  odtwarzaną projekcją techniczną.
- General worker jest zatrzymany, a job pozostaje `failed`.

## Recommended execution

`gpt-5.6-sol high`; zmiana dotyczy semantyki retry trwałego workflowu oraz
ochrony monotonicznego postępu. Dodatkowy review nie jest wymagany, jeśli test
regresyjny potwierdzi reset wyłącznie agregatów joba i ten sam job przejdzie po
restarcie workera.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`

## Scope

- Dla retry joba `import/image_directory` użyć istniejącego resetu postępu.
- Zachować UUID, input payload i wszystkie checkpointy per plik.
- Dodać test regresyjny dla stanu odpowiadającego awarii 2343/4400.
- Ponowić i monitorować wskazany job użytkownika do poprawnej granicy
  `waiting_for_review` albo `completed` bez błędnych plików.

## Out of scope

- Zmiana kontraktu API lub schematu bazy.
- Usuwanie stagingu, plików albo danych gry.
- Reset checkpointów per plik i ponowne wykonywanie ukończonych etapów.

## Acceptance criteria

- [x] Retry `image_directory` zeruje techniczne agregaty i checkpoint joba.
- [x] Retry zachowuje tożsamość oraz input payload joba.
- [x] Test regresyjny, Ruff i mypy przechodzą.
- [x] Job `1a1cff95-436e-4054-ae1f-8ef4565cd7b0` osiąga poprawną granicę
  terminalną bez `failed` plików.

## Technical notes

`JobService.retry_job` powinien wybrać `requeue_job_with_fresh_progress` dla
`JobType.IMPORT` z `import_kind == image_directory`. Funkcja czyści wyłącznie
agregaty, błąd i checkpoint joba; stan `image_import_job_files` pozostaje
nienaruszony i zostanie ponownie zagregowany przez handler.

## Expected files

- Istniejący: `services/api/src/game_predictor_api/application/jobs.py` —
  wybór semantyki retry.
- Istniejący: `services/api/tests/test_jobs_api.py` — regresja serwisu.
- Istniejący: `ai_docs/process/CURRENT_STATE.md`.
- Nowy: `ai_docs/tasks/0532-image-import-retry-progress-reset.md`.

## Test cases

- Failed image import 2343/4400 z licznikami błędów → retry zwraca ten sam UUID,
  status `created`, postęp 0 z nieznanym totalem, zerowe liczniki i brak błędu.
- Input payload po retry pozostaje identyczny, dzięki czemu worker odczyta
  istniejące checkpointy plików.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_jobs_api.py -k image_directory_retry -q
.\.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/application/jobs.py services/api/tests/test_jobs_api.py
$env:MYPYPATH = 'services/api/src;services/worker/src'
.\.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api/application/jobs.py
```

## Risks / open questions

- Dalszy przebieg może ujawnić kolejny historyczny zapis legacy; worker będzie
  monitorowany, a każda taka przyczyna usunięta osobnym commitem.

## Outcome

### Changed

- `JobService.retry_job` używa resetu postępu dla importu `image_directory`.
- UUID, input payload i checkpointy plików pozostają zachowane.

### Verification results

- Regresja serwisu: `1 passed`.
- Domena resetu postępu: `1 passed`.
- Ruff, formatowanie i mypy zmienionego modułu: passed.
- Job `1a1cff95-436e-4054-ae1f-8ef4565cd7b0`: `waiting_for_review`,
  `4400/4400`, 2200 źródeł do review, 0 błędów.
- Trwały zapis: 2200 źródeł, 19380 plansz i 290700 komórek; wszystkie
  zapisane plansze są kompletne i mają status `pending_review`.

### Not completed

- Nie zmieniono kontraktu API ani schematu bazy i nie usunięto danych.

### Documentation updates

- Uzupełniono kontrakt API, architekturę i `CURRENT_STATE.md`.

### Recommended next task

- Zakończyć review plansz i symboli `?`; brakujące automatyczne detekcje
  rozstrzygnąć w istniejącym workflow geometrii.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0532 | `gpt-5.6-sol` | `high` | Retry trwałego importu musi zachować checkpointy plików i odbudować tylko agregaty joba. | Nie, jeśli regresja i rzeczywisty restart workera przejdą. |
