---
title: TASK-0788 — Zdjęcie planszy w oknie „Pokaż planszę” do 800 px
status: done
last_updated: 2026-10-02
---

# TASK-0788 — Zdjęcie planszy w oknie „Pokaż planszę” do 800 px

## Status

`done`

## Goal

Zgłoszenie operatora z 2026-10-02: po poszerzeniu okna (TASK-0784) zdjęcie
planszy jest za duże; ma mieć najwyżej 800 px szerokości.

## Scope

- `packages/board-search-ui/src/board-search.css`: kolumna planszy w oknie
  `minmax(0, 800px)`, `max-inline-size: 800px` dla SVG planszy; okno
  zwężone do 1180 px (800 px plansza + 300 px legenda), żeby nie zostawało
  puste miejsce po prawej.

## Acceptance criteria

- [x] Plansza w oknie ma najwyżej 800 px szerokości; legenda obok.

## Outcome

### Verification results

- Tylko CSS; interakcje 36/36. Na żywym Adminie (1440 px) plansza w oknie
  ma 800 × 388 px, legenda 300 px.
