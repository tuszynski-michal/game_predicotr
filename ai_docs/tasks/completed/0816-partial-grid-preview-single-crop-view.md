---
title: Partial grid preview and single crop view
status: done
last_updated: 2026-10-02
---

# TASK-0816 — podgląd korekty siatki dla niepełnych plansz, jeden widok cropów

## Status

`done`

## Goal

Umożliwić podgląd korekty siatki dla niepełnych plansz i pokazywać w Reviewerze
jeden widok cropów zamiast dwóch.

## Context

Podgląd niepełnej planszy zwracał `IMAGE_GRID_REVIEW_VIRTUAL_CELLS_INCOMPLETE`:
`_contact_sheet_png` oczekiwał renderów dokładnie dla pól spoza maski
`unavailableCellIndices`, a `derive_virtual_cells` od D-434/D-435 renderuje
także pola z maski, które mają rzeczywiste piksele. Reviewer pokazywał ten sam
arkusz dwukrotnie: jako obraz zbiorczy i jako kafelki.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-434, D-435, D-462)

## Scope

- Kontrola kompletności arkusza podglądu zgodna z renderami częściowymi.
- Usunięcie zdublowanego obrazu zbiorczego w edytorze korekty.

## Out of scope

- Przypisywanie symboli w korekcie siatki i podgląd predykcji (wymaga planu
  i zmiany D-462).

## Acceptance criteria

- [x] Podgląd planszy z maską pól częściowo widocznych zwraca PNG i komórki.
- [x] Pole spoza maski bez renderu nadal jest błędem.
- [x] Edytor pokazuje jeden widok 15 cropów.

## Technical notes

Wymagane: `wszystkie − maska ⊆ wyrenderowane ⊆ wszystkie`. Zapis geometrii nie
używa arkusza podglądu, więc jego zachowanie się nie zmienia.

## Expected files

- `services/api/src/game_predictor_api/application/virtual_grid_geometry.py`
- `services/api/tests/test_virtual_grid_geometry.py`
- `apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx`
- `apps/reviewer/test-interactions/deferred-geometry.test.mjs`

## Outcome

### Changed

- Poluzowana kontrola `_contact_sheet_png`; test podglądu częściowego opisuje
  bieżące zachowanie renderera i ma nową nazwę.
- Usunięty `<img>` arkusza zbiorczego; test interakcji czyta kafelek.

### Verification results

- `test_virtual_grid_geometry.py` + `test_virtual_grid_geometry_repository.py`:
  50 passed.
- `test:geometry` Reviewera 9/9; `typecheck` i `lint` Reviewera czyste; Ruff
  i Prettier czyste.

### Not completed

- Brak odbioru na żywym Reviewerze; wymagany restart API i przebudowa
  Reviewera.

### Documentation updates

- `CURRENT_STATE.md`.

### Recommended next task

- Plan przypisywania symboli w korekcie siatki (decyzja zastępująca regułę
  D-462 „zapis siatki nie zatwierdza symboli”).
