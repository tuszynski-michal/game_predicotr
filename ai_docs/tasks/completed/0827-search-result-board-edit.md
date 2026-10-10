---
title: Poprawianie planszy z wyników wyszukiwania
status: done
last_updated: 2026-10-03
---

# TASK-0827 — Poprawianie planszy z wyników wyszukiwania

## Status

`done`

## Goal

Z karty „Wyniki wyszukiwania” można otworzyć to samo okno planszy z liniami
wypłat co z tabeli „Przybliżona wygrana” i poprawić w nim pola, gdy znaleziona
plansza się nie zgadza.

## Context

Okno `BoardSearchBoardLinesModal` było dostępne tylko z wierszy tabeli
przybliżonej wygranej i wymagało jej wiersza.

## Scope

- Przycisk „Pokaż planszę” w `BoardSearchResults` dla aktywnego wyniku.
- Okno przyjmuje `sequenceNumber` i opcjonalny wiersz tabeli (`null` z wyników):
  nagłówek bez numeru spinu, wygrana i spójność linii z odczytu planszy.
- Po zapisanej poprawce wyszukiwanie uruchamia się ponownie ze zachowaniem
  zaznaczonego wyniku.

## Out of scope

- Zmiany API; poprawianie geometrii siatki z tego okna.

## Acceptance criteria

- [x] Aktywny wynik ma przycisk „Pokaż planszę”, który otwiera okno planszy.
- [x] W oknie działa „Popraw symbole” (symbol, „Nieczytelny”, „Zła siatka”).
- [x] Zamknięcie po poprawce ponawia wyszukiwanie; bez poprawki tylko zamyka.

## Verification

```powershell
npm run test:interactions --workspace @game-predictor/board-search-ui
npm run typecheck --workspace @game-predictor/board-search-ui
```

## Outcome

### Changed

- `board-search-board-lines-modal.tsx`, `board-search-results.tsx`,
  `board-search-workspace.tsx`, `board-search-approximate-win.tsx`
  (`unitNoun` wyeksportowany), test interakcji.

### Verification results

- Interakcje 38/38 (1 nowy), typecheck i lint pakietu, typecheck Admin i
  Reviewera czyste.

### Not completed

- Brak odbioru na żywym Reviewerze; wymagany `reviewer:build` i restart.
