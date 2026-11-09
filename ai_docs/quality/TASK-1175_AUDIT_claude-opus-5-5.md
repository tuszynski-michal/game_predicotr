# Audyt TASK-1175 — Pełne pola symboli bez marginesu 8%

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...1181797cbad2bdd62fda9ff249ee60ce8d1123b7 oraz zmiany niezacommitowane, data 2026-11-09
Runda: 2
SHA pakietu: db6034a137b87f8aca30883777c2267c3c1e8bfc12988caff007f50eacd01648
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Runda 2 sprawdziła zamknięcie P0-1, status obu znalezisk P2 oraz to, czy nowe pole nie psuje innych konsumentów snapshotu. Błąd P0-1 jest usunięty: wspólny schemat payloadu joba przyjmuje zamknięty token, a historyczne odpowiedzi nie dostają pola `null`. Pion OpenAPI, SDK, wrapper i test jest domknięty. Nie znaleziono nowych błędów P0, P1 ani P2. Główne pozostałe ryzyko to świadomie przyjęty fallback P2-2 dla historycznych jobów bez pinu klasyfikatora.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-2] `services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py:2804` — job bez `symbol_model` nadal przyjmuje konfigurację z pierwszego bieżącego manifestu źródła lub importu, więc po ręcznym zapisie 0% w sąsiednim slocie wywołanie bez tokenu może odziedziczyć 0%. Zachowanie nie zmieniło się, ale jest jawnie opisane w `Outcome`, w `ai_docs/quality/TASK-1175_VERIFICATION.md` i w `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`. Dotyczy wyłącznie danych bez pinu klasyfikatora, a Reviewer przy ofercie serwera wysyła jawny token. Propozycja: pozostawić jako zaakceptowane ryzyko kompatybilności.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Kryteria sekcji T2 planu i regresje dotychczasowych konsumentów | spełnione | `services/api/src/game_predictor_api/schemas/jobs.py:74`–`81`; `services/api/src/game_predictor_api/domain/grid_render_reference.py:44`–`50`; `services/api/src/game_predictor_api/storage/grid_content_oracle_context.py:90`–`95`; `services/worker/src/game_predictor_worker/images/production_workflow.py:2016` |
| Spójny kontrakt API/OpenAPI/SDK/wrapper/test | spełnione | `services/api/src/game_predictor_api/schemas/jobs.py:74`; `packages/admin-api-client/openapi/openapi.json:48342` (pole w tym schemacie według diffu pakietu); `packages/admin-api-client/test/client.test.mjs:4633`; `services/api/tests/test_jobs_api.py:848` |
| Testy, lint, typy, build, dokumentacja, mapa i niezależny audyt Opus z receipt | niezweryfikowane | Audytor nie uruchamiał kontroli. Logi wykonawcy: `artifacts/t1175-fix-red.log:478`–`482`, `artifacts/t1175-fix-import.log:13` (4 passed, 50 deselected), `artifacts/t1175-fix-jobs.log:61`–`62` (36 passed, 1 failed). Ten sam test nie przechodzi w `artifacts/t1175-fix-jobsbaseline.log:25`. Receipt rundy 2 powstaje po tym raporcie. |
| Outcome, task-close, osobny commit i hash w kolejnym commicie | niezweryfikowane | `Outcome` jest uzupełniony w `ai_docs/tasks/1175-full-cell-render-policy.md`; commit i task-close należą do etapu po audycie |
| Historyczny brak pola zachowuje payload, fingerprint i 8% | spełnione | `services/api/src/game_predictor_api/domain/symbol_model_snapshots.py:80`–`85`, `:109`, `:129`; `services/api/tests/test_full_cell_crop_policy.py:30`–`47` |
| Preview, symbole i zapis używają tego samego 0%, bez surowego paddingu z klienta | spełnione | `services/api/src/game_predictor_api/application/virtual_grid_geometry.py:1102`, `:1515`, `:1686`–`1707`; `services/api/tests/test_full_cell_crop_policy.py:88`–`138` |
| Zmiana tokenu daje konflikt; CAS i idempotencja zachowane | spełnione | `services/api/src/game_predictor_api/application/virtual_grid_geometry.py:989`–`1014`; `services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py:3443`–`3455`; `services/api/tests/integration/test_full_cell_correction_postgres.py:205`–`222` |
| Transport Reviewera, w tym przyjęcie modelowe i edytowane | spełnione | `apps/reviewer/src/features/operational-reviews/grid-geometry-proposals.tsx:196`, `:226`, `:306`–`325`; `apps/reviewer/src/features/operational-reviews/board-geometry-correction-target.ts:208`–`217`, `:260`–`265`, `:712`; `services/api/src/game_predictor_api/storage/grid_geometry_proposals.py:423` |
| Pending nie pożycza konfiguracji innego slotu przy poprawnym pinie; niekompletny pin klasyfikatora zachowuje jego padding | spełnione | `services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py:2768`–`2771`, `:2815`, `:2833`–`2840`; `services/api/tests/test_full_cell_crop_policy.py:166`–`230` |
| Zmiana pikseli unieważnia stary symbol, a dowód 8% nie kwalifikuje 0% | spełnione | `services/api/tests/integration/test_full_cell_correction_postgres.py:248`–`255`; `services/worker/src/game_predictor_worker/images/production_crop_classification.py:103`; `services/worker/src/game_predictor_worker/images/pipeline_contract.py:699` (`autoAcceptEnabled=False`) |

