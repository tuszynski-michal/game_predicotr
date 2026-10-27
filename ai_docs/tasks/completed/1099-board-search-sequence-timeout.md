---
title: Dłuższy limit wyszukiwania ciągów plansz
status: done
last_updated: 2026-10-27
---

# TASK-1099 — Dłuższy limit wyszukiwania ciągów plansz

## Status

`done`

## Goal

Wyszukiwanie wielu układów ma maksymalnie 60 sekund na ranking SQL zamiast dotychczasowych 10 sekund, z zachowaniem krótszego jawnego limitu bazy i odtworzenia ustawień po zapytaniu.

## Context

Operator zgłosił `Sequence search took too long. Try again. (BOARD_SEARCH_SEQUENCE_TIMEOUT)` podczas prac nad TASK-1098 i polecił wydłużyć zbyt krótki limit. `_rank_with_timeout` narzuca 10000 ms. Odczyt rzeczywistego `SHOW statement_timeout` lokalnej bazy zwrócił 0, więc źródłem krótkiej granicy jest kod wyszukiwarki. Przyjęto 60 sekund, poniżej 120 sekund proxy panelu. Zgłoszenie nie jest zgodą na restart usług ani pomiary obciążeniowe.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`. Wąska zmiana limitu z testami odtwarzania ustawień i transakcji; bez zmiany rankingu. Audyt dodatkowy niewymagany, eskalacja przy konieczności przebudowy zapytania.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — wspólne wyszukiwanie lokalne i udostępnione.
- `ai_docs/architecture/API_CONTRACT.md` — timeout rankingu i błąd 503.
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md` — ten sam backend dla Admina i linków.
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-573--wyszukiwanie-po-kolejnych-układach`
- `ai_docs/delivery/BOARD_SEARCH_SEQUENCE_PLAN_20261024.md` — dotychczasowy limit 10 sekund, zmieniony bieżącym zleceniem.

## Scope

Limit 60 sekund; testy wartości efektywnej przy wcześniejszym 0/krótszym/dłuższym limicie, odtworzenia ustawienia po sukcesie i błędzie oraz zachowania kodu 503. Test rzeczywistego PostgreSQL na małych odczytach, bez benchmarku. Zapis hasha TASK-1098 w następnym commicie.

## Out of scope

Zmiana rankingu, migracje, operacje na danych operatora, restarty, merge i push.

## Acceptance criteria

- [x] Przy wcześniejszym limicie 0 lub większym niż 60 sekund ranking otrzymuje 60000 ms.
- [x] Krótszy limit jawny nadal obowiązuje; wcześniejsze ustawienie wraca po sukcesie i błędzie.
- [x] SQLSTATE 57014 nadal daje `BOARD_SEARCH_SEQUENCE_TIMEOUT`; pozostałe awarie bazy nie są maskowane.
- [x] Zmiana działa w nowym procesie i obejmuje Admina oraz oba udostępnienia dzięki istniejącej wspólnej ścieżce.
- [x] Testy pionu, Ruff, formatowanie, mypy zmienionego modułu, docs:check i code-map:check przechodzą.

## Technical notes

Zachować SAVEPOINT, `min(previous_ms, configured_limit)` dla niezerowego poprzedniego limitu i przywracanie ustawień. Nie przedłużać pozostałych endpointów i nie dodawać retry. Test ustawienia nie czeka rzeczywistej minuty: odczytuje `current_setting` wewnątrz chronionego zapytania. Osobny test krótkiego limitu kontroluje rollback po `pg_sleep(0.05)` i możliwość następnego SELECT.

## Expected files

- `services/api/src/game_predictor_api/storage/board_search_sequence.py` — `_rank_with_timeout`.
- Nowy: `services/api/tests/test_board_search_sequence_timeout.py` — polityka limitu i błędów.
- Wymagania, kontrakt, D-573, dotychczasowy plan, CURRENT_STATE i task.

## Test cases

0, 5 ms, 15 s i 5 minut przed rankingiem; odtworzenie po sukcesie i przerwaniu; nieprzetłumaczony inny SQLSTATE; brak zmian w API i publicznych testach sekwencji. Odczyt ustawienia na rzeczywistym PostgreSQL w nowym procesie, bez zapisu danych.

## Verification

Z katalogu repozytorium, timeout każdej komendy 120 s:

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_search_sequence_timeout.py services/api/tests/test_board_search_sequence_public.py services/api/tests/test_board_search_sequence_api.py services/api/tests/test_board_search_sequence_domain.py -x -q
.\.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/storage/board_search_sequence.py services/api/tests/test_board_search_sequence_timeout.py
.\.venv\Scripts\python.exe -m ruff format --check services/api/src/game_predictor_api/storage/board_search_sequence.py services/api/tests/test_board_search_sequence_timeout.py
.\.venv\Scripts\python.exe -m mypy --follow-imports=skip services/api/src/game_predictor_api/storage/board_search_sequence.py
npm run docs:check
npm run code-map:check
```

