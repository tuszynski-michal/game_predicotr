---
title: TASK-0781 — Kwadratowe kafelki symboli w „Wyszukaj plansze”
status: done
last_updated: 2026-10-02
---

# TASK-0781 — Kwadratowe kafelki symboli w „Wyszukaj plansze”

## Status

`done`

## Goal

Zgłoszenie operatora: cropy symboli w palecie i we wzorze są zminiaturyzowane
(38 px w większym kafelku), kafelki palety są prostokątne, a numer skrótu w
lewym górnym rogu ma pełne tło. Kafelek ma być kwadratem wypełnionym cropem,
a numer ma mieć delikatne, przezroczyste tło.

## Scope

- `packages/board-search-ui/src/board-search.css`:
  - `.boardSearchSymbolButton`: `aspect-ratio: 1`, bez dopełnienia, crop
    wypełnia kafelek (`object-fit: cover`); nazwa symbolu jako półprzezroczysty
    podpis przy dolnej krawędzi; kafelki bez grafiki („Nieznany”) bez zmian
    treści.
  - `.boardSearchSymbolShortcut`: bez ramki, tło `rgba(8, 14, 24, 0.4)`.
  - `.boardSearchCell` (pola wzoru): crop wypełnia pole; nazwa i kod są
    ukryte, gdy pole ma grafikę (zostają w `aria-label`).
- Dotyczy też palety korekty symbolu w oknie planszy (ta sama klasa).

## Acceptance criteria

- [x] Kafelki palety są kwadratowe, crop wypełnia cały kafelek.
- [x] Numer skrótu ma przezroczyste, delikatne tło.
- [x] Pola wzoru z symbolem pokazują crop na całym polu.

## Outcome

### Verification results

- Pakiet UI: testy 79/79, interakcje 36/36 (zmiana tylko w CSS).
- Podgląd na działającym Adminie (3000, gra 777, 1440 px) z nowymi regułami
  wstrzykniętymi do strony: kafelek 62 × 62 px wypełniony cropem, numer i
  podpis czytelne. Paleta w oknie planszy nie była oglądana.
