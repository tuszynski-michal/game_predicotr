---
title: TASK-0552 Monotonic geometry guard resume progress
status: done
last_updated: 2026-09-15
---

# TASK-0552 — Monotoniczny postęp wznowienia kontroli geometrii

## Status

`done`

## Goal

Wznowiony import zdjęć zachowuje utrwalony postęp pipeline'u podczas ponownego
wejścia w kontrolę geometrii i nie kończy się `JOB_PROGRESS_REGRESSION`.

## Context

Job `b3aad697-5091-4603-b303-3ab001f78a2d` skopiował 2373 oryginały i rozpoczął
pipeline. Po restarcie kontrola geometrii próbowała zapisać ponownie granicę
`2373/4746`, mimo że job miał już większy postęp z przetworzonych zdjęć.

## Dependencies / entry conditions

- Checkpointy plików i liczniki joba są trwałe.
- Kontrola geometrii może wykonać się ponownie po restarcie workera.
- Bieżący job nadal ma poprawne checkpointy plików i może być bezpiecznie wznowiony.

## Recommended execution

`gpt-6-astra high`; zmiana dotyczy odporności trwałego workflowu na restart i
ochrony monotonicznych liczników. Dodatkowy review nie jest wymagany po teście
regresyjnym oraz wznowieniu rzeczywistego joba w nowym procesie workera.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`

## Scope

- Zachować największy utrwalony postęp i total podczas ponownego checkpointu
  kontroli geometrii.
- Pobierać liczniki wyników z aktualnego stanu kontekstu, a nie ze snapshotu
  joba z chwili przejęcia.
- Dodać regresję restartu po częściowo wykonanym pipeline.
- Doprowadzić wskazany job do poprawnej granicy terminalnej.

## Out of scope

- Zmiana kontraktu API lub schematu bazy.
- Usuwanie danych, stagingu albo checkpointów per plik.
- Zmiana algorytmu geometrii lub jakości rozpoznania.

## Acceptance criteria

- [x] Checkpoint kontroli geometrii nie zmniejsza `progress.current` ani `total`.
- [x] Checkpoint zachowuje aktualne liczniki sukcesów, błędów i review.
- [x] Test odtwarza restart po częściowo wykonanym pipeline i przechodzi.
- [x] Rzeczywisty job przechodzi problematyczną granicę po restarcie i kontynuuje
  bez `JOB_PROGRESS_REGRESSION`.

## Technical notes

Źródłem prawdy dla monotonicznej projekcji joba jest `context.job`, aktualizowany
po każdym checkpointcie. Kontrola geometrii ma raportować co najmniej granicę
kopiowania źródeł, lecz nie może nadpisywać większego postępu pipeline'u.

## Expected files

- Istniejący: `services/worker/src/game_predictor_worker/images/production_workflow.py` — checkpoint kontroli geometrii.
- Istniejący: `services/worker/tests/test_production_image_workflow.py` — regresja restartu.
- Istniejący: `ai_docs/process/CURRENT_STATE.md` — stan poprawki.
- Nowy: `ai_docs/tasks/0552-monotonic-geometry-guard-resume-progress.md`.

## Test cases

- Job z utrwalonym `3400/4746` i 1027 elementami review ponownie przechodzi
  kontrolę geometrii → checkpoint pozostaje `3400/4746` i zachowuje liczniki.
- Pierwsze wykonanie bez postępu pipeline'u → checkpoint pozostaje na granicy
  liczby skopiowanych źródeł.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_production_image_workflow.py -k "systemic_geometry_guard" -q
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images/production_workflow.py services/worker/tests/test_production_image_workflow.py
$env:MYPYPATH = 'services/api/src;services/worker/src'
.\.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/images/production_workflow.py
```

## Risks / open questions

- Rzeczywisty job może dojść do granicy review zamiast `completed`; jest to
  poprawny wynik domenowy i nie oznacza awarii technicznej.

## Outcome

### Changed

- Checkpoint kontroli geometrii korzysta z aktualnego `context.job` i zachowuje
  monotoniczny progress, total oraz liczniki wyników.
- Regresja ustawia stan odpowiadający częściowo wykonanemu pipeline'owi i
  potwierdza, że ponowne wejście w guard go nie cofa.

### Verification results

- `pytest services/worker/tests/test_production_image_workflow.py -q`: 56 passed.
- Skoncentrowana regresja: 3 passed.
- Ruff i mypy zmienionego workflowu: passed.
- Po kontrolowanym restarcie nowy general worker przejął rzeczywisty job jako
  próbę 4, zachował `3530/4746` na guardzie i przeszedł do `3533/4746` bez błędu.

### Not completed

- Job nadal wykonuje pozostałe zdjęcia; nie zmieniano jego danych, checkpointów
  plików ani stagingu.

### Documentation updates

- Zaktualizowano `CURRENT_STATE.md` i Outcome tego zadania.

### Recommended next task

- Brak osobnego zadania kodowego. Monitoring istniejącego importu powinien
  poczekać na `waiting_for_review` albo `completed`.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0552 | `gpt-6-astra` | `high` | Poprawka obejmuje restart trwałego importu i monotoniczne liczniki joba. | Nie, po regresji i weryfikacji w nowym procesie. |
