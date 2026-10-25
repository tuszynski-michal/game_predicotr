---
title: Gotowość API i workera do migracji 0169
status: done
---

# TASK-1097 — Gotowość API i workera do migracji 0169

## Status

`done`

## Goal

Usunąć blokadę startu API/workera po migracji 0169 i przygotować kontrolowany rollout bez uruchamiania starego kodu na nowej bazie.

## Context / entry conditions

Operator 2026-10-25 zlecił migrację oraz potrzebne operacje i dawne P2-3 (zamknięte TASK-1096, v1.7.478 / e8018ef1). Preflight: baza operatora nadal 0168_source_crop_runs; API/Admin/Reviewer działają ze starego checkoutu. Nowa migracja ma głowę 0169, lecz schema_readiness wciąż wymaga 0168. Istniejący test odtwarza błąd: 1 failed, 14 passed. Numer 1097 sprawdzony we wszystkich refs i plikach aktywnych worktree. W worktree pozostał wyłącznie własny zapis hasha TASK-1096 do kolejnego commita.

## Recommended execution

gpt-6.1-sol / high, bez delegowania i nowego audytu. Dwuliniowa synchronizacja bramki startowej, test kontraktu głowy i rzeczywisty PostgreSQL wyłącznie w istniejącym disposable fixture. Eskalacja przy innej rewizji bazy, kolizji migracji albo potrzebie zmiany danych poza zatwierdzoną migracją.

## Relevant docs

- AGENTS.md; ai_docs/process/PLAN_STANDARD.md, TASK_TEMPLATE.md, DEFINITION_OF_DONE.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/architecture/API_CONTRACT.md — 0169 i logi
- ai_docs/architecture/CODE_MAP.md i CODE_MAP_SYMBOLS.md
- ai_docs/guides/LOCAL_OPERATION_GUIDE.md — kontrola usług i migracji
- ai_docs/delivery/BOARD_SEARCH_SEQUENCE_PLAN_20261024.md — migracja 0169
- ai_docs/quality/BOARD_SEARCH_SEQUENCE_IMPLEMENTATION_20261024.md

## Scope / Technical notes

EXPECTED_ALEMBIC_HEAD musi równać się jedynej głowie 0169_board_search_sequence_logs. Nie osłabiać exact-head guard; test odrzuca także poprzednie 0168 i przyszłą nieznaną rewizję. Manifest ownership pozostaje v19. Nowy test rzeczywistej bazy sprawdza require_alembic_head po pełnym upgrade w istniejącym owned *_test fixture.

Migracja operatora jest zatwierdzona, ale wymaga wspólnego przejścia stop → zaakceptowana integracja → migracja → start zgodnego kodu. Root D:/game_predicotr jest na innej gałęzi z cudzymi zmianami. Nie zatrzymywać działających usług ani nie zmieniać bazy przed przygotowaniem zgodnego kodu i uzgodnieniem integracji. To zadanie zamyka poprawkę gotowości; rzeczywiste wdrożenie musi być opisane oddzielnie jako wykonane albo oczekujące. Nie raportować testowej migracji jako migracji operatora.

## Expected files

Istniejące services/api/src/game_predictor_api/storage/schema_readiness.py, tests/test_schema_readiness.py, tests/integration/test_board_search_sequence_postgres.py, API_CONTRACT, LOCAL_OPERATION_GUIDE, raport odbioru, CURRENT_STATE i task. Zapis hasha poprzedniego TASK-1096 w dokumentacji w tym commicie. Bez nowej migracji, REST API lub modeli danych.

## Acceptance criteria / Verification

- [x] Test głowy, odmowa startu na 0168 i akceptacja 0169 PASS; istniejący RED udokumentowany.
- [x] Test require_alembic_head na disposable PostgreSQL po migracji PASS, bez zmian bazy operatora. Istniejące testy migracji i bezpiecznego downgrade bez regresji.
- [x] Ruff/format/mypy zmienionych modułów, testy gotowości i domeny/API wyszukiwarki, docs/map PASS.
- [x] Gotowy commit, zapis hasha i jawny status rzeczywistej migracji/usług. Nie deklarować wykonania bez dowodu. Preflight integracji następuje po zamknięciu poprawki, przed prośbą o akceptację main.

Komendy: .venv/Scripts/python.exe -m pytest dla test_schema_readiness.py i wybranych testów board-search sequence; jawny PYTHONPATH=services/api/src. PostgreSQL opt-in GAME_PREDICTOR_RUN_POSTGRES_TESTS=1, fixture waliduje *_test. Ruff i mypy ograniczone do zmienionych plików. scripts/generate_code_map.py, code-map:check, docs:check, diff --check. subprocess.run(timeout=120), DB connect_timeout=5 i krótkie statement_timeout dla odczytów preflight.

## Out of scope / Risks

