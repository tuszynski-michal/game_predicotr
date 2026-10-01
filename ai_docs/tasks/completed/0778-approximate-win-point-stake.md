---
title: TASK-0778 — „Wkład” w etykiecie punktu wykresu bilansu
status: done
last_updated: 2026-10-01
---

# TASK-0778 — „Wkład” w etykiecie punktu wykresu bilansu

## Status

`done`

## Goal

Zgłoszenie operatora z 2026-10-01: kafelek „Maksymalny wkład” dotyczy całego
zakresu, a operator często liczy tylko od początku do wybranego punktu (np.
do 500. spinu). Etykieta punktu ma pokazać trzecią wartość: ile trzeba mieć
od zera, żeby dojść do tego punktu. Nazwa krótka: „Wkład”.

## Scope

- `board-search-approximate-win-state.ts`: `approximateWinStakeToPoint`
  (najgłębszy dołek od spinu 1 do punktu; spin opłacany przed wypłatą, co
  najmniej koszt jednego spinu); wysokość etykiety 30 → 43.
- `board-search-approximate-win.tsx`: trzeci wiersz etykiety „Wkład: …”,
  ta sama wartość na liście przypiętych punktów i w opisie przycisku
  odpinania; zdanie objaśnienia pod nagłówkiem wykresu.
- `ADMIN_APP.md`.

## Acceptance criteria

- [x] Etykieta najechanego i przypiętego punktu pokazuje „Wkład” w wybranej
  jednostce i stawce.
- [x] Wartość uwzględnia tylko dołki do punktu, nie późniejsze.

## Outcome

### Verification results

- Pakiet UI: testy 79/79 (nowy test funkcji), interakcje 36/36 (etykieta i
  lista przypięć z „Wkład”, przeliczenie stawką i jednostką), typecheck
  czysty.
- Weryfikacja wizualna nie została wykonana: testowe API 8011 było
  zatrzymane przez równoległy tor pracy. Audyt agentem wstrzymany przez
  operatora.
