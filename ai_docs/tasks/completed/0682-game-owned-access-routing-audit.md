---
title: TASK-0682 — T03 — audit routingu dostępu game-owned
status: done
last_updated: 2026-09-25
---

# TASK-0682 — T03 — audit routingu dostępu game-owned

## Status

`done`

## Goal

Zapewnić, że każdy produkcyjny repository, worker i raw SQL dotykający relacji game-owned wiąże V2 przed odczytem lub zapisem.

## Context

Poprzedni błąd `board_import_coverage` odczytał pusty `public`, mimo poprawnej V2 location (D-440).

## Dependencies / entry conditions

T02 done; istniejące taski i kod są ponownie zinwentaryzowane, a każda znaleziona ścieżka ma właściciela testu.

## Recommended execution

`gpt-6-astra`, reasoning `high`; niezależny review `gpt-6-sol`, reasoning `high`. Nieudowodniona ścieżka dynamicznego SQL blokuje T05.

## Relevant docs

- `AGENTS.md`, plan D-448, D-440
- `storage/game_storage_routing.py`, `storage/`, `services/worker/`, `scripts/`
- `tests/integration/test_game_storage_routing_postgres.py`

## Scope

- Użyć audytu symboli/SQL do wykrycia dostępu do `GAME_TABLES`, w tym wsadowych workerów i skryptów operatorskich.
- Naprawić produkcyjne pathy przez istniejący `GameStorageRouter.bind()`/`qualified_game_table()` i dodać regresje na V2 z danymi.
- Udokumentować świadomie nieprodukcyjne fixture/adapters, których nie obejmuje runtime audit.

## Out of scope

Funkcjonalne rozszerzenia endpointów, schema DDL, refaktor niezwiązanych query i zmiana danych.

## Acceptance criteria

- [ ] Każda ścieżka produkcyjna do game-owned ma jawny bind lub uzasadnione, testowane repozytorium pośrednie.
- [ ] Raw SQL ma kwalifikację z routera, nie interpolowany schema/name od klienta.
- [ ] Nowe regresje wykrywają odczyt pustego `public` zamiast V2.

## Technical notes

Audyt kończy się listą sprawdzonych punktów wejścia, nie deklaracją „rg bez wyników”. Jedna transakcja nie może zmieniać scope między grami; zachować write fence i expected generation.

## Expected files

- Istniejące: właściwe repository/workery/skrypty wykazane audytem oraz ich testy.
- Nowe (proponowane): `ai_docs/quality/V2_GAME_OWNED_ACCESS_AUDIT.md`.

## Test cases

- Każdy naprawiony read/write na V2; druga gra w tej samej sesji → conflict; brak bind → regresja fail-closed; raw SQL nie przyjmuje nazwy schematu od requestu.

## Verification

```powershell
# Najpierw testy zmienionych repository/workerów, potem ich lint/typecheck; każdy proces z timeoutem <= 120 s.
```

## Risks / open questions

- Audyt może odkryć endpointy wymagające zmian OpenAPI; nie tworzyć równoległego kontraktu.

## Outcome

### Changed

- `SqlAlchemyOperationalImageReviewRepository` wiąże V2 przed każdym
  publicznym read/write relacji game-owned, także dla endpointów, których URL
  nie zawiera `/games/{id}`.
- `SqlAlchemyBoardSearchProjectionRepository.upsert_candidates()` wiąże
  pojedynczą grę jako write, wymaga batcha jednej gry i stosuje wyłącznie
  złożony klucz V2.
- Weryfikacja symboli wiąże V2 przed ustaleniem wariantu projekcji i zwracaniem
  jej generation.
- Image batch worker rozwiązuje globalny job, wiąże jego grę przed każdym
  odczytem/zapisem relacji plików, a raw INSERT otrzymuje nazwę tabeli wyłącznie
  z `qualified_game_table()` routera.
- Dodano raport [V2_GAME_OWNED_ACCESS_AUDIT.md](../../quality/V2_GAME_OWNED_ACCESS_AUDIT.md)
  z punktami wejścia, granicą raw SQL i świadomie nieprodukcyjnymi adapterami.

### Verification results

- 40/40 testów jednostkowych zmienionych repository przeszło.
- Izolowany PostgreSQL: 2/2 (operacyjny review w świeżej sesji i upsert
  board-search V2) oraz 1/1 (image batch zapisuje V2, nie `public`) przeszły.
- Ruff check dla zmienionych modułów przeszedł.

### Not completed

- Pełny historyczny scenariusz image batch nadal zakłada brak location V2 i
  kończy się `GAME_STORAGE_LOCATION_MISSING`; jego bootstrap/fixture jest
  zakresem TASK-0683, więc nie został tu globalnie zmieniony.
- Strict mypy nie zakończył się w limicie 30 s; przed przerwaniem wskazał sześć
  wcześniejszych błędów `shape_geometry_v2/core.py`, poza zmienionymi modułami.
  Proces kontroli został zakończony, bez pozostawionego procesu tego przebiegu.

### Recommended next task

- TASK-0683 — V2-only test and bootstrap contract.
