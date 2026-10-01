---
title: TASK-0796 — S6 — usunięcie ścieżek plików cropów v19 i zawężenie trybów zasobów w kodzie
status: done
last_updated: 2026-10-01
---

# TASK-0796 — S6 — usunięcie ścieżek plików cropów v19 i zawężenie trybów zasobów w kodzie

## Status

`done` (audyt pominięty — decyzja operatora 2026-10-01; commit v1.7.125; wdrożenie = restart usług)

## Goal

Kod (API, worker, ORM, klient, Admin, Reviewer, testy) zna wyłącznie tryby
`virtual_source`/`none`: nie ma ścieżek plików cropów v19 ani gałęzi
`legacy_file`, enumy API są zawężone pionem, CHECK-i w modelach ORM
odpowiadają bazie po `0135`/`0136`, a fixture testów tworzą plansze
wirtualne — domknięcie S6 (reszta zakresu TASK-0791).

## Context

D-467, S6. Baza operatora: `0137`; 0 plansz/komórek `legacy_file`
(TASK-0791), CHECK-i plansz i komórek bez gałęzi legacy. ORM
(`storage/models.py`) nadal dopuszcza `legacy_file` w CHECK-ach planszy i
komórek oraz ma domyślne `asset_mode = "legacy_file"` — świadoma
rozbieżność z bazy, do usunięcia tutaj. Ścieżki legacy w kodzie (stan po
TASK-0794): korekta geometrii v19 Reviewera
(`api/image_reviews.py::createOperationalImageReviewGeometryRevision` i
`previewOperationalImageReviewGeometry` → `application/image_reviews.py::correct_geometry`
/ podgląd → `storage/image_review_repository.py::save_geometry_revision`,
previewer plików cropów w workerze; Reviewer
`apps/reviewer/src/features/operational-reviews/operational-review-geometry-editor.tsx`
+ `operational-review-actions.ts`, allowlista `reviewer-proxy-policy.ts`
`image-review-items/{id}/(geometry-preview|geometry-revisions)`; obok
istnieje wirtualna korekta `board-geometry-correction-target.ts` →
`createImageGridReviewGeometryRevision`), `worker/images/pending_grid_reinference.py::_run_v1`
(wybiera tylko plansze `legacy_file`, więc martwy), gałęzie `legacy_file`
w `storage/current_board_cell_sources.py`, `image_review_repository.py`
(mapper), `image_symbol_review_repository.py` (stale-check, wersja
croppera, `get_assets`), `board_search_projection_repository.py`,
`worker/images/pending_symbol_reinference.py` (rewizja > 0 legacy czyta
`crop_artifacts`), enumy API `assetMode`/`cellAssetMode`/`ImageReviewCell.assetMode`
(`schemas/*`, OpenAPI, klient, wrapper, Admin, Reviewer, `shared-ts` jeśli
dotyczy), kod `IMAGE_REVIEW_GEOMETRY_ASSET_MODE_UNSUPPORTED`. Testy
jednostkowe (SQLite) i PG tworzą plansze `legacy_file` (ok. 28 plików z
jawnym `legacy_file` + fixture z domyślnym trybem ORM; po `0135` PG padają:
`test_image_batch_store` 11, `partial_board_reconciliation` 5,
`verified_cell_search_projection` 4, `board_render_manifests` 2,
`outside_current_owner` 1, `cell_level_verification_migration` 1 —
fixture `legacy_file` odrzucane przez CHECK).

## Dependencies / entry conditions

- Fakt: HEAD `v1.7.122`; TASK-0790–0794 scalone i wdrożone.
- Decyzja operatora 2026-10-01: jeden tryb danych; audyty zawieszone.
- Założenie: Reviewer przez tunel używa korekty v19 dla zwykłych plansz
  (editor w `operational-review-workspace.tsx`); po konwersji wszystkie
  plansze są wirtualne, więc ta ścieżka zwraca dziś 422 — przepięcie na
  ścieżkę wirtualną przywraca funkcję.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo). Audyt: zawieszony.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md` (S6)
- `ai_docs/process/DECISION_LOG.md` (D-467, D-462)
- `ai_docs/tasks/completed/0790-virtual-only-manual-resolution-and-import-policy.md`
  (delegacja endpointu Reviewera do ścieżki wirtualnej — wzorzec),
  `0791-convert-legacy-boards-and-narrow-asset-modes.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`, `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Korekta geometrii Reviewera: endpointy `geometry-preview` i
  `geometry-revisions` pod `image-review-items/{id}` zostają (kontrakt i
  allowlista bez zmian, autoryzacja sesji Reviewera bez zmian), ale
  delegują do `VirtualGridGeometryService` (podgląd = render wirtualny,
  zapis = `save_virtual_geometry_revision` dla istniejącej planszy, reguła
  rewizji TASK-0702, idempotencja po `idempotencyKey`), jak `manual-resolution`
  w TASK-0790; odpowiedź zachowuje kształt
  `OperationalImageReviewGeometryResponse` (pola plików cropów → `null`/usunięte
  pionem, jeśli Reviewer ich nie używa). Usunięcie `save_geometry_revision`
  (v19), previewera plików cropów, `correct_geometry` v19 i kodu
  `IMAGE_REVIEW_GEOMETRY_ASSET_MODE_UNSUPPORTED`.
