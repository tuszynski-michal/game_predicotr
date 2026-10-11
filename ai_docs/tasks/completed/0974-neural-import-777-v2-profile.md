# TASK-0974 — Import V3 (`neural_grid`) dla profilu `grid_profile_777_v2`

## Status

`done`

## Goal

Gra z formatem strony `grid_profile_777_v2` (pierwsza: `777a2`, „777 a2”) importuje folder zdjęć tą samą ścieżką V3 co Mumie, z własnym zarejestrowanym modelem profilu 777 v2; stara gra 777 (kod `7`) zostaje na V1.1 bez zmian.

## Context

Operator 2026-10-11: V1.1 zostaje w panelu importu wyłącznie dla starej gry 777. Nowa gra 777 a2 ma przejść przez silnik V3, który nie myli się w rysowaniu siatek, z modelem 777 v2 wytrenowanym w laboratorium (run `43933ac8…`, preset A, eksport `2cd19738367121e6-round3`, snapshot `286f2e37…`). Model jest zarejestrowany w `domain/grid_engine_profiles.py` i zainstalowany (`artifacts/models/grid-engine/grid_profile_777_v2/v1`, status `available`). Ścieżka importu V3 powstała jako pilot Mumii (D-521) i jest przypięta do `grid_profile_mumie_v1`, więc dla profilu 777 v2 Admin pokazuje V1.1. Decyzja: D-544.

## Dependencies / entry conditions

- Fakty: rejestr profili (TASK-0830, migracja `0140`) dopuszcza oba profile w `games.shape_geometry_configuration`; model 777 v2 przechodzi kontrolę SHA-256 w magazynie modeli.
- Gra `777a2` (`6e20a58f-88f3-4a9c-87b5-ae3297ed4fbf`) ma `grid_profile_777_v2`, aktywny storage, 8 symboli i szkic reguł 3 × 5, zero jobów.
- Bez migracji schematu (sprawdzić podczas implementacji).

## Recommended execution

`claude-opus-5-5`, reasoning `high`: zmiana kontraktu między API, workerem i Adminem w ścieżce importu z bramkami kompletności; wymaga ostrożności przy zachowaniu istniejących jobów Mumii. Audyt krzyżowy wstrzymany decyzją operatora (2026-10-01). Eskalacja: potrzeba migracji albo zmiany zamrożonego identyfikatora polityki preflightu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-521, D-544)
- `ai_docs/guides/MUMIE_MAIN_APP_OPERATOR_GUIDE_20261006.md`
- `ai_docs/guides/VISION_LAB_LOCAL.md` (sekcja „Sieć `neural_grid`”)

## Scope

- Jeden zbiór profili importu neuronowego (`grid_profile_777_v2`, `grid_profile_mumie_v1`); każda gra używa modelu własnego profilu.
- API: resolver snapshotu, `uses_neural_grid_pilot` (resolver i repozytorium kanoniczne), `NeuralGridSnapshot` (walidacja i odczyt payloadu po profilu z payloadu), schemat `NeuralGridModelManifestPayload.profile`, zgodność profilu zamrożonego preflightu z profilem gry.
- Worker: wybór modelu z zamrożonego snapshotu joba (bez stałego profilu Mumii).
- Admin: wybór V3 i etykiety według profilu gry; walidacja snapshotu joba dla obu profili.
- OpenAPI i wygenerowany klient.
- Testy jednostkowe dla profilu 777 v2 oraz regresja Mumii.

## Out of scope

- Trening lub zmiana modeli sieci; nowe wersje rejestru.
- Gra 777 (kod `7`, `requires_clarification`) i jej import V1.1.
- Zmiana identyfikatora polityki `page-geometry-preflight-v13-neural-mumie-pilot` (utrwalony w jobach Mumii; nazwa historyczna).
- Rejestr symboli i bramki modelu symboli związane z `MUMIE_GAME_ID`.
- Wdrożenie: scalenie, restart Admina i workera wykonuje operator za zgodą.

## Acceptance criteria

- [x] Gra z `grid_profile_777_v2` dostaje w preflighcie snapshot modelu 777 v2 (run `43933ac8…`), a gra Mumie nadal model Mumii.
- [x] Panel importu dla profilu 777 v2 pokazuje V3 z etykietą profilu, bez wyboru V1.1; dla gier bez profilu sieci nic się nie zmienia.
- [x] Zamrożony snapshot innego profilu niż profil gry nie jest użyty ani przy ponownym preflighcie, ani przy starcie importu.
- [x] Istniejące joby i payloady Mumii pozostają ważne (ten sam identyfikator polityki i kształt snapshotu).
- [x] OpenAPI i klient zregenerowane; `openapi:check`, testy API/worker/Admin zielone dla zmienionych obszarów.

## Technical notes

