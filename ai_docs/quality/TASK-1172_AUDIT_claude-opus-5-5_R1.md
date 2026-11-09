# Audyt TASK-1172 — Powiązanie renderowania i danych z uczeniem

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: HEAD...14fcfb4e6017dd2f1b1d2c7879bc4f498699f91f oraz zmiany niezacommitowane, data 2026-11-09
Runda: 1
SHA pakietu: 6c4e94472ff8a1dbf798f0bedf47c45175c02f439db73e4a1ae011cf4610339e
Otwarte P0: 0
Otwarte P1: 4

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano pion D-596/D-597: tworzenie sesji v2, oracle, wybór kontraktu z aktualnych adnotacji A, freeze, referencję v2, świeżość, preflight workera, diagnostyczny czytnik pomiaru i raport liczników. Główna konstrukcja jest spójna. Import i kontrakt wykonawczy są rozdzielone, replay nie rozwiązuje aktywnego modelu, a domyślny `content_pin`, `ProductionContentRun` i preflight nie przepuszczają pomiaru `render_contract_blocked`.

Cztery problemy blokują commit. Reguła zgodności pomiaru v2 odrzuca też ręczne etykiety poza rolą A. Preflight zmienia zachowanie kohort v1, choć D-596 opisuje go jako opt-in. D-597 pogarsza globalny wybór pomiaru dla TRAIN w T2. Negatywne ścieżki wyboru kontraktu A nie mają testów. Żaden z tych defektów nie poluzowuje kwalifikacji ani publikacji, a główne ryzyko to ciche wypadanie danych i zmiana historycznych ścieżek.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/api/src/game_predictor_api/domain/grid_render_reference.py:93` — `require_reference_v2` wymaga zgodności kontraktu pomiaru dla każdej roli, a `capture_production_reference` (`services/api/src/game_predictor_api/storage/production_cell_reference.py:56-64`) dołącza pomiar z każdej zamrożonej sesji pass 2. Sesje blind obejmują także sloty TRAIN (`services/api/src/game_predictor_api/storage/grid_cell_content.py:356`, `:387`). Etykieta TRAIN z wcześniejszej zamrożonej sesji v1 albo z innego kontraktu daje więc `CONTENT_MEASUREMENT_CONTRACT_CHANGED`, a czytnik zamienia ją na `label=None` (`services/api/src/game_predictor_api/storage/grid_training_cohort_evidence.py:468-470`). Taka plansza znika z nowej kohorty, a w trybie wymagającym pełnego zdjęcia wypada całe źródło TRAIN (`:476-495`). Podobny skutek ma `CONTENT_IMPORT_PROVENANCE_REQUIRED` (`domain/grid_render_reference.py:57-60`) dla plansz TRAIN/B/REG z niedostępnym rodowodem, które w v1 pozostają z jawnym pinem `unavailable`. Jest to sprzeczne z D-596 („Pozostałe role dostają ten sam wybrany kontrakt bez fikcyjnego blind pochodzenia”), z wymaganiem, że dowody B/REG mogą pozostać niedostępne, oraz z celem użycia istniejących korekt. Według `Outcome` obecne dane operatora nie mają zatwierdzonych TRAIN, więc warunek ujawni się przy kolejnych danych. Proponowana poprawka: wiązać pomiar i wymóg zgodności tylko z rolą A, a poza A zapisywać `measurement: null`. Niedostępny rodowód poza A powinien pozostać jawnym stanem bez usuwania etykiety. Dodać test zamrożonej etykiety TRAIN z sesji v1 w kohorcie v2.

- [P1-2] `services/worker/src/game_predictor_worker/images/grid_content_experiment_run.py:269` — `require_render_preflight` działa bezwarunkowo, także dla kohort v1 i przy wznowieniu przed odczytem istniejącego banku. W `services/worker/src/game_predictor_worker/images/grid_content_experiment_data.py:150-154` blokuje użyty TRAIN bez dostępnego kontekstu, a w `:161-163` odrzuca różne konfiguracje w całym zbiorze TRAIN+A+B. Przed zmianą A było sprawdzane przez `ContentSelectionEvaluator` (`grid_content_experiment_data.py:316-330`), a konfiguracja była wymagana jako jednolita tylko w obrębie źródła (`production_cell_evaluation.py:249-251`). Eksperyment v1 łączący legalnie importy 8% i 0% albo mający TRAIN z rodowodem `unavailable` przestaje więc działać, także przy retry. D-596 nazywa ten guard „Preflight opt-in eksperymentu”, a kryterium wymaga niezmienionego zachowania legacy/v1/retry. Test `services/worker/tests/test_grid_render_preflight.py:39` (`mixed_b`) utrwala nowe zachowanie na pinie v1. Proponowana poprawka: warunki TRAIN/B i jednolitości całej kohorty stosować tylko przy `expected is not None`, zachować wczesne sprawdzenie gotowości A dla v1 i dodać regresję dla v1 z mieszanym TRAIN/B. Jeżeli blokada v1 jest zamierzona, potrzebna jest jawna zmiana D-596.

- [P1-3] `services/api/src/game_predictor_api/storage/production_crop_capture.py:146-157` — po D-597 pomiar zablokowany i poprawny diagnostycznie trafia do tego samego zbioru `qualified` co pomiar `ready`, a funkcja wymaga dokładnie jednego elementu. Globalne wywołanie bez `session_ids` (`:300`) zasila zdjęcia TRAIN (`:316`). Zestaw „stary pomiar 8% zablokowany + nowy pomiar `ready`”, czyli naturalny przebieg po zmianie cropu, daje teraz `None`. Przed zmianą wybierany był jedyny `ready`. Brak `u` powoduje `CONTENT_UNCERTAINTY_MISSING` (`services/worker/src/game_predictor_worker/images/production_cell_evaluation.py:245-246`) i `not_evaluable` w raporcie T2 (`services/worker/src/game_predictor_worker/images/production_crop_comparison.py:83-84`, `:573-574`). Jest to regresja dotychczasowego wyniku, a testy D-597 wywołują `_measurement` wyłącznie z jawnym identyfikatorem sesji (`services/worker/tests/test_crop_blocked_repeatability.py:155`, `:245`). Proponowana poprawka: najpierw wybierać unikalny pomiar `ready`, a wyjątek diagnostyczny stosować tylko, gdy `ready` nie ma. Dodać test mieszanego zestawu bez `session_ids`.

- [P1-4] `services/api/src/game_predictor_api/storage/grid_render_selection.py:64-96` — negatywne ścieżki wyboru kontraktu nie mają żadnego testu. W drzewach testowych `services/` nie występują `select_a_render_contract` ani `CONTENT_A_RENDER_SELECTION_REQUIRED`. Ścieżka PostgreSQL pokrywa przebieg pozytywny z porzuconą sesją v1. Nie sprawdzono blank A obok A v2, aktualnego pass 1, mieszania v1/v2, dwóch sesji, kontraktu innego niż wybrany ani raportu nie-`ready`. Kryterium oznaczone jako wykonane wymaga wprost, by „blank lub aktualny pass1 A blokuje”, a D-596 wymaga zatrzymania mieszania. Brakuje też testu sprzeczności w `grid_cell_content_pins.py:102-108`. Proponowana poprawka: dodać parametryzowany test czytnika SQL (wzorzec SQLite z `test_crop_blocked_repeatability.py`) dla wymienionych przypadków oraz przypadek poprawny „inna stara pusta sesja nie unieważnia frozen A”.

### P2

- [P2-1] `services/api/src/game_predictor_api/storage/production_cell_reference.py:102` — kontrola świeżości v2 uruchamia pełny resolver dla każdej etykiety. Dla modeli innych niż LAB oznacza to odczyt i hash ONNX, klas i kalibracji na planszę (`storage/symbol_model_snapshot_resolver.py:147-149`). Może to znacząco wydłużyć `inspect_member` w dużej kohorcie. Propozycja: jednorazowe rozwiązanie konfiguracji na grę w ramach sprawdzenia.

- [P2-2] `services/worker/src/game_predictor_worker/images/production_cell_evaluation.py:59` — oracle v2 jest sprawdzane tylko przy niepustym `measurement`, a `production_cell_run.py:67-75` wymaga jedynie jednego unikalnego raportu. Cel A z `measurement: null` obok innych celów A przeszedłby preflight. Normalny freeze tego nie tworzy, ale kryterium mówi o blokowaniu brakujących pinów A. Fixture ma jedną planszę A (`services/worker/tests/test_production_cell_frozen_pipeline.py:36-40`), więc test tego nie obejmuje. Propozycja: wymagać pomiaru i oracle dla każdego użytego celu A v2.

- [P2-3] `services/api/src/game_predictor_api/storage/grid_cell_content.py:796-809` — techniczna awaria oracle zapisuje receipt bez `renderConfiguration` (`:711-717`), przez co sesja v2 kończy się mylącym `CONTENT_ORACLE_CONTRACT_CHANGED` i nie może zostać zamrożona. W v1 ten sam przypadek daje jawny stan `render_contract_blocked`. Propozycja: osobny kod błędu albo zamrożenie stanu zablokowanego, z testem.

- [P2-4] `services/worker/tests/test_grid_content_experiment_workflow.py:163` — wspólny fixture wyłącza preflight, a zgłoszony przez wykonawcę test `test_real_child_dispatch_completes_and_replays_lost_export_response_once` nie ma PASS. Porównanie z `main` użyło innego limitu czasu (60 s zamiast 120 s) i dało inny objaw, więc nie ustala wspólnej przyczyny. Sama zmiana w tym przebiegu jest wyłączonym wywołaniem, dlatego przyczynowość po stronie T3 jest mało prawdopodobna. Rzeczywisty przebieg R0–R3 na migawce v2 pozostaje jednak bez dowodu. Propozycja: odnotować to jako ograniczenie odbioru albo wykonać izolowany przebieg CPU.

- [P2-5] `services/api/src/game_predictor_api/storage/grid_content_diagnostic_measurement.py:54` — jedna komórka `occluded` lub `out_of_frame` wyklucza cały pomiar z diagnostyki D-597. Jest to bezpieczne, ale może ograniczyć użyteczność na danych częściowych. Propozycja: zaakceptować ryzyko i opisać je w raporcie T4 albo doprecyzować decyzję.

- [P2-6] `services/api/src/game_predictor_api/storage/grid_content_diagnostic_measurement.py:147` — bajtowa rekonstrukcja raportu zakłada kolejność `oracles` taką jak w `advance` (`grid_cell_content.py:771`, kolejność z `progress`). Dla kluczy JSONB równej długości kolejność statycznie się zgadza, więc nie stwierdzono błędu. Test buduje jednak raport ręcznie na SQLite, a nie przez `advance` na PostgreSQL. Błąd działałby bezpiecznie (odrzucenie), ale wyłączałby ścieżkę D-597. Propozycja: dodać ograniczony test PostgreSQL z realnym `advance`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| D-597: pomiar u/δ tylko do diagnostyki; strict bez poluzowania | spełnione | `services/api/src/game_predictor_api/storage/grid_cell_content_pins.py:93-101`, `storage/grid_content_diagnostic_measurement.py:32-71`, `services/worker/src/game_predictor_worker/images/production_cell_run.py:83`; skutek uboczny w P1-3 |
| Import 8% + aktywny LAB 0% daje nową sesję/oracle/referencję v2; pełny pion API | spełnione | `storage/grid_cell_content.py:337-341`, `storage/production_cell_reference.py:71-77`, OpenAPI/SDK/test wrappera w pakiecie; uruchomień nie weryfikowano |
| Ten sam pin przez freeze, parent/child i ocenę; drift blokuje, same wagi nie | spełnione | `storage/grid_correction_split.py:472-477`, `:553-558`, `storage/grid_training_cohort_evidence.py:452`, `:466`, `services/api/tests/test_grid_render_reference.py` (`test_active_freshness_uses_crop_not_weights`) |
| Legacy/v1/retry bez zmian; blank lub aktualny pass 1 A blokuje | niespełnione | P1-2, P1-3 i brak testów negatywnych P1-4; ślepy replay zachowany w `storage/grid_cell_content.py:325-334` |
| Niepoprawne/mieszane/brakujące piny blokowane przed kosztami; grid-only bez zmian | spełnione | `images/grid_content_experiment_run.py:268-269` przed siecią i bankiem; `images/grid_content_experiment_data.py:72` zawęża ścieżkę do polityki treści; luka obronna P2-2 |
| Każdy punkt T3 ma implementację lub warunek zależny od danych | spełnione | `storage/grid_content_training_inventory.py`, `storage/grid_render_selection.py`, `scripts/export_grid_content_training_inventory.py` |
| Liczniki i braki; te same dane R0–R3; zmiana kontraktu unieważnia; partial bez tła; cold restart/replay | niezweryfikowane | Statycznie: wspólne `snapshots` w `images/grid_content_experiment_run.py:267-269`, `:328`; pełny przebieg R0–R3 v2 bez PASS (P2-4) |
| Historyczne kontrakty i ręczne korekty zachowane | niespełnione | Rekordy nie są mutowane, ale etykiety spoza A mogą wypaść z nowej kohorty: P1-1 |
| Właściwe testy, lint, typy, docs/map; niezależny audyt i receipt | niespełnione | P1-4; ten raport nie uruchamiał poleceń, a logi wykonawcy nie były przedmiotem weryfikacji |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P1-1, P1-2, P1-3, P1-4, P2-1, P2-2, P2-3, P2-4, P2-5, P2-6.

## Proponowane testy

- Nowy test w `services/worker/tests/test_grid_render_preflight.py` dla v1 z mieszanym TRAIN/B i rodowodem TRAIN `unavailable`: `D:/game_predicotr/.venv/Scripts/python.exe -m pytest services/worker/tests/test_grid_render_preflight.py`.
- Nowy test w `services/worker/tests/test_crop_blocked_repeatability.py`: `_measurement(session, game)` dla zestawu „jeden `ready` + jeden diagnostycznie poprawny blocked” zwraca `ready`.
- Nowy parametryzowany plik `services/api/tests/test_grid_render_selection.py`: blank A, aktualny pass 1, v1+v2, dwie sesje, inny kontrakt, raport nie-`ready`, poprawna frozen A obok starej pustej sesji; polecenie: `D:/game_predicotr/.venv/Scripts/python.exe -m pytest services/api/tests/test_grid_render_selection.py`.
- Nowy test czytnika kohorty: etykieta TRAIN z zamrożonej sesji v1 oraz B/REG bez rodowodu w kohorcie v2 zachowują etykietę i jawny stan.
- Rozszerzenie `services/worker/tests/test_grid_render_preflight.py`: dwie plansze A v2, z których jedna ma `measurement: null`.
- Ograniczony test PostgreSQL przez `advance` i `diagnostic_measurement_ready`, uruchamiany z `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1` na dedykowanej bazie testowej.

## Zakres przeglądu i ograniczenia

Przeczytano `AGENTS.md`, cały zamrożony pakiet oraz potrzebny kod spoza diffu: czytniki oracle i pinów, `create_session`/`advance`, przygotowanie splitu, czytnik dowodów kohorty, świeżość, resolver modelu symboli, `run_experiment`, `ProductionContentRun`, obserwator i część porównania T2 z fixture testów. Przegląd był wyłącznie statyczny i nie uruchamiano testów, lintu, typecheck, migracji, usług ani poleceń zapisujących. Wyniki z pakietu i logów `artifacts/t1172-*` są deklaracjami wykonawcy, których nie weryfikowano. Nie sprawdzono rzeczywistego zachowania PostgreSQL, RLS, GPU ani jakości modelu. Skutki P1-1 i P1-2 zależą od układu danych, który statycznie potwierdzono jako osiągalny, ale nie zmierzono go na danych operatora.