- Worker: usunięcie `_run_v1` z `pending_grid_reinference.py` (i payloadu
  v1, jeśli nic go nie tworzy), gałęzi `legacy_file` w
  `pending_symbol_reinference.py`; API/storage: gałęzie `legacy_file` w
  mapperze, `current_board_cell_sources`, stale-check, wersji croppera,
  `get_assets`, projekcji wyszukiwarki.
- Enumy API `assetMode` / `cellAssetMode` / `BoardSearch*AssetMode`
  zawężone do `virtual_source` (+ `none` dla komórek) pionem: backend,
  `scripts/export_admin_openapi.py`, regeneracja klienta, wrapper,
  Admin, Reviewer, `packages/shared-ts` (jeśli ma ten enum; aplikacja
  mobilna czyta snapshot — sprawdzić wpływ na `snapshot:generate`).
- ORM `storage/models.py`: CHECK-i `ck_recognized_boards_asset_provenance`,
  `ck_image_symbol_review_cells_asset_provenance`, `..._source_asset`,
  `..._approved_provenance` (gałąź `approved_asset_mode = 'legacy_file'`
  — zostaje tylko jeśli historyczne zatwierdzenia na bazie ją mają;
  sprawdzić `SELECT count(*) ... approved_asset_mode = 'legacy_file'` i
  opisać), `ck_image_board_geometry_revisions_asset` (historia — zostaje),
  domyślne `asset_mode = "virtual_source"`; zgodność z `pg_get_constraintdef`
  po `0136` (test offline porównujący wyrażenia ORM z migracjami nie jest
  wymagany, ale CHECK-i muszą być równoważne).
- Testy: fixture tworzące plansze/komórki `legacy_file` przepięte na
  wirtualne (wspólna fabryka fixture: plansza `virtual_source` z rewizją
  geometrii źródła, manifest renderu, komórki z sumami); zielone PG
  wymienione w Context; nowe testy Reviewera (podgląd/zapis geometrii
  przez endpoint operacyjny → rewizja wirtualna; 404 dla usuniętych
  ścieżek nie dotyczy — endpointy zostają).
- Dokumentacja: `API_CONTRACT.md`, `DATA_MODEL.md`, `REMOTE_REVIEWER_THREAT_MODEL.md`
  (nota), `DECISION_LOG.md` (nota D-467 S6 domknięcie), plan (S6 zamknięty),
  Outcome.

## Out of scope

- Zmiany danych na bazie (brak migracji w tym zadaniu, chyba że ORM
  wymaga korekty nazwy constraintu — wtedy opisać; nie przewiduje się).
- TASK-0795 (rola bazy), kompaktacja VHDX.

## Acceptance criteria

- [ ] `git grep -n "legacy_file"` w `services/*/src`, `apps/*/src`,
      `packages/*/src` zwraca tylko migracje historyczne, CHECK rewizji
      geometrii (historia) i ewentualnie gałąź `approved_asset_mode` z
      uzasadnieniem.
- [ ] Reviewer: podgląd i zapis korekty geometrii zwykłej planszy przez
      endpoint operacyjny daje rewizję wirtualną z manifestem (test PG).
- [ ] OpenAPI bez `legacy_file` w enumach; klient/wrapper/Admin/Reviewer
      zielone (testy, typecheck, lint); `openapi:check`, `check:generated`.
- [ ] PG testy z Context zielone (fixture wirtualne); unit/PG poza znanymi
      niepowodzeniami HEAD zielone; `--collect-only` OK.

## Technical notes

- Wzorzec delegacji: TASK-0790 (`BoardCellGeometryPendingService` →
  `VirtualGridGeometryService.save_pending_slot`); dla istniejącej planszy
  użyć `save_virtual_geometry_revision` z kontekstem `virtual_geometry_context(review_item_id=…)`.
