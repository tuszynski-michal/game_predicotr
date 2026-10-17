# Audyt TASK-1012 — Dynamiczne snapshoty i spójny routing V3

Werdykt: PASS
Audytor: claude-fable-5-1, reasoning high
Wykonawca: gpt-6.1-sol, reasoning high
Zakres: c06b7432e76e6e3d24b1cd78757d9f900bc9cac7...c06b7432e76e6e3d24b1cd78757d9f900bc9cac7 oraz zmiany niezacommitowane (korekta po rundzie 1: 6 plików z `artifacts/audits/TASK-1012_CORRECTION_SCOPE.json`), data 2026-10-15
Runda: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Ponownie zbadano wyłącznie zakres rundy 1 (P1-1, P2-1–P2-4) oraz zachowanie korekty: nowy test workera, rozszerzony test API, sekcję TASK-1012 w `CURRENT_STATE.md`, daty frontmatter dwóch dokumentów, doprecyzowanie D-549 przez leada oraz plik taska. Korekta nie zmienia żadnego pliku produkcyjnego ani współdzielonych fixture API; diffy w `TASK-1012_CORRECTION_DIFFS/` zgadzają się z aktualną treścią plików. P1-1 jest zamknięte: test workera importuje tylko pakiety z oficjalnego `pythonpath` i sąsiedni moduł testowy workera, a receipt samodzielnego procesu potwierdza 1 PASS. Wszystkie cztery P2 są zamknięte. Jedyne nowe ryzyko to istniejący wcześniej błąd launchera `run_python_tests.ps1` dla pojedynczej suite, który leży poza diffem taska i nie blokuje commita.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-5] `scripts/run_python_tests.ps1:14-18` i `scripts/run_python_tests.ps1:25` — dla `-Suite Api` lub `-Suite Worker` `switch` zwraca jednoelementową tablicę, którą PowerShell rozwija do skalara; splatting `@testPaths` na polecenie natywne iteruje wtedy po znakach napisu, więc pytest dostaje argumenty `s`, `e`, `r`, … (log `artifacts/audits/TASK-1012_CORRECTION_worker_suite.log:7-12`: `rootdir: D:\`, `file or directory not found: s`). Skutek: udokumentowana w `CLAUDE.md` ścieżka `npm run python:test -- -Suite Worker` nie zbiera żadnego testu; wariant `All` działa, bo tablica ma dwa elementy. Błąd istniał przed TASK-1012 i nie jest częścią jego diffu, dlatego nie blokuje tego taska. Proponowana poprawka w osobnym tasku: wymusić tablicę, np. `[string[]]$testPaths = ...` lub `@(,'services/worker/tests')`, i uruchomić obie pojedyncze suite. Alternatywnie lead akceptuje ryzyko i odnotowuje je w `CURRENT_STATE.md`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Trzecia rodzina działa (snapshot v2, roundtrip, nowy proces, resolver dla trzech formatów) | spełnione | bez zmian źródeł od rundy 1: `domain/grid_model_snapshots.py:27-70`, `storage/grid_profile_snapshot_resolver.py:47-104`; `services/api/tests/test_dynamic_grid_snapshots.py:789-827` (brief), worker `services/worker/tests/test_dynamic_grid_snapshot_replay.py:58-71`; receipt `TASK-1012_CORRECTION_api_final.log:2` (28 passed) |
| Stary job wznawia się po zmianie aktywacji (replay i start/reuse zachowują pin) | spełnione | `application/jobs.py:2131-2172`, `:2200-2235`; `test_dynamic_grid_snapshot_replay.py:79-127` (`resolve_neural_grid_proposal.assert_not_called`, `unused.calls == 0`); receipt `TASK-1012_CORRECTION_worker_standalone.log:2` (1 passed) |
| Stary preflight nie uruchamia innej wersji | spełnione | `application/jobs.py:2168-2172`, `storage/grid_profile_snapshot_resolver.py:135-139`; `test_dynamic_grid_snapshots.py:251-258` |
| Brak lub zmiana hashy nie powoduje fallbacku | spełnione | `storage/grid_engine_model_store.py:155-182`, `:223-240`; `test_dynamic_grid_snapshot_replay.py:128-140` (usunięty `board.onnx` → `GridEngineModelError` w replay i w starcie importu) |
| Gra kod 7 z błędną konfiguracją V3 pozostaje klasyczna bez odczytu assignment (P2-4) | spełnione | `storage/grid_profile_snapshot_resolver.py:114-125`; `application/jobs.py:2117-2119`, `:2193-2195`; `test_dynamic_grid_snapshots.py:292-326` (`assignment`/`version` `assert_not_called`) |
| Kontrakt API: dyskryminowana unia v1/v2 w GET istniejącego joba | spełnione | `schemas/neural_grid_proposals.py:52-70`; `test_dynamic_grid_snapshots.py:202-248` (parametr `legacy`/`catalogue`, `TypeAdapter(NeuralGridSnapshotContract)`) |
| Test workera zbiera się samodzielnie na oficjalnym `pythonpath` (P1-1) | spełnione | `pyproject.toml:41`; `test_dynamic_grid_snapshot_replay.py:12-20` (tylko `game_predictor_api.*`, `game_predictor_worker.*` i sąsiedni `test_neural_page_geometry_preflight`, wzorzec istniejący w 40+ testach workera); `TASK-1012_CORRECTION_worker_standalone.json:2-13` (PYTHONPATH bez katalogu testów API, exit 0) |
| Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu | spełnione | `ai_docs/tasks/1012-dynamic-grid-snapshots.md:300-313` (wynik rundy poprawek, ograniczenia launchera i pełnej suite opisane jawnie); `DECISION_LOG_2026.md:60`, `DECISION_LOG.md:41`; `API_CONTRACT.md:4`, `IMAGE_INGESTION.md:4`; `CURRENT_STATE.md:189-195`. Zapis wyniku rundy 2 należy do leada po tym raporcie. |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później):

- P1-1 — `services/worker/tests/test_dynamic_grid_snapshot_replay.py:12-20` nie importuje już `test_grid_model_registry` ani `test_jobs_domain`; lokalna fabryka `inference_candidate` (`:23-55`) buduje descriptor z `historical_catalogue()[0]` i spełnia `validate_manifest` (`domain/grid_model_registry.py:130-163`: cztery pliki inference, trainingArtifacts z zachowanym `checkpoint.pt`/`weights.pt` i podmienionymi `bundle.json`/`preset.json`, manifest.json zgodny z `grid_engine_manifest`, `grid_engine_profiles.py:312-313`). Wąski mock `get_job` (`:90-93`) wystarcza, bo `_neural_import_snapshot` odczytuje repozytorium wyłącznie przez `JobService.get_job` (`jobs.py:1723-1731`, `:2201`), a `_neural_preflight_snapshot` i konstruktor (`jobs.py:399-425`) repozytorium nie dotykają. Receipt: `TASK-1012_CORRECTION_worker_standalone.log:2` „1 passed”, `…_standalone.json:12` PYTHONPATH tylko `services/api/src;services/worker/src;services/test_support`. Dodatkowo bezpośrednie `pytest services/worker/tests` ukończyło kolekcję i wykonało testy do ok. 50 % przed limitem 120 s (`TASK-1012_CORRECTION_SCOPE.json:240-251`), co potwierdza brak błędu zbierania w całym katalogu.
- P2-1 — `CURRENT_STATE.md:189-195`: pozostała jedna sekcja `### TASK-1012`; starszy stub `##` usunięty (`TASK-1012_CORRECTION_DIFFS/ai_docs__process__CURRENT_STATE.md.patch:16-19`); sekcje innych tasków nienaruszone.
- P2-2 — `API_CONTRACT.md:4` i `IMAGE_INGESTION.md:4` mają `last_updated: 2026-10-15`; patche zawierają wyłącznie tę zmianę.
- P2-3 — lead doprecyzował Consequences D-549 w pełnym wpisie (`decisions/DECISION_LOG_2026.md:60`), kopii (`DECISION_LOG.md:280`) i indeksie (`DECISION_LOG.md:41`): assignment zastępuje statyczny `current` dla nowych preflightów wszystkich formatów V3, D-544 zachowuje znaczenie dla snapshotów v1. Wykonawca nie edytował Decision Log (plik poza `correctionFiles` w `TASK-1012_CORRECTION_SCOPE.json:43-50`). Bez nowej decyzji produktowej, zgodnie z briefem leada.
- P2-4 — `test_dynamic_grid_snapshots.py:292-326`: trzy konfiguracje V3 dla kodu 7 dają `neural_grid_profile is None`, `uses_neural_grid_pilot` False, oba snapshoty `None`, `assignment`/`version` nie wywołane. Zachowanie produktu bez zmian (`runtimeProductionFilesChangedInCorrection: []`).

Otwarte: P2-5.

## Proponowane testy

- Po naprawie launchera (P2-5, osobny task): `npm run python:test -- -Suite Worker` i `npm run python:test -- -Suite Api` z limitem 120 s każdy; do czasu naprawy pełną suite workera uruchamiać w porcjach, np. `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_dynamic_grid_snapshot_replay.py services/worker/tests/test_neural_page_geometry_preflight.py services/worker/tests/test_neural_folder_correction_pipeline.py`, aby otrzymać końcowy wynik zamiast timeoutu.
- `services/worker/tests/test_dynamic_grid_snapshot_replay.py`: wariant z podmienioną treścią `board.onnx` (ta sama nazwa, inny SHA) obok istniejącego `unlink`, aby objąć gałąź `CHECKSUM_MISMATCH` (`grid_engine_model_store.py:196-198`) także po stronie workera; dziś drift hashu testuje tylko API.

## Zakres przeglądu i ograniczenia

Przeczytano w całości: brief, raport rundy 1, `TASK-1012_CORRECTION_SCOPE.json`, sześć patchy korekty, aktualny `services/worker/tests/test_dynamic_grid_snapshot_replay.py`, fragmenty `services/api/tests/test_dynamic_grid_snapshots.py:195-344`, `storage/grid_profile_snapshot_resolver.py`, `domain/grid_model_snapshots.py`, `domain/grid_model_registry.py:27-293`, `storage/grid_engine_model_store.py:150-240`, `application/jobs.py:399-425`, `:1723-1731`, `:2107-2347`, `domain/image_sequence_canonical.py:101-136`, `storage/image_sequence_canonical_repository.py`, `schemas/neural_grid_proposals.py:40-70`, `scripts/run_python_tests.ps1`, `pyproject.toml:39-42`, sekcje TASK-1012 w `CURRENT_STATE.md`, D-549/D-544 w obu logach decyzji oraz logi/receipty `TASK-1012_CORRECTION_*`. Grepem potwierdzono, że import sąsiednich modułów testowych bez `conftest.py` jest ustalonym wzorcem w `services/worker/tests`. Nie uruchamiano testów, Ruff, mypy ani skryptów; wyniki 1 PASS standalone i 28 PASS API przyjęto z logów wykonawcy. Nie przeliczano SHA-256 plików z `CORRECTION_SCOPE.json` (brak narzędzia do uruchamiania poleceń w tej sesji); zgodność patchy z plikami sprawdzono przez odczyt treści. Pełnej suite workera nie da się ocenić statycznie: bezpośrednie uruchomienie przerwano po 120 s bez końcowego wyniku, a udokumentowany launcher nie działa dla pojedynczej suite (P2-5). Nie badano korekty ORM TASK-0994 ani stanu bazy operatora; nie weryfikowano zmian spoza zakresu rundy 1.