Zmiana kontraktu API, nowy schemat, downgrade bazy operatora i jakiekolwiek usuwanie jego danych. Integracja main wymaga osobnej akceptacji wyniku według AGENTS.md i skilla merge-to-main. Nie wymuszać zmiany obcej gałęzi/brudnego checkoutu ani zatrzymywania niezidentyfikowanych procesów.

## Outcome

Commit: v1.7.479 / `c2e870454a808baa29a508badcb352c334ac11c0`.

### Changed

Zsynchronizowano EXPECTED_ALEMBIC_HEAD z jedyną głową Alembic 0169_board_search_sequence_logs. Guard pozostaje exact-head i fail-closed. Test odrzuca również poprzednie 0168; nowy test integration sprawdza guard na rzeczywiście zmigrowanej jednorazowej bazie testowej. Manifest v19, kontrakt REST, migracja i dane domenowe bez zmian w tym tasku.

### Verification results

- Istniejący RED: test_schema_readiness 1 failed, 14 passed, rozbieżność 0169 vs 0168. Log schema-readiness-before-fix.log w artifacts/board-search-sequence-browser/.
- Po poprawce test_schema_readiness + test_board_search_sequence_domain + test_board_search_sequence_api: 29 PASS. Log task-1097-unit.log; nowy proces z jawnym PYTHONPATH lokalnego API.
- PostgreSQL integration test_board_search_sequence_postgres: 9 PASS, w tym nowy require_alembic_head po upgrade, ranking/timeout i guarded downgrade. Istniejący fixture generuje unikalną bazę *_test, zapisuje ownership, migruje i usuwa tylko własną bazę. Nie migrowano operatora. Log task-1097-postgres.log.
- Ruff check i format --check trzech plików PASS. Pierwszy mypy timeout 120 s bez wyniku; dokładny odczyt procesów wykazał brak pozostałego procesu mypy. Ta sama ścisła kontrola w nowym procesie z dostępem do lokalnych zależności PASS: no issues in 1 source file. Nie osłabiano konfiguracji ani testów. Log task-1097-mypy.log.
- Mapa wygenerowana bez różnic; code-map:check, docs:check i diff --check PASS. Kontrole zamknięcia i indeksu ponawiane przy commicie. Komendy z timeout 120 s (odczyty git/DB do 30 s), bez restartów usług.
- Offline SQL preview 0168:0169: BEGIN, lock_timeout 5 s, drop/recreate ck_bss_query_request do 32768, aktualizacja alembic_version, COMMIT. Bez połączenia/modyfikacji operatora; zapis migration-0169-preview.sql w artifacts/board-search-sequence-browser/.
- Dwa odczyty operatora potwierdziły 0168_source_crop_runs; dokładna definicja ck_bss_query_request nadal 4096. Wykryte działające porty 8000/3000/3001. Root na codex/selector-games-updates z M DOC_INDEX, dwoma usuniętymi artefaktami i nieśledzonymi plikami planu. Nie naruszono tych zmian ani procesów.

### Not completed

Rzeczywista migracja i potrzebne restarty są zlecone, ale pozostają niewykonane. Najpierw potrzebne uzgodnione przejście do zgodnego kodu: osobna akceptacja main oraz ochrona cudzych zmian. Stary kod odmówi startu po 0169, więc nie pozostawiono działającej instalacji w takim stanie. Brak merge/push i nowego audytu Claude. Nie deklarować testowego upgrade jako wdrożenia. Pierwotny audyt A miał timeout bez werdyktu; ta mała poprawka ma testy, nie nowy niezależny audyt.

### Documentation updates / Definition of Done

API_CONTRACT opisuje wymagany head 0169 przy manifest v19; LOCAL_OPERATION_GUIDE ma kontrolowaną procedurę rollout. Raport odbioru i CURRENT_STATE rozróżniają naprawiony bloker startowy, udzieloną zgodę na migrację i niewykonaną operację. W tym commicie również wymagany zapis pełnego hasha TASK-1096. AC1: RED→GREEN i odrzucenie starego head; AC2: rzeczywisty *_test upgrade/guard/downgrade; AC3: narzędzia i testy PASS; AC4: task-close, commit/hash i jawny status wdrożenia. Brak nowych decyzji domenowych, endpointów lub migracji; klient/OpenAPI nie wymagają regeneracji.

### Recommended next task

Preflight całej gałęzi, akceptacja gotowego wyniku i decyzja operatora o integracji main z ochroną obcej pracy; potem wykonanie zatwierdzonej migracji oraz uruchomienie zgodnych usług i rzeczywisty odbiór Admin/link/panel. Nie jest potrzebna ponowna zgoda na samą migrację i konieczne restarty w tym zleceniu.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1097 — Gotowość 0169 | gpt-6.1-sol | high | Exact-head guard, mała synchronizacja z istniejącą migracją i testy rzeczywistej bazy testowej. | Bez nowego audytu; istniejące testy głowy i migracji plus odczyt preflight. |
