---
title: TASK-0541 — Odświeżenie szybkiego indeksu wyszukiwania plansz po upsercie
status: done
last_updated: 2026-09-14
---

# TASK-0541 — Odświeżenie szybkiego indeksu wyszukiwania plansz po upsercie

## Status

`done`

## Goal

Po aktualizacji istniejącego kandydata wyszukiwania plansz szybki dokument tej
samej sekwencji otrzymuje bieżące kody symboli w tej samej transakcji, a układ
sekwencji 12 jest znajdowany z wynikiem 100%.

## Context

Dla gry `bfc4f949-5c14-4850-b02a-db99610bcfa5` sekwencja 12 ma w
`image_symbol_review_cells` i `image_board_search_candidates` dokładnie układ
zgłoszony przez operatora. `image_board_search_fast_documents` tej samej
sekwencji zachował jednak pięć tablic z samymi `NULL` i pusty zbiór znanych
pozycji, dlatego endpoint pomija planszę 12 i zwraca wyniki około 83%.

Przyczyną jest tożsamość ORM: `sync_review_item()` ładuje istniejącego kandydata,
upsert aktualizuje jego wiersz bez odświeżenia obiektu w identity map, a
`reconcile_sequence()` ponownie otrzymuje ten stary obiekt i kopiuje stare
tablice do fast documentu. Pomiar read-only wykazał 19 377 takich dokumentów;
wszystkie mają poprawnego właściciela i status, lecz nieaktualne primary,
alternatywy i znane pozycje.

## Dependencies / entry conditions

- Projekcja gry jest aktywna w `game_data_v2` i ma stan gotowy.
- Kandydaci są źródłem prawdy dla fast documents.
- Właściciel i status wszystkich zmierzonych niespójnych dokumentów są zgodne;
  naprawa danych może być wykonana addytywnym `UPDATE`, bez usuwania tabel,
  kandydatów, review ani obrazów.
- Kolejność edytora kolumny/wiersze działa zgodnie z TASK-0421 i nie jest
  przyczyną zgłoszenia.

## Recommended execution

`gpt-6-astra high`; błąd łączy identity map SQLAlchemy, partycjonowany magazyn
V2 i naprawę 19 377 pochodnych dokumentów na aktywnej grze. Dodatkowy review nie
jest wymagany, jeżeli regresja PostgreSQL odtworzy stary obiekt po upsercie,
testy repozytorium przejdą, a przed i po naprawie zostaną porównane liczniki
niespójności oraz wynik sekwencji 12.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/tasks/completed/0292-board-search.md`
- `ai_docs/tasks/completed/0421-board-search-entry-order.md`
- `ai_docs/tasks/completed/0530-v2-board-search-candidate-upsert.md`

## Scope

- Wymusić ponowne zasilenie istniejących obiektów kandydatów z bazy w
  `reconcile_sequence()` po upsercie.
- Dodać regresję PostgreSQL: załadowany kandydat ze starymi tablicami → upsert
  nowych symboli → reconcile → fast document ma nowe tablice i znane pozycje.
- Naprawić zmierzone niespójne fast documents aktywnej gry setowym `UPDATE`
  wyłącznie z ich aktualnych kandydatów i sprawdzić wynik 0 niespójności.
- Potwierdzić przez publiczny endpoint, że pełny wzór operatora zwraca
  sekwencję 12 z wynikiem 100% i 15 exact matches.
- Zaktualizować architekturę projekcji, bieżący stan i Outcome zadania.

## Out of scope

- Zmiana kolejności wprowadzania wzoru, rankingu, API, OpenAPI lub Admin UI.
- Zmiana symboli, decyzji review, geometrii, kandydatów albo obrazów.
- Pełny rebuild kandydatów lub usuwanie danych domenowych.
- Naprawa innych niezależnych problemów importu i workerów.

## Acceptance criteria

- [x] `reconcile_sequence()` nie kopiuje starego stanu obiektu ORM po upsercie.
- [x] Regresja PostgreSQL odtwarza aktualizację pustego kandydata do pełnego
  wzoru i potwierdza spójny fast document.
- [x] Po naprawie gry liczba rozbieżnych fast documents wynosi 0.
- [x] Zapytanie pełnym układem zwraca sekwencję 12 jako pierwszy wynik z 100%,
  15 exact, 0 mismatch i 0 unknown.
- [x] Testy repozytorium, PostgreSQL, Ruff i mypy przechodzą.
- [x] Nie zmieniono kontraktu HTTP, układu edytora ani danych źródłowych.

## Technical notes

Źródłem prawdy pozostaje `image_board_search_candidates`. Wybór logicznego
właściciela sekwencji pozostaje bez zmian. Zapytanie ORM w
`reconcile_sequence()` musi użyć `populate_existing=True`, aby wynik SELECT
nadpisał stan obiektu obecnego już w identity map po DML `INSERT ... ON
CONFLICT DO UPDATE`.

Naprawa realnych danych jest ograniczona do dokumentów, których
`review_item_id` nadal wskazuje aktualnego kandydata. Setowy `UPDATE ... FROM`
kopiuje wyłącznie status, checksumę dowodu i istniejące kolumny wyszukiwawcze,
ustawiając `updated_at`; nie usuwa wierszy. Przed wykonaniem należy ponownie
potwierdzić brak rozjazdu właściciela/statusu. Po wykonaniu ten sam read-only
audyt musi zwrócić zero różnic.

## Expected files

- Istniejący: `services/api/src/game_predictor_api/storage/board_search_projection_repository.py` — `reconcile_sequence()`.
- Istniejący: `services/api/tests/integration/test_game_storage_routing_postgres.py` — regresja identity map V2.
- Istniejący: `ai_docs/architecture/DATA_MODEL.md` — kontrakt odświeżenia fast documentu.
- Istniejący: `ai_docs/process/CURRENT_STATE.md`.
- Nowy: `ai_docs/tasks/0541-refresh-board-search-fast-document-after-upsert.md`.

## Test cases

- Istniejący kandydat z pustymi kodami zostaje załadowany do identity map,
  następnie upsert otrzymuje pełny wzór → fast document zawiera nowe mobile
  codes i 15 znanych pozycji.
- Kandydat i fast document bez różnic → reconcile zachowuje właściciela i
  ranking.
- Realna sekwencja 12 → pełny wzór operatora daje 100%.
- Ten sam wzór wprowadzony prawidłowo w trybie kolumnowym lub wierszowym →
  identyczne kanoniczne indeksy; istniejące testy Admina pozostają zielone.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_game_storage_routing_postgres.py -q
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_search_projection_repository.py services/api/tests/test_board_search_api.py -q
.\.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/storage/board_search_projection_repository.py services/api/tests/integration/test_game_storage_routing_postgres.py
.\.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api/storage/board_search_projection_repository.py
npm run test --workspace @game-predictor/admin -- board-search-editor-state.test.mjs
```

