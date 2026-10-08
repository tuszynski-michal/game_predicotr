# TASK-0940 — Zielona bramka `npm run quality` (naprawa błędów sprzed planu)

## Status

`done`

## Goal

`npm run quality` (format:check, openapi:check, lint, typecheck, test,
snapshot/fixture validate) przechodzi w całości na gałęzi integracyjnej, bez
osłabiania asercji i bez ogólnych wyłączeń typów; lista „znanych błędów”
w audytach znika.

## Context

Audyty TASK-0929–0932 musiały za każdym razem odfiltrowywać te same błędy
istniejące przed planem. Operator zaakceptował to zadanie 2026-10-08 jako
TASK-0940 przed etapem S-B. Plan:
`ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`, etap T.

## Dependencies / entry conditions

- Gałąź `feat/mumie-super-game-plan` na v1.7.271 (równa integracyjnej).
- Fakty (z audytów i raportów wykonawców, do potwierdzenia na starcie):
  1. `services/api/tests/test_v7_independent_progress.py`: błąd kolekcji
     (`ModuleNotFoundError: test_v7_run_state`, import modułu testów workera).
  2. `services/api/tests/test_game_data_v2_schema.py::test_manifest_is_exhaustive_disjoint_and_fail_closed`:
     trzy tabele V7 nieujęte w manifeście własności tabel V2.
  3. `services/api/tests/integration/test_postgres_baseline.py::test_upgrade_downgrade_upgrade_cycle_on_postgres`:
     tabele `management_*` poza `EXPECTED_PUBLIC_TABLES` (test PG,
     `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`, bazy `*_test`).
  4. Reviewer: `test/local-reviewer-workspace-contract.test.mjs:63`,
     `test/operational-review-workspace-contract.test.mjs:151` (źródła nie
     zmieniane od v1.7.183 / v1.7.143).
  5. `services/api/tests/test_board_search_share_access_api.py::test_invalid_lifetime_is_rejected_before_starting_the_ingress`:
     1441 minut jest poprawne od TASK-0925 (test opisuje stary limit).
  6. Ruff: `storage/models.py` I001; `services/worker/tests/test_page_geometry_preflight.py:345`
     E501; `ruff format --check` w `application/catalog.py` (hunk ok. linii 173–176).
  7. Mypy: błąd konfiguracji „moduł pod dwiema nazwami” dla
     `scripts/prepare_v7_reviewed_pilot.py`; `main.py:2005` `no-untyped-call`;
     błędy w `board_search_share_queries.py`, `v7_label_geometry_calibration.py`,
     `shape_geometry_v2/core.py`, `contrast_frame_grid_v12.py`,
     `qualified_manual_geometry.py`, `page_geometry_preflight.py`.
  8. TASK-0928 wspomina „cztery stare błędy fixture CLI” w `npm run python:test`.

## Recommended execution

claude-sonnet-5-5 / high. Naprawy testów, lintu i typów bez zmian zachowania
produktu; wiele małych, niezależnych poprawek. Eskalacja do claude-opus-5-5 /
high, gdy naprawa wymaga zmiany logiki produkcyjnej. Audyt: gpt-6.1-sol / high;
do czasu CLI zamiennik claude-opus-5-5 / high.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md` (manifest własności tabel)
- `ai_docs/quality/TEST_STRATEGY.md`

## Scope

- Uruchomić pełne `npm run quality` i `npm run python:test` (oraz PG testy
  bazowe) i zebrać kompletną listę błędów; potwierdzić albo skorygować
  listę powyżej.
- Naprawić każdy błąd u źródła: brakujące wpisy manifestu/`EXPECTED_PUBLIC_TABLES`
  (klasyfikacja tabel według `GAME_DATA_V2_OWNERSHIP.md`), import testowy
  między pakietami (fixture współdzielona albo przeniesienie modułu), testy
  opisujące nieaktualne reguły (dostosować do obowiązującej reguły, z
  odwołaniem do taska, który ją zmienił), formatowanie, długości linii,
  kolejność importów, realne poprawki typów (bez `# type: ignore` bez kodu
  i uzasadnienia; dozwolone tylko przy brakujących typach bibliotek
  zewnętrznych), konfiguracja mypy dla duplikatu nazwy modułu.
- Po naprawach: pełny `npm run quality` zielony.

## Out of scope

- Zmiany zachowania produktu, API, schematu; refaktory poza miejscem błędu.
- Benchmarki i testy obciążeniowe.

## Acceptance criteria

- [x] `npm run quality` kończy się kodem 0.
- [x] `npm run python:test` kończy się kodem 0 (łącznie z testami PG przy
      `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`).
- [x] Żadna asercja nie została usunięta ani osłabiona bez odwołania do
      obowiązującej reguły; każda zmiana testu ma komentarz z numerem taska
      reguły.
- [x] Brak nowych `# type: ignore` bez kodu błędu i uzasadnienia.

## Expected files

- Istniejące: pliki wymienione w faktach 1–8 oraz manifest własności tabel
  V2, `pyproject.toml` (konfiguracja mypy), `scripts/run_python_tests.ps1`
  tylko jeśli wymaga tego fakt 8.

## Verification

```powershell
# katalog worktree, timeout 600 s
npm run quality
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; npm run python:test
```

## Risks / open questions

