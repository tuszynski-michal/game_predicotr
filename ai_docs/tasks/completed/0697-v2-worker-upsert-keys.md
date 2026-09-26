---
title: TASK-0697 — klucze konfliktu upsertów workera w V2
status: done
last_updated: 2026-09-26
---

# TASK-0697 — klucze konfliktu upsertów workera w V2

## Status

`done`

## Goal

Przywrócić idempotentne zapisy stagingu, normalizacji i payoutów na fizycznych
tabelach V2 z kluczami prefiksowanymi `game_id`.

## Context

Po poprawieniu fixture worker store zwraca PostgreSQL `InvalidColumnReference`:
`ON CONFLICT` wskazuje historyczny klucz bez `game_id`. To rzeczywisty błąd
produkcji od greenfield V2, odsłonięty podczas T08, a nie błąd migracji 0125.

## Dependencies / entry conditions

Wsparcie T08/TASK-0694. Naprawa jest objęta poleceniem wykonania całego
pozostałego planu z usuwaniem blokerów. Nie zmienia schematu ani danych użytkownika.

## Recommended execution

`gpt-6-sol`, reasoning `high`; niezależny review `gpt-6-astra`, reasoning `medium`.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/V2_READINESS_REMEDIATION_PLAN.md`
- `ai_docs/requirements/MANUAL_DATA_IMPORT.md`, `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`, `ai_docs/architecture/DATA_MODEL.md`

## Scope / technical notes

- `imports/store.py::upsert_rows`, `upsert_normalized_rows` oraz
  `payouts/store.py::upsert_payouts`: dopasować target konfliktu do istniejącego
  złożonego klucza V2. Nie zmieniać danych w kluczu ani algorytmu payout.
- Wartość `game_id` nadal pochodzi z kontrolowanego scope workera i domyślnej
  wartości V2; nie inferować jej z niejednoznacznych danych.
- Zachować adaptery nie-PostgreSQL, jeśli mają rzeczywiste użycia w testach.
- Fixture integracyjne tych scenariuszy provisionują V2 i odtwarzają scope
  produkcyjnego `LocalJobWorker`; powtórzenie partii i nowy proces/sesja muszą
  dawać ten sam zbiór rekordów.

## Out of scope

Globalne wydania mobilne, nowe API, schema migration, import danych użytkownika.

## Acceptance criteria

- [x] Upserty raw/normalized/payout na head 0125 przechodzą i są idempotentne.
- [x] Restart sesji nie duplikuje rekordów; brak scope pozostaje błędem.
- [x] Testy, Ruff i kontrola typów zmienionych części oraz niezależny audit.

## Expected files

- `services/worker/src/game_predictor_worker/imports/store.py`
- `services/worker/src/game_predictor_worker/payouts/store.py`
- `services/api/tests/integration/test_worker_job_store.py`
- `services/api/tests/integration/test_payout_store.py`

## Verification

Pojedyncze scenariusze PostgreSQL z tych plików w odrębnych procesach,
`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`, timeout maksymalnie 120 s na krok.
Fixture wyłącznie izolowane; przed stałym DROP potwierdzić nazwę i brak bazy.

## Outcome

### Changed

Dodano `game_id` do trzech istniejących targetów ON CONFLICT. Fixture
provisionują V2 i odtwarzają scope LocalJobWorker, bez zmiany algorytmu/API.

### Verification results

- raw/normalized/payout: 3 passed, 4 deselected w41,41s, izolowane head0125.
- Retry po `engine.dispose()`/nowej sesji; brak scope SQLSTATE42P01 i obca
  gra SQLSTATE23503. Małe fixture, brak operacji na danych użytkownika.
- Ruff check, format --check, mypy czterech plików passed; mypy z jawnym
  MYPYPATH i --follow-imports=silent (config issue zapisany w TASK-0695).
- Niezależny audit gpt-6-astra/medium: brak P0–P2, zgodność PK V2 i scope
  runtime potwierdzona odczytowo. Wszystkie trzy kryteria taska spełnione.

### Not completed

Pełna suite nie była zakresem tej naprawy. Globalny release z game_id=None
nadal wymaga TASK-0698; niniejsza naprawa nie rozwiązuje owner routing.

### Documentation updates

CURRENT_STATE, raport T08, plan naprawczy i ten Outcome.

### Recommended next task

TASK-0698: rozstrzygnięcie konfliktu transakcji; następnie TASK-0694/T08.
