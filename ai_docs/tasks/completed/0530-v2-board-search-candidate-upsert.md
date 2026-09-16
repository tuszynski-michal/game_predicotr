---
title: TASK-0530 — Idempotentny zapis indeksu plansz w V2
status: done
last_updated: 2026-09-14
---

# TASK-0530 — Idempotentny zapis indeksu plansz w V2

## Status

`done`

## Goal

Projekcja wyszukiwania plansz zapisuje i aktualizuje kandydatów w
`game_data_v2` z pełnym kluczem właściciela gry, dzięki czemu pierwszy import
bez modelu może utworzyć plansze oczekujące na weryfikację.

## Context

Po naprawie rejestracji plików job `1a1cff95-436e-4054-ae1f-8ef4565cd7b0`
doszedł do projekcji rozpoznanych plansz. PostgreSQL odrzucił każdy zapis
`image_board_search_candidates`, ponieważ kod używał legacy konfliktu
`(review_item_id)`, a V2 ma klucz `(game_id, review_item_id)`.

## Dependencies / entry conditions

- TASK-0529 wdrożył zapis powiązań importu w V2.
- Import został zatrzymany po rozpoznaniu przyczyny, przed przetworzeniem całego
  stagingu w błędnym trybie.
- Gra ma aktywną lokalizację `game_data_v2`, generacja 2.

## Recommended execution

`gpt-5.6-sol high`; zmiana dotyka idempotencji projekcji używanej podczas
zapisu plansz. Dodatkowy review nie jest wymagany, jeżeli test PostgreSQL
potwierdzi dwukrotny upsert do V2 oraz brak zapisu do legacy `public`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`

## Scope

- Dobierać klucz konfliktu projekcji kandydatów zgodnie z fizycznym magazynem gry.
- Dla V2 używać `(game_id, review_item_id)`, a dla adaptera legacy zachować
  `(review_item_id)`.
- Dodać regresję PostgreSQL wykonującą dwukrotny zapis kandydata w V2.
- Po wdrożeniu wznowić i monitorować wskazany job importu.

## Out of scope

- Zmiana schematu lub migracja danych.
- Usuwanie stagingu, tabel `public` albo danych gry.
- Zmiana API i UI wyszukiwania plansz.

## Acceptance criteria

- [x] Pierwszy zapis kandydata do V2 nie kończy się PostgreSQL `42P10`.
- [x] Powtórny zapis aktualizuje ten sam rekord bez duplikatu.
- [x] Legacy zachowuje swój dotychczasowy klucz konfliktu.
- [x] Test PostgreSQL, Ruff i mypy dla zmienionego pionu przechodzą.
- [x] Poprawka jest gotowa do załadowania przez restart workera i retry joba.

## Technical notes

Repozytorium zna `game_id` z payloadu projekcji. Przed zbudowaniem inserta
odczyta fizyczną lokalizację przez `GameStorageRouter`; V2 wybierze pełny klucz
partycjonowanej tabeli, a adapter legacy zachowa dotychczasowy klucz. Nie jest
potrzebna migracja, ponieważ właściwe ograniczenie już istnieje w bazie.

## Expected files

- Istniejący: `services/api/src/game_predictor_api/storage/board_search_projection_repository.py`.
- Istniejący: `services/api/tests/integration/test_game_storage_routing_postgres.py`.
- Istniejący: `ai_docs/process/CURRENT_STATE.md`.
- Nowy: `ai_docs/tasks/0530-v2-board-search-candidate-upsert.md`.

## Test cases

- Gra V2 + kandydat planszy → rekord wyłącznie w `game_data_v2`.
- Ten sam `game_id` i `review_item_id` zapisany drugi raz → jeden rekord z
  uaktualnionymi wartościami.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_game_storage_routing_postgres.py -q
.\.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/storage/board_search_projection_repository.py services/api/tests/integration/test_game_storage_routing_postgres.py
.\.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api/storage/board_search_projection_repository.py
```

## Risks / open questions

- Kolejny zapis V2 może ujawnić następne historyczne założenie o kluczu
  `public`; job będzie monitorowany po restarcie workera.

## Outcome

### Changed

- Upsert kandydatów rozpoznaje fizyczny magazyn gry. V2 używa pełnego klucza
  partycji, a adapter legacy zachowuje dotychczasowy konflikt.
- Nie zmieniono schematu ani danych użytkownika.

### Verification results

- Regresja V2 PostgreSQL: `1 passed`; pierwszy insert i drugi update pozostawiły
  jeden rekord w V2 oraz zero rekordów w legacy.
- Testy repozytorium projekcji: `11 passed`.
- Pełny plik routingu: `8 passed`, a niezależny istniejący teardown testu
  geometrii zgłosił jedno otwarte połączenie.
- Ruff zmienionych plików: passed. Mypy zmienionego modułu: passed.

### Not completed

- W tym tasku nie zmieniano schematu ani nie usuwano danych.

### Documentation updates

- Zaktualizowano `CURRENT_STATE.md` i rezultat taska.

### Recommended next task

- Zrestartować general worker, ponowić job
  `1a1cff95-436e-4054-ae1f-8ef4565cd7b0` i monitorować dalszy zapis V2.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0530 | `gpt-5.6-sol` | `high` | Naprawa idempotentnego upsertu projekcji w partycjonowanym magazynie V2. | Nie, jeśli test PostgreSQL potwierdzi dwukrotny zapis. |