- Kolejność blokad i reguła rewizji z TASK-0790/0791.
- Chronione: kontrakt i allowlista Reviewera, decyzje, zdarzenia, historia
  rewizji legacy.

## Expected files

- Zmienione: pliki z Context; testy; OpenAPI + klient + wrapper; docs.
- Usunięte: previewer plików cropów v19 (worker), `_run_v1`.

## Verification

```powershell
$env:PYTHONPATH = "services/worker/src;services/api/src"
.\.venv\Scripts\python.exe -m ruff check services/api/src services/worker/src scripts
.\.venv\Scripts\python.exe -m mypy --strict <zmienione moduły>
.\.venv\Scripts\python.exe -m pytest services/api/tests services/worker/tests -q -p no:cacheprovider --basetemp C:\Users\tuszy\AppData\Local\Temp\t796   # porcjami
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_image_batch_store.py services/api/tests/integration/test_partial_board_reconciliation_postgres.py services/api/tests/integration/test_verified_cell_search_projection.py services/api/tests/integration/test_board_render_manifests_postgres.py -p no:cacheprovider --basetemp C:\Users\tuszy\AppData\Local\Temp\t796pg
.\.venv\Scripts\python.exe scripts/export_admin_openapi.py --check
npm run check:generated --workspace @game-predictor/admin-api-client
npm run test --workspace @game-predictor/admin-api-client
npm run test --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/reviewer
```

## Risks / open questions

- Reviewer przez tunel: zmiana zachowania endpointu (render wirtualny
  zamiast plików) — kontrakt bez zmian, ale podgląd PNG może różnić się
  pikselami (render wirtualny vs crop pliku); akceptowane.
- Zakres fixture testów może być duży; dopuszczalne pomocnicze fabryki w
  `services/api/tests/_virtual_fixtures.py` (nazwa orientacyjna).

## Outcome

Implementacja gotowa, bez commitu (commit, wdrożenie i zamknięcie zadania
wykonuje orkiestrator); audyt zawieszony przez operatora — wykonany
przegląd własnego diffu. **Bez migracji** — wdrożenie = restart API,
workera i Reviewera.

### Changed

- Reviewer, korekta geometrii bieżącej planszy:
  `image-review-items/{id}/geometry-preview` i `.../geometry-revisions`
  zachowują trasy, kontrakt wejścia, allowlistę i autoryzację sesji, ale
  `OperationalImageReviewService.preview_geometry` / `correct_geometry`
  delegują do nowych `VirtualGridGeometryService.preview_review_item` /
  `save_review_item` (tożsamość źródła, wymiary i topologia z
  `virtual_geometry_context(review_item_id=…)`, potem istniejące
  `preview`/`save`: replay po `idempotencyKey`, CAS rewizji,
  `save_virtual_geometry_revision`, manifest renderu, ponowne otwarcie).
  Brak serwisu wirtualnego → `IMAGE_REVIEW_GEOMETRY_UNAVAILABLE` (bez
  cichego fallbacku). `IMAGE_REVIEW_GEOMETRY_IDEMPOTENCY_CONFLICT` i
  `IMAGE_REVIEW_SUPERSEDED` mapowane na 409. Odpowiedź
  `OperationalImageReviewGeometryRevisionResponse`: bez
  `decisionChecksumSha256`/`boardChecksumSha256`, z
  `sourceGeometryRevisionId`, `geometryChecksumSha256`,
  `virtualRenderSpecChecksumSha256` (wymagane). Reviewer: konflikt
  rewizji wirtualnej przeładowuje planszę, cel korekty bez gałęzi
  `virtualSource`.
- Usunięte: `save_geometry_revision`/`get_geometry_revision_by_idempotency`
  (v19) z repozytorium operacyjnego, domenowe artefakty geometrii v19,
  previewer `worker/images/manual_board_cell_geometry_preview.py` (+ test),
  fallback legacy w `api/image_grid_reviews.py` (i zależność od serwisu
  operacyjnego), `IMAGE_REVIEW_GEOMETRY_ASSET_MODE_UNSUPPORTED`,
  `IMAGE_GRID_REVIEW_QUALIFICATION_UNSUPPORTED`.
