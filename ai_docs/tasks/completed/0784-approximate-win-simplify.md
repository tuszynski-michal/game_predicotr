---
title: TASK-0784 — Uproszczenie „Przybliżonej wygranej”, wyników i okna planszy
status: done
last_updated: 2026-10-02
---

# TASK-0784 — Uproszczenie „Przybliżonej wygranej”, wyników i okna planszy

## Status

`done`

## Goal

Zgłoszenie operatora z 2026-10-02 (D-479), plan zaakceptowany w trybie
planowania: nazwy „kasa na czysto” i „wygrana”, „kasa na maszynie” i
czerwony wkład w etykiecie punktu, usunięcie kafelków, wiersza reguł, radia
zakresu i statusu planszy, tytuł sekcji z planszą startową, większe okno
planszy.

## Scope

- `packages/board-search-ui/src/board-search-approximate-win.tsx`: tytuł
  sekcji, usunięte kafelki i wiersz reguł, nowe nazwy w tabeli, suwaku,
  wykresie i komunikatach, czwarty wiersz etykiety punktu, lista
  przypiętych punktów.
- `board-search-approximate-win-state.ts`: `approximateWinMachineCashAtPoint`;
  usunięte `approximateWinMaximumStake`; etykieta 56 × 182.
- `board-search-workspace.tsx`, `board-search-results.tsx`: bez radia
  zakresu (zawsze `all_searchable`) i bez statusu w nagłówku wyników.
- `board-search-board-lines-modal.tsx`: „wygrana” w tekstach okna.
- `board-search.css`: czerwony wkład, usunięte style zakresu, okno planszy
  do 1500 px z kartą na całą szerokość, plansza do 76vh.
- D-479, `ADMIN_APP.md`.

## Acceptance criteria

- [x] „Kasa na czysto” i „Wygrana” zamiast „Bilans” i „Wypłata”.
- [x] Etykieta punktu: kasa na czysto, wkład (czerwony), kasa na maszynie.
- [x] Brak czterech kafelków i wiersza reguł; tytuł „Plansza startowa #N ·
  X spinów”.
- [x] Brak radia zakresu; brak statusu w nagłówku wyników.
- [x] Okno planszy wykorzystuje szerokość dialogu.

## Outcome

### Verification results

- Pakiet UI: testy 79/79, interakcje 36/36; Admin 604/604, Reviewer
  194/194; typecheck Admina i Reviewera, lint pakietu bez uwag.
- Szerokość etykiety 182 to największa, przy której test układu ośmiu
  przypiętych punktów i etykiety najechania nie wykrywa nakładania.