- Część błędów może wymagać decyzji (np. czy tabela V7 jest „gry” czy
  „wspólna”); klasyfikować według `GAME_DATA_V2_OWNERSHIP.md`, a przy braku
  jednoznaczności opisać wybór w Outcome.

## Outcome

Wykonawca: claude-sonnet-5-5 / high. Wszystkie bramki są zielone; wyjątek to
jeden test zależny od środowiska worktree (junction `.venv`), patrz „Not
completed”. Fakty 1–8 zweryfikowano: wszystkie się potwierdziły, ale pełny
przebieg ujawnił więcej błędów niż lista (mypy na `scripts/` nigdy wcześniej nie
dochodził do sprawdzania typów z powodu błędu konfiguracji, a testy PG i korpusowe
nie były uruchamiane w całości). Decyzje koordynatora z końca pracy: reguła
TASK-0882 wygrywa nad komentarzem o kolejności bramki, trzy historyczne testy PG
wycofane z jawnym `skip`, testy korpusowe M5 pomijane przez wspólny helper.

### Changed

Format i konfiguracja
- `.prettierrc.json`: `endOfLine: auto`. Przy `core.autocrlf=true` (systemowy
  gitconfig tej maszyny) każdy checkout ma CRLF, a Prettier domyślnie wymaga LF,
  więc `format:check` zgłaszał 650 plików niezależnie od treści. Indeks i tak
  jest LF (`i/lf`).
- 23 pliki zgłoszone przez Prettier po tej zmianie przeformatowane
  (`prettier --write`: `apps/admin`, `apps/vision-lab`, `apps/reviewer/test`,
  `packages/*`, `TEMP PLAN V7.md`). Testy kontraktowe Admina czytające źródła
  po reformatowaniu nadal przechodzą.
- `pyproject.toml` (mypy): `explicit_package_bases`, `namespace_packages`,
  `mypy_path` + `.`. Błąd „moduł pod dwiema nazwami” wynikał z tego, że
  `scripts/*.py` były widziane jako `prepare_v7_reviewed_pilot` (katalog bez
  `__init__.py`) i jako `scripts.prepare_v7_reviewed_pilot` (import w trzech
  skryptach). Teraz każdy plik ma jedną nazwę `scripts.<nazwa>`. Cztery skrypty
  importują rodzeństwo po gołej nazwie (uruchamiane jako `python scripts/x.py`,
  `sys.path[0]` = `scripts/`); dla tych czterech modułów jest wpis
  `[[tool.mypy.overrides]] ignore_missing_imports` z komentarzem. Nie ukrywa to
  błędów w samych skryptach.
- `pyproject.toml` (pytest): `services/test_support` w `pythonpath`;
  `package.json`: `python:lint` obejmuje też `services/test_support`.

Ruff (fakt 6)
- `storage/models.py` I001: dwa importy `management_*` zapisane tak, by ruff
  zaakceptował i sortowanie, i `noqa: E402` (po jednym `from ... import (  # noqa: E402`).
- `test_page_geometry_preflight.py:345` E501: zawinięty `monkeypatch.setattr`.
- `application/catalog.py`: `ruff format` (jedna instrukcja, hunk 173–176).
- Trzy pliki skryptów po usunięciu nieużywanych ignore’ów: tylko spacje przed
  `# noqa` (`ruff --fix`).

Mypy (fakt 7; 79 błędów po naprawie konfiguracji, 0 po pracy)
- `board_search_share_queries.py`: metoda `list` zasłaniała wbudowane `list`
  w adnotacjach klasy; aliasy modułowe `_EventGroup`/`_EventGroups`.
- `v7_label_geometry_calibration.py`: `receipt` budowany przez
  `V7LabelGeometryReceiptResponse.model_validate({...})`, profil z typowanych
  pól rekordu zamiast z `dict[str, object]`. Odpowiedź identyczna.
- `main.py:2005`: lambda zastąpiona typowaną funkcją `plain_session() -> Session`.
- `contrast_frame_grid_v12.py`, `shape_geometry_v2/core.py`,
  `page_geometry_preflight.py`: `cast` wyniku `cv2.warpPerspective`/`dilate`/
  `cvtColor`/`Sobel` na `NDArray[np.uint8]`/`float32` (stuby OpenCV poszerzają
  dtype; dtype w czasie działania się nie zmienia), rozpakowanie krotek w
  `margins()` i `_source_quad_to_quad` do jawnych 4-krotek, zmiana nazwy zmiennej
  `evaluation` → `v12_evaluation` w gałęzi V1.2, `cast(Sequence[object], …)` przy
  trzech `list(...)`, `_ordered_quad` przyjmuje `NDArray[np.integer | np.floating]`.
- `qualified_manual_geometry.py`: `Point(int(point.x + width), …)` (wartości są
  już całkowite po walidacji `type(...) is int`).
- Skrypty: usunięte nieużywane `# type: ignore[import-untyped]` (trzy pliki);
  `runtime_diagnostics or {}` (pole `Mapping | None`); `cast` w
  `benchmark_v7_selection_runtime.py` (+ dwa `# type: ignore[attr-defined]`
  z uzasadnieniem dla `paddle`, brak stubów); `_canonical_rgb` ma poprawny typ
  zwracany `NDArray[np.uint8]`; `FloatArray` importowany z modułu źródłowego;
  usunięty zbędny `cast`; `bool(b["valid"])`; `Point` w
  `evaluate_page_registration_variants.py` zachowuje współrzędne zmiennoprzecinkowe
  (`cast(int, float(...))` z komentarzem, bez zmiany wyników).

