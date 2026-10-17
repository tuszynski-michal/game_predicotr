# Audyt TASK-1012 — Dynamiczne snapshoty i spójny routing V3

Werdykt: REVISE
Audytor: claude-fable-5-1, reasoning high
Wykonawca: gpt-6.1-sol, reasoning high
Zakres: c06b7432e76e6e3d24b1cd78757d9f900bc9cac7...c06b7432e76e6e3d24b1cd78757d9f900bc9cac7 oraz zmiany niezacommitowane, data 2026-10-15
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano nowy snapshot `neural-grid-proposal-snapshot-v2` i jego adapter (`grid_model_snapshots.py`, `neural_grid_proposal.py`, `grid_engine_profiles.py`), resolver przypisań (`grid_profile_snapshot_resolver.py`), ścieżki start/reuse w `jobs.py`, weryfikację artefaktów w `grid_engine_model_store.py`, konsumentów w workerze (`neural_page_geometry_preflight.py`, `production_workflow.py`), kontrakt Pydantic/OpenAPI/klienta/Admina oraz nowe i zmienione testy. Logika domenowa jest spójna z planem (sekcja 4.1) i Technical notes taska: nowy preflight każdego formatu V3 wymaga jawnego assignment, pin v2 zawiera kanoniczny descriptor z SHA-256, start/reuse/replay nie odczytują aktualnego przypisania, brak lub drift pliku kończy się błędem bez wyboru innej wersji, czytnik v1 porównuje nadal statyczny rejestr, a migracja 0156 przypisuje istniejącym grom tę samą wersję v1, którą dotąd wskazywał `current`, więc zachowanie istniejących gier nie zmienia się w praktyce. Główne ryzyko to nowy test workera, który importuje moduły pomocnicze z katalogu testów API i nie da się go zebrać w samodzielnym przebiegu suite `Worker`. Pozostałe uwagi dotyczą dokumentacji i pokrycia brzegowego.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/worker/tests/test_dynamic_grid_snapshot_replay.py:16-17` — test importuje `candidate` z `test_grid_model_registry` i `MemoryJobRepository` z `test_jobs_domain`, które istnieją wyłącznie w `services/api/tests/`. `pyproject.toml:41` dodaje do `pythonpath` tylko `services/api/src`, `services/worker/src` i `services/test_support`; w `services/worker/tests/` nie ma `conftest.py`, a pytest w trybie `prepend` wstawia na `sys.path` jedynie katalog zbieranego modułu. Import działa tylko wtedy, gdy w tej samej sesji pytest wcześniej zebrał moduły z `services/api/tests/` (tak było w skoncentrowanym przebiegu wykonawcy, 90 PASS). Samodzielne `npm run python:test -- -Suite Worker` (`scripts/run_python_tests.ps1:16`) albo `pytest services/worker/tests/test_dynamic_grid_snapshot_replay.py` zakończy się błędem zbierania `ModuleNotFoundError`, co psuje udokumentowaną w `CLAUDE.md` ścieżkę uruchamiania suite workera. Żaden inny test workera nie importuje modułów z testów API. Poprawka: przenieść współdzielone helpery (`candidate`, `MemoryJobRepository`) do `services/test_support/` będącego już na `pythonpath` albo zbudować descriptor i repozytorium lokalnie w teście workera; po zmianie uruchomić suite `Worker` osobno.

### P2

- [P2-1] `ai_docs/process/CURRENT_STATE.md:189` i `ai_docs/process/CURRENT_STATE.md:196` — dwie sekcje TASK-1012 „(in progress)”: nowa `###` z wynikami oraz starszy stub `##` z bootstrapu, który nie został usunięty ani scalony. Czytelnik widzi sprzeczne poziomy nagłówków i dwa opisy tego samego stanu. Poprawka: usunąć stub z linii 196–198 lub scalić go z sekcją wyżej.
- [P2-2] `ai_docs/architecture/API_CONTRACT.md:4` (`last_updated: 2026-10-11`) i `ai_docs/requirements/IMAGE_INGESTION.md:4` (`last_updated: 2026-10-14`) — oba dokumenty otrzymały nowe sekcje TASK-1012 datowane na 2026-10-15, lecz frontmatter nie został podniesiony. Poprawka: ustawić `last_updated: 2026-10-15` w obu plikach.
- [P2-3] `services/api/src/game_predictor_api/storage/grid_profile_snapshot_resolver.py:60-104` — nowe preflighty formatów `grid_profile_777_v2` i `grid_profile_mumie_v1` wybierają model z assignment katalogu, a nie z własnego statycznego profilu. Indeks D-544 (`ai_docs/process/DECISION_LOG.md:46`) nadal brzmi „każdy profil silnika siatek importuje … z własnym modelem”; D-549 opisuje katalog i default, ale nie mówi wprost, że format przestaje wskazywać checkpoint dla nowych zadań istniejących gier. Wymaganie zapisano w IMAGE_INGESTION i API_CONTRACT, więc kontrakt jest udokumentowany, lecz AGENTS.md (linie 235–238) oczekuje wpisu DECISION_LOG przy zmianie modelu domenowego. Poprawka: krótka adnotacja w „Consequences” D-549 (lub osobny wpis), że od TASK-1012 przypisanie zastępuje statyczny `current` dla nowych preflightów wszystkich formatów V3, a D-544 opisuje odtąd tylko snapshoty v1. Alternatywnie lead akceptuje ryzyko i zapisuje decyzję w Outcome.
- [P2-4] `services/api/src/game_predictor_api/storage/grid_profile_snapshot_resolver.py:114-122` — `neural_grid_profile` zwraca `None` dla gry o kodzie `7` niezależnie od konfiguracji, więc `uses_neural_grid_pilot` daje `False` i gałąź `GRID_MODEL_HISTORICAL_GAME_PROTECTED` w liniach 52–55 jest nieosiągalna przez `JobService` (`jobs.py:2117-2119`, `jobs.py:2193-2195`). Gra kod 7 błędnie ustawiona na format V3 przejdzie po cichu do importu klasycznego zamiast zgłosić kontrolowany konflikt. Zachowanie jest zgodne z notatką „historyczna gra kod7 pozostaje klasyczna”, ale brakuje testu tego przypadku; istniejący `test_legacy_reader_keeps_historical_meaning_and_protects_game7` sprawdza tylko kod 7 z `framed_full_page_v2`. Poprawka: dodać test kodu 7 z konfiguracją V3 potwierdzający brak odczytu assignment i brak ścieżki neuronowej, albo świadomie zaakceptować i opisać w Outcome.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Trzecia rodzina działa (snapshot v2, roundtrip, nowy proces, resolver dla trzech formatów) | spełnione | `domain/grid_model_snapshots.py:27-70`, `domain/neural_grid_proposal.py:136-225`, `storage/grid_profile_snapshot_resolver.py:47-104`; testy `services/api/tests/test_dynamic_grid_snapshots.py:60-89`, `:92-108`; worker `services/worker/tests/test_dynamic_grid_snapshot_replay.py:284-297` |
| Stary job wznawia się po zmianie aktywacji (replay i start/reuse zachowują pin) | spełnione | `application/jobs.py:2168-2172`, `:2228-2235`; `grid_engine_profiles.py:80-84`, `:309-313`; worker `neural_page_geometry_preflight.py:232-234`, `:369`; test `test_dynamic_grid_snapshot_replay.py:303-351` (`resolve_neural_grid_proposal.assert_not_called`) |
| Stary preflight nie uruchamia innej wersji | spełnione | `application/jobs.py:2131-2183` (nowe rozwiązanie assignment tylko przy braku zgodnego kandydata), `storage/grid_profile_snapshot_resolver.py:135-139`; test `test_dynamic_grid_snapshots.py:221-228` |
| Brak lub zmiana hashy nie powoduje fallbacku | spełnione | `storage/grid_engine_model_store.py:155-182`, `:185-240`; `storage/grid_profile_snapshot_resolver.py:84-93`; testy `test_dynamic_grid_snapshots.py:111-125`, `:128-146`, `:149-162`; worker `test_dynamic_grid_snapshot_replay.py:352-365` |
| Kontrakt API: backend, OpenAPI, klient, wrapper i test żądania razem | spełnione | `schemas/neural_grid_proposals.py:58-70`, `schemas/jobs.py:286`, `packages/admin-api-client/openapi/openapi.json` (CatalogueNeuralGridSnapshotPayload), `src/generated/types.gen.ts`, `src/index.ts:113`, `test/neural-grid-geometry.test.mjs:131-160` |
| Wyniki kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu | niezweryfikowane | Outcome taska zawiera kontrole i ograniczenia; wynik audytu z natury jeszcze nie jest zapisany; otwarte P2-1, P2-2, P2-3 dotyczą spójności dokumentacji |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): nie dotyczy, runda 1.

