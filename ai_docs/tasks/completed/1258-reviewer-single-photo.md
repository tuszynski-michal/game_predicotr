# TASK-1258 — Korekta plansz jednego zdjęcia

## Status

`done`

## Goal

Link z listy zdjęć otwiera w lokalnym Reviewerze wyłącznie plansze wskazanego zdjęcia.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/TECH_STACK.md`

## Scope

Strona Reviewera, bramka dostępu, edytor geometrii i linki lokalnej listy operatora. Używamy istniejącego filtru API po zdjęciu i imporcie.

## Acceptance criteria

- Zapis i nawigacja zachowują zakres zdjęcia. Koniec zakresu pozwala wrócić do listy.
- Błędny adres lub niedostępne źródło nie otwiera całego importu.
- Zwykła kolejka korekt zachowuje dotychczasową obsługę.

## Outcome

Commit: v1.7.690 (hash dopisuje kolejny commit).

Osobny lokalny adres wiąże edytor z grą, importem i zdjęciem od pierwszego pobrania do ostatniego zapisu. Widok pomija historię i akcje obejmujące cały import. Interakcje 42/42, kontrakty 9/9, typy i lint zaliczone. Odczyt lokalnego API potwierdził po dziewięć właściwych plansz dla wszystkich 30 zdjęć.