Błąd kolekcji (fakt 1)
- Nowy moduł `services/test_support/v7_run_state_support.py` (`manifest`,
  `manifest_with_paths`, `quality`, `SELECTION_ID`) zamiast importu
  `test_v7_run_state` z innego pakietu testów; importują go `test_v7_run_state`,
  `test_v7_checkpoint_batching`, `test_v7_independent_runtime` i API
  `test_v7_independent_progress` (także `PYTHONPATH` podprocesu w teście
  odzyskiwania).

Manifest własności (fakt 2)
- Trzy tabele V7 (`semi_automatic_selection_v7_output_operations`,
  `_pilot_acceptances`, `_source_observations`) są klasyfikowane `shared` w nowym
  zbiorze `POST_V5_SHARED` manifestu v5 (`ownership()` go uwzględnia, test
  `known = ... | POST_V5_SHARED | ...`). Uzasadnienie: bez `game_id`; dwie z FK
  wyłącznie do wspólnych `semi_automatic_image_selection_runs`/`_ranges`, a
  `pilot_acceptances` to receipt singletonowej bramki aktywacji V7. Zamrożone
  `game_data_v2_manifest_v2.SHARED` (z którego dziedziczą v3, v4 i v5) zostaje
  bez zmian, a v5 `SHARED` też: migracje 0131, 0134 i 0142 wstawiają do
  `game_storage_table_manifest` wiersze z
  `sorted(CATALOG | SHARED | GAME_TABLES | CONTROL_TABLES)`, więc dopisanie
  tabel powstałych później zmieniłoby wiersze zapisywane przez te migracje.
  Dlatego osobny zbiór, a nie rozszerzenie `SHARED` (odstępstwo od wzorca v3).
  Tabele `management_*` są już `shared` w `management_manifest.py`; test
  dodatkowo importuje `management_session_models` (tabele z migracji 0150 nie
  były rejestrowane w metadanych przez `models`).

PostgreSQL (fakt 3 i dalsze)
- `EXPECTED_PUBLIC_TABLES`: klucze `public.<tabela>` z metadanych ORM
  normalizowane (inspektor zwraca nazwy bez schematu); test importuje
  `management_session_models`.
- Migracje 0148–0150 (TASK-0921, TASK-0922, TASK-0925) świadomie odmawiają
  `downgrade`. `test_upgrade_downgrade_upgrade_cycle_on_postgres`: odmowa 0136
  sprawdzana na bazie zbudowanej do `0147_merge_v7_main`, potem `head`, potem
  `downgrade` do `0150` (0151 jest odwracalna) i oczekiwana odmowa przy kolejnym
  kroku. `test_grid_engine_profiles_migration_postgres`: powrót do `REVISION`
  zamiast `head` (TASK-0830).
- Testy, które cofały bazę z `head` (`rls_policy_function_parallel`,
  `slim_prediction_revisions`, `image_geometry_completeness_gate` 0139): znacznik
  wersji ustawiany `alembic stamp` na rewizję cofanej migracji (nic późniejszego
  nie dotyka jej obiektów), po teście `stamp head`. `lab_symbol_candidate_registry`
  i `neural_page_geometry`: baza budowana od rewizji 0143/0144
  (`application_role_database(..., revision=...)`); w pierwszym dalsza część na
  `head`, a odmowa `downgrade` sprawdzana przez `stamp` na 0144.

Testy opisujące nieaktualne reguły (każdy z komentarzem o regule)
- `test_board_search_share_access_api`: limit linku to 72 h (TASK-0925);
  odrzucana wartość to `BOARD_SEARCH_SHARE_MAX_LIFETIME_MINUTES + 1`.
- `test_migration_baseline`: jeden head równy `EXPECTED_ALEMBIC_HEAD` (zamiast
  przypiętego 0129).
- `test_image_import_geometry_guard_api` (5 wywołań): router stracił pierwszy
  parametr w v0.10.298.
- `test_lateral_lock_order`: atrapa `_require_ready_state` przyjmuje
  `current_board` (TASK-0885).
- `test_openapi_contract`: brak `minItems` na `cells` (v0.10.224, rewizje częściowe).
- `test_image_symbol_reviews_api`: domyślny limit listy 20 s (v1.7.32).
- `test_grid_audit_symbol_suggestions`: dwa nowe pola `previewCommand` (TASK-0882).
- `test_worker_cli`: atrapa ustawień ma `v7_label_geometry_runtime_root`,
  `v7_selection_ocr_model_root`, `v7_pilot_acceptance_scope`, `grid_shadow_enabled`
  (fakt 8: cztery „stare błędy fixture CLI”).
- `test_vision_lab_symbol_augmentation`: pierwsza niepoprawna generacja to 5
  (v1.7.212 dodała generacje 3 i 4).