- `pending_grid_reinference`: obie ścieżki plikowe (schema 1 i 2 zapisywały
  cropy v19 wyłącznie planszom `legacy_file`) usunięte; handler odmawia
  `IMAGE_GRID_REINFERENCE_LEGACY_UNSUPPORTED` (nieznany schemat →
  `IMAGE_GRID_REINFERENCE_SCHEMA_UNSUPPORTED`); podgląd/start w API
  zostają z `recalculableBoardCount = 0` (plansze pending poza chronionymi
  liczone jako `unsupportedVirtualBoardCount`).
- Gałęzie `legacy_file` usunięte z: mappera i
  `materialize_current_image_review_cells` (nie-wirtualna plansza →
  `IMAGE_REVIEW_ASSET_MODE_UNSUPPORTED`), `current_board_cell_sources`,
  stale-checku i wersji croppera oraz `get_assets`
  (`SYMBOL_CELL_REVIEW_ASSET_MODE_UNSUPPORTED`) w repozytorium recenzji
  symboli, podglądów/atlasu i endpointu assetu komórki (zawsze render
  wirtualny), kandydatów i materializacji wzorców symboli, źródła
  treningowego i kohort, projekcji wyszukiwarki i przybliżonej wygranej
  (tożsamość planszy = `geometry_checksum_sha256`),
  `pending_symbol_reinference` (nie-wirtualna →
  `IMAGE_SYMBOL_REINFERENCE_LEGACY_UNSUPPORTED`).
- Enumy API: `ImageGridReviewItemResponse.assetMode` i
  `ImageGridReviewGeometryRevisionResponse.assetMode` = `virtual_source`,
  `SymbolCellReviewListItemResponse.assetMode` i
  `UnreadableBoardReviewCellResponse.assetMode` = `virtual_source | none`
  (wymagane); domeny z domyślnym `virtual_source`. OpenAPI i klient
  zregenerowane (`openapi.json`, `generated/types.gen.ts`, `sdk.gen.ts`);
  wrapper `src/index.ts` bez zmian (re-eksportuje typy); test żądania w
  `client.test.mjs`. `packages/shared-ts` i `snapshot:generate` nie
  używają trybu zasobu — bez zmian.
- ORM `storage/models.py`: `ck_recognized_boards_asset_provenance` i
  `ck_image_symbol_review_cells_asset_provenance` tylko z gałęzią
  wirtualną (`none` dla komórek), domyślne `virtual_source` — zgodne z
  `pg_get_constraintdef` po `0135`/`0136`. Gałąź `approved_asset_mode =
  'legacy_file'` w `..._approved_provenance` zostaje (jest w bazie; na
  bazie operatora 0 komórek z zatwierdzeniem plikowym; usunięcie wymaga
  migracji). CHECK-i i domyślne tabel historii (zdarzenia, rewizje
  geometrii, kohorty) bez zmian.
- Testy: wspólna fabryka `services/api/tests/integration/_virtual_board_fixtures.py`
  (rewizja geometrii źródła, kolumny planszy wirtualnej, manifest renderu,
  zapis geometrii ręcznej); przepięte PG: `test_image_batch_store`,
  `test_partial_board_reconciliation_postgres`,
  `test_verified_cell_search_projection`, `test_board_render_manifests_postgres`,
  `test_outside_current_owner_postgres`, `test_cell_level_verification_migration`,
  `test_game_storage_routing_postgres`, `test_board_search_approximate_win_repository`,
  `test_board_import_coverage_repository` (test routingu v2); nowy
  `test_reviewer_operational_geometry_postgres.py` (2 testy: pełna korekta
  przez endpointy operacyjne → rewizja `virtual_source` z manifestem;
  odmowa 409 dla planszy zastąpionej). Testy jednostkowe API/workera,
  Reviewera i Admina przepięte na fixture wirtualne.
- Świadome wyjątki od „0 `legacy_file` w kodzie”: narzędzie konwersji
  TASK-0791 (`application/legacy_board_conversion.py`, ścieżka w
  `virtual_grid_geometry*`, wymagane przez `0135` przy odtwarzaniu bazy
  sprzed `0135`), tryby rolloutu `legacy_files` w snapshotach historycznych
  jobów (`schemas/jobs.py`, `pipeline_contract.py`, `image_geometry_cutover.py`),
  czytelnicy zamrożonych artefaktów (`symbols/training_dataset.py`,
  `vision_lab/symbol_snapshot.py`, skrypty `vision_lab_export.py`,
  `measure_symbol_review_page.py`), CHECK-i historii w ORM.

### Verification results

