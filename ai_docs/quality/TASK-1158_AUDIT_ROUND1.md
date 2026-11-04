Werdykt: PASS

# Audyt TASK-1158 — Kompletność i rozdzielona kalibracja

Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: baza `f78c5b5a1a6dcbc1c0d280a0f4d2204417e5d9a3` (v1.7.562) plus niezacommitowane zmiany TASK-1158 z pakietu `artifacts/audits/task1158-r1` (19 części), data 2026-11-04
Runda: 1

To był wyłącznie przegląd statyczny (Read/Glob/Grep). Nie zmieniałem żadnych plików i nie uruchamiałem testów, usług ani zapytań do bazy. Nie otwierałem prywatnego pliku stagingowego operatora.

## Streszczenie

Sprawdziłem w kodzie główne elementy zadania:
- czystą domenę kalibracji: menu progów, wybór na B, test na REG, warunki kwalifikacji,
- trwałe cele A/B w istniejącym rejestrze użyć zdjęć (SQL v8, migracja 0181, blokady w triggerach),
- przebieg A/menu → B/seal → REG z wznowieniem po restarcie,
- odczyt raportu v5 i weryfikację pliku z dowodami (sidecar),
- pin v3, akceptację v4 i wyszukiwanie historycznego pinu przy ponowieniu,
- rejestrację diagnostyk.

Ochrona ról jest zamknięta po stronie SQL. Kolejność „plan przed B, B przed REG” jest utrwalona i odtwarzalna. Surowy wynik jakości jest rozdzielony od automatycznej kwalifikacji. Każdy brak danych daje stan „manual/unqualified”, czyli działanie zostaje zablokowane, a nie przepuszczone. Nie znalazłem otwartych P0 ani P1. Główne ryzyko to dwa rodzaje słabszej weryfikacji: hashe przypięte w planie nie są potem sprawdzane, a tożsamość routingu między ewaluatorem a runtime nie ma testu end-to-end. Skutkiem obu jest zablokowanie automatu, nie fałszywa akceptacja.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/api/src/game_predictor_api/storage/full_board_calibration_evidence.py:48`
  - **Problem:** plan zapisuje `bAssessmentSha256`, `regressionAssessmentSha256` i `bTargets` przed odczytem B. Ani weryfikator sidecara, ani `FullBoardCalibrationRun.finish` (`full_board_calibration_run.py:257`) nie sprawdzają potem, że obserwowane cele B/REG (`groundTruthSha256`, ich liczba) odpowiadają tym hashom.
  - **Skutek:** wstępna rejestracja zbioru celów jest tylko deklaracją. Utrata lub podmiana celu w sidecarze przejdzie, o ile wybór na B przeliczy się spójnie.
  - **Poprawka:** sprawdzić `len(b.targets) == plan.bTargets` oraz zbiór (źródło, pozycja, GT-SHA) względem metadanych snapshotu, które dają `bAssessmentSha256`. Analogicznie dla REG.
- [P2-2] `services/worker/src/game_predictor_worker/images/full_board_calibration_run.py:107` oraz `full_board_runtime_evidence.py:55`
  - **Problem:** `routingSha256` profilu jest liczony z `core.settings.board` i `getattr(engine, "routing")` silnika ewaluatora. Runtime liczy go z `bundle.json["preset"]["board"]` i `observation["routing"]`. Test runtime buduje ten SHA ręcznie (`routing=None`).
  - **Skutek:** przy rozjeździe obu źródeł żaden wynik nie dostanie dowodu, więc automat będzie zawsze ręczny. Działanie jest zablokowane, nie fałszywie przepuszczone, ale kwalifikacja może być w praktyce nieosiągalna.
  - **Poprawka:** jeden test liczący oba SHA z tego samego bundla i silnika z wybraną ścieżką ratunku.
- [P2-3] `services/api/src/game_predictor_api/storage/neural_grid_operation_qualification.py:190`
  - **Problem:** `_automatic_evidence` przy tworzeniu operacji czyta sidecar (do 96 MB) i synchronicznie przelicza sweep (do 256 konfiguracji × liczba celów). Dzieje się to w transakcji, która trzyma blokadę admisji.
  - **Skutek:** ryzyko przekroczenia limitu czasu przy dużym B. Wykonawca to jawnie odnotował.
  - **Poprawka:** cache wyniku weryfikacji po `reportSha256` albo akceptacja ryzyka do T5.
- [P2-4] `services/worker/src/game_predictor_worker/images/full_board_calibration_observations.py:147`
  - **Problem:** minima warstw (30/30) liczą źródła po SHA pikseli. Rodzeństwo z tej samej sesji lub pochodzenia liczy się jako osobne źródła.
  - **Uwagi:** to zgodne z literą D-587 („po scaleniu kopii”), a ograniczenie jest jawne w `LIMITATIONS`.
  - **Poprawka:** opcjonalnie raportować dodatkowo liczbę unikalnych komponentów sesji/pochodzenia w `CalibrationCounts`. Inaczej akceptacja ryzyka.
- [P2-5] `services/api/src/game_predictor_api/storage/job_repository.py:138`
  - **Problem:** sprawdzenie, że pin i polityka akceptacji są parą, działa tylko dla IMPORT. Dla VALIDATE polityka wynika później z pinu, więc para jest spójna niejawnie.
  - **Skutek:** brakuje dodatniego testu PG dla zimnego ponowienia VALIDATE w v4. Kryterium taska jawnie to ograniczenie przyjęło.
  - **Poprawka:** dodać scenariusz VALIDATE (pin v3 z bazy po świeżym połączeniu) w `test_calibrated_acceptance_postgres.py`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status | Dowód |
|---|---|---|
| Definicja bad/good, overlap, kandydat naprawia wszystkie błędy, 29/30, zakres partial, brak dowodów | spełnione | `full_board_calibration.py:236`, `:275`; testy `test_full_board_calibration.py:70`, `:83` |
| Deterministyczne cechy, pokrycie pikseli, brak referencji, perspektywa, primary/rescue; dowód routingu A, stare znaczenie triggerów | spełnione (patrz P2-2) | `full_board_completeness.py` (`missing_cell_area`, `features`); `grid_rescue_policy.py` (`completeness_routing`, routing v2 tylko dla `validation-purpose-a-v1`); test integracyjny A-evaluatora |
| Trwałe A/B, closure/bufory/diagnostyki, blokady legacy; migracja zachowuje JSON/hash/receipts; atomowy rollback/retry | spełnione | `source_recording_sql_v8.py:55` (jawna projekcja v6/v7), `:180` (trigger), `:198` (`training_scope`); `grid_validation_purpose.py:101`; `test_validation_purpose_migration_postgres.py:25` |
| Menu B wstępnie zarejestrowane, REG zapieczętowane bez strojenia; rozdzielenie publikacji i automatu; aktualność i restart | spełnione (patrz P2-1) | `full_board_calibration_run.py:173` i `:198`; `grid_model_evaluation_handler.py:436`; `full_board_calibration_report.py` (`attach_calibration`); `grid_model_publication.py` (reader v5); test wznowienia faz `test_full_board_calibration_integration.py:314` |
| Zimne ponowienie IMPORT/VALIDATE z pinem i polityką, bez autolabel/wczesnej akceptacji/nowego budżetu | spełnione dla IMPORT, częściowo dla VALIDATE (P2-5) | `v3_engine_acceptance.py:42`; `job_repository.py:138`; `test_calibrated_acceptance_postgres.py:183` |
| Manifest diagnostyczny i polecenie, bez zapisu u operatora | spełnione | `diagnostic_registration.py` (staging bez wykonania); `DIAGNOSTIC_SQL` (`source_recording_sql_v8.py:270`), idempotencja i unieważnienie raportów |
| Pełny pion API/SDK, testy/lint/mypy/docs/mapa, audyt Opus, Outcome, task-close | częściowo; task-close i commit poza zakresem rundy | schematy, OpenAPI, typy SDK, wrapper i test żądania obecne w pakiecie; logi ruff/mypy/openapi/map w part-19 przeczytane jako deklaracja, nie wykonane przeze mnie |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P2-1, P2-2, P2-3, P2-4, P2-5.

## Proponowane testy

- `services/worker/tests/test_full_board_calibration_integration.py`: test równości `routingSha256` z `FullBoardCalibrationRun` i `runtime_evidence` dla tego samego bundla i ścieżki ratunku (P2-2).
- Ten sam plik: sidecar z usuniętym jednym celem B ma zostać odrzucony przez `require_calibration_evidence` (P2-1).
- `services/api/tests/integration/test_calibrated_acceptance_postgres.py`: dodatnie zimne ponowienie VALIDATE dla pinu v3 i późniejsze odrzucenie dryfu (P2-5).
- Uruchamiać przez `.\.venv\Scripts\python.exe -m pytest <plik> -k <nazwa>`, test PG z `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'`.