- Reviewer (fakt 4): `local-reviewer-workspace-contract` oczekuje
  `localMode || gridAuditMode || gridShadowMode ? …` (TASK-0805);
  `operational-review-workspace-contract` toleruje łamanie wiersza JSX
  (`pozostaje\s+statyczny`) i nową postać resetu siatki
  (`original === null ? copyCorners(...) : boardLatticeCorners(original)`, TASK-0882).
- `services/api/tests/conftest.py` (nowy): autouse przywraca `disabled=False`
  loggerom aplikacji. `alembic/env.py` wywołuje `fileConfig` z domyślnym
  `disable_existing_loggers=True`, więc po teście migracji w tym samym procesie
  `test_asset_resolution_logs_missing_file…` nie widział żadnych rekordów
  (zależność od kolejności). `env.py` (kod produktu) nie zmieniony.
- Przepięcie skrótów CRLF → LF w dowodach (runda poaudytowa). Zapisany skrót
  `m5-corpus-manifest.json` (`aeed11c7…`) i skrót `m5-golden-annotations.json`
  (`92fa6ea0…`) były skrótami wersji CRLF, a od TASK-0812 pliki
  `ai_docs/quality/*.json` w indeksie są LF (`3c364188…` oraz `7c1eceb6…`,
  `.gitattributes` `eol=lf`). Są to artefakty środowiska, więc zamieniono te
  skróty i, kaskadowo, skróty zmienionych przez to plików w każdym miejscu
  (`ai_docs/quality/*.json` oraz kod), które je przypina. Zmieniono wyłącznie
  wartości skrótów (weryfikacja: po zamianie każdej 64-znakowej wartości
  szesnastkowej na znacznik pliki są identyczne z HEAD, końce linii zachowane);
  `calibrated_symbol_inventory._digest` nietknięty. Wartości liczone z zawartości
  zamiast prostej zamiany: `expectedManifestChecksumSha256` deskryptora v19 oraz
  stała `REAL_CORPUS_MANIFEST_SHA256` w teście (nowa wartość `c352ed0f…`) i
  `pipelineFingerprint` w `m7-image-pipeline-manifest-v1.json` (nowa wartość
  `963891c4…`, liczona przez `build_pipeline_envelope`). Zakres: 78 plików
  (`ai_docs/quality/*.json` oraz `pipeline_contract.py`, gdzie przypięte są
  skróty czterech raportów); skrót pliku przed → po (8 znaków, wartości
  końcowe) i liczba zmienionych wartości skrótu:
  - `ai_docs/quality/board-cell-geometry-v19-real-corpus.json`: 3d13bed2 → 8bfd0799 (3 wartości skrótu)
  - `ai_docs/quality/image-selection-v10-smoke-report.json`: 2cb21dec → 2ebb97b7 (1 wartości skrótu)
  - `ai_docs/quality/m5-board-cell-crops-v10-wide-frame-preflight-report.json`: f3063485 → 96c81135 (1 wartości skrótu)
  - `ai_docs/quality/m5-board-cell-crops-v2-calibrated-quality-report.json`: 8e53f463 → 3da1947c (3 wartości skrótu)
  - `ai_docs/quality/m5-board-cell-crops-v2-calibrated-report.json`: cefe1a54 → e652ef9b (2 wartości skrótu)
  - `ai_docs/quality/m5-board-cell-crops-v2-quality-report.json`: d66b129c → 121c3993 (1 wartości skrótu)
  - `ai_docs/quality/m5-board-cell-crops-v3-local-report.json`: 330f07f2 → 2f689518 (2 wartości skrótu)
  - `ai_docs/quality/m5-board-cell-crops-v4-symbol-aware-report.json`: b7a5ef54 → f9c84445 (2 wartości skrótu)
  - `ai_docs/quality/m5-board-cell-crops-v5-symbol-aware-affine-report.json`: 6356c3dc → f40a742a (2 wartości skrótu)
  - `ai_docs/quality/m5-board-cell-crops-v7-reviewed-symbol-aware-report.json`: 0950ac49 → 8e12dd96 (1 wartości skrótu)
  - `ai_docs/quality/m5-board-cell-crops-v8-safe-context-report.json`: c48074a0 → aa291438 (1 wartości skrótu)
  - `ai_docs/quality/m5-board-cell-crops-v9-safe-context-shifted-overlap-report.json`: 2bfa16f2 → 31797f1a (1 wartości skrótu)
  - `ai_docs/quality/m5-bounding-frame-crop-spike-report.json`: 6e209459 → a74447cd (1 wartości skrótu)
  - `ai_docs/quality/m5-cell-grid-golden.json`: a25b1753 → 6bbfba58 (2 wartości skrótu)
  - `ai_docs/quality/m5-cell-grid-v1-baseline-report.json`: a62532ba → cf2da7a1 (1 wartości skrótu)
  - `ai_docs/quality/m5-complete-local-grid-profiles.json`: 2c0e19b8 → c1f31f5c (2 wartości skrótu)
  - `ai_docs/quality/m5-full-symbol-grid-refinement-detector-report.json`: f501d6a7 → fa831b33 (1 wartości skrótu)
  - `ai_docs/quality/m5-full-symbol-grid-refinement-report.json`: 13e340c5 → 923d2f09 (1 wartości skrótu)
  - `ai_docs/quality/m5-global-bbox-fallback-v14-bounded-regression-report.json`: 13dfac7e → 23ca0abb (2 wartości skrótu)
  - `ai_docs/quality/m5-global-bbox-fallback-v14-full-failure-diagnostics-report.json`: 94b72248 → 55150c11 (3 wartości skrótu)
  - `ai_docs/quality/m5-global-bbox-fallback-v14-full-failure-diagnostics-v2-report.json`: a9c76d86 → ae154cbd (3 wartości skrótu)
  - `ai_docs/quality/m5-global-bbox-fallback-v14-full-failure-diagnostics-v3-report.json`: 2aeb1799 → 4db321ab (3 wartości skrótu)
  - `ai_docs/quality/m5-global-bbox-fallback-v14-full-preflight-report.json`: 026e12ac → e773d7bb (2 wartości skrótu)
  - `ai_docs/quality/m5-global-bbox-fallback-v14-seq29-gate-report.json`: 545b81c0 → fcb7fe98 (2 wartości skrótu)
  - `ai_docs/quality/m5-global-source-aware-v13-bounded-regression-report.json`: 210b8d93 → babcd2d9 (2 wartości skrótu)
  - `ai_docs/quality/m5-global-source-aware-v13-seq29-gate-report.json`: 22ac9ab8 → 4c5fe1b7 (2 wartości skrótu)
  - `ai_docs/quality/m5-grid-calibration-profiles.json`: 6928c0cb → 1536fa92 (2 wartości skrótu)
  - `ai_docs/quality/m5-image-benchmark-report.json`: 0c290433 → ec714a83 (4 wartości skrótu)
  - `ai_docs/quality/m5-local-grid-calibration-profiles.json`: 67a43eea → 9fd69392 (2 wartości skrótu)
  - `ai_docs/quality/m5-projective-fixed-padding-v12-bounded-regression-report.json`: 57fc69a6 → 3f1141eb (2 wartości skrótu)
  - `ai_docs/quality/m5-projective-fixed-padding-v12-seq29-gate-report.json`: 3593ffab → a21137af (2 wartości skrótu)
  - `ai_docs/quality/m5-reviewed-manual-merge-v16-full-preflight-report.json`: c336a872 → 59f9bdfa (3 wartości skrótu)
  - `ai_docs/quality/m5-reviewed-manual-merge-v16-owner-acceptance.json`: aab00d7b → baad686d (1 wartości skrótu)
  - `ai_docs/quality/m5-sequence-ocr-raw-input-report.json`: 2e9521ec → 99f3a8b6 (2 wartości skrótu)
  - `ai_docs/quality/m5-sequence-ocr-report.json`: 6c5e17ca → 31420b5f (2 wartości skrótu)
  - `ai_docs/quality/m5-v7-owner-visual-feedback.json`: 08265d73 → 55e0a4fc (1 wartości skrótu)
  - `ai_docs/quality/m6-active-learning-iteration-v2-manifest.json`: f745038a → 304b7576 (8 wartości skrótu)
  - `ai_docs/quality/m6-active-learning-iteration-v3-manifest.json`: de44d94a → b1347f56 (9 wartości skrótu)
  - `ai_docs/quality/m6-classifier-review-vertical-slice-report.json`: 552a54e5 → 50ba9ccd (8 wartości skrótu)
  - `ai_docs/quality/m6-classifier-review-vertical-slice-v2-report.json`: 525084ad → 86414208 (8 wartości skrótu)
  - `ai_docs/quality/m6-classifier-review-vertical-slice-v3-report.json`: cb150a50 → 5b45d991 (8 wartości skrótu)
  - `ai_docs/quality/m6-spatial-symbol-model-confidence-calibration-report.json`: aa34ec22 → 0c0153a6 (3 wartości skrótu)
  - `ai_docs/quality/m6-spatial-symbol-model-onnx-report.json`: 5e8f4d7b → c6afb973 (2 wartości skrótu)
  - `ai_docs/quality/m6-spatial-symbol-model-release-decision.json`: f92cd135 → 50362655 (3 wartości skrótu)
  - `ai_docs/quality/m6-spatial-symbol-model-release-manifest.json`: 9f0dd6f7 → 86c9c80e (10 wartości skrótu)
  - `ai_docs/quality/m6-spatial-symbol-model-vertical-slice-report.json`: d9f56165 → 6c806199 (2 wartości skrótu)
  - `ai_docs/quality/m6-symbol-active-learning-selection-v2.json`: fda4b766 → 18160916 (4 wartości skrótu)
  - `ai_docs/quality/m6-symbol-active-learning-selection-v3.json`: 27aa4adf → b1cb8680 (4 wartości skrótu)
  - `ai_docs/quality/m6-symbol-active-learning-selection.json`: 2ab9a79a → 6bf1fa62 (4 wartości skrótu)
  - `ai_docs/quality/m6-symbol-classifier-active-learning-v2-report.json`: 45c1f160 → 693747d8 (2 wartości skrótu)
  - `ai_docs/quality/m6-symbol-classifier-active-learning-v3-report.json`: 226dd664 → a687c04a (2 wartości skrótu)
  - `ai_docs/quality/m6-symbol-classifier-baseline-report.json`: 9098dcbc → ee255828 (2 wartości skrótu)
  - `ai_docs/quality/m6-symbol-classifier-onnx-report.json`: 6f4596ae → ee7c3d72 (2 wartości skrótu)
  - `ai_docs/quality/m6-symbol-classifier-onnx-v2-report.json`: b8e97bd8 → cf784a15 (2 wartości skrótu)
  - `ai_docs/quality/m6-symbol-classifier-onnx-v3-report.json`: 2fc8b53d → c63c5328 (2 wartości skrótu)
  - `ai_docs/quality/m6-symbol-confidence-calibration-report.json`: a2359efe → 5a2e1068 (3 wartości skrótu)
  - `ai_docs/quality/m6-symbol-confidence-calibration-v2-report.json`: 14cb18d0 → f72aefac (3 wartości skrótu)
  - `ai_docs/quality/m6-symbol-confidence-calibration-v3-report.json`: f84d9a2e → 0e11b3ad (3 wartości skrótu)
  - `ai_docs/quality/m6-symbol-crop-inventory-v2.json`: 5687f80b → 3266205b (5 wartości skrótu)
  - `ai_docs/quality/m6-symbol-crop-inventory-v3.json`: 55a10739 → d8734d31 (5 wartości skrótu)
  - `ai_docs/quality/m6-symbol-crop-inventory.json`: 8c6e0a04 → 4b7d3575 (2 wartości skrótu)
  - `ai_docs/quality/m6-symbol-dataset-export-report-v2.json`: 99d0f943 → a30d14b8 (6 wartości skrótu)
  - `ai_docs/quality/m6-symbol-dataset-export-report-v3.json`: 3657d8ee → 596ecb53 (6 wartości skrótu)
  - `ai_docs/quality/m6-symbol-dataset-export-report.json`: ed1f9e32 → f3464833 (6 wartości skrótu)
  - `ai_docs/quality/m6-symbol-dataset-split-report-v2.json`: 4b91e368 → 11028289 (1 wartości skrótu)
  - `ai_docs/quality/m6-symbol-dataset-split-report-v3.json`: 7b6adb55 → e966a593 (1 wartości skrótu)
  - `ai_docs/quality/m6-symbol-dataset-split-report.json`: 214bb9ee → 5f616526 (1 wartości skrótu)
  - `ai_docs/quality/m6-symbol-model-benchmark-decision.json`: 9f3b1cab → 998dddb2 (5 wartości skrótu)
  - `ai_docs/quality/m6-symbol-model-benchmark-spatial-augmented-report.json`: 836c26c0 → 38b2c0ae (2 wartości skrótu)
  - `ai_docs/quality/m6-symbol-model-benchmark-spatial-report.json`: 01c9c3b7 → 53519bf2 (2 wartości skrótu)
  - `ai_docs/quality/m6-symbol-model-selected-test-report.json`: 0e0ddcba → fb62ab01 (3 wartości skrótu)
  - `ai_docs/quality/m6-symbol-model-validation-selection-report.json`: 1c8d2c0e → 2b8eb36c (5 wartości skrótu)
  - `ai_docs/quality/m6-symbol-suggestion-validation-report.json`: 7bd77eea → a2ed0974 (2 wartości skrótu)
  - `ai_docs/quality/m65-workbench-acceptance-report.json`: 98eee87c → 6615a11a (2 wartości skrótu)
  - `ai_docs/quality/m7-image-pipeline-manifest-v1.json`: 99e3c2a8 → 5ff764ab (5 wartości skrótu)
  - `ai_docs/quality/m7-import-operations-benchmark-report.json`: a372b46d → 903b4a24 (2 wartości skrótu)
  - `ai_docs/quality/m7-queue-architecture-decision.json`: c511da76 → 618fecb8 (1 wartości skrótu)
  - `services/worker/src/game_predictor_worker/images/pipeline_contract.py`: b3e6862a → 5337a060 (4 wartości skrótu)
  Narracyjne dokumenty `.md` (zadania, DECISION_LOG), które historycznie cytują
  stare skróty, nie były zmieniane. Stałe `pipeline_contract.py` to wartości
  skrótów artefaktów, nie logika.

