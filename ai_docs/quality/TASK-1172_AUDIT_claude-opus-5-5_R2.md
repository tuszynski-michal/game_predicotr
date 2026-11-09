# Audyt TASK-1172 — Powiązanie renderowania i danych z uczeniem

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: HEAD...14fcfb4e6017dd2f1b1d2c7879bc4f498699f91f oraz zmiany niezacommitowane, data 2026-11-09
Runda: 2
SHA pakietu: 42a49fd64f15f8a758ce671ed70bd9a9df4c1bf74d0bf4ad18fab130f9e23e7a
Otwarte P0: 0
Otwarte P1: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono poprawki znalezisk rundy 1 oraz ich wpływ na referencję v2, preflight workera, wybór pomiaru D-597 i odczyt ról A/B/REG. Wszystkie cztery P1 z rundy 1 oraz P2-2, P2-3 i P2-6 są usunięte w kodzie i mają testy, a poprawki nie poluzowują strict `content_pin`, freeze ani bramek publikacji. Blokuje jeden nowy defekt z rundy poprawek: nowy test PostgreSQL importuje na poziomie modułu pliki z `services/api/tests/integration`, co statycznie wskazuje na błąd kolekcji całej samodzielnej suity Worker. Pozostałe ryzyka mają poziom P2.

## Znaleziska

### P0

Brak.

### P1

- [P1-5] `services/worker/tests/test_crop_blocked_repeatability_postgres.py:10` — nowy test importuje `_application_role_database` (`:10`) i `test_v3_engine_acceptance_postgres` (`:31`) na poziomie modułu, a oba pliki istnieją wyłącznie w `services/api/tests/integration`. Pytest wykonuje te importy podczas kolekcji, zanim zadziała `pytestmark` ze `skipif`. Katalogu integracyjnego nie ma w `pythonpath` (`pyproject.toml:41`), `services/worker/tests` nie ma `conftest.py`, a `scripts/run_python_tests.ps1:16` i `:25` nie ustawiają `PYTHONPATH`. Polecenie `run_python_tests.ps1 -Suite Worker` albo `pytest services/worker/tests` powinno więc zakończyć się `ModuleNotFoundError` podczas kolekcji, a przerwana kolekcja nie uruchomi żadnego testu Worker. Wariant `All` przechodzi kolekcję tylko dlatego, że wcześniej zbierane `services/api/tests` dopisują katalog integracyjny do `sys.path`. Wykonawca uruchamiał testy z `PYTHONPATH` zawierającym ten katalog, co ukrywa problem. Proponowana poprawka: przed tymi importami dodać jawną ścieżkę, zgodnie ze wzorcem z `services/worker/tests/test_full_board_variant_pipeline.py:257`, albo przenieść współdzieloną obsługę do `services/test_support`. Trzeba też potwierdzić kolekcję samej suity Worker bez dodatkowego `PYTHONPATH`.

### P2

- [P2-1] `services/api/src/game_predictor_api/storage/production_cell_reference.py:103` — kontrola świeżości v2 nadal uruchamia resolver dla każdej etykiety, co może wydłużyć `inspect_member` w dużej kohorcie. Wykonawca jawnie przyjął to ryzyko. Propozycja: pozostawić je w `Outcome` albo dodać cache ograniczony do gry i transakcji.

- [P2-4] `services/worker/tests/test_grid_content_experiment_workflow.py:163` — pełny przebieg treningowy R0–R3 nadal nie ma wyniku PASS, a wspólny fixture wyłącza preflight. Ograniczenie jest jawnie opisane w tasku i raporcie weryfikacji. Propozycja: utrzymać je jako warunek odbioru, bez deklarowania pełnego dowodu treningowego.

- [P2-5] `services/api/src/game_predictor_api/storage/grid_content_diagnostic_measurement.py:54` — jedna komórka niewidoczna wyklucza cały pomiar z wyjątku D-597. Działanie jest bezpieczne, lecz ogranicza użyteczność danych częściowych. Propozycja: zgodnie z decyzją wykonawcy przekazać to do jawnego odbioru w T4.

