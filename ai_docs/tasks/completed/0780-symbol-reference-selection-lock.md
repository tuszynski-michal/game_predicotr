---
title: TASK-0780 — Blokada kandydata przy ustawianiu grafiki symbolu
status: done
last_updated: 2026-10-01
---

# TASK-0780 — Blokada kandydata przy ustawianiu grafiki symbolu

## Status

`done`

## Goal

Zgłoszenie operatora z 2026-10-01: „Ustaw jako grafikę symbolu” w Weryfikacji
symboli kończyło się komunikatem „Crop zatwierdzono, ale nie ustawiono
grafiki symbolu: nieznany błąd”. API zwracało 500:
`FOR UPDATE cannot be applied to the nullable side of an outer join`.

## Scope

- `storage/symbol_references_repository.py`: zapytanie kandydata dołącza
  rewizję geometrii źródła przez `LEFT OUTER JOIN`, a `_locked_current_candidate`
  używało gołego `FOR UPDATE`. Blokada dostaje jawną listę
  (`FOR UPDATE OF` pole, pozycja review, plansza, symbol); niezmienna rewizja
  geometrii nie jest blokowana.
- Test kompilacji zapytania dla dialektu PostgreSQL.

## Acceptance criteria

- [x] Zapytanie blokujące wykonuje się na PostgreSQL.
- [x] Blokada nie obejmuje tabeli z zewnętrznego złączenia.

## Outcome

### Verification results

- `test_symbol_references_repository.py` 7/7 (nowy test listy `FOR UPDATE OF`).
- Zapytanie wykonane na bazie deweloperskiej dla pola ze zgłoszenia
  (`a8c51553-…`), w transakcji wycofanej bez zapisu: 1 wiersz, bez błędu.
- Pełnej ścieżki (zapis grafiki) nie uruchamiałem; wymaga restartu API.