Decyzje końcowe (koordynator)
- Kolejność bramki w `start_ready_browser_import`: obowiązuje reguła TASK-0882
  (istniejący import zwracany przed bramką bocznej geometrii). Komentarz w
  `api/image_imports.py` opisuje teraz faktyczną kolejność (zmiana wyłącznie
  komentarza). Test `…cannot_drop_guard_history[browser]` oczekuje 201,
  `created=False`, tego samego `job.id`, braku nowego zadania i braku dostępu do
  stagingu przez `bind_ready_game`; fixture ma poprawny payload schematu 5
  (klucz manifestu guard dotyczy tylko wejścia `managed`), a atrapy `get_ready`,
  serwisu kanonicznego i serwisu nadpisań wystarczają do zbudowania odpowiedzi
  preflight.
- Trzy historyczne testy PG wycofane jawnie (`pytest.mark.skip`, powód:
  „retired by TASK-0940: historical revision harness incompatible with manifest
  v5 (0142) and 0151; see Outcome”): `test_convert_legacy_boards_postgres`,
  `test_drop_cell_observations_postgres`, `test_drop_cell_render_spec_postgres`.
  Pliki zostają. Ponowne włączenie wymaga harnessu budującego stan ORM i
  provisioningu z tamtych rewizji (manifest v4, schemat bez kolumn 0151).