Otwarte: P1-1, P2-1, P2-2, P2-3, P2-4.

## Proponowane testy

- Po poprawce P1-1 uruchomić samodzielnie suite workera: `npm run python:test -- -Suite Worker` (timeout 120 s) oraz `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_dynamic_grid_snapshot_replay.py`, aby potwierdzić zbieranie bez katalogu testów API na `sys.path`.
- Test HTTP przez `JobService`/router dla gry `neural_grid_v3` bez assignment: żądanie nowego preflightu zwraca 409 z kodem `GRID_MODEL_ASSIGNMENT_REQUIRED` (dziś pokryte wyłącznie na poziomie resolvera w `test_dynamic_grid_snapshots.py:111-120`); plik `services/api/tests/test_dynamic_grid_snapshots.py`.
- Test ścieżki kanonicznej dla gry V3 bez przypisania: `SqlAlchemyImageSequenceCanonicalRepository.uses_neural_grid_pilot` podnosi `JobConflictError`, a `ImageSequenceCanonicalService.preflight` propaguje go jako 409 (`image_sequence_canonical.py:130-136`, `image_imports.py:686-695`); dziś testowana jest tylko ścieżka pozytywna (`test_dynamic_grid_snapshots.py:107-108`).
- Test gry o kodzie `7` z konfiguracją V3 (P2-4): `uses_neural_grid_pilot` zwraca `False`, `repository.assignment` nie jest wywoływane, import pozostaje klasyczny.
- Regresja dyskryminowanej unii: GET istniejącego joba z payloadem v1 nadal waliduje się przez `NeuralGridSnapshotContract` po aliasie `contractVersion` (`schemas/neural_grid_proposals.py:67-70`), analogicznie do `test_public_http_payload_roundtrip_keeps_catalogue_pin`.

