# TASK-0973 — Ponowienie kroku partycji przy przekroczeniu lock timeout

## Status

`done`

## Goal

Utworzenie gry (`POST /api/v1/admin/games`) kończy się powodzeniem mimo krótkotrwałej długiej transakcji odczytu na tabeli nadrzędnej `game_data_v2`, a po wyczerpaniu prób zwraca czytelne `409 GAME_PARTITION_LOCK_BUSY` zamiast `500`.

## Context

2026-10-11 dodanie gry na bazie V2 (dysk D) zwróciło 500: `LockNotAvailable` przy `CREATE TABLE game_data_v2.gpv2_… PARTITION OF game_data_v2.board_render_manifests`. Krok partycji potrzebuje `ACCESS EXCLUSIVE` na tabeli nadrzędnej i ma `lock_timeout = 2s`. W bazie sesja aplikacji trzymała `AccessShareLock` na `board_render_manifests` ponad 22 s (`SELECT count(image_symbol_review_cells.id) … JOIN`, plan obejmuje ~1446 partycji). Na starej bazie bez partycji ten problem nie istniał.

## Dependencies / entry conditions

- D-540 (baza na dysku D), migracja `0110` (cykl życia partycji) bez zmian.

## Recommended execution

`claude-sonnet-5-5`, reasoning `medium`: mała, zlokalizowana zmiana w warstwie `storage/` z testami. Audyt krzyżowy pominięty (wstrzymany decyzją operatora 2026-10-01); eskalacja: potrzeba zmiany schematu albo timeoutów w migracji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/DATA_MODEL.md`

## Scope

- `game_partition_lifecycle.py`: `is_lock_not_available` (SQLSTATE `55P03`), `lock_retry_delay_seconds`, stałe `LOCK_RETRY_*`.
- `catalog_repository._run_partition_step_in`: do 6 prób; po `LockNotAvailable` rollback kroku, wykładniczy backoff 0,5–4 s, wznowienie od checkpointu; po wyczerpaniu `GamePartitionLifecycleError("GAME_PARTITION_LOCK_BUSY")` (handler w `main.py` mapuje na 409).
- Testy jednostkowe i test integracyjny na izolowanej bazie PostgreSQL.

## Out of scope

- Przyspieszenie `_current_selected_cell_count` (osobny temat wydajności).
- Zmiana `lock_timeout` (krótki timeout jest celowy: oczekujący `ACCESS EXCLUSIVE` kolejkuje nowe odczyty).
- Ścieżka usuwania gry (nie używa `_run_partition_step_in`).

## Acceptance criteria

- [x] Test integracyjny: czytelnik trzyma `ACCESS SHARE` na `board_render_manifests`, create kończy się `active` po jego zwolnieniu.
- [x] Błąd inny niż `55P03` nie jest ponawiany; dryf checkpointu nadal zapisuje `blocked` i nie jest ponawiany.
- [x] Po 6 próbach `GAME_PARTITION_LOCK_BUSY`, bez commita częściowego kroku.

## Technical notes

Krok partycji to jedna transakcja (`run_next`): rollback usuwa częściowe DDL, a checkpoint w `game_storage_lifecycle_operations` zostaje na tej tabeli, więc ponowienie (w pętli lub kolejnym żądaniem) wznawia ten sam krok. Najgorszy czas jednego żądania: 6 × 2 s + 11,5 s backoffu ≈ 24 s.

## Expected files

- `services/api/src/game_predictor_api/storage/game_partition_lifecycle.py`
- `services/api/src/game_predictor_api/storage/catalog_repository.py`
- `services/api/tests/test_game_partition_lifecycle.py`
- `services/api/tests/integration/test_game_partition_lifecycle_postgres.py`

## Test cases

- Dwie porażki `55P03` i sukces → trzy wywołania, dwa rollbacki, jeden commit, opóźnienia 0,5 s i 1 s.
- Sześć porażek → `GAME_PARTITION_LOCK_BUSY`, brak commita.
- `DeadlockDetected` → bez ponowienia.
- Dryf checkpointu → commit diagnostyki, bez ponowienia.
- PostgreSQL: blokada `ACCESS SHARE` zwolniona przy pierwszym backoffie → gra `active`, 64 partycje.

## Verification

```powershell
$env:PYTHONPATH = "<worktree>\services\api\src;<worktree>\services\worker\src"
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_game_partition_lifecycle.py services/api/tests/test_catalog_api.py -q
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_game_partition_lifecycle_postgres.py -k "retries_while or greenfield" -q
.\.venv\Scripts\python.exe -m ruff check <pliki>; .\.venv\Scripts\python.exe -m mypy --strict <pliki>
```

## Risks / open questions

- Poprawka działa po restarcie API (kod w procesie); do tego czasu działające API ma stary kod.
- Przyczyna źródłowa blokady (wolny count po `image_symbol_review_cells`) pozostaje; nie blokuje już tworzenia gier, ale może spowalniać panel.

## Outcome

### Changed

- Ponowienie kroku partycji przy `55P03` z backoffem i błędem `GAME_PARTITION_LOCK_BUSY` (409).

### Verification results

- `test_game_partition_lifecycle.py` + `test_catalog_api.py`: 21 passed.
- Integracja PostgreSQL (`retries_while`, `greenfield`): 2 passed.
- ruff check i format: czyste; mypy --strict: zmienione pliki czyste (2 wcześniejsze błędy w `schemas/source_lattice_geometry.py` poza zakresem).

### Commit

- Version v1.7.313; hash do dopisania przy następnym commicie dokumentacyjnym.

### Not completed

- Audyt krzyżowy (wstrzymany decyzją operatora).
- Optymalizacja `_current_selected_cell_count`.

### Documentation updates

- `CURRENT_STATE.md`.

### Recommended next task

- Zmierzyć i przyspieszyć `_current_selected_cell_count` (join po partycjach).
