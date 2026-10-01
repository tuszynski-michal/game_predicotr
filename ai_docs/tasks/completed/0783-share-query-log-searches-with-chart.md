---
title: TASK-0783 — Dziennik linku: wyszukiwania z wykresem, usuwanie wpisu
status: done
last_updated: 2026-10-02
---

# TASK-0783 — Dziennik linku: wyszukiwania z wykresem, usuwanie wpisu

## Status

`done`

## Goal

Zgłoszenie operatora z 2026-10-02 (D-478): w dzienniku udostępnionego linku
liczy się tylko wzór, który odbiorca wpisał, i wykres wygranych planszy,
którą otworzył. Wpisy przybliżonej wygranej i szczegółów planszy oraz linia
opisu zaśmiecają widok. Wykres ma zająć resztę szerokości wpisu. Przejrzany
wpis ma dać się usunąć.

## Scope

- API: filtr `kind` listy dziennika; `followUpApproximateWin` we wpisie
  wyszukiwania; `DELETE /admin/board-search-shares/queries/{eventId}`
  (wyszukiwanie usuwa też swoje późniejsze zapisy do następnego
  wyszukiwania); operacja wysokiego wpływu `delete-board-search-share-query`.
- OpenAPI, wygenerowany klient, wrapper (`kind`, `deleteBoardSearchShareQuery`).
- `packages/board-search-ui`: eksport `ApproximateWinBalanceChart` z trybem
  `compact` i identyfikatorami per instancja (`useId`).
- Admin: dziennik listuje `kind=search` po 10; wpis = godzina, akcje
  („Odtwórz w wyszukiwarce”, „Usuń” z potwierdzeniem), wzór 3 × 5 i wykres
  liczony kolejno (jedna kalkulacja naraz), stawka bazowa w złotych.
- `API_CONTRACT.md`, `ADMIN_APP.md`, D-478.

## Acceptance criteria

- [x] Dziennik pokazuje wyłącznie wyszukiwania.
- [x] Wpis z uruchomioną przybliżoną wygraną pokazuje jej wykres; bez niej
  krótką informację.
- [x] Linia „Zakres … limit … wyniki …” nie jest pokazywana.
- [x] Wpis można usunąć po potwierdzeniu; znika z listy i z bazy razem z
  zapisami pochodnymi.

## Outcome

### Verification results

- API: `test_board_search_share_query_log.py` 10/10 (filtr rodzaju,
  powiązany zakres tylko z okna do następnego wyszukiwania i tylko udany,
  usuwanie zakresem, trasa HTTP i wpis operacji wysokiego wpływu).
- Klient 71/71, Admin 599/599, pakiet UI 79/79 i 36/36, typecheck Admina i
  Reviewera, lint Admina bez błędów, ruff czysty.
- Zapytania repozytorium SQL (`next_event_key`,
  `latest_successful_event_between`, `delete_events`) nie mają testu na
  PostgreSQL.