## Zakres przeglądu i ograniczenia

Przeczytano w całości: brief wraz z pełnym diffem, plik taska, `grid_model_snapshots.py`, `neural_grid_proposal.py`, `grid_profile_snapshot_resolver.py`, `grid_engine_model_store.py`, `grid_model_registry.py` (domena i storage), `schemas/neural_grid_proposals.py`, `schemas/grid_model_registry.py:40-94`, `neural-import-preflight-state.ts`, migrację `0156_grid_model_registry.py`, oba nowe testy Python i test Admina. Wyrywkowo przeczytano `application/jobs.py` (linie 720–810 i 2100–2360), `grid_engine_profiles.py` (55–315), `neural_page_geometry_preflight.py` (60–260, 340–400), `production_workflow.py` (3350–3410), `image_sequence_canonical.py`, `api/image_imports.py` (440–500, 640–720), `main.py` (mapowanie `JobConflictError` na 409), D-549 w `DECISION_LOG_2026.md`, sekcje planu dotyczące snapshotów oraz sekcje TASK-1012 w `CURRENT_STATE.md`. Sprawdzono grepem, że żaden inny konsument API/workera/Admina nie odczytuje już pola `model` snapshotu bez dyskryminacji i że `neural_import_profile` pozostaje używany tylko przez czytnik v1. Nie uruchamiano testów, lintera, mypy, typecheck ani eksportu OpenAPI; wyniki 90 PASS pytest i 21 PASS TS przyjęto z receiptów wykonawcy bez ich odtworzenia. Nie weryfikowano zachowania dyskryminatora Pydantic z aliasem `contractVersion` poza odczytem kodu i deklaracją zaliczonego testu HTTP. Nie badano stanu bazy operatora ani rzeczywistych artefaktów w `D:/game_predicotr/artifacts`.
