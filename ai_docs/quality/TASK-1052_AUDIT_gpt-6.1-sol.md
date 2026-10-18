# Audyt TASK-1052 - Import resume with originals replaced by verified crops

Werdykt: REVISE  
Audytor: Codex `gpt-6.1-sol` / `high`  
Wykonawca: Claude `claude-opus-5-5` / `xhigh`  
Zakres: HEAD...dec6f4e737b1196c770d0fa2620ae1dd08751421 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-18  
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono ingestowanie oryginałów, retry pojedynczego pliku, geometry guard oraz wskazane ścieżki preflightu i override’u geometrii. Zmiana chroni przed ponownym kopiowaniem poprawnie atestowanego cropu, lecz stosuje wyjątek zbyt szeroko i nie zapewnia wszystkich wymaganych odmów przed zapisem. Brakuje również wymaganego testu pełnego wznowienia z PostgreSQL i restartem.

## Znaleziska

### P0

- [P0-1] `services/worker/src/game_predictor_worker/images/source_ingestion.py:443` — Uznanie brakującego oryginału za obecny zależy wyłącznie od plików cropu i atestu. Kod nie sprawdza wymaganego stanu `original_deleted` w rejestrze. Przy wierszu `verified` albo braku wiersza również pomija odtworzenie oryginału, choć R11 nakazuje wtedy dotychczasową kopię ze źródła albo `IMAGE_SOURCE_UNAVAILABLE`. Należy przekazać do ingestii informację z rejestru i ograniczyć wyjątek do potwierdzonego `original_deleted`.

- [P0-2] `services/worker/src/game_predictor_worker/images/source_ingestion.py:320` — Wyjątek działa także podczas nowego importu tego samego pliku. `ensure_original` nie rozróżnia wznowienia od ponownego importu, więc przy poprawnym cropie nie odtwarza pełnego oryginału mimo dostępnego źródła. Narusza to zachowanie zachowane przez R10 i sekcję Out of scope; późniejszy konsument pełnego kadru nadal otrzyma `SOURCE_ORIGINAL_CROPPED`. Należy ograniczyć pomijanie kopii do wznowienia istniejącego importu i dodać regresję ponownego importu przy poprawnym cropie.

- [P0-3] `services/api/src/game_predictor_api/api/image_imports.py:2498` — Override geometrii nie odmawia operacji dla usuniętego managed original, jeżeli staging nadal istnieje. Wówczas `page_source_asset` zwraca bezpośrednio plik stagingu (`image_imports.py:603`), a endpoint dekoduje go i dochodzi do zapisu override’u zamiast zwrócić wymagany `SOURCE_ORIGINAL_CROPPED`. Istniejąca blokada obejmuje jedynie fallback do managed source. Należy sprawdzić stan oryginału przed dekodowaniem i zapisem, również dla zachowanego stagingu.

- [P0-4] `services/worker/src/game_predictor_worker/images/page_geometry_preflight.py:268` — Preflight managed source najpierw wywołuje `load_or_create_manifest`, a dopiero potem sprawdza crop (`page_geometry_preflight.py:277`). Dla nowego joba metoda zapisuje sklonowany manifest przed odmową (`source_ingestion.py:116`). Ta sama kolejność występuje w `services/worker/src/game_predictor_worker/images/neural_page_geometry_preflight.py:246`. Kod zwraca właściwy błąd, ale pozostawia zapisany artefakt, co narusza kryterium braku skutków ubocznych. Należy zweryfikować cały istniejący manifest źródłowy przed materializacją manifestu nowego joba w obu preflightach.

### P1

- [P1-1] `services/worker/tests/test_import_resume_with_cropped_originals.py:61` — Nowy test zastępuje deletion job przez `original.unlink()`, korzysta z atrap i ponownie uruchamia wyłącznie handler ingestii (`test_import_resume_with_cropped_originals.py:81`). Nie obejmuje PostgreSQL, restartu procesu, rzeczywistego `retry_job` ani dojścia importu do końcowego stanu. Oddzielny test guardu potwierdza lokalne ponowne użycie raportu, ale nie zastępuje wymaganego scenariusza całego workflow. Należy dodać test integracyjny: import, crop, deletion job, restart i retry, osobno ze stagingiem obecnym i usuniętym; sprawdzić brak kopii oraz brak dekodowania ukończonych plików.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Test restart/PostgreSQL: retry po deletion job, staging obecny i usunięty, bez kopii i błędu | niespełnione | `services/worker/tests/test_import_resume_with_cropped_originals.py:61` — ręczne usunięcie pliku; `:81` — tylko ingestia z atrapą kontekstu. |
| Odmowy `SOURCE_ORIGINAL_CROPPED` bez skutków ubocznych dla każdej ścieżki pełnego kadru | niespełnione | P0-3 i P0-4. Poprawne lokalne blokady: `services/api/src/game_predictor_api/storage/image_job_repository.py:226` oraz `services/worker/src/game_predictor_worker/images/large_import_geometry_guard.py:221`. |
| Lint, mypy, testy skupione i PostgreSQL przechodzą; audyt zamknięty | niespełnione | Brief nie zawiera wyników weryfikacji; testów nie uruchamiano. Otwarte P0/P1 oznaczają niezamknięty audyt. |

## Listy zamknięte i otwarte

Zamknięte: Brak — runda 1.

Otwarte: P0-1, P0-2, P0-3, P0-4, P1-1.

## Proponowane testy

- W `services/worker/tests/test_import_resume_with_cropped_originals.py` dodać przypadki braku wiersza rejestru, stanu `verified` i nowego importu identycznego pliku z poprawnym cropem. Komenda: `D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/worker/tests/test_import_resume_with_cropped_originals.py`.
- W `services/api/tests/test_image_imports_api.py` dodać odmowę override’u przy zachowanym stagingu i stanie `original_deleted`, z kontrolą braku zapisu. Komenda: `D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_imports_api.py`.
- W testach obu preflightów sprawdzić, że odmowa nie tworzy manifestu ani checkpointów. Komenda: `D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/worker/tests/test_page_geometry_preflight.py services/worker/tests/test_neural_page_geometry_preflight.py`.
- W `services/api/tests/integration/test_source_original_deletion_postgres.py` dodać scenariusz opisany w P1-1, wykorzystując rzeczywisty deletion job i nowe procesy. Po ustawieniu `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1` uruchomić: `D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_source_original_deletion_postgres.py`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, aktywny task, wymagane dokumenty startowe, decyzje D-562/D-563 oraz właściwe fragmenty planu i kontraktu API. Sprawdzono cały wskazany diff, nowy plik testów oraz powiązane ścieżki ingestii, orkiestracji, preflightów, override’u, loadera i rejestru cropów.

Nie uruchamiano testów, lintowania, mypy, usług ani operacji bazodanowych. Nie zweryfikowano wykonawczo restartu, transakcji PostgreSQL ani końcowego wyniku pełnego importu. Żaden plik nie został utworzony, zmieniony ani usunięty.