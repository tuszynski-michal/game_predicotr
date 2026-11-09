# Audyt TASK-1172 — Powiązanie renderowania i danych z uczeniem

Werdykt: PASS
Audytor: claude-opus-5-5, high (poziom żądany w tasku, niezaobserwowany)
Wykonawca: gpt-6-astra, high
Zakres: HEAD...14fcfb4e6017dd2f1b1d2c7879bc4f498699f91f oraz zmiany niezacommitowane, data 2026-11-09
Runda: 2
SHA pakietu: 83937579f3986f516e7e106a4a05de81e0730bd922bae2fa2c186648b8b8af01
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Skupiona kontrola objęła dodatkową poprawkę P1-5, czyli samodzielną kolekcję testu PostgreSQL workera, oraz dokumenty procesu z pakietu. Poprawka usuwa przyczynę w trwały sposób: ścieżka jest wyliczana względem pliku i ustawiana przed importami, a logi z nowych procesów bez `PYTHONPATH` potwierdzają kolekcję pojedynczego pliku i całej suity Worker. Nie znaleziono nowych P0 ani P1, a znaleziska zamknięte w poprzedniej rundzie nie wykazują regresji. Główne ryzyko pozostaje poza tą poprawką: pełny przebieg treningowy R0–R3 nadal nie ma wyniku PASS (P2-4), więc nie można deklarować zmierzonej jakości modelu.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/api/src/game_predictor_api/storage/production_cell_reference.py:103` — kontrola świeżości v2 uruchamia resolver dla każdej etykiety, co może wydłużyć `inspect_member` w dużej kohorcie. Propozycja: utrzymać jawną akceptację ryzyka w `Outcome` albo dodać cache ograniczony do gry i transakcji.

- [P2-4] `services/worker/tests/test_grid_content_experiment_workflow.py:163` — pełny przebieg treningowy nie ma wyniku PASS, a fixture tego testu wyłącza preflight. Ograniczenie jest jawnie opisane w tasku i raporcie weryfikacji. Propozycja: utrzymać je jako warunek odbioru, bez deklarowania pełnego dowodu treningowego.

- [P2-5] `services/api/src/game_predictor_api/storage/grid_content_diagnostic_measurement.py:54` — jedna niewidoczna komórka wyklucza cały pomiar z wyjątku D-597. Działanie jest bezpieczne, lecz ogranicza użyteczność danych częściowych. Propozycja: jawnie odebrać to ograniczenie w T4.

- [P2-7] `services/api/tests/integration/test_grid_content_experiment_parent_postgres.py:460` — asercje v2 są objęte warunkiem `if selected_contract is not None`, więc utrata `evaluationContract` w kohorcie v2 pominęłaby je bez błędu. Propozycja: zapisać oczekiwaną politykę w stanie fixture i wymagać kontraktu dla konfiguracji v2.

- [P2-8] `apps/admin/src/features/model-quality/grid-content-reference-workspace.tsx:453` — Admin zawsze wysyła politykę v2, a według ustaleń poprzedniej rundy brak rodowodu importu w dowolnym wybranym celu, także TRAIN, odrzuca utworzenie sesji. Blokada jest wczesna i jawna, ale operator musi wtedy zawęzić wybór źródeł. Propozycja: pokazać ten stan w odbiorze T4, jak zapisano w `ai_docs/quality/TASK-1172_FIXES_P1_5.md`.

- [P2-9] `ai_docs/process/CURRENT_STATE.md:94` — zdanie „Poprzednie uwagi zamknięte” jest zbyt szerokie, ponieważ P2-1, P2-4, P2-5, P2-7 i P2-8 pozostają otwarte, a plik ten jest obowiązkowym punktem startowym kolejnych sesji. Skutek dotyczy tylko dokumentacji stanu, lecz może ukryć ograniczenia wymagane w T4. Propozycja: przy zamykaniu taska napisać, że zamknięte są wszystkie P1, a wymienione P2 pozostają otwarte.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| D-597: pomiar u/δ tylko do diagnostyki; strict bez poluzowania | spełnione | `services/api/src/game_predictor_api/storage/production_crop_capture.py:152-163`, `services/api/src/game_predictor_api/storage/grid_content_diagnostic_measurement.py:53-57`; testów nie uruchamiano |
| Import 8% + aktywny LAB 0% daje nową sesję/oracle/referencję v2; pełny pion API | spełnione | `services/api/src/game_predictor_api/storage/production_cell_reference.py:51-78`, `apps/admin/src/features/model-quality/grid-content-reference-workspace.tsx:453`; pozostałe dowody przeniesione z poprzedniej rundy |
| Ten sam pin przez freeze, parent/child i ocenę; drift blokuje, same wagi nie | spełnione | `services/api/src/game_predictor_api/storage/production_cell_reference.py:98-107`; dowody dla freeze i parent/child przeniesione z poprzedniej rundy |
| Legacy/v1/retry bez zmian; blank lub aktualny pass 1 A blokuje | spełnione | `services/worker/src/game_predictor_worker/images/grid_content_experiment_data.py:144`, `:168-172`, `services/api/tests/test_grid_render_selection.py:108` |
| Niepoprawne/mieszane/brakujące piny blokowane przed kosztami; grid-only bez zmian | spełnione | `services/worker/src/game_predictor_worker/images/grid_content_experiment_data.py:147-172`; miejsce wywołania przeniesione z poprzedniej rundy |
| Każdy punkt T3 ma implementację lub warunek zależny od danych | spełnione | Ustalenie poprzedniej rundy; kod produkcyjny według kolejności modyfikacji jest starszy od raportu tej rundy |
| Liczniki i braki; te same dane R0–R3; zmiana kontraktu unieważnia; partial bez tła; cold restart/replay | niezweryfikowane | Statyczne ustalenie poprzedniej rundy; pełny przebieg R0–R3 v2 bez PASS (P2-4), ograniczenie ujawnione w `Verification` taska |
| Historyczne kontrakty i ręczne korekty zachowane | spełnione | `services/api/src/game_predictor_api/storage/production_cell_reference.py:52-57`, `services/api/tests/test_grid_render_selection.py:290` |
| Właściwe testy, lint, typy i docs/map; niezależny audyt i receipt | niezweryfikowane | Odczytano wyniki kolekcji oraz Ruff/format z `artifacts/t1172-p15-*`; pozostałe kontrole są deklaracjami wykonawcy, a receipt tej rundy powstanie po raporcie |

## Listy zamknięte i otwarte

Zamknięte: P1-1, P1-2, P1-3, P1-4, P1-5, P2-2, P2-3, P2-6.

Otwarte: P2-1, P2-4, P2-5, P2-7, P2-8, P2-9.

Dowody zamknięcia:

- P1-5 — przyczyna: `services/worker/tests/test_crop_blocked_repeatability_postgres.py:13-14` wylicza względem `__file__` katalog `services/api/tests/integration` i dopisuje go przed importami z `:17` i `:38`. Wyliczenie `parents[2]` wskazuje `services`, a warunek skip w `:40-42` pozostał.
- P1-5 — wynik: `artifacts/t1172-p15-single.json` i `artifacts/t1172-p15-worker.json` zapisują `PYTHONPATH: null`, `freshProcess: true` i `exitCode: 0`. Log pojedynczego pliku podaje `1 test collected in 15.96s`, a `artifacts/t1172-p15-worker.log:3625` podaje `3623 tests collected in 33.87s`, z badanym testem w `:225`. Ruff i format są czyste.
- P1-5 — skutki uboczne: `test_crop_blocked_repeatability` istnieje wyłącznie w `services/worker/tests`, więc dopisana ścieżka go nie przesłania. Jedyne pliki w katalogu integracyjnym bez prefiksu `test_` lub `_` to `conftest.py`, `grid_content_experiment_test_resources.py` i `grid_reinference_schema_support.py`, więc nie przesłaniają `alembic` ani innych używanych pakietów.
- P1-5 — proces: jest to druga runda poprawek, ponad limit z `AGENTS.md:237`, a zapis zgody operatora znajduje się w `ai_docs/quality/TASK-1172_FIXES_P1_5.md:3-6`. Trwałość w nowym procesie, wymagana przez `AGENTS.md:115-121`, została potwierdzona logami.
- P1-1: `services/api/src/game_predictor_api/storage/production_cell_reference.py:52-57` i `services/api/src/game_predictor_api/domain/grid_render_reference.py:95-99` ograniczają wymogi do celów A, a poza A dopuszczają jawny stan `unavailable`.
- P1-2: `services/worker/src/game_predictor_worker/images/grid_content_experiment_data.py:144` i `:168` uruchamiają kontrole całej kohorty wyłącznie przy przypiętym kontrakcie.
- P1-3: `services/api/src/game_predictor_api/storage/production_crop_capture.py:156-157` daje pierwszeństwo pomiarowi `ready`.
- P1-4: `services/api/tests/test_grid_render_selection.py:108`, `:188` i `:213` zawierają testy ścieżek A na rzeczywistym SQL.
- P2-2: `services/worker/src/game_predictor_worker/images/grid_content_experiment_data.py:160-161` wymaga pomiaru dla użytego celu A.
- P2-3: `services/api/src/game_predictor_api/storage/grid_cell_content.py:796-804` daje awarii technicznej osobny kod `CONTENT_ORACLE_RENDER_UNAVAILABLE`.
- P2-6: `services/worker/tests/test_crop_blocked_repeatability_postgres.py:45` zawiera rzeczywisty `advance` i rekonstrukcję raportu z JSONB. Wynik PASS tego testu jest deklaracją wykonawcy.

## Proponowane testy

- Pełne uruchomienie samej suity Worker bez `PYTHONPATH`, ponieważ dotąd wykonano tylko kolekcję: `powershell -File scripts/run_python_tests.ps1 -Suite Worker`.
- Ponowne wykonanie testu PostgreSQL bez `PYTHONPATH`, za zgodą operatora i na dedykowanej bazie testowej, z `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`: `D:/game_predicotr/.venv/Scripts/python.exe -m pytest services/worker/tests/test_crop_blocked_repeatability_postgres.py`.
- Bezwarunkowa asercja obecności `evaluationContract` dla konfiguracji v2 w `services/api/tests/integration/test_grid_content_experiment_parent_postgres.py` (P2-7).
- Test tworzenia sesji v2 z celem TRAIN bez rodowodu importu w `services/api/tests/test_grid_render_selection.py`, sprawdzający kod błędu i brak zapisanej sesji (P2-8).

## Zakres przeglądu i ograniczenia

Przeczytano `AGENTS.md`, cały zamrożony pakiet, konfigurację pytest i ruff/mypy, `scripts/run_python_tests.ps1`, odpowiednie fragmenty `scripts/audit_task.ps1`, nagłówki importów współdzielonych fixture, logi `artifacts/t1172-p15-*` dotyczące kolekcji, Ruff i formatu oraz fragmenty kodu dla zamknięć i otwartych P2. Użyto wyłącznie odczytu plików i wyszukiwania. Nie uruchamiano testów, lintu, typecheck, migracji, usług ani baz, a wyniki z logów pozostają zapisami wykonawcy.

Kolekcja dowodzi usunięcia błędu importu, ale nie dowodzi poprawnego wykonania 3623 testów ani ponownego przejścia testu PostgreSQL po zmianie sposobu ustawiania ścieżki. Poprawka nie zmienia logiki testu. Typecheck nie obejmuje testów (`package.json:138`). Dopisana ścieżka pozostaje w `sys.path` przez resztę procesu pytest. Pełna kolekcja nie wykazała konfliktu, lecz nie porównywano wszystkich nazw modułów w obu katalogach.

Zamrożenie kodu produkcyjnego oceniono jedynie po kolejności czasów modyfikacji: pliki produkcyjne z próby są starsze od raportu poprzedniej rundy, a poprawiony test i `TASK-1172_FIXES_P1_5.md` nowsze. Nie jest to dowód kryptograficzny. Nie przeliczano SHA pakietu; podano wartość ze zlecenia. Treści zgody operatora nie da się potwierdzić poza zapisem w dokumentach. Nie sprawdzano rzeczywistego zachowania PostgreSQL, RLS, GPU ani jakości modelu.