## Zakres przeglądu i ograniczenia

**Przeczytałem w całości:**
- INDEX oraz części 01–11: task, weryfikacja, wycinek planu T4, D-587, wymagania i architektura, domena kalibracji, raport v5, pin i akceptacja, SQL v8, migracja 0181, uprawnienia, warstwy aplikacji i storage, przebieg kalibracji, cechy kompletności, dowody runtime, dataset, handler ewaluatora.
- Z części 17 i 18: wybrane testy (raster i ratunek, dostępny box, wznowienie faz, partial B) oraz wyemitowany `PHOTO_SQL`.

**Tylko przegląd struktury, bez czytania kodu w całości:**
- części 12–14: `grid_reinference_handler`, `grid_rescue_*`, `grid_training_*`, preflight, `production_workflow`,
- treść testów PG w częściach 15–16,
- logi w części 19.

Wnioski o wiązaniu tożsamości rastra z `RescueAttemptStore` i o zachowaniu przepływu produkcyjnego opieram więc na przeczytanych testach i kontraktach domenowych, a nie na pełnej lekturze tych modułów. W tych obszarach warto ewentualnie zlecić krótki przegląd celowany.

Wyniki testów i lintów to deklaracje wykonawcy, których nie powtarzałem. Pozytywny scenariusz PG jest syntetyczny i dowodzi kontraktu integracyjnego, a nie empirycznej kwalifikacji realnego modelu.
