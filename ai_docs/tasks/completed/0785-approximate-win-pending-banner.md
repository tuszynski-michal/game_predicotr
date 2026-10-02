---
title: TASK-0785 — Usunięcie banera o niezatwierdzonej planszy startowej
status: done
last_updated: 2026-10-02
---

# TASK-0785 — Usunięcie banera o niezatwierdzonej planszy startowej

## Status

`done`

## Goal

Zgłoszenie operatora z 2026-10-02: komunikat „Plansza startowa #N nie jest
jeszcze zatwierdzona — jej pozycja w sekwencji może się jeszcze zmienić” nie
jest potrzebny. Po D-479 wyszukiwanie zawsze obejmuje plansze oczekujące,
więc baner pojawiał się przy większości wyników.

## Scope

- `packages/board-search-ui/src/board-search-approximate-win.tsx`: usunięty
  baner dla `startBoardStatus === 'pending'`. Pole w odpowiedzi API zostaje.

## Acceptance criteria

- [x] Baner nie jest pokazywany; ostrzeżenie o zawinięciu sekwencji zostaje.

## Outcome

### Verification results

- Pakiet UI: testy 79/79, interakcje 36/36, typecheck czysty.
