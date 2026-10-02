---
title: TASK-0755 — S2 — bramka usuwania symbolu liczona z komórek V2
status: done
last_updated: 2026-09-30
---

# TASK-0755 — S2 — bramka usuwania symbolu liczona z komórek V2

## Status

`done`

## Goal

`symbol_usage_summary` (bramka `SYMBOL_DELETE_BLOCKED`) liczy predykcje
symbolu z `image_symbol_review_cells.prediction_symbol_code` zamiast ze skanu
`cell_observations` (28 GB, JSONB `prediction->>'symbolCode'`).

## Context

D-467, S2 (plan `LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md`). Dwa
liczniki (`pending_board_predictions`, `observation_predictions`) skanowały
`cell_observations` z trzema joinami. Komórka V2 trzyma bieżącą predykcję
w kolumnie `prediction_symbol_code` (bez indeksu; bramka działa tylko przy
usuwaniu symbolu, więc skan partycji gry wystarcza).

## Dependencies / entry conditions

- TASK-0754 done (v1.7.85).

## Recommended execution

`claude-opus-5-5`, reasoning `medium` (warunkowo). Audyt: `claude-opus-5-5`,
`medium`, osobny agent.

## Relevant docs

- `ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-467)

## Scope

- `storage/catalog_repository.py::symbol_usage_summary`:
  `pending_board_predictions` = komórki gry z `prediction_symbol_code` =
  kod symbolu na review itemach `pending`; `observation_predictions` =
  wszystkie komórki gry z tą predykcją. Pozostałe liczniki bez zmian.
- Test kompilacji SQL bez bazy.

## Out of scope

- Zmiana pól `SymbolUsageSummary` i kontraktu API (nazwy zostają;
  `observation_predictions` oznacza teraz predykcje na komórkach).

## Acceptance criteria

- [x] Żadne zapytanie bramki nie czyta `cell_observations`.
- [x] Blokada liczy bieżące predykcje: symbol z jakąkolwiek bieżącą
  predykcją na komórce V2 blokuje usunięcie (świadome zawężenie, patrz
  Technical notes).
- [x] Ruff, mypy, testy katalogu; audyt bez P0–P2.

## Technical notes

- **Zawężenie semantyki (zmiana bramki domenowej, nota w D-467):** stara
  bramka liczyła historyczne predykcje z importu; nowa liczy predykcje
  bieżące. Nie widzi: plansz `superseded` bez komórek (777: 10 390), predykcji
  nadpisanych nowszą rewizją (przeliczenie modelem, biblioteka wzorców —
  `prediction_symbol_code` trzyma wtedy propozycję biblioteki), zamaskowanych
  pozycji bez komórek. Zawężenie jest nieuniknione, bo `cell_observations`
  znika w S5, i nie tworzy luki: odwołania w JSONB nie mają FK, a grę z
  artefaktami modelu blokują fail-closed liczniki kohort, iteracji i
  aktywacji. Pomiar na 777: każdy z 8 symboli ma setki tysięcy trafień w obu
  źródłach (SIEDEM: 587 226 obserwacji, 624 312 komórek).
- Join `image_review_items` po `(game_id, id)`; `cell.game_id` daje
  przycinanie partycji zamiast przejścia przez `public.jobs`.
- Kod symbolu jest unikalny w grze; porównanie po kodzie, jak wcześniej.
- Etykieta „predykcje obserwacji” w Adminie
  (`apps/admin/src/features/symbols/symbol-catalog-actions.ts`) oznacza
  teraz predykcje na komórkach; zmiana etykiety poza zakresem.

## Test cases

- `services/api/tests/test_catalog_symbol_usage_statements.py`: instrukcje
  bramki nie zawierają `cell_observations`; dwa liczniki predykcji czytają
  `image_symbol_review_cells` z filtrem `game_id` i kodem symbolu, jeden z
  joinem `image_review_items` po `(game_id, id)` i `status`.

## Verification

```powershell
$env:PYTHONPATH = "services/worker/src;services/api/src"
.\.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/storage/catalog_repository.py services/api/tests/test_catalog_symbol_usage_statements.py
$env:MYPYPATH = "services/api/src;services/worker/src"; .\.venv\Scripts\python.exe -m mypy --strict --follow-imports=silent services/api/src/game_predictor_api/storage/catalog_repository.py
.\.venv\Scripts\python.exe -m pytest -q services/api/tests/test_catalog_symbol_usage_statements.py services/api/tests/test_catalog_api.py services/api/tests/test_catalog_domain.py
```

## Outcome

### Changed

- `symbol_usage_summary`: liczniki `pending_board_predictions` i
  `observation_predictions` z komórek V2 (`prediction_symbol_code`, join
  `image_review_items` po `(game_id, id)`); import `CellObservationModel`
  usunięty z repozytorium katalogu.
- Test `test_catalog_symbol_usage_statements.py`; nota o bramce w D-467.

### Verification results

- Ruff, mypy `--strict`, 15 testów katalogu.
- Audyt `claude-opus-5-5`: FAIL (P2: plik zadania błędnie twierdził
  równoważność semantyczną; pomiar: 10 390 plansz `superseded` bez komórek,
  predykcje nadpisane rewizjami) → uczciwy opis zawężenia i nota D-467 →
  PASS. P3 wdrożone (join po `game_id`, mocniejszy test, dokumenty).
  Pominięty test integracyjny PostgreSQL (P3, bramka tylko w `delete_symbol`).
