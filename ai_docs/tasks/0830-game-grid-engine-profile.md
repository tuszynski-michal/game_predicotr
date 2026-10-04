---
title: TASK-0830 — profil silnika siatek gry w polu „Format strony” (777 v2, Mumie)
status: done
last_updated: 2026-10-04
---

# TASK-0830 — profil silnika siatek gry w polu „Format strony”

## Status

`done` (commit, `CURRENT_STATE.md` i przeniesienie pliku wykonuje orkiestrator)

## Goal

Przy tworzeniu i edycji gry operator wybiera w polu „Format strony” profil
silnika siatek „777 v2” albo „Mumie”; wybór jest trwale zapisany w grze i
wskazuje zamrożony, sprawdzony sumą kontrolną model `neural_grid` w
zarządzanym katalogu modeli, gotowy do użycia przez tryb shadow (TASK-0805).

## Context

Polecenie operatora 2026-10-04: po doszkoleniu na Mumiach chce przy
zakładaniu nowej gry wskazać, dla której gry silnik jest dostosowany — gry
„Mumie” i „777 v2” (dla 777 v2 nie ma jeszcze materiału, pojawi się
później; kolejne wersje, np. „777 v3”, mają móc użyć zapisanego profilu
777 v2). Dziś pole „Format strony” (`games.shape_geometry_configuration`)
ma wartości `framed_full_page_v2` („Pełna strona z ramką”) i
`requires_clarification`, związane z przygotowaniem preflightu (gotowość
`ShapeGeometryReadinessStatus`). Jedyna gra w katalogu to 777
(`requires_clarification`).

Modele (raport `ai_docs/quality/GRID_V3_COMPARISON_REPORT_20261004.md`):

| Profil | Model | Uzasadnienie |
|---|---|---|
| 777 v2 | run 1, preset A, eksport `neural-grid-runs\43933ac8d7d443c8b9079630a83de2e6\exports\2cd19738367121e6-round3` | wybrany na development przed odczytem holdoutów; pod niego skalibrowano bramkę `hybrid_v3` |
| Mumie | doszkolenie run 3, iteracja 3, eksport `neural-grid-runs\5bc981568c3f42bd96f6f9238e57aedc\exports\iteration03-f896da7196431be2` | 79% propozycji przyjętych bez zmian w ostatniej porcji; holdout Mumii 36/36 |

## Dependencies / entry conditions

- Head Alembic `0139` na gałęzi integracyjnej; nowa migracja `0140`
  (sprawdź przed commitem, czy inny tor nie zajął numeru).