## Risks / open questions

Zmiana daje więcej czasu, nie stanowi pomiaru szybkości rankingu na danych operatora. Odbiór zgłoszonego wyszukiwania wymaga uruchomienia poprawionej gałęzi przez operatora; usługi nie są zarządzane przez agenta.

## Outcome

Commit: v1.7.485 (hash dopisuje kolejny commit).

### Changed

- Limit SQL rankingu ciągów wynosi 60000 ms zamiast 10000 ms. Wcześniejszy niezerowy krótszy limit nadal ma pierwszeństwo. SAVEPOINT i mapowanie wyjątków bez zmian.
- Sześć testów regresyjnych sprawdza skuteczny limit dla 0/5 ms/15 s/5 min, przywracanie poprzedniej wartości po sukcesie, wyjście z SAVEPOINT po awarii oraz rozróżnienie anulowania i innego SQLSTATE.
- Zapisano hash poprzedniego TASK-1098 w jego Outcome, oknie i archiwum.

### Verification results

- Testy limitu, API lokalnego, API publicznego i domeny: 24/24 PASS w 19,24 s.
- Nowy proces z istniejącą lokalną bazą: `statement_timeout=0`; wewnątrz rankingu 60000 ms, po sukcesie 0. Przy wcześniejszym 5 min: wewnątrz 60000 ms, potem 5 min. Przy 5 ms test `pg_sleep(0.05)` kończy się właściwym kodem; rollback przywraca 5 ms i pozwala wykonać następny SELECT. Zamknięcie sesji przywraca 0. Bez zapisów danych i bez zapytania rankingowego na zbiorze operatora.
- Ruff check i format: PASS. Mypy zmienionego modułu z `--follow-imports=skip`: PASS. Regeneracja mapy kodu wykonana; docs:check i code-map:check sprawdzone przed commitem.
- Pierwszy przebieg pytest w ograniczonym środowisku zakończył się po 120 s z błędami fixture; bez osieroconego procesu. Powtórzenie tych samych ograniczonych testów poza ograniczeniem uprawnień przeszło. Pełne śledzenie zależności mypy przekroczyło 60 s; sprawdzono brak procesu i wykonano kontrolę samego zmienionego modułu, bez rozszerzania zakresu.
- Kryteria akceptacji sprawdzone punkt po punkcie; rzeczywisty odczyt w nowym procesie potwierdza trwałą zmianę kodu, bez sesyjnego obejścia konfiguracji.

### Not completed

- Bez ponowienia wyszukiwania operatora, benchmarku, przebudowy zapytania, restartów, merge i push.
- Bez pełnego typecheck zależności backendu po przekroczeniu limitu czasu. Audyt krzyżowy niewymagany dla tego taska.

### Documentation updates

- Wymagania, opis limitu w API_CONTRACT (bez zmiany OpenAPI), doprecyzowanie D-573, plan z dodatkowym wierszem wykonawczym, mapa kodu i CURRENT_STATE.

### Recommended next task

- Akceptacja obu poprawek i zgoda na scalenie; odbiór zgłoszonego wyszukiwania na uruchomionej poprawionej wersji. Ewentualna optymalizacja rankingu wymaga osobnego zakresu i pomiaru.