Kryterium zaliczenia: wszystkie komendy przechodzą, audyt realnej gry zwraca
zero rozbieżności, a publiczny endpoint znajduje sekwencję 12 na pierwszym
miejscu z pełnym dopasowaniem.

## Risks / open questions

- Aktywne importy mogą dodawać dokumenty podczas diagnozy. Naprawa i audyt
  końcowy działają w jednej transakcji oraz ograniczają się do tej gry.
- Jeśli ponowny audyt wykaże rozjazd właściciela, naprawa setowym UPDATE zostaje
  zatrzymana i wymaga osobnej analizy wyboru canonical owner. Pomiar wejściowy
  wykazał 0 takich przypadków.

## Outcome

### Changed

- Zapytanie kandydatów w `reconcile_sequence()` używa
  `populate_existing=True`, więc SELECT nadpisuje stan obiektu obecnego w
  identity map po upsercie.
- Test PostgreSQL ładuje pustego kandydata, wykonuje upsert pełnego układu i
  potwierdza, że fast document dostaje 15 bieżących kodów oraz 15 znanych
  pozycji.
- Naprawiono setowo 19 377 niespójnych fast documents aktywnej gry. Kandydaci,
  komórki review, decyzje i assety pozostały bez zmian.

### Verification results

- Pełny plik integracji PostgreSQL: 8 testów zaliczonych.
- Repozytorium i endpoint board search: 16 testów zaliczonych.
- Edytor kolejności wprowadzania planszy: 6 testów zaliczonych.
- Ruff dla zmienionego kodu i testu: zaliczony; mypy dla zmienionego modułu:
  zaliczony.
- Audyt po naprawie: 0 niespójnych fast documents, 0 rozjazdów właściciela i
  0 rozjazdów statusu.
- Publiczny endpoint zwraca sekwencję 12 jako pierwszy wynik: score 100.0,
  exact 15, alternative 0, mismatch 0, unknown 0.
- API i ogólny worker działają z nowym kodem; końcowy audyt po przeładowaniu
  nadal zwrócił 0 rozbieżności. Import
  `f4ef3449-4ac2-46de-9dbc-23525cd864ed` został bezpiecznie ponowiony z tym
  samym UUID, manifestem i checkpointami plików po niezależnym błędzie
  odzyskania postępu. Po ukończeniu preflightu 2611/2611 rozpoczął próbę 3 i
  osiągnął rosnące 1444/2320, status `processing`, bez błędu.

### Not completed

- Nie zmieniano API, OpenAPI, Admin UI, algorytmu rankingu ani danych
  źródłowych. Pełny mypy pliku integracyjnego nadal raportuje trzy wcześniejsze
  błędy typów poza zmienioną regresją; wymagany mypy modułu produkcyjnego jest
  zielony.
- Automatyczne odzyskanie aktywnego importu po twardym restarcie workera nadal
  może zgłosić `JOB_PROGRESS_REGRESSION`; istniejący jawny retry działa
  poprawnie i nie traci checkpointów plików.

### Documentation updates

- `DATA_MODEL.md` opisuje obowiązek odświeżenia kandydata po upsercie.
- `CURRENT_STATE.md` zawiera diagnozę, naprawę danych i wynik sekwencji 12.

### Recommended next task

- Oddzielnie ujednolicić niejawne odzyskanie importu po utracie workera z
  semantyką świeżego agregatu używaną przez jawny retry. Nie jest to część
  wyszukiwania plansz ani bieżącej poprawki projekcji.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0541 | `gpt-6-astra` | `high` | Identity map SQLAlchemy i partycjonowana projekcja V2 wymagają regresji transakcyjnej oraz kontrolowanej naprawy 19 377 dokumentów pochodnych. | Nie, jeśli test PostgreSQL i audyt realnych danych potwierdzą pełną spójność oraz wynik 100% dla sekwencji 12. |