- Inne okno pracuje równolegle na gałęzi integracyjnej (numery zadań 0825
  i 0826–0829 zajęte) — przed zmianami w Adminie sprawdź aktualny stan
  plików katalogu gier.

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Zmiana katalogu gier (migracja,
kontrakt API, Admin) i wprowadzenie zarządzanego rejestru modeli
produkcyjnych. Audyt zawieszony decyzją operatora (2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/ADMIN_APP.md` (katalog gier), `ai_docs/architecture/API_CONTRACT.md`,
  `ai_docs/architecture/DATA_MODEL.md`, `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`
- `ai_docs/process/DECISION_LOG.md` (D-447, D-461, D-490 i wpisy o
  `shape_geometry_configuration` — znajdź przez grep)
- `ai_docs/quality/GRID_V3_COMPARISON_REPORT_20261004.md`

## Scope

1. **Wartości pola** `shape_geometry_configuration` (enum domeny, schemat,
   migracja CHECK, OpenAPI, klient, Admin): dodać `grid_profile_777_v2`
   („777 v2”) i `grid_profile_mumie_v1` („Mumie”); istniejące wartości
   zostają bez zmian. Gotowość (`ShapeGeometryReadinessStatus`) dla nowych
   wartości: ustal z kodu znaczenie stanów i przypisz zachowanie
   równoważne `framed_full_page_v2` dla preflightu (nowe gry startują z
   ręczną weryfikacją pierwszego importu); jeżeli nowe wartości wymagałyby
   zmiany działania preflightu albo pipeline'u, zatrzymaj się i opisz.
2. **Rejestr modeli** (proponowane `services/api/.../grid_engine_profiles.py`
   i katalog `<ARTIFACT_ROOT>/models/grid-engine/<profil>/<wersja>/`):
   skrypt jednorazowo kopiuje wskazane eksporty ONNX (`screen.onnx`,
   `board.onnx`, `bundle.json`, preset) do zarządzanego katalogu z
   kontrolą SHA-256 i manifestem (profil, wersja, run, preset, fingerprint,
   wyniki z raportu V3-C, data); rejestr w kodzie mapuje profil → wersja →
   SHA. Brak pliku albo niezgodny SHA = jawny błąd, bez cichego fallbacku.
   Bez nowej tabeli bazy (wybór profilu jest w `games`, model w plikach).
3. **Admin:** etykiety w polu „Format strony” i krótki opis pod polem
   (który model, że profil 777 v2 służy też przyszłym wersjom 777);
   widoczność profilu w liście gier.
4. **Endpoint tylko do odczytu** z listą profili i stanem ich modeli
   (dostępny / brak / niezgodny SHA) dla Admina.
5. Dokumentacja: `ADMIN_APP.md`, `API_CONTRACT.md`, `DATA_MODEL.md`,
   wpis w przewodniku operatora o profilach.

## Out of scope

- Uruchamianie sieci w pipeline importu i tryb shadow (TASK-0805).
- Zmiana „Formatu strony” gry 777 (operator decyduje sam w Adminie).
- Tworzenie gier „Mumie” i „777 v2” — robi to operator.
- Trening, przekalibrowanie bramki.

## Acceptance criteria

- [x] Operator może utworzyć grę z formatem „777 v2” albo „Mumie”;
      wartość zapisuje się i wraca w API i Adminie; stare wartości działają
      jak dotąd (test regresji).
- [x] Migracja `0140` z `downgrade` (odmowa, gdy istnieje gra z nową
      wartością) przechodzi test cyklu na bazie `*_test`.
- [x] Modele obu profili są w zarządzanym katalogu z manifestem; test
      wykrywa brak i zmianę pliku.
- [x] Endpoint profili zwraca stan modeli; Admin pokazuje stan przy polu.
- [x] Kontrakt pionem (OpenAPI, klient, wrapper, test żądania).
- [x] Brak zapisu do bazy deweloperskiej przez wykonawcę; migrację na bazie
      deweloperskiej wykonuje orkiestrator.
- [ ] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

## Technical notes

- Nazwy wartości są stabilne i niezależne od etykiet; etykiety po polsku w
  Adminie. Kolejna wersja modelu tej samej gry = nowa wersja w rejestrze
  profilu, nie nowa wartość pola.
- Katalog modeli w `ARTIFACT_ROOT` (konfiguracja API), nie w danych labu i
  nie w repo (pliki ONNX ~25 MB); rejestr w repo zawiera tylko SHA i
  metadane.

## Expected files

- Istniejące: `domain/catalog.py`, `schemas/catalog.py`,
  `application/catalog.py`, `storage/models.py`, Admin
  `features/games/game-catalog*.tsx|ts`, `packages/admin-api-client`.
- Nowe (proponowane): migracja `0140_grid_engine_profiles.py`,
  `grid_engine_profiles.py`, skrypt `scripts/install_grid_engine_models.py`,
  testy.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests -q -p no:cacheprovider -k "catalog or grid_engine_profile"
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/<nowy test migracji> -q -p no:cacheprovider
npm run openapi:generate; npm run openapi:check
npm run typecheck --workspace @game-predictor/admin; npm run test --workspace @game-predictor/admin
```

## Outcome

Integracja przed pracą: `git merge --no-edit v1.1-vision-lab-hybrid-geometry`
→ „Already up to date” (HEAD `v1.7.179`; w trakcie pracy na gałęzi pojawił
się commit `v1.7.180`, który dodał ten plik zadania).

### Changed

- Domena: `GameShapeGeometryConfiguration` ma `grid_profile_777_v2` i
  `grid_profile_mumie_v1`; `FRAMED_FULL_PAGE_CONFIGURATIONS` /
  `uses_framed_full_page_geometry` w `domain/catalog.py`. Oba resolvery
  gotowości (`DefaultShapeGeometryReadinessResolver`,
  `GlobalShapeGeometryReadinessResolver`) liczą profile dokładnie jak
  `framed_full_page_v2` (te same statusy, kody i `sharedProfile`;
  `configuration` = zapisany profil). Uzasadnienie: z kodu wynika, że pole i
  gotowość są wyłącznie projekcją odczytową katalogu — worker, preflight i
  pipeline ich nie czytają (grep), więc żadne zachowanie preflightu ani
  pipeline'u się nie zmienia; Mumie i 777 to pełne strony z ramką, a nowa gra
  startuje od `manual_review_required` (bez aktywnego profilu wspólnego).
- Rejestr `domain/grid_engine_profiles.py`: profil → bieżąca wersja `v1` →
  4 pliki (`screen.onnx`, `board.onnx`, `bundle.json`, `preset.json`) z
  SHA-256 i rozmiarem, metadane (run, eksport, preset, fingerprint, wagi,
  checkpoint, snapshot, powód wyboru, wyniki V3-C) i deterministyczny
  `manifest.json` (`grid_engine_manifest`).
- `storage/grid_engine_model_store.py`: `ManagedGridEngineModelStore`
  (`inspect` → `available` / `missing` / `checksum_mismatch`, liczy SHA przy
  każdym odczycie, porównuje manifest z rejestrem; `require` rzuca
  `GridEngineModelError`, bez fallbacku).
- `scripts/install_grid_engine_models.py`: jednorazowa instalacja (weryfikacja
  źródła wobec rejestru i tożsamości bundla, kopia do katalogu tymczasowego,
  weryfikacja, `os.replace`; poprawny katalog zostaje, niezgodnego nie
  nadpisuje; `--check`). Uruchomiono: oba modele zainstalowane w
  `C:\Users\tuszy\Documents\game_predicotr\artifacts\models\grid-engine\{grid_profile_777_v2,grid_profile_mumie_v1}\v1\`;
  drugie uruchomienie → `already_installed`, `--check` → kod 0.
- Migracja `0140_grid_engine_profiles` (CHECK rozszerzony, bez zmian
  wierszy; downgrade odmawia `GRID_ENGINE_PROFILE_IN_USE`);
  `EXPECTED_ALEMBIC_HEAD` = `0140_grid_engine_profiles`.
- API: `GET /api/v1/admin/grid-engine-profiles` (`listGridEngineProfiles`,
  `api/grid_engine_profiles.py`, `application/grid_engine_profiles.py`,
  `schemas/grid_engine_profiles.py`, wpięty w `api/router.py`).
- Kontrakt: OpenAPI i klient wygenerowane, wrapper `listGridEngineProfiles`
  i eksport typów w `packages/admin-api-client/src/index.ts`, test żądania w
  `client.test.mjs`.
- Admin: etykiety „777 v2” / „Mumie”, opis profilu i stan modelu pod polem
  („Profil 777 v2 służy również przyszłym wersjom gry 777”), linia
  „Format strony: …” ze stanem modelu na karcie gry, `loadGridEngineProfiles`
  (błąd nie blokuje katalogu).
- Testy: `test_grid_engine_profiles.py`, `test_grid_engine_profiles_migration.py`,
  `integration/test_grid_engine_profiles_migration_postgres.py`, nowe
  przypadki w `test_catalog_api.py`, `test_shape_geometry_game_readiness.py`,
  `integration/test_catalog_repository.py`, `test_schema_readiness.py`,
  testy Admina (`game-catalog-*.test.mjs`).

### Verification results

- `pytest services/api/tests -k "catalog or grid_engine_profile or shape_geometry or schema_readiness"`:
  59 passed, 5 skipped (PostgreSQL).
- PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`, bazy `*_test`):
  `test_grid_engine_profiles_migration_postgres.py` 1 passed (0139 → 0140,
  nowe wartości przyjęte, nieznana odrzucona, downgrade odrzucony z
  `GRID_ENGINE_PROFILE_IN_USE`, po zmianie gry downgrade i ponowny upgrade);
  `test_catalog_repository.py` 3 passed.
