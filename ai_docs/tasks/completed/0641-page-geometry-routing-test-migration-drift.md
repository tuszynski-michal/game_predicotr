---
title: TASK-0641 — napraw dryf migracji fikstury testu routingu Postgres
status: done
last_updated: 2026-09-24
---

# TASK-0641 — napraw dryf migracji fikstury testu routingu Postgres

## Status

`done`

## Goal

`test_page_geometry_snapshot_reads_v2_in_a_new_unscoped_session` (Postgres
integration) przechodzi zielono na czystym, nieskróconym schemacie.

## Context

Przy realizacji TASK-0637 (D-442) napotkano ten test jako czerwony,
niezwiązany z realizowanym planem — użytkownik poprosił o naprawę po
zamknięciu planu D-442. `database` (fikstura w
`services/api/tests/integration/test_game_storage_routing_postgres.py`)
migruje bazę tylko do `0106_game_storage_routing_fence`, ale model ORM
`image_page_geometry_overrides` (używany przez
`PageGeometryOverrideService`) oczekuje kolumny `board_frame_quads`,
dodanej dopiero późniejszą migracją. Ten sam rodzaj rozjazdu (inna
kolumna, `games.shape_geometry_configuration`) naprawiono punktowo w
TASK-0637 dla nowo dodanego testu.

## Dependencies / entry conditions

- Brak zależności; test istniał przed TASK-0637 i był czerwony
  niezależnie od zmian D-442 (potwierdzone na czystym checkout przed
  TASK-0637).

## Recommended execution

claude-sonnet-5, reasoning: medium. Punktowa naprawa fikstury testu wg
istniejącego wzorca (ten sam mechanizm już użyty w TASK-0637); niskie
ryzyko, jeden plik. Dodatkowy review: nie.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`

## Scope

- `services/api/tests/integration/test_game_storage_routing_postgres.py`:
  wydzielony helper `_upgrade_database_to_head(database)` (dotąd
  zduplikowany inline w teście z TASK-0637), użyty też w
  `test_page_geometry_snapshot_reads_v2_in_a_new_unscoped_session`.

## Out of scope

- Zmiana wspólnej fikstury `database` (pozostałe ~8 testów w pliku
  celowo zostają przypięte do migracji `0106`).
- Inne testy z dryfem schematu, jeśli się ujawnią — osobny task.

## Acceptance criteria

- [x] `test_page_geometry_snapshot_reads_v2_in_a_new_unscoped_session`
      zielony.
- [x] Pełny plik `test_game_storage_routing_postgres.py` zielony (10/10).
- [x] `python:lint`/format czyste dla zmienionego pliku.

## Technical notes

Rozwiązanie: nowy helper `_upgrade_database_to_head(database: Engine) ->
None` (buduje `alembic.config.Config` wskazujący na URL danej,
izolowanej bazy testu i woła `command.upgrade(config, "head")`), wołany
na początku testu — przed wstawieniem `game_storage_locations` i
tworzeniem partycji. Ten sam helper zastąpił zduplikowany inline blok w
`test_grid_review_source_asset_reads_v2_in_a_new_unscoped_session`
(TASK-0637). Każdy test w tym pliku dostaje własną, izolowaną bazę
(`database` fixture tworzy nową nazwę per test), więc wywołanie helpera
w jednym teście nie wpływa na pozostałe.

## Expected files

- Istniejące: `services/api/tests/integration/test_game_storage_routing_postgres.py`.

## Test cases

- `test_page_geometry_snapshot_reads_v2_in_a_new_unscoped_session`: zapis
  i odczyt `PageGeometryOverrideService` w nowej, niezbindowanej sesji dla
  gry V2, po migracji do head.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_game_storage_routing_postgres.py -q
npm run python:lint
```

Uruchomione i zielone: 10/10 testów w pliku, `ruff check`/`format --check`
czyste.

## Risks / open questions

- Brak. Naprawa jest lokalna do jednego testu istniejącego pliku.

## Outcome

### Changed

- [services/api/tests/integration/test_game_storage_routing_postgres.py](../../services/api/tests/integration/test_game_storage_routing_postgres.py):
  nowy `_upgrade_database_to_head` helper, użyty w
  `test_page_geometry_snapshot_reads_v2_in_a_new_unscoped_session` i
  refaktoryzowany do użycia w `test_grid_review_source_asset_reads_v2_in_a_new_unscoped_session`.

### Verification results

- `pytest services/api/tests/integration/test_game_storage_routing_postgres.py`
  (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`): 10/10 zielone (wcześniej 9/10).
- `ruff check`/`ruff format --check`: czyste.
- `python:typecheck`: brak nowych błędów w zmienionym pliku.

### Not completed

- Nic — pełny zakres wykonany.

### Documentation updates

- Ten plik przeniesiony do `ai_docs/tasks/completed/`.
- `ai_docs/process/CURRENT_STATE.md` — nowa notatka.

### Recommended next task

- Brak.
