---
title: TASK-0682 — T03 — audit routingu dostępu game-owned
status: todo
last_updated: 2026-09-25
---

# TASK-0682 — T03 — audit routingu dostępu game-owned

## Status

`todo`

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

Wypełnia agent po pracy.
