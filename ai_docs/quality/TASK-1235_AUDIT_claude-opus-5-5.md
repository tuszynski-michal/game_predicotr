# Audyt TASK-1235 — Naprawa timeoutu rejestracji kohorty siatek

Werdykt: PASS
Audytor: claude-opus-5-5, przegląd statyczny
Wykonawca: Codex (inna rodzina modeli), reasoning nieznany
Zakres: HEAD...4dbb57b5ecae9d966f86957fafbfe27d76e048f4 oraz zmiany niezacommitowane, data 2026-11-16
Runda: 2
SHA pakietu: 9eb9bc7b0c24e5b6414eb3256a910f925416ad655d9c92b17685c9f25ff86199
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Runda 2 obejmuje kontynuację, czyli migrację `0192_grid_cohort_header_cache`. Migracja przepisuje `recording_photo_cohort_v4` tak, żeby pola dużego nagłówka (`policyVersion`, `mode`, `familyId`, `contentSampling.policy`, `photoSplit`) były odczytywane raz w istniejącym `SELECT ... INTO header`. Złożyłem docelową definicję funkcji z szablonów v4, v6, v7, v8 i v10 oraz z przepisań 0188, 0189 i 0191. Wynik: liczby wystąpień w `_HEADER_REPLACEMENTS` (1/1/3/1/1/1) dokładnie odpowiadają wszystkim dostępom do `header.document`. Kolejność zamian (najpierw `contentSampling`, potem `photoSplit`) jest poprawna w obu kierunkach. Typy pól projekcji (`text` / `jsonb`) są identyczne z oryginalnymi wyrażeniami, a rzutowanie `::uuid` zostaje w miejscu INSERT. Nie znalazłem błędu działania ani naruszenia procesu. Główne ryzyko się nie zmieniło: dopiero ponowienie na żywych danych pokaże, czy cała rejestracja mieści się w 300 s. Do tego test PostgreSQL nie dochodzi do dwóch przepisanych gałęzi (opis w P2-4).

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-2] `services/api/src/game_predictor_api/storage/source_recording_closure_performance.py:100` — Bez zmian od rundy 1. Brak wpisu w `closure_page` dałby `context = NULL`. Dziś jest to nieosiągalne, a ryzyko zostało świadomie zaakceptowane w `ai_docs/tasks/1235-grid-cohort-closure-timeout.md:223`. Proponowana poprawka: bez zmian (jawny `IF context IS NULL THEN RAISE`) albo dalsza akceptacja ryzyka.
- [P2-3] `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md:19` — Dokumentacja architektury mówi teraz wprost, że konteksty w `recording_training_scope_v1` i `recording_validation_fence_v1` zostają liczone osobno dla każdego źródła i że czas całej kohorty trzeba zweryfikować. Ta część rundy 1 jest więc załatwiona. Nadal nie ma ograniczonego pomiaru `recording_training_scope_v1`.
  - Dodatkowa obserwacja z tej samej klasy kosztu: `recording_training_scope_v1` odczytuje `c.document->>'policyVersion'` z dużego dokumentu kohorty raz na każdego użytego członka VALIDATION z celem B (`services/api/src/game_predictor_api/storage/source_recording_sql_v8.py:205-207`). Przy 41 członkach VALIDATION i zmierzonym koszcie ok. 0,045 s na dostęp (`ai_docs/tasks/1235-grid-cohort-closure-timeout.md:159-160`) daje to najwyżej ok. 2 s, więc samo w sobie nie blokuje.
  - Wrapper v7 czyta dokument jednorazowo (`source_recording_sql_v10.py:86-88`).
  - Proponowana poprawka: zaakceptować ryzyko. Po wdrożeniu 0192 zapisać wynik ponowienia jako spełnienie kryterium 5 albo jako nowy konkretny bloker.
- [P2-4] `services/api/tests/integration/test_recording_closure_performance_postgres.py:337` — Test PostgreSQL nie wykonuje dwóch przepisanych fragmentów w ich gałęziach decyzyjnych.
  - Przypadek `bad_binding` z `policy="invalid"` nie dociera do `recording_photo_cohort_v4`. Wrapper `recording_cohort_command_v7` kieruje do v4 tylko kohorty `application-grid-corrections-v4` z `learningMaterial` (`services/api/src/game_predictor_api/storage/source_recording_sql_v10.py:83-88`). Dla innych polityk przekazuje sterowanie starszemu dyspozytorowi (`:101`), a `recording_photo_cohort_v4` jest funkcją wewnętrzną bez prawa EXECUTE dla aplikacji (`services/api/src/game_predictor_api/storage/source_recording_permissions_v10.py:10-13`). `RECORDING_BINDING_INVALID` pochodzi więc ze starszej ścieżki. Przepisany warunek `IF NOT FOUND OR header.policy_version ... OR header.cohort_mode NOT IN (...)` jest sprawdzony tylko w gałęzi „prawda” (udana rejestracja).
  - Gałąź zwolnienia `geometryOnlyTraining` z `header.sampling_policy='full-symbol-content-sampling-v1'` nie ma przypadku, w którym warunek jest prawdziwy. Fixture nie zawiera `contentSampling`, więc pole jest zawsze NULL (`test_recording_closure_performance_postgres.py:98-107`).
  - Statycznie równoważność jest mocna. Test jednostkowy porównuje pełny round-trip, kody `RAISE`, miejsce rzutowania i brak `header.document` (`services/api/tests/test_recording_closure_performance.py:98-112`). Podgląd na rzeczywistym nagłówku wykazał równość wszystkich pól (`ai_docs/tasks/1235-grid-cohort-closure-timeout.md:193-196`). Stąd P2.
  - Opis „invalid policy binding … failed as required” (`ai_docs/tasks/1235-grid-cohort-closure-timeout.md:185-186`) jest prawdziwy, ale nie świadczy o pokryciu przepisanego warunku.
  - Proponowana poprawka: dodać kohortę z polityką v4 i np. `mode="invalid"`, oczekiwany `RECORDING_BINDING_INVALID` z v4, oraz kohortę `screen+grid` z TRAIN `geometryOnlyTraining` i `contentSampling.policy='full-symbol-content-sampling-v1'` bez pełnych zdjęć dla tego źródła, oczekiwana udana rejestracja. Można też zaakceptować ryzyko i doprecyzować opis w tasku.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Zmierzone wąskie gardło i poprawka są udokumentowane | spełnione | `ai_docs/tasks/1235-grid-cohort-closure-timeout.md:159-176`; `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md:11-19` |