## Listy zamknięte i otwarte

Zamknięte: P0-1, P2-1.

Dowód zamknięcia P0-1: `SymbolModelJobSnapshotPayload` ma pole `crop_policy_version` z zamkniętym literałem i `exclude_if` (`services/api/src/game_predictor_api/schemas/jobs.py:74`–`81`). Wszystkie wystąpienia `symbol_model` w schemacie jobów używają tej jednej klasy (`jobs.py:323`, `:383`, `:415`, `:440`, `:457`, `:481`, `:676`). Przeszukanie kodu nie wykazało równoległego schematu snapshotu. Regresja obejmuje POST, replay, GET i listę dla wariantów legacy/full oraz bootstrap/LAB (`services/api/tests/test_image_imports_api.py:741`, `:1105`), a dla ponownej inferencji GET i listę (`services/api/tests/test_jobs_api.py:848`–`871`). Log wykonawcy potwierdza wcześniejszy błąd `extra_forbidden` (`artifacts/t1175-fix-red.log:478`).

Dowód zamknięcia P2-1: wybrano wariant jawnego opisu z rundy 1. Opis pola stwierdza, że pin nie przelicza historycznych pikseli (`services/api/src/game_predictor_api/schemas/jobs.py:77`–`80`), a tę samą granicę podaje `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`. Handler renderuje wycinki z zapisanego `render_spec`, weryfikując jego sumy kontrolne (`services/worker/src/game_predictor_worker/images/pending_symbol_reinference.py:100`–`112`).

Otwarte: P2-2.

## Proponowane testy

- Pełne przejście `services/api/tests/test_image_imports_api.py` w kontrolowanym limicie czasu lub w podzielonych partiach, ponieważ po poprawce wykonano 4 z 54 przypadków. Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_imports_api.py`.
- Reviewer: w `apps/reviewer/test-interactions/board-geometry-correction.test.mjs` dodać przypadki celu operacyjnego oraz przyjęcia propozycji w trybie `edited`, sprawdzające zgodność `cropPolicyVersion` w poleceniu i w `geometry`. Komenda: `npm run test:geometry --workspace @game-predictor/reviewer`.

## Zakres przeglądu i ograniczenia

Przeczytano zamrożony pakiet, `AGENTS.md` oraz fragmenty modułów objętych zmianą: schemat jobów, snapshot domenowy, serwis i repozytorium geometrii wirtualnej, przyjmowanie propozycji, cele korekty Reviewera, ponowną inferencję symboli, worker produkcyjny oraz konsumentów kontraktu renderu. Przeszukano także `services` pod kątem wartości paddingu, odcisków inferencji i użyć resolvera.

Nie uruchamiano testów, lintu, mypy, builda, usług ani bazy. Wyniki pochodzą z deklaracji wykonawcy i odczytu jego lokalnych logów, więc nie stanowią wykonania przez audytora. Nie potwierdzono samodzielnie, że błąd mypy jest zastany. Pełna próba plików import i jobs nie ma wyniku PASS: po poprawce wykonano wybrane przypadki importu, a cały plik jobs ma jeden test niezaliczony, ten sam co w osobnym przebiegu na bazie. Bieżące działanie HTTP po poprawce wynika z analizy kodu i logów wykonawcy. Nie oceniano jakości klasyfikacji na danych operatora.