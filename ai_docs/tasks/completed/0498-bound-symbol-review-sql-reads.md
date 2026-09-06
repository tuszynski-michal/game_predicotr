---
title: TASK-0498 — Ograniczenie czasu zapytań SQL Weryfikacji symboli
status: done
version: v0.10.213
---

# TASK-0498 — Ograniczenie czasu zapytań SQL Weryfikacji symboli

## Goal

Ograniczyć po stronie PostgreSQL czas listy Weryfikacji symboli do 5 sekund,
a liczników do 15 sekund, bez wpływu na inne endpointy i transakcje.

## Context

TASK-0497 anuluje nieaktualne requesty w przeglądarce, ale zapytanie SQL może
nadal zajmować połączenie. Pierwszą ochroną backendu jest transakcyjny
`statement_timeout`; anulowanie natychmiast po rozłączeniu należy do TASK-0499.

## Dependencies / entry conditions

- TASK-0497 jest ukończony.
- Odczyty listy i liczników korzystają z osobnej sesji SQLAlchemy na request.
- PostgreSQL wspiera transakcyjny `set_config(..., true)`.

## Recommended execution

`gpt-5.6-sol` z poziomem `high`: zmiana przecina port aplikacyjny, adapter
SQLAlchemy, konfigurację i mapowanie błędów, ale pozostaje małym pionem API.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0497-cancel-stale-symbol-review-requests.md`

## Scope

- dodać dodatnie, konfigurowalne limity 5000 ms dla strony i 15000 ms dla
  liczników;
- ustawiać `statement_timeout` lokalnie dla transakcji odczytu;
- objąć limitem cały use case, w tym sprawdzenie gotowości i aktywnej kohorty;
- mapować PostgreSQL SQLSTATE `57014` na stabilny błąd
  `SYMBOL_CELL_REVIEW_QUERY_TIMEOUT` oraz HTTP 503;
- wycofać transakcję po timeoutcie przez istniejącą granicę sesji;
- dodać testy konfiguracji, wyboru limitu, SQL i odpowiedzi API.

## Out of scope

- nasłuchiwanie rozłączenia klienta i natychmiastowe `cancel()` połączenia;
- optymalizacja zapytania liczników;
- zmiana schematu bazy, migracja lub nowy endpoint.

## Acceptance criteria

- [x] Lista i liczniki ustawiają własny `SET LOCAL` przez parametryzowany SQL.
- [x] Timeout jednego requestu nie pozostaje na połączeniu z puli.
- [x] Inne błędy bazy nie są maskowane jako timeout.
- [x] Admin otrzymuje stabilne HTTP 503 z kodem i limitem w details.
- [x] Konfiguracja odrzuca wartości niedodatnie.
- [x] Testy API i storage, Ruff oraz ukierunkowany mypy przechodzą; pełny mypy
      repozytorium nadal raportuje wcześniejsze błędy poza tym pionem.

## Technical notes

Port repozytorium udostępnia context manager `bounded_read`. Adapter PostgreSQL
ustawia `set_config('statement_timeout', '<N>ms', true)` i tłumaczy wyłącznie
SQLSTATE `57014`. Zakres `true` oznacza ustawienie lokalne dla bieżącej
transakcji; dependency sesji wykonuje rollback po wyjątku.

## Expected files

- `services/api/src/game_predictor_api/config.py`
- `services/api/src/game_predictor_api/application/image_symbol_reviews.py`
- `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`
- `services/api/src/game_predictor_api/main.py`
- `services/api/src/game_predictor_api/api/image_symbol_reviews.py`
- testy konfiguracji, API, use case'u i adaptera storage;
- OpenAPI oraz wygenerowany klient tylko jeśli kontrola driftu wykaże zmianę.

## Test cases

- list używa 5000 ms, counts używa 15000 ms;
- override środowiskowy jest przekazywany przez dependency;
- SQLSTATE 57014 daje kontrolowany timeout, inny SQLSTATE jest propagowany;
- API zwraca 503 i szczegóły operacji bez danych SQL;
- następny request na nowej transakcji nie dziedziczy timeoutu.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_config.py services/api/tests/test_image_symbol_reviews_api.py services/api/tests/test_image_symbol_review_query_storage.py
.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api services/api/tests
.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api
npm run openapi:check
```

## Risks / open questions

- Limit chroni PostgreSQL po maksymalnym czasie, ale nie zastępuje szybszego
  przerwania po disconnect; to pozostaje jawnie w TASK-0499.

## Outcome

### Changed

- Lista używa transakcyjnego limitu 5000 ms, a liczniki 15000 ms; oba limity
  obejmują cały use case i są konfigurowalne przez środowisko.
- Adapter SQLAlchemy ustawia parametryzowane `set_config(..., true)` i tłumaczy
  wyłącznie PostgreSQL SQLSTATE `57014` na kontrolowany błąd domenowy.
- API publikuje dla obu odczytów HTTP 503
  `SYMBOL_CELL_REVIEW_QUERY_TIMEOUT`; OpenAPI i klient zostały zregenerowane.

### Verification results

- `pytest`: 73 testy przeszły.
- Ruff lint i format zmienionych plików: przeszły.
- OpenAPI drift i typecheck klienta TypeScript: przeszły.
- Mypy zmienionego portu i konfiguracji: przeszły. Kontrola adaptera/API z
  wyłączonymi trzema znanymi kategoriami wcześniejszych błędów również
  przeszła bez nowych diagnostyk.

### Not completed

- Pełny mypy repozytorium nadal kończy się 48 wcześniejszymi błędami, głównie
  brakiem `py.typed` workera oraz istniejącymi błędami w innych modułach.
- Nie dodano anulowania SQL po disconnect ani optymalizacji agregatu.

### Documentation updates

- Zaktualizowano wymagania Admina, kontrakt API, instrukcję operatorską,
  `.env.example` i `CURRENT_STATE.md`.

### Recommended next task

- TASK-0499 — przerwanie SQL po rozłączeniu klienta.