- `pytest services/api/tests --collect-only`: 1867 testów, OK.
- ruff + `ruff format --check` (59 zmienionych plików Python): czyste;
  `mypy --strict` (33 zmienione moduły źródłowe): błędy wyłącznie w znanych
  plikach HEAD (`qualified_manual_geometry.py`, `shape_geometry_v2/core.py`,
  `contrast_frame_grid_v12.py`, `v7_label_geometry_calibration.py` ×2,
  `page_geometry_preflight.py`); `git diff --check` czysty.
- API unit (porcjami po 6 plików): 1691 passed, 4 skipped, 20 failed —
  wszystkie znane z HEAD (`test_image_import_geometry_guard_api` 7,
  `test_reviews` 6, `test_virtual_grid_geometry` partial preview 2,
  `test_openapi_contract` 2 — schemat identyczny w OpenAPI HEAD,
  `test_image_symbol_reviews_api` 1, `test_lateral_managed_reprocess[browser]` 1,
  `test_migration_baseline` 1). Trzy testy z timeoutem połączenia podczas
  awarii Dockera przeszły po ponownym uruchomieniu.
- Worker unit: 2046 passed, 9 skipped, 36 failed — wszystkie z listy
  bazowej (korpus/artefakty lokalne).
- PG (pojedyncze pliki, bazy `*_test` usunięte): `test_reviewer_operational_geometry_postgres` 2/2,
  `test_image_batch_store` 15/15, `test_partial_board_reconciliation_postgres` 5/5,
  `test_verified_cell_search_projection` 4/4, `test_board_render_manifests_postgres` 3/3,
  `test_outside_current_owner_postgres` 1/1, `test_cell_level_verification_migration` 1/1,
  `test_virtual_deferred_resolution_postgres` 9/9, `test_convert_legacy_boards_postgres` 1/1,
  `test_game_storage_routing_postgres` 11/12 (pada znany
  `test_grid_review_source_asset_reads_v2…`: wywołanie bez zakresu nie
  zgłasza `IMAGE_GRID_REVIEW_PROJECTION_INCOMPLETE`; kod `require_game`
  bez zmian w tym zadaniu), `test_board_search_approximate_win_repository` 2/2,
  `test_cell_render_specs_postgres` 1/1, `test_drop_cell_render_spec_postgres` 1/1,
  `test_symbol_visibility_groups_postgres` 2/2, `test_drop_cell_observations_postgres` 1/1,
  `test_game_data_v2_postgres` 4/4, `test_board_import_coverage_repository` 1/9
  i `test_resumable_game_deletion` 0/1 (przed zmianą także czerwone:
  fixture na usuniętym magazynie `public` — `UndefinedTable
  image_import_job_files`, `'public' is not a valid GameStorageSchema`).
- TS: `@game-predictor/admin` test 597/597, typecheck i lint OK (4
  ostrzeżenia sprzed zmiany); `test:geometry` admina 34/35 — pada
  `bulk unreadable reconciles two outside positions…` także z fixture
  `legacy_file` (kod Admina bez zmian; niezależne od zadania);
  `@game-predictor/reviewer` test 194/194, `test:geometry` 7/7,
  typecheck i lint OK; `@game-predictor/admin-api-client` test 71/71,
  `check:generated` OK; `export_admin_openapi.py --check` OK.

### Not completed

- Gałąź `approved_asset_mode = 'legacy_file'` w CHECK zatwierdzeń komórek
  (ORM i baza) — usunięcie wymaga osobnej migracji (0 wierszy na bazie
  operatora).
- Edytor operacyjny Reviewera nie wysyła kwalifikacji częściowej: plansza
  z kwalifikacją częściową dostaje `IMAGE_GRID_REVIEW_QUALIFICATION_REQUIRED`
  (poprawny kod, brak ścieżki UI).
- Znane czerwone testy spoza zakresu (wyżej) nie były naprawiane.

### Documentation updates

- `API_CONTRACT.md` (delegacja korekty, odpowiedź rewizji, podglądy,
  pending grid reinference), `DATA_MODEL.md` (stan po S6),
  `REMOTE_REVIEWER_THREAT_MODEL.md` (nota TASK-0796), `DECISION_LOG.md`
  (D-467 „Domknięcie S6”), plan D-467 (S6 — nota wykonania),
  `CURRENT_STATE.md`.

### Recommended next task

- Migracja usuwająca gałąź `approved_asset_mode = 'legacy_file'` z
  `ck_image_symbol_review_cells_approved_provenance` (po potwierdzeniu 0
  wierszy na wszystkich bazach).
- Naprawa fixture `public` w `test_board_import_coverage_repository` /
  `test_resumable_game_deletion` (magazyn `game_data_v2`).
