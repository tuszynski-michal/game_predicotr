---
title: TASK-0683 — T04 — bootstrap i testy V2-only
status: todo
last_updated: 2026-09-25
---

# TASK-0683 — T04 — bootstrap i testy V2-only

## Status

`todo`

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

- Zmienić bootstrap/test fixtures tak, aby PostgreSQL dochodził do Alembic head i provisionował partycje V2 zamiast bazować na `Base.metadata` publicznego legacy.
- Dodać test świeżej bazy i nowego procesu po 0125 oraz ochronę, że lista usuwana nie wraca przez nowy bootstrap.

## Out of scope

Modyfikowanie historycznych migracji, produkcyjne DDL, kasowanie testowego adaptera pamięci i zmiana domeny.

## Acceptance criteria

- [ ] Świeży PostgreSQL na head tworzy grę i wykonuje reprezentatywne read/write wyłącznie przez V2.
- [ ] Żadna fixture produkcyjnego kontraktu nie wymaga tabel legacy `public`.
- [ ] Testy migracji chronią staticzną listę manifestu i head 0125.

## Technical notes

Nie zmieniać zamrożonych 0105/manifestu v1. `0125` jest kolejnym stanem historii; bootstrap ma testować ten stan, nie przepisywać przeszłości.

## Expected files

- Istniejące: `services/api/tests/conftest.py`, testy Alembic/lifecycle i konfiguracja bootstrapu ustalona audytem.

## Test cases

- Alembic fresh head → brak 65 relacji public, V2 parents/partycje istnieją; nowy process → routing V2; adapter non-Postgres nie jest używany przez test integracyjny.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_game_data_v2_schema.py services/api/tests/integration/test_game_partition_lifecycle_postgres.py
```

## Risks / open questions

- Testy historycznych rewizji muszą pozostać zdolne do testowania migracji przed 0125 bez zmiany ich znaczenia.

## Outcome

Wypełnia agent po pracy.
