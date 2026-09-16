---
title: TASK-0531 — Routing operacji plików joba do V2
status: done
last_updated: 2026-09-14
---

# TASK-0531 — Routing operacji plików joba do V2

## Status

`done`

## Goal

Odczyt operacji importu i retry pojedynczego pliku rozwiązują magazyn V2 na
podstawie właściciela wspólnego joba, bez wymagania `game_id` w ścieżce API.

## Context

Po zatrzymaniu błędnej próby importu 143 powiązania plików istniały w V2, lecz
endpoint retry zwrócił `IMAGE_JOB_FILE_NOT_FOUND`. Repozytorium odczytywało
wspólny job z `public`, ale przed zapytaniem o game-owned asocjację nie wiązało
sesji z `job.game_id`.

## Dependencies / entry conditions

- TASK-0529 zapisuje asocjacje importu do V2.
- TASK-0530 naprawia następujący po retry zapis kandydatów plansz.
- General worker jest zatrzymany, a job pozostaje `created`.

## Recommended execution

`gpt-5.6-sol high`; zmiana obejmuje granicę wspólnego control-plane i zapisu
game-owned. Dodatkowy review nie jest wymagany, jeśli regresja PostgreSQL
wykona nieskopowany retry pliku przez publiczne `job_id`.

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

- Po walidacji joba wiązać repozytorium operacji obrazów z jego `game_id`.
- Odczyt wiązać jako `READ`, retry jako `WRITE`.
- Dodać regresję PostgreSQL odtwarzającą retry bez zewnętrznego scope gry.
- Po wdrożeniu zresetować 143 błędne pliki przez API i wznowić job.

## Out of scope

- Zmiana URL lub kontraktu API.
- Bezpośrednia edycja danych użytkownika z pominięciem endpointu retry.
- Usuwanie stagingu lub asocjacji.

## Acceptance criteria

- [x] Operacje joba widzą jego asocjacje V2 w nieskopowanej sesji API.
- [x] Retry zmienia dokładnie wskazany błędny plik na `processing`.
- [x] Zapis przechodzi przez istniejący write fence magazynu gry.
- [x] Test PostgreSQL, Ruff i mypy przechodzą.

## Technical notes

`jobs` pozostaje tabelą wspólną, więc `_image_job` może najpierw bezpiecznie
odczytać rekord i zweryfikować jego rodzaj. Następnie używa `job.game_id` do
transakcyjnego `GameStorageRouter.bind`; dalsze ORM trafia przez `search_path`
do V2. Dla retry wymagany jest write fence, dla raportu wystarcza odczyt.

## Expected files

- Istniejący: `services/api/src/game_predictor_api/storage/image_job_repository.py`.
- Istniejący: `services/api/tests/integration/test_game_storage_routing_postgres.py`.
- Istniejący: `ai_docs/process/CURRENT_STATE.md`.
- Nowy: `ai_docs/tasks/0531-v2-image-job-operations-routing.md`.

## Test cases

- Job V2 z dwoma asocjacjami → nieskopowany raport zwraca dwa pliki.
- Jedna asocjacja oznaczona jako `failed/discovery` → nieskopowany retry po
  `job_id` i execution key ustawia ją na `processing` i usuwa błąd.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_game_storage_routing_postgres.py::test_image_batch_registration_uses_v2_composite_identity -q
.\.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/storage/image_job_repository.py services/api/tests/integration/test_game_storage_routing_postgres.py
.\.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api/storage/image_job_repository.py
```

## Risks / open questions

- Po uruchomieniu joba mogą ujawnić się dalsze historyczne upserty z kluczem
  legacy; monitoring PostgreSQL pozostaje aktywny do końca importu.

## Outcome

### Changed

- `_image_job` wiąże magazyn na podstawie `job.game_id` po walidacji rodzaju
  joba. Odczyt używa intencji `READ`, a retry `WRITE`.
- Nie zmieniono API ani schematu bazy.

### Verification results

- Izolowany test PostgreSQL nieskopowanego retry V2: `1 passed`.
- Ruff i formatowanie zmienionych plików: passed.
- Mypy zmienionego repozytorium z pełnym `MYPYPATH`: passed.
- Dwa testy API są blokowane przez istniejący Windows `PermissionError` dla
  katalogu pytest tmp; nie jest to błąd kodu ani regresji PostgreSQL.

### Not completed

- W tym tasku nie zmieniano ani nie usuwano danych użytkownika.

### Documentation updates

- Zaktualizowano `CURRENT_STATE.md` i rezultat taska.

### Recommended next task

- Załadować poprawkę w API, zresetować błędne pliki przez endpoint, uruchomić
  worker i monitorować job importu do terminalnego wyniku.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0531 | `gpt-5.6-sol` | `high` | Routing retry między wspólnym jobem a game-owned asocjacją V2. | Nie, jeśli izolowany PostgreSQL potwierdzi nieskopowany retry. |
