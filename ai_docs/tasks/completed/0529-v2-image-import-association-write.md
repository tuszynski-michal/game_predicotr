---
title: TASK-0529 — Zapis powiązań importu zdjęć w V2
status: done
last_updated: 2026-09-14
---

# TASK-0529 — Zapis powiązań importu zdjęć w V2

## Status

`done`

## Goal

Import zdjęć rejestruje pliki idempotentnie w jedynym produkcyjnym magazynie
gry `game_data_v2` i może przejść od bramki geometrii do tworzenia plansz.

## Context

Job `1a1cff95-436e-4054-ae1f-8ef4565cd7b0` zakończył analizę 2200 źródeł,
po czym PostgreSQL odrzucił zapis `image_import_job_files`: kod użył legacy
konfliktu `(job_id, file_execution_key)`, podczas gdy V2 ma klucz
`(game_id, job_id, file_execution_key)`. Produkcyjny routing jest już V2-only;
`public` pozostaje właścicielem katalogu i współdzielonych wykonań.

## Dependencies / entry conditions

- Baza użytkownika ma rewizję `0110_game_partition_lifecycle`.
- Gra ma aktywną lokalizację `game_data_v2`, generacja 2.
- Tabele legacy danych gry są puste; wspólnych tabel `public` nie wolno usuwać.

## Recommended execution

`gpt-5.6-sol high`; zmiana dotyka granicy shared/game oraz idempotencji zapisu.
Niezależny review nie jest wymagany, jeżeli izolowany test PostgreSQL odtworzy
błąd 42P10 i potwierdzi rozdział V2/public.

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

- Zapisywać `image_import_job_files` w V2 z jawnym `game_id` i pełnym kluczem konfliktu.
- Zachować `image_file_executions` jako współdzieloną tabelę w `public`.
- Zachować zgodność nieprodukcyjnego adaptera legacy/SQLite.
- Dodać regresję PostgreSQL dla zapisu zbiorczego i idempotentnego retry.
- Po zielonej weryfikacji wznowić wskazany job na osobne polecenie operatora.

## Out of scope

- Usuwanie schematu `public`, katalogu gier, jobów albo współdzielonych wykonań.
- Migracja schematu, kopiowanie lub kasowanie danych.
- Zmiana API i UI.

## Acceptance criteria

- [x] Zapis zbiorczy trafia wyłącznie do partycji gry V2.
- [x] Powtórzenie identycznej rejestracji nie tworzy duplikatów.
- [x] Globalne wykonania pozostają w `public.image_file_executions`.
- [x] Skupiony test PostgreSQL, Ruff i mypy zmienionego modułu przechodzą.

## Technical notes

Repozytorium wybiera wariant inserta na podstawie `GameStorageRouter.describe`.
Dla V2 używa jawnego `game_id` oraz konfliktu po trzech kolumnach. Odczyty i
aktualizacje pozostają chronione przez istniejący transaction-local scope i RLS.
Legacy zachowuje dotychczasowy insert po dwóch kolumnach.

## Expected files

- Istniejący: `services/worker/src/game_predictor_worker/images/orchestration_store.py`.
- Istniejący: `services/api/tests/integration/test_game_storage_routing_postgres.py`.
- Istniejący: `ai_docs/process/CURRENT_STATE.md`.
- Nowy: `ai_docs/tasks/0529-v2-image-import-association-write.md`.

## Test cases

- V2 + dwa źródła → dwie asocjacje w partycji gry, zero w legacy.
- Identyczny retry → nadal dwie asocjacje i dwa współdzielone execution.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_game_storage_routing_postgres.py -q
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images/orchestration_store.py services/api/tests/integration/test_game_storage_routing_postgres.py
.\.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/images/orchestration_store.py
```

## Risks / open questions

- Wznowienie joba wymaga działającego workera z nowym kodem; nie należy go
  ponawiać przed restartem procesu.

## Outcome

### Changed

- Wspólny helper rejestracji rozpoznaje fizyczny magazyn gry i dla V2 zapisuje
  jawny `game_id` z pełnym kluczem konfliktu.
- Zapis pojedynczy i zbiorczy korzystają z tego samego kontraktu.
- Nie usunięto tabel `public`: katalog, joby i globalne wykonania są wymaganymi
  tabelami współdzielonymi, a legacy tabele danych gry są puste.

### Verification results

- Izolowany PostgreSQL routingu V2: `7 passed`.
- Testy orkiestracji workera: `16 passed, 1 deselected`; pominięty test dotyczy
  niezależnego seedera katalogu i wcześniej blokował się na systemowym tmp.
- Ruff dla całych `services/api` i `services/worker`: passed.
- Mypy zmienionego modułu z jawnym `MYPYPATH`: passed.
- Historyczny test PostgreSQL bez registry kończy się zgodnie z greenfield
  cutoverem błędem `GAME_STORAGE_LOCATION_MISSING`; nie przywrócono fallbacku.

### Not completed

- Wskazanego joba nie wznowiono podczas testów kodu. Wymaga załadowania
  poprawki przez restart workera, a następnie retry tego samego joba.

### Documentation updates

- Zaktualizowano `CURRENT_STATE.md`; wymagania i zaakceptowana architektura już
  definiowały V2 jako jedyny produkcyjny magazyn gry.

### Recommended next task

- Po wdrożeniu commita zrestartować general worker i wznowić job
  `1a1cff95-436e-4054-ae1f-8ef4565cd7b0`, monitorując pierwszy checkpoint
  pipeline'u powyżej 2200/4400.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0529 | `gpt-5.6-sol` | `high` | Naprawa idempotentnego zapisu na granicy współdzielonego koordynatora i partycji V2. | Nie, jeśli izolowany PostgreSQL potwierdzi pełny przepływ. |
