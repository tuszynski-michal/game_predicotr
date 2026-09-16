---
title: Audit hardening for disconnected symbol review SQL
status: done
last_updated: 2026-09-07
---

# TASK-0499 — Utwardzenie anulowania SQL po audycie

## Status

`done`

## Goal

Usunąć cztery wyścigi wykryte w dodatkowym audycie TASK-0499 i potwierdzić
fizyczne przerwanie zapytania przez rzeczywisty middleware oraz PostgreSQL.

## Context

Pierwsza implementacja używała `Request.is_disconnected()` za
`BaseHTTPMiddleware`, wspólnego limitera AnyIO dla query i cancel oraz
jednorazowego `cancel_safe()`. Audyt `gpt-6-astra high` wykazał, że middleware
może ukryć disconnect, zajęty limiter opóźnia cancel, sygnał wysłany pomiędzy
instrukcjami SQL nie zatrzymuje następnej, a ponowne anulowanie taska może
zwolnić request-scoped sesję przed zakończeniem wątku query.

## Dependencies / entry conditions

- Pierwotny TASK-0499 i serwerowe limity TASK-0498 są wdrożone.
- Psycopg `cancel_safe()` pozostaje fizycznym mechanizmem przerwania aktywnego
  zapytania; `statement_timeout` pozostaje niezależną granicą końcową.

## Recommended execution

`gpt-6-astra high`: zmiana dotyczy współbieżności ASGI, anulowania tasków,
limiterów wątków i cyklu życia sesji SQLAlchemy. Ponowny review jest wymagany,
jeżeli test z rzeczywistym PostgreSQL wykaże zależność od kolejności schedulerów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/tasks/completed/0499-cancel-disconnected-symbol-review-sql.md`

## Scope

- Oczekiwać na rzeczywisty komunikat ASGI `http.disconnect` zamiast
  niepewnego pollingu `Request.is_disconnected()`.
- Oddzielić fizyczne anulowanie od limitera wątku zajętego przez query.
- Zapamiętać żądanie anulowania w request-scoped repozytorium i sprawdzać je
  przed kolejnymi instrukcjami SQL.
- Po disconnect lub wielokrotnym `Task.cancel()` czekać na pełne zakończenie
  query i operacji cancel przed zwolnieniem sesji.
- Dodać regresje z rzeczywistym middleware i PostgreSQL.

## Out of scope

- Optymalizacja treści zapytania liczników (TASK-0500).
- Zmiana filtrów, paginacji, schematu bazy i innych endpointów.

## Acceptance criteria

- [x] Disconnect jest widoczny za `LocalAdminSecurityMiddleware`.
- [x] Cancel nie czeka na wolny token limitera query.
- [x] Sygnał pomiędzy dwiema instrukcjami SQL blokuje drugą instrukcję.
- [x] Wielokrotne anulowanie taska nie kończy requestu przed wątkiem query.
- [x] Po cleanupie pooled connection jest ponownie używalne i nie otrzymuje
      spóźnionego cancel.
- [x] Timeout i publiczne zachowanie endpointów pozostają kompatybilne.

## Technical notes

Watcher ma wykonywać normalne `await request.receive()` do
`http.disconnect`; endpoint GET nie konsumuje body. Query pozostaje w AnyIO
threadpoolu, natomiast krótki `cancel_safe()` korzysta z niezależnego executora.
Repozytorium utrwala `cancel_requested` do końca requestu. Fizyczny cancel jest
ponawiany do zakończenia query, ponieważ PostgreSQL może zignorować pakiet
wysłany pomiędzy zapytaniami. Cleanup działa w osobnym tasku odpornym na
powtórne anulowanie i kończy się przed re-raise `CancelledError`.

## Expected files

- `services/api/src/game_predictor_api/api/image_symbol_reviews.py`
- `services/api/src/game_predictor_api/application/image_symbol_reviews.py`
- `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`
- `services/api/tests/test_image_symbol_reviews_api.py`
- `services/api/tests/test_image_symbol_review_query_storage.py`
- dokumentacja wymagań, kontraktu i stanu

## Test cases

- Rzeczywisty middleware przekazuje disconnect do watchera.
- Limit AnyIO równy jeden nie blokuje osobnego cancel executora.
- Dwa `Task.cancel()` nadal czekają na zakończenie workera.
- Cancel pomiędzy instrukcjami daje stabilny błąd przed następnym SQL.
- Aktywne `pg_sleep` zostaje przerwane, transakcja wycofana, a połączenie
  wykonuje następnie `SELECT 1`.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_image_symbol_reviews_api.py services/api/tests/test_image_symbol_review_query_storage.py
.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api services/api/tests/test_image_symbol_reviews_api.py services/api/tests/test_image_symbol_review_query_storage.py
.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api/api/image_symbol_reviews.py services/api/src/game_predictor_api/application/image_symbol_reviews.py services/api/src/game_predictor_api/storage/image_symbol_review_repository.py
npm run openapi:check
```

## Risks / open questions

- Fizyczny test PostgreSQL zależy od dostępnej lokalnej bazy; brak usługi nie
  może być przedstawiony jako zaliczony test integracyjny.

## Outcome

### Changed

- Watcher czeka na rzeczywisty `http.disconnect` przez middleware.
- Request-scoped sygnał anulowania zatrzymuje kolejne etapy SQL, a fizyczny
  cancel działa poza limiterem query i jest ponawiany do końca workera.
- Cleanup pozostaje aktywny mimo kolejnych `Task.cancel()` i kończy się przed
  zwolnieniem sesji.

### Verification results

- `42 passed` dla testów API i storage.
- Rzeczywisty PostgreSQL: `pg_sleep(5)` przerwany, rollback wykonany, to samo
  połączenie wykonało następnie `SELECT 1` (`1 passed`).
- Ruff: passed; mypy zmienionych modułów: passed przy wyłączeniu istniejących
  kategorii błędów dużych modułów współdzielonych.
- OpenAPI i wygenerowany klient: current.

### Not completed

- Nie optymalizowano zapytania liczników; zakres należy do TASK-0500.

### Documentation updates

- Zaktualizowano wymagania Admina, kontrakt API i `CURRENT_STATE.md`.

### Recommended next task

- TASK-0500 po pełnym zaliczeniu poprawek audytu.