| Kontrole źródła, aktualności, chronionych ról i celu walidacji działają nadal | spełnione | Statycznie: zamiany 1:1 z kontrolą liczby wystąpień i końcowym zakazem `header.document` (`source_recording_closure_performance.py:156-187`); pełne pokrycie dostępów z `source_recording_sql_v4.py:78-79,85,157`, `source_recording_sql_v8.py:140`, `source_recording_sql_v10.py:12,43`; testy negatywne `test_recording_closure_performance_postgres.py:353-363`; luki w P2-4 |
| Docelowe regresje jednostkowe i PostgreSQL, jakość w zakresie i audyt wykonane | niezweryfikowane | Deklaracja wykonawcy (`ai_docs/tasks/1235-grid-cohort-closure-timeout.md:182-199`); audytor nie uruchamiał testów; checkbox w tasku słusznie odznaczony do zakończenia audytu |
| Upgrade/downgrade bazy i bezpieczeństwo funkcji sprawdzone | niezweryfikowane | Statycznie: migracja 0192 z blokadami doradczymi i limitami (`services/api/alembic/versions/0192_grid_cohort_header_cache.py:13-26`); `CREATE OR REPLACE` z `pg_get_functiondef` (`source_recording_closure_performance.py:190-198`); asercje byte-for-byte po downgrade do 0191 i metadanych (`test_recording_closure_performance_postgres.py:299-304,412-427`); wykonania nie sprawdzałem |
| Ten sam rodzic przechodzi rejestrację albo zapisano konkretny bloker | niezweryfikowane | Bloker po 0191 zapisany (`ai_docs/tasks/1235-grid-cohort-closure-timeout.md:155-170`); 0192 jeszcze nie wdrożona (`:199`) |

## Listy zamknięte i otwarte

Zamknięte: P2-1

Otwarte: P2-2, P2-3, P2-4

Uzasadnienie zamknięcia P2-1: w nowym teście są teraz przypadki, o które prosiła runda 1:
- `newUseExcluded` z rolą, oczekiwany `GRID_CORRECTION_REGISTRY_CHANGED` (`test_recording_closure_performance_postgres.py:338-340,359`);
- walidacja B na źródle z `selectionExposed` (`:341-344,360`);
- brak pełnych zdjęć dla `screen+grid` (`:336,357`);
- brak użyć po wszystkich nieudanych próbach, w tym `bad_diagnostic` (`:371-389`);
- dokładne zwolnienia rezerwacji źródeł 23 i 24 (`:390-398`).

Historyczny test materiału efektywnego dalej się zatrzymuje, ale przyjęto alternatywną poprawkę zaproponowaną w rundzie 1. Pozostałą lukę w ścieżce `RECORDING_BINDING_INVALID` opisuje P2-4.

## Proponowane testy

- W `services/api/tests/integration/test_recording_closure_performance_postgres.py` dodać kohortę z `policy="application-grid-corrections-v4"` i `mode="invalid"`, oczekiwany `RECORDING_BINDING_INVALID` zgłoszony z `recording_photo_cohort_v4`, oraz kohortę `screen+grid`, w której jedno źródło TRAIN ma `geometryOnlyTraining` i `contentSampling.policy='full-symbol-content-sampling-v1'` bez pełnego zdjęcia (P2-4). Komenda: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_recording_closure_performance_postgres.py`.
- Przed ponowieniem na żywych danych wykonać ograniczony pomiar tylko do odczytu `SELECT public.recording_training_scope_v1(:game,:cohort)` dla kohorty `19a52a6c-…` (P2-3).

## Zakres przeglądu i ograniczenia

Przeczytałem pakiet audytu (task, diff, nowe pliki, raport i receipt rundy 1) oraz:
- `services/api/src/game_predictor_api/storage/source_recording_closure_performance.py`;
- migracje `0191_grid_cohort_linear_closure.py` i `0192_grid_cohort_header_cache.py`;
- moduły przepisań 0188 i 0189 (`source_recording_source_limit.py`, `source_recording_unlimited_sources.py`);
- szablony `source_recording_sql_v4.py`, `_v6.py` (fragment PHOTO_SQL), `_v7.py`, `_v8.py` (od l. 100), `_v10.py`, `_v11.py`, `_v12.py`, `_v13.py`;
- `source_recording_permissions_v10.py`;
- testy `test_recording_closure_performance.py` i `test_recording_closure_performance_postgres.py`.

Nie uruchamiałem testów, migracji ani zapytań. Nie sprawdziłem dosłownego wyniku `pg_get_functiondef` na żywej bazie, kosztu samej projekcji pięciu pól (do pięciu jednorazowych detoastów) ani plików `.runtime/task1235-header-probe.json` i `.runtime/task1235-header-preview.json`. Wyniki weryfikacji w tasku traktuję jako deklarację wykonawcy. Zmian w `CODE_MAP*.md` i `CURRENT_STATE.md` nie oceniałem, bo są poza listą ścieżek pakietu.