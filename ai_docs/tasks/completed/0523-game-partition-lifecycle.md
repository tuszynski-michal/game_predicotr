---
title: Game partition lifecycle
status: in_progress
last_updated: 2026-09-09
---

# TASK-0523 — Cykl życia partycji gry

## Status

`done`

## Goal

Zapewnić wznawialne, odporne na dryf tworzenie i usuwanie kompletnego zestawu partycji jednej gry.

## Dependencies / entry conditions

TASK-0519–0522 są ukończone. Manifest `game-data-v2-manifest-v1` jest zamrożonym źródłem wymaganych tabel gry.

## Recommended execution

`gpt-6-astra high`; dodatkowy audyt `gpt-6-astra high` obejmuje DDL, checkpointy, zależności i GC.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- zaakceptowany plan partycjonowania danych gier

## Scope

- Trwały receipt i checkpoint lifecycle.
- Idempotentne tworzenie oraz kontrolowane usuwanie partycji z manifestu.
- Walidacja bound/parent/shape, krótkie timeouty DDL, ANALYZE i autovacuum.
- Zamykanie zapisów przed usuwaniem i ochrona obcych/współdzielonych danych.

## Out of scope

- Wykonanie lifecycle na danych użytkownika.
- Usunięcie istniejących gier (TASK-0524).
- Greenfield cutover aplikacji (TASK-0525).

## Acceptance criteria

- [x] Restart w połowie provisioningu wznawia się z trwałego checkpointu.
- [x] Dryf nazwy, parenta albo bound blokuje operację.
- [x] Usunięcie nie korzysta z `CASCADE` i nie narusza innej gry.
- [x] Lokalizacja V2 staje się aktywna dopiero po komplecie zweryfikowanych partycji.
- [x] Każdy etap ma krótkie timeouty DDL.

## Technical notes

Każde wywołanie wykonuje najwyżej jeden etap manifestu w transakcji wywołującego. Nazwy partycji są deterministyczne z UUID gry i nazwy tabeli. Receipt przeżywa usunięcie gry. Usuwanie przebiega w odwrotnej kolejności zależności i kończy katalog dopiero po usunięciu partycji.

## Expected files

- nowa migracja lifecycle po 0109
- nowy storage service i testy jednostkowe/integracyjne
- dokumentacja architektury i procesu

## Test cases

- restart/lost response, ponowienie tego samego etapu, konflikt nazwy/bound;
- dwie gry z izolowanymi partycjami;
- blokada wspólnej referencji i brak `CASCADE`;
- pełny provision/delete testowej gry.

## Verification

Skoncentrowane testy, izolowany PostgreSQL, Ruff, mypy i staged diff audit.

## Risks / open questions

- Operacje na realnych grach wymagają osobnego preview i potwierdzenia.

## Outcome

### Changed

- Dodano migrację 0110 i manifest-bound repository lifecycle.
- Provisioning jest idempotentny, checkpointowany i aktywuje routing dopiero po walidacji.
- Delete używa FK-derived order, DETACH + DROP bez CASCADE i kończy katalog atomowo.

### Verification results

- 3 testy jednostkowe/offline passed; Ruff i scoped mypy passed.
- Izolowany PostgreSQL: pełny provision dwóch gier, wznowienie i delete jednej — passed.
- Tor migracji/schema przeszedł po aktualizacji oczekiwanego headu.

### Not completed

- Nie wykonano migracji ani lifecycle na bazie użytkownika; nie usunięto plików.

### Documentation updates

- GAME_DATA_V2_OWNERSHIP, DECISION_LOG i CURRENT_STATE.

### Recommended next task

- TASK-0524 — read-only inventory i osobno potwierdzane usunięcie realnych danych.