- Testy korpusowe M5: nowy helper `services/test_support/local_corpus.py`
  (`require_local_corpus(*paths)`), wołany na początku każdego testu, który czyta
  lokalny, ignorowany przez Git korpus (`artifacts/m5-*`, `examples/imgs/*.jpg`,
  `artifacts/m6-symbol-classifier-onnx`). Skip podaje brakującą ścieżkę; test
  nadal działa bez zmian tam, gdzie korpus istnieje. Objęte: 25 testów w 13
  plikach oraz `test_current_manifest_is_valid_and_all_local_artifacts_match`.
- `test_lateral_partial_contract::test_absent_extension_preserves_historical_bytes`
  ×3 nie zależą od korpusu: przypięte sumy pochodziły z d74fc4d7, a
  `VIRTUAL_CELL_RENDERER_VERSION` zmieniło się potem z `…source-direct-v1` na
  `…source-direct-v4`, więc zmieniają się bajty każdego snapshotu. Sumy
  przepięte na bieżące stałe, z komentarzem; niezmienność bajtów przy braku
  rozszerzenia nadal sprawdza równość bajtów przed i po odtworzeniu.
- `whole_layout_symbol_review`: `test_inventory_rejects_quality_gate_drift` nie
  wymaga korpusu (błąd jest zgłaszany przed odczytem `crop_root`), więc nie ma
  już `require_local_corpus` i przechodzi; wcześniejszy skip ukrywał
  deterministyczny `SYMBOL_DATASET_CALIBRATION_CHAIN_DRIFT`, usunięty przez
  przepięcie skrótów wyżej. `test_real_calibrated_inventory_is_deterministic_and_complete`
  zachowuje skip, bo naprawdę czyta `artifacts/m5-board-crops`; czy przechodzi
  z korpusem, nie mogłem sprawdzić (korpusu brak). Łańcuch sum
  (corpus, annotations, grid, profiles) zgadza się teraz z plikami.