- [P2-7] `services/api/tests/integration/test_grid_content_experiment_parent_postgres.py:460` — wszystkie asercje v2 drugiej fazy są objęte warunkiem `if selected_contract is not None`, a faza druga nie zna oczekiwanej polityki. Gdyby kohorta v2 straciła `evaluationContract` i przeszła ścieżką v1, ten blok zostałby cicho pominięty. Propozycja: zapisać oczekiwaną politykę w stanie fixture i wymagać kontraktu, gdy była to konfiguracja v2.

- [P2-8] `apps/admin/src/features/model-quality/grid-content-reference-workspace.tsx:453` — Admin zawsze wysyła politykę v2, a `services/api/src/game_predictor_api/storage/grid_content_oracle_context.py:68-72` wraz z `services/api/src/game_predictor_api/domain/grid_render_reference.py:57-60` odrzuca całe tworzenie sesji, gdy choć jeden wybrany cel, także TRAIN, nie ma rodowodu importu. Jest to wczesna, jawna blokada zgodna z potrzebą renderowania oracle, ale operator musi wtedy zmienić wybór źródeł, a UI nie oferuje ścieżki v1. Propozycja: zaakceptować ryzyko i opisać ten stan w odbiorze T4.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| D-597: pomiar u/δ tylko do diagnostyki; strict bez poluzowania | spełnione | `services/api/src/game_predictor_api/storage/grid_cell_content_pins.py:93-134`, `services/api/src/game_predictor_api/storage/production_crop_capture.py:152-163`, `services/worker/src/game_predictor_worker/images/production_cell_run.py:85` |
| Import 8% + aktywny LAB 0% daje nową sesję/oracle/referencję v2; pełny pion API | spełnione | `services/api/src/game_predictor_api/storage/grid_cell_content.py:325-341`, `services/api/src/game_predictor_api/storage/production_cell_reference.py:51-78`, `packages/admin-api-client/openapi/openapi.json:8556-8567`; testów nie uruchamiano |
| Ten sam pin przez freeze, parent/child i ocenę; drift blokuje, same wagi nie | spełnione | `services/api/src/game_predictor_api/storage/grid_correction_split.py:466-478`, `:552-560`, `services/api/src/game_predictor_api/storage/grid_training_cohort_evidence.py:452`, `:466`, `services/api/src/game_predictor_api/storage/production_cell_reference.py:95-113` |
| Legacy/v1/retry bez zmian; blank lub aktualny pass 1 A blokuje | spełnione | `services/worker/src/game_predictor_worker/images/grid_content_experiment_data.py:144`, `:168-172`, `services/api/src/game_predictor_api/storage/grid_render_selection.py:70-96`, `services/api/tests/test_grid_render_selection.py` (`test_current_sql_a_selection`) |
| Niepoprawne/mieszane/brakujące piny blokowane przed kosztami; grid-only bez zmian | spełnione | `services/worker/src/game_predictor_worker/images/grid_content_experiment_run.py:268-269`, `services/worker/src/game_predictor_worker/images/grid_content_experiment_data.py:147-172` |
| Każdy punkt T3 ma implementację lub warunek zależny od danych | spełnione | `services/api/src/game_predictor_api/storage/grid_render_selection.py`, `services/api/src/game_predictor_api/storage/grid_content_training_inventory.py`, `scripts/export_grid_content_training_inventory.py` |
| Liczniki i braki; te same dane R0–R3; zmiana kontraktu unieważnia; partial bez tła; cold restart/replay | niezweryfikowane | Statycznie wspólne `snapshots` w `services/worker/src/game_predictor_worker/images/grid_content_experiment_run.py:267-269`; pełny przebieg R0–R3 v2 bez PASS (P2-4) |
| Historyczne kontrakty i ręczne korekty zachowane | spełnione | `services/api/src/game_predictor_api/storage/production_cell_reference.py:52-57`, `services/api/tests/test_grid_render_selection.py` (`test_old_blind_labels_outside_a_survive_v2_capture`) |
| Właściwe testy, lint, typy i docs/map; niezależny audyt i receipt | niespełnione | P1-5; wyniki lintu, typów i map są deklaracjami wykonawcy, a receipt tej rundy nie jest częścią pakietu |

