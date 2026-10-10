---
title: TASK-0931 — audyt niezależny (claude-fable-5-1 / high)
status: accepted
last_updated: 2026-10-08
---

# TASK-0931 — audyt: Wild, „Uruchamia supergrę” i rodzaj supergry

Audytor: niezależny subagent claude-fable-5-1 / high, świeży kontekst, tylko
odczyt (zamiennik audytu gpt-6-astra do czasu dostępności CLI, D-535).
Wykonawca: claude-opus-5-5 / high. Zakres: zmiany niezacommitowane względem
v1.7.267 (6323939f) w worktree `mumie-super-game`.

## Werdykt

PASS. Brak P0 i P1. Cztery znaleziska P2, naprawione przez wykonawcę w jednej
rundzie poprawek przed commitem. Osiem odstępstw od pliku taska zaakceptowane.

## Znaleziska P2 (naprawione)

1. Endpoint `GET /super-game-kinds` poza prefiksem `/admin`, wbrew konwencji
   routera. Naprawione: `/api/v1/admin/super-game-kinds`, OpenAPI i klient
   zregenerowane, testy i dokumenty zaktualizowane.
2. Opis sekcji symboli nadal mówił o skrótach `1–9` w weryfikacji symboli
   (uwaga przekazana z audytu TASK-0930). Naprawione: „1–9 i 0 w weryfikacji
   symboli oraz 1–9 w wyszukiwarce plansz”.
3. `super_game_trigger_count` nieobowiązkowe w `SymbolResponse`, więc TS
   miał `?: number | null`. Naprawione: pole wymagane, adaptery Reviewera
   ustawiają `null`, zbędne sprawdzenia `!== undefined` usunięte.
4. Trzecia kopia stałej `"none"` w `domain/rules.py`. Naprawione: import
   `NO_SUPER_GAME` z `domain/catalog.py`.

## Odstępstwa wykonawcy (zaakceptowane)

1. Przy zyskaniu roli Wild lub uruchamiającej `minimum_match_length` jest
   czyszczone wyłącznie w wersjach `draft`, w tej samej transakcji; wypłaty
   nietknięte. Utrata obu ról nie przywraca minimum (readiness zgłasza
   `INVALID_MINIMUM_MATCH_LENGTH`; operator ustawia je w zakładce reguł).
2. `SUPER_GAME_KIND_IN_USE` (409) przy zmianie rodzaju gry na `none`, gdy
   symbol ma rolę uruchamiającą.
3. Blokada zmiany roli obejmuje także wersje `archived` (były opublikowane).
4. `payout_configuration_fits_dimensions` sprawdza też `rows`.
5. Pole trigger w TS — po poprawce 3 wymagane.
6. Leniwy import rejestru rodzajów w domenie katalogu (Alembic bez workera);
   pakiet workera jest w procesie API przez wspólny `pyproject.toml`.
7. `definition.py` w rejestrze i CHECK formatu kodu rodzaju w bazie.
8. Ścieżka endpointu — po poprawce 1 pod `/admin`.

## Sprawdzone bez uwag

- Migracja `0151_super_game_roles` addytywna, jeden head; cykl
  upgrade → downgrade `0150` → upgrade na jednorazowej bazie
  `game_predictor_audit0931` (usuniętej po teście); strażnik schematu
  startowego i jego testy przypięte do nowego head.
- Reguły domeny zgodne z planem (trigger null/3/4/5, rodzaj gry ≠ `none`,
  blokada po publikacji, wypłaty za sztuki 2…rows×columns rosnące, Wild bez
  roli jak dotąd, readiness odrzuca trigger przy `none`); 777 bez zmian
  zachowania (żadna asercja testów nie została osłabiona).
- Pion API: schematy, OpenAPI, klient, wrapper, test żądań; Admin: etykieta
  „Wild”, checkbox i select 3/4/5, select rodzaju w tworzeniu i edycji gry,
  pola „sztuk na planszy”; dokumenty DATA_MODEL/API_CONTRACT/ADMIN_APP
  spójne; instrukcja operatora wykonalna.
- Trzy nowe testy po audycie: utrata obu ról nie przywraca minimum,
  readiness zgłasza `INVALID_MINIMUM_MATCH_LENGTH`, symbol uruchamiający
  bez wypłat jest publikowalny.

## Testy uruchomione przez audytora

- Pytest katalog/reguły/readiness/rejestr: 74 PASS; po poprawkach 72 PASS
  w zestawie skupionym (wykonawca).
- `alembic heads`: `0151_super_game_roles (head)`; cykl migracji na bazie
  jednorazowej OK.
- PostgreSQL `integration/test_catalog_repository.py`: 4 PASS.
- `npm run openapi:check`: aktualne. Admin test 679/679, typecheck i lint
  (0 błędów, 5 istniejących ostrzeżeń); admin-api-client 102/102; Reviewer
  i board-search-ui typecheck PASS; ruff i mypy --strict na zmienionych
  modułach czyste.

Wyniki istniejące wcześniej poza zakresem: błąd kolekcji
`test_v7_independent_progress.py`, manifest `test_game_data_v2_schema`
(tabele V7), test cyklu bazowego (tabele `management_*`), ruff I001 w
`storage/models.py`, błędy mypy w 7 niezmienionych plikach.
Przegląd statyczny, bez zmian plików przez audytora.
