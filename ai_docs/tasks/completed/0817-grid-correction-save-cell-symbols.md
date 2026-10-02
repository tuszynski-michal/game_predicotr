---
title: Zapis symboli operatora przy zapisie siatki
status: done
last_updated: 2026-10-02
---

# TASK-0817 — Zapis symboli operatora przy zapisie siatki

## Status

`done`

## Goal

Zapis geometrii z ekranu korekty przyjmuje symbole narzucone przez operatora i
zatwierdza je w tej samej transakcji.

## Context

Decyzja D-486 zmienia regułę D-462 „zapis geometrii nie weryfikuje symboli”
dla pól wskazanych jawnie przez operatora.

## Dependencies / entry conditions

TASK-0816 wykonane. Fakty i decyzje w planie.

## Recommended execution

`claude-fable-5-1`, poziom bieżącej sesji (nazwy poziomu nie da się odczytać ze środowiska — rekomendacja warunkowa). Eskalacja: rozbieżność kodu z planem
`ai_docs/delivery/GRID_CORRECTION_SYMBOLS_EXECUTION_PLAN.md`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GRID_CORRECTION_SYMBOLS_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-462, D-486)

## Scope

- `cellSymbols` (opcjonalne) w `ImageGridReviewGeometryCommand` i
  `BoardCellGeometryManualResolutionCommand`.
- `VirtualGridGeometryService.save` / `save_pending_slot` oraz
  `BoardCellGeometryPendingService.resolve_manual` przekazują przypisania.
- Port `VirtualGridGeometryRepository.assign_cell_symbols` + implementacja SQL.
- OpenAPI, wygenerowany klient, `save` celów korekty w Reviewerze.

## Out of scope

- UI wyboru symboli (TASK-0819), podpowiedzi (TASK-0818).

## Acceptance criteria

- [x] Zapis z `cellSymbols` zatwierdza wskazane pola (`approved`, `human`).
- [x] Zapis bez `cellSymbols` zachowuje dotychczasowe zachowanie.
- [x] Błąd przypisania wycofuje zapis geometrii.
- [x] Powtórzenie tym samym kluczem ponownie stosuje przypisania.

## Technical notes

Walidacja w serwisie: indeksy unikalne
(`IMAGE_GRID_REVIEW_CELL_SYMBOLS_INVALID`). Repozytorium: po `flush` odczyt
bieżących komórek planszy (`review_item_id`, bieżąca `geometry_revision`,
`source_available`), dla każdej `REASSIGN` z tożsamością odczytaną w tej samej
transakcji; brak komórki → `IMAGE_GRID_REVIEW_SYMBOL_CELL_UNAVAILABLE`.

## Expected files

- `services/api/src/game_predictor_api/application/virtual_grid_geometry.py`
- `services/api/src/game_predictor_api/application/board_cell_geometry_pending.py`
- `services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py`
- `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`
- `services/api/src/game_predictor_api/schemas/image_grid_reviews.py`,
  `schemas/board_cell_geometry_pending.py`, `api/image_grid_reviews.py`,
  `api/board_cell_geometry_pending.py`
- `packages/admin-api-client` (OpenAPI + generated)
- `apps/reviewer/src/features/operational-reviews/board-geometry-correction-target.ts`

## Test cases

- zapis + 2 symbole → repozytorium dostaje dokładnie te przypisania;
- zdublowany indeks → błąd bez zapisu; replay → przypisania stosowane ponownie;
- SQL: pola `approved`/`human`, pozostałe bez zmian.

## Verification

```powershell
npm run python:lint; npm run openapi:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_virtual_grid_geometry.py
```

## Risks / open questions

- Komórki mogą nie istnieć (D-484) — jawny błąd.

## Outcome

### Changed

- `VirtualGridCellSymbol`, `VirtualGridGeometryService.save` /
  `save_pending_slot` (`cell_symbols`), port `assign_cell_symbols`.
- `SqlAlchemyGridCorrectionSymbolRepository.assign` — `REASSIGN` na bieżących
  komórkach planszy w transakcji wywołującego.
- `GridCorrectionCellSymbolPayload`, pole `cellSymbols` obu komend zapisu,
  OpenAPI i wygenerowany klient, `save` celów korekty w Reviewerze.

### Verification results

- `test_virtual_grid_geometry.py` + `_repository.py`: 53 passed.
- `integration/test_grid_correction_cell_symbols_postgres.py`: 1 passed
  (PostgreSQL, izolowana baza testowa).
- `test_board_cell_geometry_pending.py`: 13 passed; klient 76/76; Reviewer
  199/199; typecheck Reviewera czysty; Ruff czysty dla zmienionych plików.
- `test_openapi_contract.py::test_grid_review_openapi_is_topology_aware_and_checksum_bound`
  pada identycznie bez tej zmiany.

### Not completed

- Zapis jednej planszy (`save`) nie ma testu PostgreSQL całego przepływu
  HTTP; pokryte są serwis i repozytorium osobno.

### Documentation updates

- `DECISION_LOG.md` (D-486), `API_CONTRACT.md`, `CURRENT_STATE.md`.

### Recommended next task

- TASK-0818.