- `npm run openapi:generate`; `npm run openapi:check` → kod 0.
- Admin: `typecheck` 0, `lint` 0 (4 wcześniejsze ostrzeżenia w innych
  plikach), `node --test` 624/624; `admin-api-client` typecheck 0, test 77/77;
  prettier `--check` na zmienionych plikach 0.
- `ruff check` (zmienione pliki) czysto; `mypy --strict` bez błędów w
  zmienionych plikach (raportuje wcześniejsze błędy w niezmienionych
  modułach).
- Endpoint na prawdziwym katalogu artefaktów: oba profile `available`,
  manifest `available`, 4/4 pliki `available`.
- Wcześniejsze, niezależne błędy (ten sam wynik na nietkniętym checkoucie
  głównym na `v1.7.179`):
  `test_openapi_contract.py::test_grid_review_openapi_is_topology_aware_and_checksum_bound`
  (`minItems`) i
  `test_migration_baseline.py::test_parallel_feature_migrations_converge_on_one_head`
  (oczekuje head `0129`).

### Not completed

- Migracja `0140` na bazie deweloperskiej `game_predictor` — wykonuje
  orkiestrator (zatrzymanie API/workerów/Reviewera wszystkich checkoutów,
  merge, `npm run db:migrate`, start).
- Commit, `CURRENT_STATE.md`, przeniesienie do `completed/` — orkiestrator.
- Wizualny przegląd Admina w przeglądarce nie był wykonany (serwery 8000 i
  3000 należą do checkoutu głównego bez nowego endpointu).

### Documentation updates

- `ai_docs/requirements/ADMIN_APP.md`, `ai_docs/architecture/API_CONTRACT.md`,
  `ai_docs/architecture/DATA_MODEL.md`, `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`
  (sekcja „Profile silnika siatek gry i migracja `0140`”).
- Proponowany wpis `DECISION_LOG.md` (orkiestrator): profile silnika siatek
  jako wartości `shape_geometry_configuration` z gotowością `framed_full_page_v2`;
  modele w `<ARTIFACT_ROOT>/models/grid-engine/` z rejestrem SHA w kodzie, bez
  tabeli; brak modelu nie blokuje zapisu gry, `require` bez fallbacku.

### Recommended next task

- TASK-0805 (tryb shadow): ładować model przez
  `ManagedGridEngineModelStore.require(grid_engine_profile_for(game.shape_geometry_configuration).current)`.
