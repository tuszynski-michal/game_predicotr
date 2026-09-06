---
title: Cancel disconnected symbol review SQL
status: done
last_updated: 2026-09-07
---

# TASK-0499 — Przerywanie SQL po rozłączeniu klienta

## Status

`done`

## Goal

Przerwać aktywne zapytanie listy lub liczników Weryfikacji symboli, gdy klient
HTTP rozłączy się przed otrzymaniem odpowiedzi.

## Context

TASK-0497 anuluje nieaktualne requesty w przeglądarce, a TASK-0498 ogranicza
czas SQL. Synchroniczny endpoint FastAPI nie propaguje jednak rozłączenia do
synchronicznego połączenia psycopg, więc porzucone zapytanie może nadal zajmować
PostgreSQL aż do `statement_timeout`.

## Dependencies / entry conditions

- TASK-0497 i TASK-0498 są ukończone.
- API używa SQLAlchemy 2 i psycopg 3.3.4, który udostępnia thread-safe
  `Connection.cancel_safe()`.

## Recommended execution

`gpt-5.6-sol` z poziomem `medium`: zmiana jest wąska, lecz dotyczy cyklu życia
requestu, pracy w innym wątku i bezpiecznego zwalniania sesji bazy. Mocniejszy
review jest potrzebny, jeśli implementacja miałaby zmienić wspólny model sesji
albo middleware całego API.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`

## Scope

- Uruchomić synchroniczne odczyty listy i liczników poza pętlą ASGI.
- Monitorować `Request.is_disconnected()` do zakończenia odczytu.
- Powiązać repozytorium bieżącego requestu z aktywnym połączeniem psycopg i po
  rozłączeniu wywołać `cancel_safe()`.
- Po wysłaniu anulowania zaczekać na zakończenie wątku zapytania przed
  zwolnieniem zależności i sesji.
- Zachować `statement_timeout` jako niezależną górną granicę.

## Out of scope

- Optymalizacja zapytania liczników (TASK-0500).
- Zmiana filtrów, paginacji, odpowiedzi API albo schematu bazy.
- Anulowanie mutacji, assetów i innych endpointów.

## Acceptance criteria

- [x] Rozłączenie klienta wywołuje anulowanie aktualnego odczytu PostgreSQL.
- [x] Anulowanie jest ograniczone do połączenia i sesji danego requestu.
- [x] Zwykłe ukończenie nie wywołuje anulowania.
- [x] Wyścig przed rozpoczęciem SQL nie pozostawia niepilnowanego zapytania.
- [x] Sesja nie jest zwalniana, dopóki wątek odczytu się nie zakończy.
- [x] Timeout z TASK-0498 i publiczny kontrakt odpowiedzi pozostają bez zmian.

## Technical notes

Endpointy listy i liczników stają się `async`, ale ich synchroniczny use case
jest wykonywany w threadpoolu. Krótki watcher cyklu ASGI sprawdza rozłączenie.
Po pierwszym rozłączeniu ponawia próbę anulowania do chwili, gdy repozytorium
zarejestruje aktywne połączenie albo query się zakończy; eliminuje to wyścig
między startem workera i sygnałem disconnect.

Repozytorium utrzymuje pod blokadą wyłącznie referencję do driver connection
aktywnego w `bounded_read`. `cancel_safe()` jest wywoływane pod tą samą blokadą,
aby połączenie nie mogło zostać wyczyszczone i później użyte przez inny request
w czasie wysyłania cancel. Wynikowy PostgreSQL `57014` nadal przechodzi przez
kontrolowaną obsługę TASK-0498; po rozłączeniu odpowiedź nie ma odbiorcy.

## Expected files

- `services/api/src/game_predictor_api/application/image_symbol_reviews.py`
- `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`
- `services/api/src/game_predictor_api/api/image_symbol_reviews.py`
- `services/api/tests/test_image_symbol_reviews_api.py`
- `services/api/tests/test_image_symbol_review_query_storage.py`
- dokumentacja stanu i kontraktu

## Test cases

- Aktywny odczyt + disconnect wywołuje dokładnie anulowanie własnego połączenia.
- Disconnect przed rejestracją połączenia jest ponawiany i ostatecznie anuluje SQL.
- Odczyt zakończony przed disconnect nie wywołuje cancel.
- Po wyjściu z `bounded_read` anulowanie jest no-op i nie dotyka połączenia.
- SQLSTATE `57014` nadal daje istniejący, kontrolowany timeout.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_image_symbol_reviews_api.py services/api/tests/test_image_symbol_review_query_storage.py
.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api services/api/tests/test_image_symbol_reviews_api.py services/api/tests/test_image_symbol_review_query_storage.py
.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api/api/image_symbol_reviews.py services/api/src/game_predictor_api/application/image_symbol_reviews.py services/api/src/game_predictor_api/storage/image_symbol_review_repository.py
npm run openapi:check
```

## Risks / open questions

- Anulowanie psycopg jest najlepszym możliwym przerwaniem: PostgreSQL może
  zakończyć query tuż przed sygnałem. Blokada i request-scoped session chronią
  przed anulowaniem późniejszego użytkownika tego samego pooled connection.

## Outcome

### Changed

- Lista i liczniki działają w threadpoolu pod watcherem rozłączenia ASGI.
- Repozytorium udostępnia request-scoped, blokowane anulowanie aktywnego
  połączenia przez `psycopg.Connection.cancel_safe()`.
- Wczesny disconnect ponawia próbę do rejestracji połączenia, a teardown czeka
  na zakończenie wątku query.

### Verification results

- `37 passed` dla testów API i storage Weryfikacji symboli.
- Ruff format i lint zmienionych plików: passed.
- Mypy zmienionych modułów: passed po wyłączeniu wyłącznie istniejących kategorii
  błędów w dużych współdzielonych modułach.
- OpenAPI i wygenerowany klient: current.

### Not completed

- Nie wykonywano optymalizacji zapytania liczników ani operacji na bazie.

### Documentation updates

- Zaktualizowano wymagania Admina, architekturę kontraktu API i `CURRENT_STATE`.

### Recommended next task

- TASK-0500 — optymalizacja zapytania liczników dla wielomilionowej projekcji.