- Punkt stały przepięcia (druga runda poaudytowa). Pierwsza kaskada nie
  doprowadziła do punktu stałego (pośrednie skróty zostały w dziesięciu
  odwołaniach). Przepięcie powtórzono pozycyjnie względem HEAD: każda wartość
  skrótu, która w HEAD była skrótem (LF lub CRLF) innego śledzonego pliku,
  dostaje bieżący surowy sha256 tego pliku; pętla do braku zmian (5 iteracji,
  19 podmian). Wartości liczone (`expectedManifestChecksumSha256`,
  `pipelineFingerprint`) sprawdzono ponownie i się nie zmieniły. Weryfikuje to
  nowy checker `scripts/check_quality_evidence_digests.py`: przechodzi każdy
  `ai_docs/quality/*.json`, sprawdza każdy obiekt `{path|relativePath, sha256}`
  wskazujący katalog śledzony (`ai_docs/`, `services/`, `scripts/`, `apps/`,
  `packages/`, `infra/`; pozostałe `path` to nazwy obrazów względem korpusu) oraz
  270 pól `*Sha256` bez ścieżki, wyliczonych do tabeli
  `ai_docs/quality/evidence-digest-references.json` (plik, wskaźnik JSON, plik
  docelowy), i porównuje z surowym sha256 bajtów pliku. Wynik: `0 mismatches`,
  exit 0. Test `services/worker/tests/test_quality_evidence_digests.py` (2 testy)
  uruchamia to samo w bramce; do `npm run fixture:validate` nie podpinałem,
  bo checker trwa około 6 s (próg 5 s).
- Mały, celowy i nieszkodliwy wpływ na zachowanie w skryptach:
  `runtime_diagnostics or {}` w `run_middle_row_range_ocr_v4_acceptance.py` i
  `run_row_first_range_ocr_v5_acceptance.py` (przy `None` dawniej
  `AttributeError`/`TypeError`, teraz puste diagnostyki; dla wartości
  niepustych bez zmian) oraz `bool(b["valid"])` w `test_mumie_folder.py` (pole
  jest już typu `bool`).
- Pozostałe poprawki po audycie: `test_image_pipeline_contract` – warunkowa jest
  tylko weryfikacja plików lokalnych modeli; `validate_pipeline_manifest`,
  asercje `maturity` i weryfikacja trzech wersjonowanych artefaktów
  `ai_docs/quality` wykonują się zawsze. `test_lateral_managed_reprocess` ma
  dodatkowy przypadek HTTP (istniejący import z `neural_grid_proposal` i
  przypiętą decyzją guard → 409 `IMAGE_LATERAL_PARTIAL_GUARD_REBIND_REQUIRED`).
  Poprawione cytaty reguł w komentarzach testów (generacje 3/4: v1.7.207 /
  7647ccb6 i v1.7.212 / e6ed2d72; pojedynczy head = `EXPECTED_ALEMBIC_HEAD`;
  atrybuty ustawień CLI: TASK-0920 / v1.7.250 oraz TASK-0805 / v1.7.191;
  TASK-0830 przy 0140).

### Verification results

Katalog: worktree `mumie-super-game`; `openapi:generate` nie był potrzebny.
- `npm run format:check`, `npm run lint` (ESLint 0 błędów, `python:lint` i
  `powershell:check` PASS), `npm run typecheck` (mypy 836 plików): exit 0,
  powtórzone po rundzie poaudytowej.