Przed: `uses_neural_grid_pilot` (resolver snapshotu i repozytorium kanoniczne), `resolve_neural_grid_proposal`, `NeuralGridSnapshot.__post_init__`/`from_payload`, Literal schematu i Admin (`usesNeuralGrid`, `neuralImportSnapshot`) porównywały profil z `grid_profile_mumie_v1`. Po: jedna funkcja `neural_import_profile(configuration)` zwraca zarejestrowany profil gry albo `None`; snapshot odczytuje profil z zamrożonego manifestu i porównuje go dokładnie z wersjami tego profilu (dryf → `NEURAL_GRID_MODEL_SNAPSHOT_DRIFT`).

Worker nie ma własnej bramki profilu: `neural_page_geometry_preflight` i import czytają model z `NeuralGridSnapshot.from_payload` joba, a `ManagedGridEngineModelStore.require` rozwiązuje katalog `<profile>/<version>`. Ścieżka cropów i weryfikacji symboli (`neural-auto-crop-v1`, silnik `neural_grid_v1`) nie zależy od profilu. Kod przypięty do `MUMIE_GAME_ID` dotyczy rejestru modeli symboli i zostaje.

Nowa reguła spójności: `_neural_profile_matches_game` porównuje profil zamrożonego snapshotu z bieżącym profilem gry. Ponowny preflight pomija kandydata innego profilu, a start importu zwraca `NEURAL_GRID_PREFLIGHT_INVALID`. Identyfikator polityki preflightu pozostaje bez zmian, bo przypinają go zakończone joby Mumii.

## Expected files

- `services/api/src/game_predictor_api/domain/grid_engine_profiles.py`
- `services/api/src/game_predictor_api/domain/neural_grid_proposal.py`
- `services/api/src/game_predictor_api/schemas/neural_grid_proposals.py`
- `services/api/src/game_predictor_api/storage/grid_profile_snapshot_resolver.py`
- `services/api/src/game_predictor_api/storage/image_sequence_canonical_repository.py`
- `services/api/src/game_predictor_api/application/jobs.py`
- `apps/admin/src/features/imports/image-folder-import-panel.tsx`
- `apps/admin/src/features/imports/neural-import-preflight-state.ts`
- `packages/admin-api-client` (generowane)

## Test cases

- Resolver: gra 777 v2 → snapshot z `profile = grid_profile_777_v2`; gra Mumie → Mumie; `requires_clarification` → `None`.
- `NeuralGridSnapshot.from_payload`: manifest 777 v2 i Mumii przyjęte; manifest zmieniony → `NEURAL_GRID_MODEL_SNAPSHOT_DRIFT`; profil spoza zbioru → błąd.
- Preflight gry 777 v2 z kandydatem zamrożonym dla innego profilu → kandydat pominięty; start importu → `NEURAL_GRID_PREFLIGHT_INVALID`.
- Admin: profil 777 v2 → V3; profil `requires_clarification` → V1.1.

## Verification

```powershell
# z katalogu worktree, PYTHONPATH na services/api/src i services/worker/src worktree
D:\game_predicotr\.venv\Scripts\python.exe -m pytest <testy zmienionych obszarów> -q
npm run openapi:check
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
```

## Risks / open questions

- Model 777 v2 nie był używany w produkcyjnej ścieżce importu; jakość mierzono w V3-C (development 777: 554/600 zdjęć pełnych i poprawnych).

## Outcome

### Changed

- `domain/grid_engine_profiles.py`: `neural_import_profile`.
- `domain/neural_grid_proposal.py`: `NeuralGridSnapshot` przyjmuje każdy zarejestrowany profil (właściwość `profile`), `from_payload` wybiera wersje po profilu z payloadu.
- `storage/grid_profile_snapshot_resolver.py`: snapshot z modelu profilu gry, nowe `neural_grid_profile`; `storage/image_sequence_canonical_repository.py`: bramka według profilu.
- `application/jobs.py`: `_neural_profile_matches_game` przy ponownym użyciu preflightu i starcie importu; komunikaty bez nazwy Mumii (także `api/image_imports.py`, `domain/image_sequence_canonical.py`).
- `schemas/neural_grid_proposals.py`: `profile` przyjmuje `grid_profile_777_v2` i `grid_profile_mumie_v1`; OpenAPI i `types.gen.ts` zregenerowane.
- Admin: `image-folder-import-panel.tsx` (V3 dla każdego profilu, etykieta „V3 — sieć neuronowa (777 v2)”, opis V1.1), `neural-import-preflight-state.ts` (oba profile).
- Testy: `test_neural_grid_proposal.py` (odwrócony test 777, round-trip obu profili, dryf i profil spoza rejestru), `test_grid_profile_snapshot_resolver.py`, `test_neural_page_geometry_api.py`, Admin `neural-import-preflight.test.mjs`, `image-folder-import-panel-contract.test.mjs`, `neural-import-readiness.test.mjs`.
- Mapa kodu zregenerowana (zawiera też zaległy wpis TASK-0973 w `game_partition_lifecycle.py`).

### Verification results

