# Audyt TASK-1151 — Przywrócenie wyszukiwania bez historii wymiany zdjęć

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: HEAD...5cfe292b436a61c15d3005393f73479883e0171b oraz zmiany niezacommitowane, data 2026-11-03
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadałem migrację 0179, zmianę pinu w `schema_readiness`, jej test, nowy test PostgreSQL oraz plik taska. Porównałem je z pierwotną definicją `source_replacement_excluded_reviews_v1` z migracji 0175 i 0176, z polityką RLS tabel wymiany z 0174, z nadawaniem uprawnień roli runtime i z istniejącymi testami guardów. Szybka ścieżka wrappera jest semantycznie równoważna starej implementacji. Wynik starej funkcji powstaje wyłącznie ze zbiorów `affected_sources` i `affected_reviews`, a te biorą się tylko z trzech źródeł: `source_replacement_retired`, `source_replacement_slots` (w każdym stanie) oraz `source_replacement_entries` z `phase='restored'`. Gdy wszystkie trzy są puste, wynik jest pusty. Wrapper działa jako SECURITY INVOKER, więc podlega tej samej polityce RLS (FORCE) co implementacja, a funkcja STABLE korzysta z migawki wywołującego. Rename zachowuje OID i ACL. Główne ryzyko szczątkowe: gałąź delegacji nie ma testu, który izolowałby każde z trzech źródeł osobno.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/api/alembic/versions/0179_empty_replacement_search.py:23` — Trzy warunki szybkiej ścieżki (linie 23–26) nie mają testu, który sprawdzałby każde źródło osobno. Nowy test `services/api/tests/integration/test_empty_replacement_search_postgres.py:15` sprawdza tylko pustą historię. Istniejące fixture guardów (`test_source_replacement_geometry_guards_postgres.py:165`, `test_source_replacement_guards_postgres.py:289`, `test_source_replacement_selection_postgres.py:111`) zawsze wstawiają też wiersz `source_replacement_retired`. Skutek: gdyby ktoś usunął albo zawęził warunek `restored` (guard „closed” z 0176) lub warunek `slots`, żaden test by tego nie wykrył, a wykluczenia dla stanu z samymi `restored` entries cicho by zniknęły. Proponowana poprawka: w tym samym teście, przy zaślepce impl rzucającej wyjątek, dodać trzy przypadki w osobnych savepointach: tylko retired, tylko slot (np. `pending_bound`), tylko entry `restored`. Każdy powinien kończyć się wyjątkiem `EMPTY_HISTORY_EXECUTED_EXCLUSION_JOINS`, co dowodzi delegacji.
- [P2-2] `services/api/tests/integration/test_empty_replacement_search_postgres.py:59` — Roundtrip porównuje tylko tekst `pg_get_functiondef`. Zakres taska deklaruje jednak zachowanie OID i ACL oryginału po downgrade. Test przeszedłby również wtedy, gdyby downgrade odtwarzał funkcję przez nowe `CREATE` z innym OID i domyślnym ACL. Obecna implementacja (rename) jest poprawna, więc chodzi tylko o lukę w dowodzie. Proponowana poprawka: przed downgrade odczytać `oid` i `proacl` z `pg_proc` dla impl i po downgrade porównać je z funkcją o nazwie publicznej.
- [P2-3] `services/api/tests/integration/test_empty_replacement_search_postgres.py:33` — Rola runtime w fixture (`test_source_replacement_postgres.py:102-108`) dostaje szerokie granty ręcznie, a nie przez `database_roles` z `ALTER DEFAULT PRIVILEGES`. Uprawnienie produkcyjnej roli aplikacji do EXECUTE na nowym wrapperze wynika z domyślnego EXECUTE dla PUBLIC oraz z `database_roles.py:245`, a nie z testu. Ryzyko jest niskie i pokryje je kryterium 4 (żywe HTTP po migracji). Proponuję akceptację ryzyka z wymogiem, by odbiór operatora sprawdził rzeczywiste wyniki, a nie sam status, co task już przewiduje.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Owned PG dowodzi, że przy pustej historii kosztowna implementacja się nie wykonuje, także dla roli runtime | spełnione (statycznie; wynik uruchomienia deklaruje wykonawca) | `services/api/tests/integration/test_empty_replacement_search_postgres.py:25-35`: zaślepka impl rzuca wyjątek, owner i runtime dostają 0 w jednej transakcji z rollbackiem |
| Dotychczasowe guardy retired/reserved/closed zachowane w PG; roundtrip downgrade/upgrade | spełnione z zastrzeżeniem P2-1 i P2-2 | Równoważność semantyczna: `0179_empty_replacement_search.py:23-29` wobec `0176_source_replacement_closed.py:33-61` i 90-93; roundtrip `test_empty_replacement_search_postgres.py:39-70`; downgrade `0179_empty_replacement_search.py:38-41` |
| Testy head/lint/types/docs/map i Opus bez P0/P1 | niezweryfikowane (część po stronie koordynatora); ten audyt: brak P0/P1 | Pin `schema_readiness.py:18`, test `test_schema_readiness.py:18-21` i odmowa 0178 w `test_schema_readiness.py:80`; mypy, docs i map nie zostały uruchomione |
| Odbiór operatora na wzorze 15 symboli: HTTP 200 z wynikami, zmierzony czas, sprawdzony podgląd/range, dane bez zmian | niezweryfikowane (zgodnie z planem po wdrożeniu) | Plik taska, sekcja „Not completed”; kryterium słusznie pozostaje niezaznaczone |
| Zakres: rename na impl, wrapper STABLE SECURITY INVOKER z `search_path=pg_catalog`, brak mutacji tabel i zmian API/UI | spełnione | `0179_empty_replacement_search.py:14-31`; zmiany obejmują tylko DDL funkcji |
| Downgrade usuwa wrapper i przywraca nazwę z zachowaniem OID/ACL | spełnione (z natury `ALTER FUNCTION ... RENAME`), dowód testowy niepełny (P2-2) | `0179_empty_replacement_search.py:38-41` |
| Wywołania w surowym SQL (supergame, zakres, szczegóły, listy) korzystają z wrappera | spełnione | Wywołania po nazwie: `super_game_series_repository.py:98,111,134,141,152`, `source_replacement_guards.py:37` (nieskorelowany podzapytanie, wykonywane raz) |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P2-1, P2-2, P2-3.

## Proponowane testy

- `services/api/tests/integration/test_empty_replacement_search_postgres.py`: trzy przypadki delegacji (tylko retired, tylko slot, tylko entry `restored`) z zaślepką impl rzucającą wyjątek, każdy w savepoincie. Uruchomienie: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_empty_replacement_search_postgres.py`.
- W tym samym pliku: asercja równości `oid` i `proacl` z `pg_proc` dla impl przed downgrade i dla funkcji publicznej po downgrade.
- Po wdrożeniu: pojedyncze żądanie HTTP tylko do odczytu na dokładnym wzorze 15 symboli z limitem 75 s (kryterium 4), wykonane przez właściciela okna.

## Zakres przeglądu i ograniczenia

Przeczytałem brief, plik taska, migrację 0179, nowy test PG, zmiany w `schema_readiness.py` i `test_schema_readiness.py`, definicje funkcji w `0175_source_replacement_guards.py` i `0176_source_replacement_closed.py`, ustawienia RLS w `0174_source_replacement.py:23-37`, nadawanie uprawnień w `database_roles.py:200-256`, fixture `test_source_replacement_postgres.py:45-119`, wywołania w `source_replacement_guards.py` i `super_game_series_repository.py` oraz fragmenty istniejących testów guardów, selekcji i geometrii. Nie uruchamiałem żadnych testów, ruff, mypy, migracji ani zapytań do bazy. Wyniki „29 PASS” i ruff przyjmuję jako deklarację wykonawcy. Nie przeglądałem zmian w `DATA_MODEL.md`, `CURRENT_STATE.md` i `CODE_MAP*.md`, bo są poza ograniczonym pathspec briefu. Nie oceniałem wydajności implementacji przy niepustej historii wymiany; task wyłącza to z zakresu.