## Listy zamknięte i otwarte

Zamknięte: P1-1, P1-2, P1-3, P1-4, P2-2, P2-3, P2-6.

Otwarte: P1-5, P2-1, P2-4, P2-5, P2-7, P2-8.

Dowody zamknięcia:

- P1-1: pomiar i wymóg rodowodu v2 dotyczą tylko celów A (`services/api/src/game_predictor_api/storage/production_cell_reference.py:52-57`), a poza A jawny stan `unavailable` przechodzi walidację (`services/api/src/game_predictor_api/domain/grid_render_reference.py:92-101`).
- P1-2: kontrole całej kohorty działają wyłącznie przy przypiętym kontrakcie (`services/worker/src/game_predictor_worker/images/grid_content_experiment_data.py:144`, `:168`). Dla v1 zostaje sprawdzenie A równoważne późniejszemu `ContentSelectionEvaluator` (`:170-172`, `:335-336`).
- P1-3: unikalny pomiar `ready` ma pierwszeństwo przed wyjątkiem diagnostycznym (`services/api/src/game_predictor_api/storage/production_crop_capture.py:152-163`).
- P1-4: `services/api/tests/test_grid_render_selection.py` obejmuje rzeczywistym SQL blank A, aktualny pass 1, v1/v2, dwie sesje, inny kontrakt, raport nie-`ready` i starą pustą sesję.
- P2-2: każdy użyty cel A v2 wymaga pomiaru (`services/worker/src/game_predictor_worker/images/production_cell_run.py:63-64`, `services/worker/src/game_predictor_worker/images/grid_content_experiment_data.py:160-161`), a oracle jest sprawdzane w `services/worker/src/game_predictor_worker/images/production_cell_evaluation.py:59-77`.
- P2-3: techniczna awaria oracle daje osobny kod w `services/api/src/game_predictor_api/storage/grid_cell_content.py:796-804`.
- P2-6: `services/worker/tests/test_crop_blocked_repeatability_postgres.py` wykonuje rzeczywiste `advance` i rekonstrukcję raportu z JSONB. Wada importu tego pliku jest osobnym znaleziskiem P1-5.

## Proponowane testy

- Kolekcja samej suity Worker bez `PYTHONPATH` wskazującego katalog integracyjny: `D:/game_predicotr/.venv/Scripts/python.exe -m pytest services/worker/tests --collect-only -q`.
- Bezwarunkowa asercja obecności `evaluationContract` dla konfiguracji v2 w `services/api/tests/integration/test_grid_content_experiment_parent_postgres.py`, uruchamiana z `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1` na dedykowanej bazie testowej.
- Test tworzenia sesji v2 z wybranym celem TRAIN bez rodowodu importu w `services/api/tests/test_grid_render_selection.py`, sprawdzający kod `CONTENT_IMPORT_PROVENANCE_REQUIRED` i brak zapisanej sesji: `D:/game_predicotr/.venv/Scripts/python.exe -m pytest services/api/tests/test_grid_render_selection.py`.

## Zakres przeglądu i ograniczenia

Przeczytano `AGENTS.md`, cały zamrożony pakiet oraz potrzebny kod spoza diffu: referencję produkcyjną, `content_pin`, odczyt dowodów kohorty, przygotowanie splitu, `advance`, datasety, obserwator, preflight, `run_experiment`, fixture testowe i konfigurację pytest. Przegląd był wyłącznie statyczny i odbył się bez powłoki, a testów, lintu, typecheck, migracji ani usług nie uruchamiano. Skutek P1-5 wynika z konfiguracji i reguł kolekcji pytest, ale nie został potwierdzony wykonaniem. Wyniki z logów `artifacts/t1172-*` pozostają deklaracjami wykonawcy; jedyne wyszukanie w logach `t1172-r1-*` potwierdziło tylko obecność identyfikatora testu PostgreSQL. Nie sprawdzono rzeczywistego zachowania PostgreSQL, RLS, GPU ani jakości modelu.