- pytest: neural API/proposal/resolver/managed/crop/profile 85 passed; worker `test_neural_page_geometry_preflight.py` + `test_image_sequence_canonical.py` + `test_catalog_api.py` 38 passed; resolver 3 passed; pełny zestaw `services/api/tests`: 2423 passed, 373 skipped i 268 failed/12 errors wyłącznie przez zbyt długą ścieżkę `--basetemp` (limit ścieżki Windows); te same 268+12 przy krótkiej ścieżce `D:/ptw`: 268 passed. Na bazie v1.7.313 ta sama długa ścieżka daje 273 failed (nadzbiór).
- ruff check i format czyste; mypy --strict czyste dla 8 zmienionych modułów.
- `export_admin_openapi.py --check` i `check:generated`: aktualne.
- Admin: `npm run test` 731/731, `neural-import-readiness` 16/16, typecheck OK, lint bez błędów (wyłącznie wcześniejsze ostrzeżenia).
- Przebieg dymny (tylko odczyt, CPU, ten sam `CPUGridProposalRunner` co worker, modele z `D:\game_predicotr\artifacts`): 12 złotych zdjęć 777 ze snapshotu `286f2e37…`; `grid_profile_777_v2` 108/108 plansz z dopasowaną siatką w 5,2 s, `grid_profile_mumie_v1` 108/108 w 5,8 s.
- Worker, selekcja `-k "neural or production_workflow or source_ingestion or page_geometry"`: 46 failed / 97 passed, identyczna lista FAILED na niezmienionym v1.7.313 (awarie środowiskowe `test_page_geometry_preflight.py` i testów vision-lab, poza zakresem).

### Audit

- Codex `gpt-6.1-sol` (na prośbę operatora, jedna runda): [TASK-0974_AUDIT_gpt-6.1-sol.md](../../quality/TASK-0974_AUDIT_gpt-6.1-sol.md), `Werdykt: REVISE`, P0 brak, P2 brak.
- P1-1 (brak testów miejsc wywołania kontroli profilu) naprawione: `test_repeated_preflight_reuses_a_frozen_snapshot_only_for_the_same_profile` (oba profile) i `test_import_start_rejects_a_preflight_frozen_for_another_profile` (bez joba importu). Kontrola mutacyjna: wyłączenie obu kontroli w `jobs.py` daje 2 failed. Zachowanie produkcyjne bez zmian, więc bez drugiej rundy.
- Commit v1.7.314 (`4344510b`), scalony fast-forward do `v1.1-vision-lab-hybrid-geometry` i wypchnięty. Na gałęzi integracyjnej: 126 testów neural API/worker, Admin 731 + 16, OpenAPI, klient i docs aktualne; działające API serwuje nowy kontrakt, Admin pokazuje „V3 — sieć neuronowa (777 v2)” dla `777a2`.
- Audyt E2E gotowości importu nowej 777 (na prośbę operatora, do 3 rund): runda 1 [TASK-0974_E2E_AUDIT_gpt-6.1-sol_round1.md](../../quality/TASK-0974_E2E_AUDIT_gpt-6.1-sol_round1.md), `Werdykt: PASS`, P0/P1 brak. P2-1 (przycisk „Rozpocznij import Mumii” także dla 777 v2) naprawione w v1.7.315: „Rozpocznij import V3” albo „Rozpocznij pierwszy import V3 bez modelu”; przewodnik Mumii zaktualizowany. Warunek bootstrapu sprawdzony: globalny bootstrap ma klasy `cherries`, `grapes`…, a `777a2` ma `WISNIA`, `WINOGRON`…, więc pierwszy import idzie w cold start (`?`).
- Runda 2 E2E: [TASK-0974_E2E_AUDIT_gpt-6.1-sol_round2.md](../../quality/TASK-0974_E2E_AUDIT_gpt-6.1-sol_round2.md), `Werdykt: PASS`, P2-1 zamknięte, brak nowych znalezisk; trzecia runda niepotrzebna. Commit poprawki v1.7.315 (`55af1b63`). Sugestia Codexa (bez znaleziska): jeden scenariusz testowy łączący profil 777 v2, pełny katalog 8 symboli, kliknięcie startu i materializację komórek `?`.

### Not completed

- Testy integracyjne PostgreSQL ścieżki neural nie były uruchamiane (osobna baza `*_test`, czas).
- Odbiór na żywym imporcie `777a2` wymaga wdrożenia (scalenie, restart workera `general` przez operatora) i folderu zdjęć operatora.

### Documentation updates

- D-544 (`DECISION_LOG.md`, `decisions/DECISION_LOG_2026.md`), `requirements/IMAGE_INGESTION.md`, `requirements/ADMIN_APP.md`, `architecture/API_CONTRACT.md`, `CURRENT_STATE.md`.

### Recommended next task

- Pierwszy import `777a2` przez V3 (partia ok. 500 zdjęć) i ocena propozycji sieci w Reviewerze.
