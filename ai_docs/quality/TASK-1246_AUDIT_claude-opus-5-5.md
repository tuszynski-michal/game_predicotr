# Audyt TASK-1246 — Aktywacja wytrenowanego modelu siatki Mumie A2 i przetworzenie dwóch stagingów

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.2-sol, high
Zakres: 9cd972aa4b6c06436286beca8f903b427432b7b0...9cd972aa4b6c06436286beca8f903b427432b7b0 oraz zmiany niezacommitowane, data 2026-11-17
Runda: 2
SHA pakietu: afabebcb7ed998b3d1ba65afa8a60bc91a9beb16d38f1d6d4652ac5ec50dc899
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

W rundzie 2 sprawdziłem poprawki dwóch znalezisk z rundy 1 oraz pełny diff z pakietu.

Znalezisko P1-1 jest usunięte. Endpoint przekazuje teraz `use_current_model=payload.managed_source_job_id is None`. Ścieżka zarządzana istniejącego importu wraca więc do dawnego wyboru zamrożonego modelu. Nowy test HTTP sprawdza to dla korekty samych quadów i dla samego wykluczenia źródła. Na kodzie z rundy 1 ten test by nie przeszedł.

Znalezisko P2-1 też jest usunięte. Test najpierw pokazuje, że ukończony manifest wersji N nadaje się do ponownego użycia pod tym samym modelem. Potem pokazuje, że dla wersji N+1 nie trafia on do `basePageGeometryManifest`.

Nie znalazłem nowych problemów P0, P1 ani P2. Operacje na żywych danych nie są jeszcze wykonane i nie podlegały temu przeglądowi.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Istniejące żądanie przeglądarki wybiera bieżące przypisanie bez zmiany API | spełnione | `services/api/src/game_predictor_api/api/image_imports.py:1753`, `services/api/src/game_predictor_api/application/jobs.py:2265-2266`, `jobs.py:2315-2320`, test `services/api/tests/test_browser_preflight_current_model.py:52-103`; diff nie zmienia schematów Pydantic ani OpenAPI |
| Powtórzone żądanie po utworzeniu nowej usługi zwraca ten sam zapisany job | spełnione | `services/api/tests/test_browser_preflight_current_model.py:104-109`; deduplikacja przez `_equivalent_page_geometry_preflight` w `jobs.py:2223-2229` |
| Inna aktywna wersja nie może ponownie użyć wpisów geometrii starego modelu | spełnione | Porównanie `neural_grid_proposal` w `jobs.py:2821`. Kontrola pozytywna: `test_browser_preflight_current_model.py:137-142`. Brak bazy dla nowej wersji: `test_browser_preflight_current_model.py:146-151` |
| Dotychczasowi konsumenci serwisu, tożsamość zapisanych powiązań i zamrożone importy pozostają nienaruszone | spełnione | Domyślne `False` w `jobs.py:1996` i `jobs.py:2245`. Jedyny wywołujący z opt-in to `image_imports.py:1753`, warunkowo. Powiązania: `test_browser_preflight_current_model.py:164-181`, `244-262`. Dotychczasowe wywołanie: `184-196`. Ścieżka zarządzana: `265-335`. Import zamrożony przez `preflightJobId`: `jobs.py:2322-2373` i `test_browser_preflight_current_model.py:152-161` |
| Nowy model siatki przypisany do Mumie A2 z trwałym potwierdzeniem aktywacji | niezweryfikowane | Dowody runtime (`.runtime/new-model-stagings-*.json`) są poza pakietem i nie dają się sprawdzić statycznie |
| Oba nowe preflighty przypinają dokładnie ten model i zachowują stare artefakty i korekty | niezweryfikowane | Operacja jeszcze niewykonana (checkbox otwarty) |
| Oba importy ukończone, oczekujące wycinki symboli dostępne w Symbol Verification | niezweryfikowane | Operacja jeszcze niewykonana |
| Brakujące, niepowiązane i zablokowane źródła jawnie zgłoszone, bez zgadywania sekwencji | niezweryfikowane | Operacja jeszcze niewykonana |
| Odczyt w świeżym procesie potwierdza trwałe wyniki i niezmienione pliki stagingu | niezweryfikowane | Operacja jeszcze niewykonana |

## Listy zamknięte i otwarte

Zamknięte: P1-1 (`image_imports.py:1753` ogranicza opt-in do `managed_source_job_id is None`; regresja w `test_browser_preflight_current_model.py:265-335`), P2-1 (ukończony manifest wersji N z kontrolą pozytywną w `test_browser_preflight_current_model.py:113-142` i brakiem bazy dla N+1 w `test_browser_preflight_current_model.py:146-151`).

Otwarte: Brak.

## Proponowane testy

- Brak testów wymaganych przed commitem.
- Opcjonalnie: test integracyjny na PostgreSQL (`$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'`). Scenariusz to ponowienie preflightu przeglądarkowego po restarcie usługi na prawdziwym repozytorium. Test sprawdzi, że kolejność `list_jobs` i porównanie wejść deduplikują job tak samo jak `MemoryJobRepository`. Dotyczy to wyłącznie pewności, nie poprawności zmiany.

## Zakres przeglądu i ograniczenia

Przeczytano:

- diff z pakietu;
- raport rundy 1 `ai_docs/quality/TASK-1246_AUDIT_ROUND1_claude-opus-5-5.md`;
- `services/api/src/game_predictor_api/api/image_imports.py:1680-1770`, czyli `start_browser_page_geometry_preflight` z gałęziami zarządzaną i nową;
- `services/api/src/game_predictor_api/application/jobs.py:1982-2235` (`create_page_geometry_preflight_job`), `2237-2385` (`_neural_preflight_snapshot`, `_neural_import_snapshot`, `_neural_profile_matches_game`) oraz porównanie modelu w `2821`;
- stałe polityk w `domain/neural_grid_proposal.py:41` i `domain/neural_grid_operation_pin.py:27`;
- fikstury testowe `_frozen_mumie_preflight` i `_neural_jobs` (`services/api/tests/test_neural_page_geometry_api.py:844-925`), `_terminal_import`, `_completed_preflight` i `_write_managed_manifest` (`services/api/tests/test_managed_reprocess_evidence.py:47-154`);
- nowe sekcje w `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md:10-23` i `ai_docs/requirements/IMAGE_INGESTION.md:9-22`.

Grep potwierdził, że `use_current_model=True` przekazuje tylko endpoint przeglądarkowy, warunkowo. Pozostałe wywołania serwisu w testach `test_jobs_domain.py` i `test_lateral_managed_reprocess.py` korzystają z wartości domyślnej.

Ograniczenia:

- Nie uruchamiałem testów, lintera, mypy ani sprawdzenia OpenAPI. Deklarowane przez wykonawcę wyniki (121 PASS, ruff, OpenAPI `--check`, mypy w izolacji) przyjąłem bez weryfikacji.
- Nie sprawdzałem dowodów runtime w `.runtime/` ani stanu bazy.
- Zmiany w `CODE_MAP*.md`, `CURRENT_STATE.md` i pliku taska są poza pathspec pakietu i nie były przeglądane.
- Kryteria operacyjne pozostają niezweryfikowane, ponieważ operacje na żywych danych jeszcze się nie odbyły.