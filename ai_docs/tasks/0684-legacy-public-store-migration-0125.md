---
title: TASK-0684 — T05 — migracja 0125 legacy public store
status: todo
last_updated: 2026-09-25
---

# TASK-0684 — T05 — migracja 0125 legacy `public`

## Status

`todo`

## Goal

Zaimplementować i izolowanie przetestować migrację Alembic 0125 usuwającą wyłącznie potwierdzone puste, legacy relacje game-owned.

## Context

Migracja jest granicą nieodwracalnego DDL; jej kod nie jest zgodą na zastosowanie w bazie użytkownika.

## Dependencies / entry conditions

T01–T04 done; T01 ma `ready`, a T03/T04 udowadniają brak zależności runtime/bootstrapa. Lista i porządek FK są niezależnie zrecenzowane.

## Recommended execution

`gpt-6-astra`, reasoning `high`; niezależny review `gpt-6-sol`, reasoning `high`. Nieznany FK, relacja niepusta lub potrzeba `CASCADE` blokuje task.

## Relevant docs

- `AGENTS.md`, plan D-448, D-377
- `alembic/versions/0105_partitioned_game_storage.py`, `sql/game_data_v2_schema_v1.sql`
- `storage/game_data_v2_manifest_v1.py::GAME_TABLES`, testy migracji

## Scope

- Dodać `0125_remove_legacy_public_game_store.py` z literalnym snapshotem 65 nazw manifestu i ich deterministycznym topologicznym porządkiem dropu.
- Przed pierwszym DDL sprawdzić reltype/schema/listę, pustość wszystkich relacji i brak nieoczekiwanych zależności; następnie użyć tylko `DROP TABLE public.<nazwa> RESTRICT`.
- Dodać izolowane testy PostgreSQL: happy path, każda klasa guard failure, przetrwanie catalog/shared/V2 i brak downgrade.

## Out of scope

`CASCADE`, modyfikacja 0105/historycznych migracji, dynamiczne generowanie produkcyjnego DDL, dane production oraz uruchomienie 0125 na bazie użytkownika.

## Acceptance criteria

- [ ] Migracja odmawia przed pierwszym dropem, gdy choć jeden guard nie przechodzi.
- [ ] Happy path usuwa dokładnie 65 legacy relacji, a zostawia catalog, shared/control i `game_data_v2` bez zmian.
- [ ] `downgrade()` jawnie odmawia z komunikatem o nieodwracalności; test nie oczekuje fałszywego odtworzenia.

## Technical notes

Sprawdzenie obejmuje wszystkie tabele **przed** pierwszym `DROP`, aby fail nie dał częściowego początku po wykrytej niepustości. Zależności wylicza się podczas implementacji z testowego katalogu i zamraża w kodzie/testach. Każdy SQL ma jawne, bezpieczne identyfikatory pochodzące z literalnej tuple, nie z requestu ani katalogu runtime.

## Expected files

- Nowe: `services/api/alembic/versions/0125_remove_legacy_public_game_store.py`, właściwy test integracyjny migracji.
- Istniejące: `services/api/tests/test_migration_baseline.py`, manifest v1 tylko jako wejście do testu zgodności.

## Test cases

- 65 pustych → drop `RESTRICT`; jedna tabela z wierszem/FK/triggerem niezgodnym → zero DDL; shared/catalog/V2 → istnieją; downgrade → kontrolowana odmowa; fresh head → brak legacy tabel.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_migration_baseline.py services/api/tests/integration/test_game_data_v2_postgres.py
```

## Risks / open questions

- Rzeczywisty porządek dependency musi być potwierdzony przed kodem; plan nie dopuszcza zgadywania listy.

## Outcome

Wypełnia agent po pracy.