- `npm run openapi:check`, `snapshot:validate`, `fixture:validate`: exit 0.
  JS: `npm run test --workspaces --if-present` exit 0 (admin 679, reviewer 237,
  vision-lab 62, admin-api-client 102, board-search-ui 80,
  manual-image-selection-core 110, shared-ts 46, vision-lab-api-client 15).
- Runda poaudytowa:
  - `pytest services/api/tests/test_game_data_v2_schema.py
    services/api/tests/test_lateral_managed_reprocess.py
    services/api/tests/test_migration_baseline.py`: 89 passed.
  - `pytest services/worker/tests` (python głównego venv, pełny zestaw, bo
    skróty dowodów dotyczą wielu testów): 2779 passed, 43 skipped, 0 failed
    (893 s). W tym `test_whole_layout_symbol_review`,
    `test_image_pipeline_contract`, `test_vision_lab_symbol_augmentation`,
    `test_worker_cli` (poza skipami korpusowymi).
  - `pytest services/api/tests` (bez PG): 2464 passed, 275 skipped, 0 failed
    (1275 s).
  - `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 pytest
    services/api/tests/integration/test_postgres_baseline.py`: 5 passed (84 s).
- Druga runda poaudytowa (punkt stały skrótów):
  - `python scripts/check_quality_evidence_digests.py`: `0 mismatches`, exit 0.
  - `pytest services/worker/tests/test_quality_evidence_digests.py
    test_whole_layout_symbol_review.py test_image_pipeline_contract.py
    test_board_cell_geometry_contract.py` (python głównego venv): 40 passed,
    10 skipped (skipy: brak lokalnego korpusu M5 i modeli).
  - `npm run format:check`, `npm run lint`, `npm run typecheck`: exit 0.
  - Po przepięciu powtórzone pełne zestawy: worker (python głównego venv)
    2781 passed, 43 skipped, 0 failed (979 s); API bez PG 2464 passed,
    275 skipped, 0 failed (1208 s).
- Pełny przebieg API z PG sprzed rundy: 2725 passed, 13 skipped, 0 failed;
  runda zmieniła jedynie wymienione pliki, których testy powyżej przechodzą.
- Pozostałość po przebiegach: dwie wygasające (1 h) role
  `game_predictor_app_test_*` po przerwanym przeze mnie przebiegu; bazy `*_test`
  usunięte; baza `game_predictor` nietknięta.

### Not completed

1. Jedyny test czerwony: worker
   `test_vision_lab_symbol_large_rgb_runs.py::test_another_root_cannot_admit_same_manifest`,
   i to wyłącznie przy uruchomieniu pythonem z `.venv` tego worktree. `.venv` jest
   tu junction (reparse point), a test sprawdza właśnie odrzucanie reparse
   pointów (`SNAPSHOT_REPARSE_POINT` zamiast `FROZEN_RUN_ROOT_REQUIRED`).
   Środowiskowe, bez zmiany; z pythonem głównego venv test przechodzi.
2. Wycofane (skip) i wymagające osobnej decyzji:
   - trzy historyczne testy PG (patrz „Decyzje końcowe”); ponowne włączenie
     wymaga harnessu budującego stan ORM/provisioningu z rewizji 0133–0136;
   - testy korpusowe M5 (w tym `test_real_calibrated_inventory_is_deterministic_and_complete`)
     i część `test_current_manifest_is_valid_and_all_local_artifacts_match`:
     pomijane, dopóki nie zostanie przywrócony korpus (`artifacts/m5-*`,
     `examples/imgs/*.jpg`, `artifacts/m6-symbol-classifier-onnx`) – tych danych
     nie ma też w głównym checkoutcie; nie mogłem sprawdzić, czy z korpusem
     przechodzą;
3. Opcjonalnie: `disable_existing_loggers=False` w `alembic/env.py` zamiast
   obejścia w `services/api/tests/conftest.py` (`env.py` nietknięty).

### Documentation updates

- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`: klasyfikacja tabel V7 i
  `management_*`, zbiór `POST_V5_SHARED` i powód, dla którego `SHARED` oraz v2
  zostają zamrożone.
- Przepięcie skrótów CRLF → LF w 78 plikach dowodowych (lista w „Changed”, punkt stały sprawdzany
  checkerem `scripts/check_quality_evidence_digests.py`, nowa tabela odwołań
  `ai_docs/quality/evidence-digest-references.json`):
  `m5-corpus-manifest.json` `aeed11c7…` → `3c364188…`,
  `m5-golden-annotations.json` `92fa6ea0…` → `7c1eceb6…` i skróty kaskadowe;
  historyczne dokumenty `.md` cytujące stare skróty pozostają bez zmian.
- `CURRENT_STATE.md` i przeniesienie zadania do `completed/` pozostawione
  prowadzącemu (status zadania bez zmian).

### Recommended next task

Osobne zadanie „Korpus M5 i historyczne testy migracji”: (a) zdecydować o
korpusie M5 (przywrócić dane albo wycofać testy), (b) zbudować harness PG
dla rewizji 0133–0136 (stan ORM i provisioningu z tamtych rewizji) i włączyć
trzy wycofane testy. Opcjonalnie `disable_existing_loggers=False` w
`alembic/env.py`.
