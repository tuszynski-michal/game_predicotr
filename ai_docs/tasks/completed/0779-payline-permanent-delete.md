---
title: TASK-0779 — Trwałe usunięcie wzorca wypłat w wersji roboczej
status: done
last_updated: 2026-10-01
---

# TASK-0779 — Trwałe usunięcie wzorca wypłat w wersji roboczej

## Status

`done`

## Goal

Zgłoszenie operatora z 2026-10-01: w modalu „Wzorce wypłat” wzorzec można
tylko zarchiwizować, a zarchiwizowany nadal blokuje dodanie nowego (zajęty
kod i ścieżka). Operator chce móc wzorzec usunąć (D-477).

## Scope

- API: `RulesService.delete_payline` (blokada wersji, tylko draft),
  `SqlAlchemyRulesRepository.delete_payline`, trasa
  `DELETE /rules-versions/{id}/paylines/{paylineId}/permanent`
  (`deletePayline`), wpis operacji wysokiego wpływu `delete-payline`.
- OpenAPI i wygenerowany klient, wrapper `deletePayline` z nagłówkami
  potwierdzenia.
- Admin: `deletePayline` w `payline-actions.ts`, `removePayline` w stanie,
  przycisk „Usuń” z potwierdzeniem „Usuń trwale” w modalu.
- `API_CONTRACT.md`, `ADMIN_APP.md`, D-477.

## Acceptance criteria

- [x] W wersji roboczej wzorzec (aktywny albo zarchiwizowany) można usunąć
  po potwierdzeniu; znika z tabeli.
- [x] Po usunięciu można dodać wzorzec z tym samym kodem i ścieżką.
- [x] W wersji opublikowanej usunięcie zwraca `RULES_VERSION_IMMUTABLE`.
- [x] Archiwizacja działa jak dotąd.

## Outcome

### Verification results

- API: `test_rules_api.py`, `test_rules_domain.py` zielone (usunięcie,
  404 po usunięciu, ponowne utworzenie z tym samym kodem i ścieżką, 409 dla
  wersji opublikowanej); mapa operacji w `test_openapi_contract.py`
  uzupełniona. Test integracyjny PostgreSQL uzupełniony, nieuruchamiany
  (wymaga `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`).
- Klient 71/71, Admin 598/598, typecheck i lint Admina bez błędów, ruff
  czysty.
- Dwa testy `test_openapi_contract.py` (grid review, operational image
  reviews: `KeyError: 'minItems'`) są czerwone niezależnie od tej zmiany.
- Bez weryfikacji w przeglądarce; audyt agentem wstrzymany przez operatora.
