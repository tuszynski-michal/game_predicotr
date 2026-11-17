# Audyt TASK-1246 — Aktywacja wytrenowanego modelu siatki Mumie A2 i przetworzenie dwóch stagingów

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.2-sol, high
Zakres: 9cd972aa4b6c06436286beca8f903b427432b7b0...9cd972aa4b6c06436286beca8f903b427432b7b0 oraz zmiany niezacommitowane, data 2026-11-17
Runda: 1
SHA pakietu: 11305db26e39ee47212af4cf0ea1087fa5ce21a26019d90ff674615f48093264
Otwarte P0: 0
Otwarte P1: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem poprawkę wyboru modelu w preflighcie geometrii uruchamianym z przeglądarki. Zmiana obejmuje `JobService.create_page_geometry_preflight_job` i `_neural_preflight_snapshot` z nową opcją `use_current_model`, endpoint `start_browser_page_geometry_preflight`, nowy plik testów regresyjnych oraz dwa dokumenty. Dla nowego stagingu bez zapisanych przypisań detekcji poprawka działa zgodnie z celem. Ponowione żądanie zwraca ten sam job, ponieważ wejście jest równe, a ponowne użycie geometrii starego modelu blokuje porównanie `neural_grid_proposal`.

Główne ryzyko: endpoint ustawia `use_current_model=True` bezwarunkowo. Opcja działa więc także na ścieżce zarządzanej (`managedSourceJobId`), z której korzystają ponowny preflight i wznowienie importu dla stagingu już zaimportowanego. Ta zmiana zachowania nie jest objęta zakresem zadania, przeczy dokumentacji i nie ma testu. Operacje na żywych danych nie są jeszcze wykonane i nie podlegały weryfikacji.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/api/src/game_predictor_api/api/image_imports.py:1753` — `use_current_model=True` jest przekazywane bezwarunkowo, także gdy żądanie zawiera `managed_source_job_id` (gałąź `image_imports.py:1701-1709`).
  - **Jak działa ścieżka zarządzana.** Dla stagingu już zaimportowanego przez sieć neuronową odpowiedź `review-sources` zwraca `managed_source_job_id` (`image_imports.py:2026-2036`). Panel admina wysyła ten identyfikator przy ponownym preflighcie po korekcie (`page-geometry-correction-panel.tsx:1476`, `image-folder-import-panel.tsx:1244-1248`). Wznowienie importu wymaga, żeby ten identyfikator był równy istniejącemu importowi (`neural-import-preflight-state.ts:96-98`, `169-216`).
  - **Co się zmieniło.** Wcześniej `_neural_preflight_snapshot` (`jobs.py:2267-2309`) dla tej samej pary `source_selection_id`/manifest ponownie używał modelu z ukończonego preflightu, czyli modelu przypiętego w pierwotnym imporcie. Teraz, gdy staging nie ma zapisanych `neuralProposalBinding` (`jobs.py:2265-2266`), preflight cicho przechodzi na bieżące przypisanie gry. Dotyczy to korekt składających się wyłącznie z wykluczeń źródeł, ręcznych quadów albo ponowień źródeł z `NEURAL_GRID_SOURCE_TIME_LIMIT`.
  - **Brak zabezpieczenia.** `create_image_import_job` na ścieżce zarządzanej nie porównuje modelu nowego preflightu z modelem źródłowego importu (`jobs.py:825-847`). Wznowiony import przejmie więc geometrię innego modelu.
  - **Sprzeczność z deklaracjami.**
    - Zadanie mówi „Keep frozen import/resume and binding-backed requests unchanged”.
    - Dokumentacja twierdzi „Import/resume nie wywołują tego odświeżenia” (`ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md:21`) oraz że wznowienie używa modelu przypiętego w preflighcie (`ai_docs/requirements/IMAGE_INGESTION.md:19-20`).
    - Komentarz w kodzie mówi „existing import/resume requests retain their old pins” (`jobs.py:2262-2264`).
    - Żaden test nie obejmuje ścieżki zarządzanej.
  - **Proponowana poprawka.** Ograniczyć opt-in do nowego stagingu: `use_current_model=payload.managed_source_job_id is None`. Dodać test HTTP pokazujący, że preflight zarządzany bez powiązań zachowuje zamrożony model pierwotnego importu. Jeśli przejście na bieżący model przy wznowieniu jest zamierzone, wymaga to jawnej decyzji operatora, zmiany zakresu, dokumentacji i osobnego testu.

### P2

- [P2-1] `services/api/tests/test_browser_preflight_current_model.py:106-113` — scenariusz zmiany aktywnej wersji sprawdza tylko `created is True` i nowy `neuralGridProposal`.
  - **Luka.** W chwili drugiego żądania pierwszy job nowego modelu nie jest ukończony. Test nie dowodzi więc, że ukończony manifest wersji N nie zostanie użyty jako `basePageGeometryManifest` dla wersji N+1. Dziś gwarantuje to tylko porównanie w `jobs.py:2821`.
  - **Proponowana poprawka.** Przed zmianą wersji oznaczyć pierwszy nowy job jako ukończony, z manifestem i sumą kontrolną. Następnie sprawdzić, że w odpowiedzi dla `next_current` brak `basePageGeometryManifest`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Istniejące żądanie przeglądarki wybiera bieżące przypisanie bez zmiany API | spełnione | `services/api/src/game_predictor_api/api/image_imports.py:1753`, `services/api/src/game_predictor_api/application/jobs.py:2265-2266`, `services/api/tests/test_browser_preflight_current_model.py:47-98`; diff nie zmienia schematów ani OpenAPI |
| Powtórzone żądanie po utworzeniu nowej usługi zwraca ten sam zapisany job | spełnione | `services/api/tests/test_browser_preflight_current_model.py:99-104`, `services/api/src/game_predictor_api/application/jobs.py:2210`, `2223-2229`, `2762-2785` |
| Inna aktywna wersja nie może ponownie użyć wpisów geometrii starego modelu | spełnione (z luką testową P2-1) | `services/api/src/game_predictor_api/application/jobs.py:2821`, `services/api/tests/test_browser_preflight_current_model.py:98`, `106-113` |
| Dotychczasowi konsumenci serwisu, tożsamość zapisanych powiązań i zamrożone importy pozostają nienaruszone | niespełnione | Domyślne `False` w `jobs.py:1996`, `2245` oraz testy `test_browser_preflight_current_model.py:127-158`, `206-226` są poprawne. Preflight wznowienia na ścieżce zarządzanej zmienia jednak model (P1-1, `image_imports.py:1753`) |
| Nowy model siatki przypisany do Mumie A2 z trwałym potwierdzeniem aktywacji | niezweryfikowane | Dowody runtime (`.runtime/new-model-stagings-*.json`) są poza pakietem; nie da się ich sprawdzić statycznie |
| Oba nowe preflighty przypinają dokładnie ten model i zachowują stare artefakty i korekty | niezweryfikowane | Operacja jeszcze niewykonana (checkbox otwarty) |
| Oba importy ukończone, oczekujące wycinki symboli dostępne w Symbol Verification | niezweryfikowane | Operacja jeszcze niewykonana |
| Brakujące, niepowiązane i zablokowane źródła jawnie zgłoszone, bez zgadywania sekwencji | niezweryfikowane | Operacja jeszcze niewykonana |
| Odczyt w świeżym procesie potwierdza trwałe wyniki i niezmienione pliki stagingu | niezweryfikowane | Operacja jeszcze niewykonana |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P1-1, P2-1.

## Proponowane testy

- Test HTTP w `services/api/tests/test_browser_preflight_current_model.py`:
  - **Przygotowanie:** ukończony import neuronowy przypięty do starego modelu, bieżące przypisanie wskazuje inny model, brak `neuralProposalBinding`, obecne tylko wykluczenie albo ręczny quad.
  - **Akcja:** `POST .../geometry-preflight` z `managedSourceJobId` równym istniejącemu importowi.
  - **Oczekiwany wynik:** zamrożony model źródłowego importu, a nie bieżące przypisanie.
  - **Polecenie:** `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_browser_preflight_current_model.py -k managed`.
- Rozszerzenie scenariusza z `test_browser_preflight_pins_current_model_and_replays_after_service_restart`:
  - **Kroki:** oznaczyć pierwszy job nowego modelu jako ukończony z manifestem, potem aktywować kolejną wersję.
  - **Oczekiwany wynik:** brak `basePageGeometryManifest` w nowym jobie.
  - **Polecenie:** `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_browser_preflight_current_model.py`.

## Zakres przeglądu i ograniczenia

Przeczytano:

- diff z pakietu;
- `services/api/src/game_predictor_api/application/jobs.py`: `_pin_neural_operation`, ścieżka zarządzana `create_image_import_job` i reprocess, `create_page_geometry_preflight_job`, `_neural_preflight_snapshot`, `_neural_import_snapshot`, `_select_page_geometry_base_manifest`, `_equivalent_page_geometry_preflight`, `_page_geometry_candidate_compatibility`, `get_page_geometry_preflight_by_source_selection`;
- `services/api/src/game_predictor_api/api/image_imports.py`: endpointy preflightu, startu importu i `review-sources`;
- `services/api/src/game_predictor_api/storage/grid_profile_snapshot_resolver.py`: `resolve_neural_grid_proposal`;
- `services/api/src/game_predictor_api/storage/job_repository.py`: sortowanie `list_jobs`;
- pomocnicze fikstury testowe w `services/api/tests/test_neural_page_geometry_api.py`;
- logikę wznowienia w admin: `apps/admin/src/features/imports/neural-import-preflight-state.ts` i `image-folder-import-panel.tsx`;
- nowe sekcje w obu dokumentach.

Ograniczenia:

- Nie uruchamiałem testów, lintera, mypy ani sprawdzenia OpenAPI. Deklarowane wyniki wykonawcy (119 PASS, ruff, OpenAPI `--check`) przyjąłem bez weryfikacji.
- Nie sprawdzałem dowodów runtime w `.runtime/` ani stanu bazy.
- Nie oceniałem wpływu ponownego importu nowym modelem na wcześniejsze ręczne weryfikacje symboli, bo wykracza to poza zakres zmiany kodu.
- Zmiany w `CODE_MAP*.md` i `CURRENT_STATE.md` są poza pathspec pakietu i nie były przeglądane.