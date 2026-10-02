---
title: TASK-0683 — T04 — bootstrap i testy V2-only
status: done
last_updated: 2026-09-25
---

# TASK-0683 — T04 — bootstrap i testy V2-only

## Status

`done`

## Goal

Usunąć z bootstrapu PostgreSQL i fixture ryzyko, że test lub nowy proces wymaga publicznej kopii relacji game-owned.

## Context

Testy jednostkowe mogą używać adapterów pamięci, ale nie mogą maskować zależności produkcji od usuwanych tabel.

## Dependencies / entry conditions

T02–T03 done; lista fixture i bootstrapów jest ustalona na podstawie rzeczywistego użycia.

## Recommended execution

`gpt-6-sol`, reasoning `high`; niezależny review `gpt-6-astra`, reasoning `high`. Jeżeli test wymaga semantyki PostgreSQL, nie zastępuje się go SQLite — dodaje się izolowany PostgreSQL.

## Relevant docs

- `AGENTS.md`, plan D-448, `DATA_MODEL.md`
- `alembic/`, `tests/conftest.py`, testy migracji i lifecycle partycji
- `storage/game_data_v2_manifest_v1.py`

## Scope

- Zmienić bootstrap/test fixtures tak, aby PostgreSQL dochodził do bieżącego Alembic head i provisionował partycje V2 zamiast bazować na `Base.metadata` publicznego legacy.
- Dodać test świeżej bazy oraz nowej sesji/procesu, które tworzą grę i wykonują reprezentatywne read/write przez V2 bez użycia kopii game-owned w `public`.
- Udokumentować fixture historycznych rewizji, które celowo testują stan przed 0125; dowód fresh-head bez 65 relacji legacy należy do TASK-0684, gdzie powstaje 0125.

## Out of scope

Modyfikowanie historycznych migracji, produkcyjne DDL, kasowanie testowego adaptera pamięci i zmiana domeny.

## Acceptance criteria

- [x] Świeży PostgreSQL na bieżącym head tworzy grę, provisionuje V2 i wykonuje reprezentatywne read/write wyłącznie przez V2.
- [x] Fixture produkcyjnego kontraktu objęte audytem nie tworzą ręcznie registry ani partycji legacy `public`.
- [x] Historyczne fixture zachowują możliwość testowania rewizji przed 0125, bez udawania stanu po przyszłej migracji.

## Technical notes

Nie zmieniać zamrożonych 0105/manifestu v1. `0125` jest kolejnym stanem
historii i jeszcze nie istnieje w T04; test braku 65 relacji legacy na fresh
headzie jest własnością TASK-0684. T04 nie duplikuje jego DDL ani nie
przepisuje przeszłości.

## Expected files

- Istniejące: `services/api/tests/conftest.py`, testy Alembic/lifecycle i konfiguracja bootstrapu ustalona audytem.

## Test cases

- Alembic fresh bieżący head → V2 parents/partycje po provisioningu istnieją,
  reprezentatywny write/read nie odwołuje się do `public.<game-table>`; nowa
  sesja/proces → routing V2; adapter non-Postgres nie jest używany przez test
  integracyjny.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_game_data_v2_schema.py services/api/tests/integration/test_game_partition_lifecycle_postgres.py
```

## Risks / open questions

- Testy historycznych rewizji muszą pozostać zdolne do testowania migracji przed 0125 bez zmiany ich znaczenia; fresh-head post-0125 jest testem T05.

## Outcome

`SqlAlchemyCatalogRepository` zawsze dostarcza `GameStorageRouter`, więc
utworzenie gry PostgreSQL wykonuje lifecycle partycji V2 również wtedy, gdy
bootstrap nie przekaże routera jawnie. Adapter non-PostgreSQL zachowuje jego
wirtualny kontrakt V2.

Izolowany test lifecycle tworzy grę przez domyślny bootstrap, sprawdza registry,
partycje oraz zapis/odczyt z nowej sesji po bindzie V2. Fixture image batch nie
tworzy już ręcznie wpisu registry ani pojedynczej partycji; dłuższy scenariusz
backfillu używa `GameStorageSession` z `game_storage_scope`, a rekord review
ma jawną własność gry. Potwierdzone testy nie wymagają kopii game-owned w
`public`.

Test po świeżym upgrade do head `0125` bez 65 relacji legacy nie należy do
tego zadania, ponieważ rewizja jeszcze nie istnieje; pozostaje kryterium T05.
Historyczne fixture rewizji przed `0125` nie zostały zmienione.

Weryfikacja: Ruff dla zmienionych modułów; 8 testów jednostkowych katalogu i
schematu V2; izolowany test lifecycle PostgreSQL; dwa scenariusze image-batch
PostgreSQL. Nie uruchomiono pełnego pliku image-batch: niezwiązany scenariusz
`test_symbol_cell_write_through_tracks_board_geometry_and_prediction_mutations`
jest czerwony także w `HEAD`, bo nie przekazuje obecnie wymaganego argumentu
`source_image_id` do `ImageGridReviewService.list`.
