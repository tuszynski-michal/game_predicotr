---
title: TASK-0681 — T02 — V2-only storage routing
status: todo
last_updated: 2026-09-25
---

# TASK-0681 — T02 — V2-only storage routing

## Status

`todo`

## Goal

Usunąć z produkcyjnego PostgreSQL możliwość odczytu lub zapisu game-owned przez fallback `public`.

## Context

`GameStorageRouter` wciąż posiada typy i zachowania legacy, choć greenfield path jest V2-only; D-440 dowodzi ryzyka pustego odczytu `public` bez binda.

## Dependencies / entry conditions

T01 passed. Inventory musi potwierdzać aktywne V2 locations; zmiana kontraktu katalogu wymaga pionu API/OpenAPI/generated client zgodnie z AGENTS.md.

## Recommended execution

`gpt-6-astra`, reasoning `high`; niezależny review `gpt-6-sol`, reasoning `high`. Niezidentyfikowany klient zależny od `legacy-public-v1` blokuje task.

## Relevant docs

- `AGENTS.md`, plan D-448, `DECISION_LOG.md` (D-377, D-440)
- `storage/game_storage_routing.py::GameStorageRouter`
- `domain/catalog.py`, `main.py`, testy `test_game_storage_routing*`, `test_catalog_api.py`

## Scope

- Zdefiniować jeden V2-only kontrakt PostgreSQL: poprawna active location V2 → bind; brak, uszkodzenie, stale generation albo inny schema → kontrolowany błąd/blocked.
- Usunąć z produkcyjnych projekcji/kontraktów `legacy-public-v1` i testować brak cichego fallbacku po restarcie sesji.
- Zachować wyraźnie odseparowany adapter nie-PostgreSQL wyłącznie, jeśli jest konieczny dla unit testów; nie może reprezentować rzeczywistego public data store.

## Out of scope

Usunięcie tabel, zmiana locations, obniżanie generation, ręczna migracja danych i niezwiązane API.

## Acceptance criteria

- [ ] PostgreSQL nie wybiera `public` dla game-owned przy braku/wadzie registry.
- [ ] Katalog/API/OpenAPI/klient i testy są zgodne z nowym kontraktem, jeśli typ odpowiedzi ulegnie zmianie.
- [ ] Test V2 z rzeczywistą partycją i test braku location przechodzą w świeżych transakcjach.

## Technical notes

Nie wystarczy usunięcie stałej tekstowej: zapytanie musi wykonać bind przed pierwszą relacją game-owned, a test ma zawierać inną pustą kopię `public` lub jej brak. Błędy programistyczne nie mogą być zamienione na sukces `blocked`.

## Expected files

- Istniejące: `storage/game_storage_routing.py`, `domain/catalog.py`, `main.py`, OpenAPI/generated client i testy routingu/katalogu.

## Test cases

- active V2 → read/write we właściwej partycji; brak registry → kontrolowany błąd; `public`/generation 1 → odrzucone; utrata odpowiedzi i nowa sesja → nadal V2.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_game_storage_routing.py services/api/tests/test_catalog_api.py services/api/tests/integration/test_game_storage_routing_postgres.py
```

## Risks / open questions

- Usunięcie pola API jest zmianą kontraktu; wykonawca musi najpierw ustalić konsumentów i zastosować pionową aktualizację.

## Outcome

Wypełnia agent po pracy.
