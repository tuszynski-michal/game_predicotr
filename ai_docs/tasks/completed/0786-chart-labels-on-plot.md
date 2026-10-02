---
title: TASK-0786 — Etykiety punktów na wykresie zamiast pasa nad nim
status: done
last_updated: 2026-10-02
---

# TASK-0786 — Etykiety punktów na wykresie zamiast pasa nad nim

## Status

`done`

## Goal

Zgłoszenie operatora z 2026-10-02: po dodaniu czwartego wiersza etykiety pas
na etykiety nad wykresem urósł i sam wykres zrobił się mały. Wykres ma
zajmować całą przestrzeń; etykiety mogą leżeć na nim, obok punktu, połączone
przerywaną linią, i mogą lekko zasłaniać wykres. Liczbę znaczników można
ograniczyć.

## Scope

- `board-search-approximate-win-state.ts`: `layoutApproximateWinPointLabels`
  zastępuje układ rzędów w pasie. Kandydaci: obok punktu (lewo/prawo ×
  nad/pod/na wysokości, trzy odległości), potem miejsca przyległe do już
  ułożonych etykiet i krawędzi, potem rzadka siatka. Wybór: bez nakładania
  na inną etykietę, potem najmniej próbek linii wykresu pod etykietą, potem
  najbliżej punktu. Etykieta 200 × 56. `APPROXIMATE_WIN_PIN_LIMIT` 8 → 6.
- `board-search-approximate-win.tsx`: brak pasa etykiet, obszar danych
  12…352 (340 jednostek), próbki linii wykresu jako przeszkody, linia
  prowadząca od najbliższej krawędzi etykiety do punktu.

## Acceptance criteria

- [x] Nad wykresem nie ma pustego pasa; obszar danych zajmuje całą wysokość.
- [x] Etykieta leży na wykresie obok punktu i nie zasłania własnego punktu.
- [x] Etykiety nie nakładają się na siebie przy 6 przypiętych punktach i
  etykiecie najechania.

## Outcome

### Verification results

- Pakiet UI: testy 76/76 (nowe testy układu: w granicach wykresu, z dala od
  linii przy wolnym miejscu, 1500 losowych układów 6 przypięć + najechanie
  bez nakładania), interakcje 36/36, typecheck i lint bez uwag.
- Pomiar na 3000 losowych układów: przy 7 przypięciach nakładanie w 9
  układach, przy 8 w 88 — stąd limit 6.
