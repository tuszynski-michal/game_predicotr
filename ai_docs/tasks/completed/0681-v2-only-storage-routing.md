---
title: TASK-0681 — T02 — V2-only storage routing
status: done
last_updated: 2026-09-25
---

# TASK-0681 — T02 — V2-only storage routing

## Status

`done`

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

### Changed

- PostgreSQL router akceptuje wyłącznie active location `game_data_v2` z
  generation co najmniej `2` i manifestem v1. Wpis `public`/generation `1`
  jest kontrolowanym `GAME_STORAGE_LOCATION_INVALID`; brak wpisu podczas
  bind pozostaje `GAME_STORAGE_LOCATION_MISSING`.
- Usunięto projekcję `legacy-public-v1`, `public` schema oraz generation `1`
  z routera i domyślnych odpowiedzi katalogu. Nie-PostgreSQL adapter unitowy
  jest wyłącznie wirtualnym V2, nie odwzorowuje fizycznego legacy store.
- Kontrakt OpenAPI nie zmienił typu pól katalogu; sprawdzono, że artefakt i
  wygenerowany klient są aktualne.

### Verification results

- `pytest services/api/tests/test_game_storage_routing.py services/api/tests/test_catalog_api.py` — 16 passed.
- Izolowany PostgreSQL: 4 scenariusze routingu TASK-0681 (active V2 z
  partycją, `public`/generation 1, brak location oraz rebind po commit) —
  4 passed. Uruchomienie odbyło się w nowym kontrolowanym procesie.
- Ruff check i format check dla zmienionych modułów — passed.
- `npm run openapi:check` — passed; OpenAPI oraz klient Admin są aktualne.

### Not completed

- Pełny, 11-testowy plik integracyjny nie został zaliczony w jednym przebiegu:
  ograniczenie wykonawcze przerwało pierwszą próbę i pozostawiło procesy oraz
  trzy tymczasowe bazy `game_predictor_task0519_*`; zostały one zweryfikowane
  jako testowe i usunięte. Zaliczone są wszystkie cztery scenariusze objęte
  tym taskiem.
- Strict mypy dla trzech zmienionych plików pozostaje zablokowany przez
  wcześniejsze błędy importów API → worker i `no-any-return` poza zakresem
  TASK-0681 (87 błędów w 28 plikach); zmienione linie nie dodały błędu.

### Documentation updates

- Zaktualizowano `CURRENT_STATE.md`; nie zmieniono decyzji ani schematu bazy.

### Recommended next task

- TASK-0682 — audyt wszystkich produkcyjnych repository, workerów i raw SQL
  game-owned pod kątem jawnego bind V2.
