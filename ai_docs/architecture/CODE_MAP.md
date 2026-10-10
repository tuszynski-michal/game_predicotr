---
title: Code map
status: active
generated_by: scripts/generate_code_map.py
---

# Mapa kodu

Plik **generowany** (`python scripts/generate_code_map.py`); nie edytuj ręcznie.
Kontrola świeżości: `python scripts/generate_code_map.py --check`.
Pełny indeks symboli (jedna linia na moduł, do `rg`): [CODE_MAP_SYMBOLS.md](CODE_MAP_SYMBOLS.md).

Użycie: najpierw znajdź obszar tutaj, potem `rg` po `CODE_MAP_SYMBOLS.md`, dopiero na końcu otwórz konkretny plik z zakresem linii. Zasady rozwiązywania sprzeczności: `AGENTS.md`.

Obszary: [api](#api), [worker](#worker), [admin](#admin), [reviewer](#reviewer), [packages](#packages), [mobile](#mobile), [scripts](#scripts), [docs](#docs).

<a id="api"></a>
## API (services/api, FastAPI Admin API)

Warstwy: `api/` (routery HTTP) -> `application/` (use case'y) -> `domain/` (czysta logika), obok `storage/` (SQLAlchemy/PostgreSQL) i `schemas/` (Pydantic). Migracje Alembic w `services/api/alembic/versions/`.

### Katalogi

- `services/api/src/game_predictor_api/api/` (45 py) - routery HTTP; rejestr w `router.py`; HTTP transport layer for the local Admin API.
- `services/api/src/game_predictor_api/application/` (85 py) - use case'y (orkiestracja, transakcje); Application use cases; populated by later M2 vertical slices.
- `services/api/src/game_predictor_api/domain/` (70 py) - czysta logika domenowa bez I/O; Administrative domain layer independent of FastAPI and storage.
- `services/api/src/game_predictor_api/schemas/` (47 py) - modele Pydantic (kontrakt OpenAPI); Transport schemas published through OpenAPI.
- `services/api/src/game_predictor_api/storage/` (109 py) - repozytoria SQLAlchemy, modele tabel; Persistence adapters for the canonical PostgreSQL database.
- `services/api/src/game_predictor_api/security/` (2 py) - autoryzacja i polityki dostępu; Security boundaries for the local administration surface.
- `services/api/src/game_predictor_api/main.py` - fabryka aplikacji FastAPI
- `services/api/src/game_predictor_api/config.py` - konfiguracja (tylko loopback)
- `services/api/alembic/versions/` (158 py) - migracje `NNNN_*.py`
- `services/test_support/` (2 py) - wspólne helpery testowe API/workera

### Moduły wejściowe i symbole

- `services/api/src/game_predictor_api/main.py`: create_app
- `services/api/src/game_predictor_api/api/router.py`: create_api_router
- `services/api/src/game_predictor_api/api/super_game_series.py`: create_super_game_series_router
- `services/api/src/game_predictor_api/api/board_search.py`: create_board_search_router, reject_rules_version_query, parse_board_search_cells
- `services/api/src/game_predictor_api/api/rules.py`: create_rules_router

### Testy

- `services/api/tests/` (325 plików w katalogu testów, rekurencyjnie)
- `services/api/tests/integration/` (77 plików w katalogu testów, rekurencyjnie)

### Komendy

- `npm run api:dev`
- `npm run python:test` (`-Suite Api`)
- `npm run openapi:generate` po zmianie kontraktu; `npm run openapi:check`
- `npm run db:migrate`

<a id="worker"></a>
## Worker (services/worker, durable jobs)

Osobny proces pobierający joby z PostgreSQL po lane (`general`, `image-selection`). Zapisuje artefakty na dysk i wyniki do bazy.

### Katalogi

- `services/worker/src/game_predictor_worker/images/` (129 py) - ingestia, geometria, preflight, crop komórek, siatka; Image corpus contracts used before algorithm implementation.
- `services/worker/src/game_predictor_worker/symbols/` (13 py) - klasyfikacja symboli, biblioteka referencyjna, RGB v2; Versioned symbol-training dataset tools.
- `services/worker/src/game_predictor_worker/payouts/` (6 py) - wypłaty: kontrakty, handler, gotowość, audyt; Batch payout precomputation for durable worker jobs.
- `services/worker/src/game_predictor_worker/domain/super_games/` (4 py) - supergry: definicje, rejestr, Wild; Code-defined super game kinds (D-535).
- `services/worker/src/game_predictor_worker/super_game_series.py` - wyprowadzanie serii supergry
- `services/worker/src/game_predictor_worker/imports/` (12 py) - import danych: parsowanie, walidacja, handler; Versioned contracts for bounded manual layout imports.
- `services/worker/src/game_predictor_worker/jobs/` (4 py) - runtime jobów, lane, store; Durable local worker runtime.
- `services/worker/src/game_predictor_worker/snapshots/` (8 py) - generowanie snapshotu SQLite dla aplikacji mobilnej; Production mobile snapshot generation.
- `services/worker/src/game_predictor_worker/domain/` (10 py) - kontrakty, sygnatury, wypłaty (czysta domena); Framework-independent Game Predictor domain contracts.
- `services/worker/src/game_predictor_worker/semi_automatic_selection/` (46 py) - półautomatyczna selekcja obrazów; Pure contracts for the independent semi-automatic image selection workflow.
- `services/worker/src/game_predictor_worker/geometry_core/` (9 py) - wspólny rdzeń geometrii; Neutral V3 geometry inference: no storage, training or laboratory dependencies.
- `services/worker/src/game_predictor_worker/training_core/` (3 py) - wspólny rdzeń treningu modeli; Neutral training primitives; no application, database or laboratory imports.
- `services/worker/src/game_predictor_worker/vision_lab/` (75 py) - laboratorium wizji (izolowane); Standalone, file-backed vision laboratory; no production entry-point imports.
- `services/worker/src/game_predictor_worker/releases/` (6 py) - wydania modeli/aplikacji; Resumable mobile release workflow and controlled Android publication.
- `services/worker/src/game_predictor_worker/benchmarks/` (4 py) - benchmarki (nie uruchamiać bez polecenia); Deterministic datasets and verification helpers for performance benchmarks.
- `services/worker/src/game_predictor_worker/cli.py` - wejście CLI workera

### Moduły wejściowe i symbole

- `services/worker/src/game_predictor_worker/cli.py`: main
- `services/worker/src/game_predictor_worker/jobs/runtime.py`: class JobExecutionResult, class JobHandlerError, class WorkerJobStore, class JobHandler, class JobExecutionContext, class LocalJobWorker
- `services/worker/src/game_predictor_worker/jobs/lane_runtime.py`: class WorkerLaneHeartbeatStore, class WorkerLaneHeartbeat
- `services/worker/src/game_predictor_worker/super_game_series.py`: class SuperGameSeriesDeriveHandler
- `services/worker/src/game_predictor_worker/domain/super_games/registry.py`: list_super_game_kinds, is_known_super_game_kind, get_super_game_kind
- `services/worker/src/game_predictor_worker/payouts/handler.py`: class PayoutBatchHandler
- `services/worker/src/game_predictor_worker/imports/handler.py`: class LayoutImportSourceAttestor, class LayoutImportStagingHandler

### Testy

- `services/worker/tests/` (249 plików w katalogu testów, rekurencyjnie)

### Komendy

- `npm run worker:once` / `npm run worker:poll`
- `npm run python:test` (`-Suite Worker`)
- pojedynczy test: `pytest services/worker/tests/<plik> -k <nazwa>` (`.venv`)

<a id="admin"></a>
## Admin (apps/admin, Next.js, port 3000)

Panel administracyjny; funkcje w `src/features/<nazwa>/`, trasy w `src/app/`.

### Katalogi

- `apps/admin/src/features/` (162 ts/tsx) - funkcje panelu (podkatalogi poniżej)
  - `board-search/` (8 plików): BOARD_SEARCH_REPLAY_PARAMETER, BoardSearchReplayScope, BoardSearchReplayPlan, BoardSearchReplayResult, BoardSearchReplaySource, boardSearchReplayPlan, boardSearchReplayHref, readBoardSearchReplayParameter (+29)
  - `catalog/` (3 plików): ADMIN_WORKSPACES, AdminWorkspace, GAME_SECTIONS, GameSection, AdminNavigationState, DEFAULT_ADMIN_NAVIGATION, SUPER_GAME_SERIES_PARAMETER, isGameSectionAvailable (+5)
  - `cleanup/` (3 plików): BoardSourceCleanupControl, CleanupClient, CleanupTarget, CleanupActionResult, loadCleanupPreview, executeCleanup, CleanupControl
  - `datasets/` (6 plików): DatasetsClient, GenerateMockDatasetResult, generateMockDataset, GetDatasetValidationReportResult, getDatasetValidationReport, ListDatasetLayoutsResult, listDatasetLayouts, DatasetTransitionResult (+13)
  - `games/` (3 plików): GamesClient, GridEngineProfilesResult, loadGridEngineProfiles, SuperGameKindsResult, loadSuperGameKinds, SaveGameIntent, SaveGameResult, saveGameIdentity (+27)
  - `grid-shadow/` (2 plików): GridShadowPanelClient, GridShadowPanel, gridShadowErrorMessage, gridShadowSourceChoices, gridShadowUnknownVisibilityCount, gridShadowMeshLines, gridShadowReviewerUrl, gridShadowRequestId (+2)
  - `image-selection/` (5 plików): ImageSelectionClient, ImageSelectionUploadProgress, ResumableImageSelectionUpload, ImageSelectionOutputSaveResult, isVisibleImageSelectionRun, visibleImageSelectionRuns, orderImageSelectionFiles, uploadPhotoSelectionFolder (+20)
  - `imports/` (23 plików): VERIFIED_V19_ACTIVATION_VERSION, boardCellProcessingModeLabel, boardCellProcessingJobLabel, jobMatchesBoardCellProcessingMode, GeometryCompletenessClient, GeometryCompletenessSection, GeometryImageStateName, GeometryPositionStateName (+190)
  - `jobs/` (3 plików): JobsClient, LoadJobsResult, loadJobs, WorkerLanesResult, loadWorkerLanes, JobMutationResult, cancelJob, DeleteImageSelectionJobResult (+42)
  - `management/` (11 plików): ManagementSharePanel, ManagementWorkspace
  - `manual-image-selection/` (14 plików): FilenameVerificationRejectedSource, FilenameVerificationPendingDecision, FilenameRangeVerificationLocalState, FilenameRangeVerificationStore, directoryPermissionIsGranted, ManualSelectionCursorSemantics, MANUAL_SELECTION_CURSOR_SEMANTICS, ResumeManualSelectionCursorInput (+72)
  - `model-quality/` (5 plików): GridQualityPanel, LabCandidateRegistryPanel, PendingLabRegistryCommand, readPendingLabRegistryCommand, saveLabRegistryCommand, clearLabRegistryCommand, reconcileLabRegistryFailure, ModelQualityClient (+25)
  - `releases/` (3 plików): ReleasesClient, LoadReleaseWorkspaceResult, loadReleaseWorkspace, CreateReleaseResult, createRelease, StartReleaseBuildResult, startReleaseBuild, CreateAndStartReleaseResult (+23)
  - `reviewer-access/` (4 plików): ReviewerAccessLauncher, reviewableGames, isImageImport, reviewReadyImports, selectReviewImportId, hasImageImport, hasReviewerWork, gridReviewTotal (+11)
  - `reviews/` (4 plików): ReviewsClient, LoadReviewBatchesResult, loadReviewBatches, LoadReviewItemsResult, loadReviewItems, LoadReviewItemResult, loadReviewItem, loadReviewSymbols (+15)
  - `rules/` (13 plików): PaylinesClient, SavePaylineIntent, SavePaylineResult, savePayline, ArchivePaylineResult, archivePayline, DeletePaylineResult, deletePayline (+73)
  - `semi-automatic-image-selection/` (24 plików): localV7PilotHref, SELECTED_IMAGE_CROP_ATLAS_BATCH_SIZE, SELECTED_IMAGE_CROP_THUMBNAIL_WIDTH, SELECTED_IMAGE_CROP_THUMBNAIL_HEIGHT, SelectedImageCropAtlas, loadSelectedImageCropAtlases, selectedImageCropAtlasPosition, SelectedImageCropSourceSelection (+139)
  - `storage/` (1 plików): StorageWorkspace
  - `super-games/` (3 plików): SUPER_GAME_SERIES_SHORTCUT_SYMBOL_LIMIT, SuperGameSeriesKeyboardCommand, SuperGameSeriesKeyboardEvent, superGameSeriesShortcutLabel, resolveSuperGameSeriesKeyboardCommand, isSuperGameSeriesTextEntryTarget, isSuperGameSeriesShortcutBlocked, SERIES_PAGE_LIMIT (+76)
  - `symbol-reviews/` (13 plików): SymbolReviewClient, SymbolReviewImportFolder, SymbolReviewProjectionResult, loadSymbolReviewProjection, startSymbolReviewProjection, LoadSymbolReviewPageOptions, LoadSymbolReviewCountsOptions, SymbolReviewCountsResult (+95)
  - `symbols/` (5 plików): SymbolsClient, SaveSymbolIntent, SaveSymbolResult, saveSymbol, DeleteSymbolResult, deleteSymbol, ReorderSymbolsResult, reorderSymbols (+25)
  - `unreadable-board-reviews/` (2 plików): UnreadableBoardReviewClient, loadUnreadableBoardPage, loadUnreadableBoardDetail, loadUnreadableBoardSymbols, saveUnreadableBoard, UnreadableBoardReviewWorkspace
  - `v7-label-geometry/` (4 plików): PendingV7LabelGeometryOperation, V7LabelGeometryQueueState, V7LabelGeometryOperationInput, enqueueV7LabelGeometryOperation, nextV7LabelGeometryOperation, acknowledgeV7LabelGeometryOperation, stopV7LabelGeometryQueue, resumeV7LabelGeometryQueue (+22)
- `apps/admin/src/app/` (2 ts/tsx) - trasy Next.js
- `apps/admin/src/api/` (1 ts/tsx) - wrappery klienta API
- `apps/admin/src/components/` (1 ts/tsx) - wspólne komponenty
- `apps/admin/src/lib/` (2 ts/tsx) - narzędzia pomocnicze
- `apps/admin/src/config/` (1 ts/tsx) - konfiguracja

### Moduły wejściowe i symbole

- `apps/admin/src/features/super-games/super-game-series-workspace.tsx`: SuperGameSeriesClient, SuperGameSeriesWorkspace
- `apps/admin/src/features/super-games/super-game-series-state.ts`: SERIES_PAGE_LIMIT, UNDEFINED_COUNT_LIMIT, SERIES_STATE_POLL_INTERVAL_MS, CompletenessFilter, RunVerificationFilter, DefinedFilter, SeriesFilters, DEFAULT_SERIES_FILTERS (+67)

### Testy

- `apps/admin/test/` (109 plików w katalogu testów, rekurencyjnie)
- `apps/admin/test-interactions/` (23 plików w katalogu testów, rekurencyjnie)
- `apps/admin/test-browser/` (2 plików w katalogu testów, rekurencyjnie)

### Komendy

- `npm run admin:dev`
- `npm run typecheck --workspace @game-predictor/admin`
- `npm run lint --workspace @game-predictor/admin`

<a id="reviewer"></a>
## Reviewer (apps/reviewer, Next.js, port 3001)

Zdalny/lokalny UI przeglądu i selekcji; proxy allowlisty do API z cookie sesji (`src/security/`).

### Katalogi

- `apps/reviewer/src/features/` (40 ts/tsx) - funkcje (podkatalogi poniżej)
  - `access/` (2 plików): LocalReviewerWorkspace, ReviewerAccessGate
  - `board-search-share/` (3 plików): BOARD_SEARCH_SHARE_API_BASE, BOARD_SEARCH_SHARE_GAME_ID, SEARCH_CACHE_TTL_MS, SEARCH_CACHE_MAX_ENTRIES, BoardSearchShareDataSourceOptions, BoardSearchShareDataSource, createBoardSearchShareDataSource, BoardSearchShareGate (+2)
  - `catalog/` (1 plików): apiErrorMessage
  - `management/` (3 plików): MANAGEMENT_SESSION_ID, managementStorageNamespace, managementAccessMessage, ManagementGate, MANAGEMENT_API_BASE, createManagementPublicAdapter, ManagementPublicAdapter
  - `manual-selection/` (12 plików): OperatorLocalOutputManifestV1, OperatorLocalOutputManifestV2, OperatorLocalOutputManifest, OperatorLocalOutputDirectoryState, OperatorLocalOutputResult, resetOperatorLocalOutputDirectory, writeOperatorLocalSelection, removeOperatorLocalSelection (+85)
  - `operational-reviews/` (19 plików): gridReviewCorners, gridReviewQualification, gridReviewGeometryPreviewCommand, parseGeometryCorners, gridCellsWithoutPixels, gridCellPolygonsWithoutPixels, BoardGeometryCorrectionView, BoardGeometryCorrectionFact (+168)
- `apps/reviewer/src/app/` (9 ts/tsx) - trasy i route handlery
- `apps/reviewer/src/security/` (4 ts/tsx) - proxy i polityka allowlisty
- `apps/reviewer/src/api/` (1 ts/tsx) - wrapper klienta API
- `apps/reviewer/src/config/` (1 ts/tsx) - konfiguracja

### Moduły wejściowe i symbole

- `apps/reviewer/src/security/reviewer-proxy-policy.ts`: remoteSelectionProxyTarget, reviewerProxyTarget

### Testy

- `apps/reviewer/test/` (33 plików w katalogu testów, rekurencyjnie)
- `apps/reviewer/test-interactions/` (9 plików w katalogu testów, rekurencyjnie)

### Komendy

- `npm run reviewer:dev`
- `npm run test --workspace @game-predictor/reviewer`
- `npm run test:geometry --workspace @game-predictor/reviewer`

<a id="packages"></a>
## Packages (packages/*)

Wspólny kod TS. Klient API jest generowany z OpenAPI (`admin-api-client/src/generated`, nie edytować ręcznie).

### Katalogi

- `packages/board-search-ui/src/` (34 ts/tsx) - wspólny UI wyszukiwarki plansz
- `packages/shared-ts/src/` (9 ts/tsx) - kontrakty domenowe i kodek sygnatur (też mobile)
- `packages/admin-api-client/src/` (2 ts/tsx) - wrappery klienta wygenerowanego z OpenAPI
- `packages/manual-image-selection-core/src/` (11 ts/tsx) - wspólna logika ręcznej selekcji
- `packages/ui/src/` (2 ts/tsx) - wspólne elementy UI
- `packages/vision-lab-api-client/src/` (1 ts/tsx) - klient API laboratorium wizji
- `packages/domain-fixtures/` - złote przypadki JSON (TS i Python)

### Testy

- `packages/board-search-ui/test/` (11 plików w katalogu testów, rekurencyjnie)
- `packages/shared-ts/test/` (4 plików w katalogu testów, rekurencyjnie)
- `packages/admin-api-client/test/` (14 plików w katalogu testów, rekurencyjnie)
- `packages/manual-image-selection-core/test/` (20 plików w katalogu testów, rekurencyjnie)
- `packages/vision-lab-api-client/test/` (3 plików w katalogu testów, rekurencyjnie)

### Komendy

- `npm run test --workspace @game-predictor/<pakiet>`
- `npm run fixture:validate`

<a id="mobile"></a>
## Mobile (apps/mobile, Expo, offline)

Aplikacja Android tylko ze snapshotem SQLite; bez uprawnienia INTERNET.

### Katalogi

- `apps/mobile/src/` (26 ts/tsx) - kod aplikacji

### Testy

- `apps/mobile/__tests__/` (11 plików w katalogu testów, rekurencyjnie)

### Komendy

- `npm run snapshot:generate`
- `npm run snapshot:validate`

<a id="scripts"></a>
## Scripts (scripts/)

Skrypty pipeline'u, akceptacji i benchmarków; grupy wg prefiksu nazwy pliku.

### Katalogi

- `scripts/` (161 py) - grupy poniżej; npm scripts wg prefiksu w `package.json`

### Grupy

Pliki wg pierwszego członu nazwy (liczba; przykłady):

- `audit_*` (3): `audit_board_cell_geometry_v19.py`, `audit_staging_lifecycle.py`, `audit_task.ps1`
- `benchmark_*` (11): `benchmark_board_search.py`, `benchmark_image_selection_versions.py`, `benchmark_m1_repository.py` (+8)
- `build_*` (14): `build_android_debug.ps1`, `build_m35_benchmark_apk.py`, `build_m5_complete_local_grid_profiles.py` (+11)
- `check_*` (12): `check_crop_v11_independent.mjs`, `check_current_state_window.py`, `check_decision_links.py` (+9)
- `crop_*` (8): `crop_m5_board_cells.py`, `crop_m5_board_cells_calibrated.py`, `crop_m5_board_cells_detector_symbol_aware.py` (+5)
- `evaluate_*` (16): `evaluate_grid_audit_feedback.py`, `evaluate_lateral_partial_v4.py`, `evaluate_m35_acceptance.py` (+13)
- `export_*` (5): `export_admin_openapi.py`, `export_m6_symbol_classifier_onnx.py`, `export_m6_symbol_dataset.py` (+2)
- `freeze_*` (3): `freeze_shape_geometry_v2_corpus.py`, `freeze_v7_corpus.py`, `freeze_vision_lab_hybrid_protocol.py`
- `generate_*` (4): `generate_code_map.py`, `generate_m1_snapshot.py`, `generate_m35_benchmark_dataset.py` (+1)
- `install_*` (2): `install_grid_engine_models.py`, `install_mumie_feedback_controls.py`
- `measure_*` (2): `measure_image_import_job.ps1`, `measure_symbol_review_page.py`
- `mumie_*` (2): `mumie_control_truth_prepare.py`, `mumie_folder_gallery.html`
- `preflight_*` (2): `preflight_vision_lab_hybrid.ps1`, `preflight_vision_lab_hybrid.py`
- `prepare_*` (6): `prepare_crop_v11_independent_sample.mjs`, `prepare_m34_device_candidate.py`, `prepare_management_browser_fixture.py` (+3)
- `preview_*` (6): `preview_management_receipt_migration.py`, `preview_manual_selection_manifest_v2.mjs`, `preview_screen_layout_v3.py` (+3)
- `probe_*` (3): `probe_v7_grid_label_corpus.py`, `probe_v7_grid_labels.py`, `probe_v7_selection_environment.py`
- `provision_*` (2): `provision_database_roles.py`, `provision_v7_sequence_ocr_model.ps1`
- `rebuild_*` (2): `rebuild_board_search_projection.py`, `rebuild_symbol_cell_reviews.py`
- `reconcile_*` (2): `reconcile_followup_777_board_positions.py`, `reconcile_partial_board_symbol_review.py`
- `review_*` (5): `review_m5_cell_grid.py`, `review_m5_local_grid_calibration.py`, `review_m5_symbol_grid_fallbacks.py` (+2)
- `run_*` (36): `run_android_device_acceptance.ps1`, `run_board_cell_geometry_shadow_benchmark.py`, `run_concurrent_worker_lane_acceptance.py` (+33)
- `select_*` (2): `select_local_image_folder.ps1`, `select_m6_symbol_model_candidate.py`
- `setup_*` (3): `setup_android_toolchain.ps1`, `setup_remote_reviewer_tunnel.ps1`, `setup_vision_lab.ps1`
- `start_*` (8): `start_controlled_api.ps1`, `start_controlled_image_selection.ps1`, `start_controlled_image_selection_rerun.ps1` (+5)
- `symbol_*` (3): `symbol_reference_blind_review.html`, `symbol_reference_preview.html`, `symbol_rgb_v2.py`
- `train_*` (2): `train_m6_symbol_classifier.py`, `train_symbol_model.py`
- `v7_*` (2): `v7_pilot_fixture_app.py`, `v7_pilot_runtime_entry.py`
- `validate_*` (5): `validate_m1_fixture.py`, `validate_m1_snapshot.py`, `validate_m35_benchmark_dataset.py` (+2)
- `verify_*` (7): `verify_android_apk.ps1`, `verify_m2_acceptance.ps1`, `verify_management_panel_browser.mjs` (+4)
- `vision_*` (5): `vision_lab_assisted_annotation.ps1`, `vision_lab_export.py`, `vision_lab_geometry_export.py` (+2)

Pojedyncze pliki: `accept_m6_classifier_vertical_slice.py`, `acceptance_concurrent_worker_lanes.ps1`, `apply_v7_pilot_acceptance.py`, `backfill_image_geometry_completeness.py`, `bundle_management_browser_fixture.mjs`, `calibrate_m6_symbol_confidence.py`, `clean_scratch_dirs.ps1`, `compact_image_pipeline_state.py`, `complete_m4_acceptance_apk.py`, `configure_windows_user_environment.ps1`, `convert_legacy_boards_to_virtual.py`, `delete_archived_v2_game.py`, `detect_m5_boards.py`, `diagnose_selected_crop_v11.mjs`, `discover_m5_images.py`, `drop_diagnostic_databases.py`, `ensure_android_release_signing.ps1`, `get_remote_reviewer_tunnel_status.ps1`, `import_grid_audit_proposals.py`, `m8_gold_frame_pilot.py`, `manage_worker_lanes.ps1`, `management_browser_flow.mjs`, `migrate_cell_level_verification.py`, `normalize_m5_images.py`, `profile_image_selection_slice.py`, `queue_image_selection_after_report.ps1`, `recognize_grid_audit_symbols.py`, `refresh_stale_board_search_documents.py`, `release_m6_spatial_symbol_model.py`, `remote_manual_selection_rollout_stage_two.py`, `remove_superseded_import_images.py`, `reset_local_admin_database.ps1`, `reverify_777_grids.py`, `reviewer_process_lifecycle.ps1`, `route_partial_boards_to_grid_correction.py`, `slim_prediction_revisions.py`, `split_m6_symbol_dataset.py`, `stop_remote_reviewer_tunnel.ps1`, `test_mumie_folder.py`, `token_pilot_collect.py`, `windows_process_environment.ps1`

npm scripts wg prefiksu (liczba): `admin:`3, `android:`7, `api:`2, `code-map:`1, `db:`10, `docs:`1, `fixture:`1, `format:`2, `image-import:`1, `images:`2, `lint:`1, `m2:`1, `m35:`7, `m4:`2, `m5:`15, `m6:`10, `m7:`10, `openapi:`2, `powershell:`1, `python:`3, `quality:`1, `remote-selection:`3, `repository:`1, `reviewer:`8, `snapshot:`2, `test:`1, `typecheck:`1, `v01:`3, `v02:`1, `v04:`2, `vision-lab:`4, `windows:`3, `worker:`4, `workers:`4

### Komendy

- `npm run docs:check`
- `npm run code-map:check` (aktualność mapy kodu; poza `quality`)
- `npm run python:lint` / `npm run python:typecheck`
- `npm run quality` (pełna bramka)

<a id="docs"></a>
## Docs (ai_docs/)

Dokumentacja procesu; kolejność czytania w `AGENTS.md` i `ai_docs/README.md`.

### Katalogi

- `ai_docs/process/` - stan, decyzje, standardy planów i zadań
- `ai_docs/requirements/` - wymagania produktu
- `ai_docs/architecture/` - architektura (ten plik: `CODE_MAP.md`)
- `ai_docs/delivery/` - plany wykonania
- `ai_docs/tasks/` - aktywne zadania (ukończone w `completed/`)
- `ai_docs/quality/` - raporty jakości i audytów
- `ai_docs/guides/` - instrukcje operatorskie

Pliki procesu: `AI_DRIVEN_DEVELOPMENT.md`, `BOARD_CORNER_PLACEMENT_STATUS.md`, `CURRENT_STATE.md`, `DECISION_LOG.md`, `DEFINITION_OF_DONE.md`, `HANDOFF_GRID_V3_20261004.md`, `MANAGEMENT_PANEL_OPERATIONS.md`, `PLAN_STANDARD.md`, `RESUMABLE_LEGACY_DELETION.md`, `TASK_TEMPLATE.md`

### Komendy

- `npm run docs:check`
- `npm run code-map:check`
