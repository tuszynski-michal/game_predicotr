---
title: TASK-0787 — Zwarty tooltip wykresu i zaokrąglone kwoty
status: done
last_updated: 2026-10-02
---

# TASK-0787 — Zwarty tooltip wykresu i zaokrąglone kwoty

## Status

`done`

## Goal

Zgłoszenie operatora z 2026-10-02: tooltip jest za długi i ma wolne miejsce
po prawej, a czcionka i pogrubienia są zbędne. „Kasa na maszynie” ma się
nazywać „Kredyty” i zawsze być w pełnych kredytach. Wygrana i kasa na czysto
zaokrąglone do pełnych złotych. Pierwsza linia: spiny po lewej, wkład po
prawej.

## Scope

- `board-search-stake.ts`: `formatApproximateWinWholeAmount` (złote do
  pełnego złotego, kredyty do pełnego kredytu, bez „-0”).
- `board-search-approximate-win.tsx`: etykieta 190 × 44, trzy linie; „Kredyty”
  zawsze w kredytach; zaokrąglone „Wygrana” i „Kasa na czysto” w tabeli,
  etykiecie i liście przypiętych punktów; przycisk „×” w prawym dolnym rogu.
- `board-search.css`: bez pogrubienia etykiety.
- Testy, `ADMIN_APP.md`.

## Acceptance criteria

- [x] Linia 1: „N spinów” z lewej, „wkład: X” (czerwony) z prawej.
- [x] Linie 2–3: „Kasa na czysto: X”, „Kredyty: N”, bez pogrubień.
- [x] Kredyty bez części dziesiętnych niezależnie od jednostki.
- [x] Wygrana i kasa na czysto zaokrąglone.

## Outcome

### Verification results

- Pakiet UI: testy i interakcje zielone (nowy test zaokrągleń, zaktualizowane
  asercje etykiety), typecheck i lint bez uwag.
