---
title: TASK-0777 — Statyczna „Przybliżona wygrana”, stawka per wzór, układ sekcji
status: done
last_updated: 2026-10-01
---

# TASK-0777 — Statyczna „Przybliżona wygrana”, stawka per wzór, układ sekcji

## Status

`done`

## Goal

Zgłoszenie operatora z 2026-10-01 (D-476): sekcja liczy od razu bez
klikania, kontrolki w jednym wierszu, złote domyślnie, stawka wybierana dla
każdego wyszukania, 15 wyników domyślnie, zakres wyszukiwania przy wynikach,
wykres nad tabelą, tabela ~20 wierszy.

## Scope

- `packages/board-search-ui/src/board-search-approximate-win.tsx`: `<section>`
  zamiast `<details>`; kalkulacja po ustaleniu wyboru (400 ms); kontrolki
  (zakres, stawka z „wybierz stawkę”, jednostka) nad wynikiem; stawka
  trzymana per `searchKey`; komunikat „Wybierz stawkę…” zamiast wyniku;
  wykres przed suwakiem i tabelą; odtworzenie z dziennika wybiera stawkę
  bazową.
- `board-search-stake.ts`: domyślna jednostka `pln`; z pamięci przeglądarki
  czytana tylko jednostka.
- `board-search-workspace.tsx`: `searchKey` wzoru, zakres wyszukiwania
  przekazany do sekcji wyników (`filters`), zmiana zakresu powtarza
  wyszukiwanie z zachowaniem wyboru; `BOARD_SEARCH_LIMIT_DEFAULT = 15`.
- CSS: nagłówek sekcji, wiersz kontrolek, tabela do 720 px.
- API: limit kalkulacji odbiorcy linku 30/min; kontrakt, model zagrożeń,
  plan.
- `ADMIN_APP.md`, D-476.

## Acceptance criteria

- [x] Po wyszukaniu sekcja jest widoczna i liczy dla wybranej planszy bez
  kliknięcia; szybkie przeglądanie wyników wysyła jedno żądanie po
  ustaleniu wyboru.
- [x] Zakres, stawka i jednostka w jednym wierszu; jednostka domyślnie złote.
- [x] Nowy wzór wymaga wyboru stawki; do wyboru wynik ukryty; ta sama
  stawka działa dla kolejnych plansz tego wzoru.
- [x] Limit wyników 15; zakres wyszukiwania w sekcji wyników.
- [x] Wykres nad tabelą; tabela ~20 wierszy.

## Outcome

### Verification results

- Pakiet UI: testy 78/78, interakcje 36/36 (nowe: sekcja statyczna z
  debounce — jedno żądanie po przejściu na następną planszę; wynik ukryty do
  wyboru stawki, złote domyślnie, kontrolki w jednym wierszu, nowy wzór
  czyści stawkę; limit domyślny 15; usunięte testy zwijania).
- API: test limitów domyślnych zaktualizowany (30/min).
- Weryfikacja wizualna (Admin 3010, API 8011, gra 777, 1440 px): limit 15,
  zakres wyszukiwania w sekcji wyników, sekcja `<section>` z komunikatem
  „Wybierz stawkę…”, jednostka złote; po wyborze 1,20 zł cztery kafelki,
  kontrolki w jednym wierszu, wykres przed tabelą, obszar tabeli 720 px.
- Audyt agentem pominięty: wstrzymany przez operatora 2026-10-01.
