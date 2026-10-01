---
title: TASK-0758 — S4 — przepięcie czytelników z `cell_observations` na manifest renderu
status: done
last_updated: 2026-10-01
---

# TASK-0758 — S4 — przepięcie czytelników z `cell_observations` na manifest renderu

## Status

`done` (audyt Opus PASS, commit v1.7.113; cutover: migracja `0132` oraz kompletny backfill manifestów na bazie
operatora)

## Goal

Żaden czytelnik runtime nie zależy od `cell_observations` poza izolowanym
adapterem plansz `legacy_file` na rewizji 0, tak aby S5 mógł usunąć tabelę.

## Context

D-467, S4, drugie zadanie. TASK-0757 dodał `board_render_manifests`
(manifest bieżącej rewizji każdej wirtualnej planszy, reguła „brak manifestu
⇔ brak renderowalnych komórek”). Do tego zadania mapper Reviewera, projekcja
weryfikacji symboli, wyszukiwarka plansz, przeliczanie predykcji, ręczna
geometria, rekonsyliacja plansz częściowych i biblioteka wzorców symboli
czytały obserwacje.

## Dependencies / entry conditions

- Fakt: HEAD `v1.7.111` (TASK-0757), `alembic heads` = `0131` przed
  zadaniem.
- Fakt (odczyt bazy operatora 2026-10-01, tylko `SELECT`): 777 ma 461 plansz
  `legacy_file`, wszystkie na rewizji 1 (297) lub 2 (164), po 15 obserwacji;
  dla wszystkich 6 915 obserwacji ścieżka, suma i wersja croppera są równe
  `crop_artifacts` bieżącej rewizji, a `prediction` jest równe wpisowi
  `cells_prediction.cells` o tej samej pozycji. Próbka ok. 480 tys.
  obserwacji plansz wirtualnych (rewizja 0 i > 0, wszystkie częściowe):
  100% zgodności `prediction` z `cells_prediction`.
- Fakt: plansz `legacy_file` na rewizji 0 jest 0; tworzy je tylko import z
  polityką `legacy`, fixture benchmarków (`real_workbench_fixture`,
  `workbench_acceptance`) i testy.
- Warunek cutoveru (nie zadania): backfill manifestów dla 777 zakończony
  (w chwili pracy trwał w tle); bez niego plansze wirtualne bez manifestu
  kończą się `IMAGE_REVIEW_RENDER_MANIFEST_MISSING`.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo). Audyt: `claude-opus-5-5`,
`high`, osobny agent.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md` (S4, S5)
- `ai_docs/process/DECISION_LOG.md` (D-467)
- `ai_docs/tasks/0757-board-render-manifests.md`

## Scope

- Odczyt manifestu: `storage/board_render_manifest_reader.py`
  (`CurrentBoardRenderManifest`, odczyt po `game_id` + `recognized_board_id`
  + bieżąca rewizja, kontrola kształtu).
- Izolowany adapter legacy: `storage/legacy_cell_observation_adapter.py`
  (jedyny czytelnik runtime `cell_observations`).
- Pakiet wejść mappera: `storage/current_board_cell_sources.py`.
- Przepięcie: `materialize_current_image_review_cells` /
  `_virtual_current_cells_from_records` / `_item_from_records`,
  `image_symbol_review_repository` (`_current_cells`, `_cell_values`,
  `_current_cropper_version`, `_selected_items_with_stale_base_crop`),
  `board_search_projection_repository`, `pending_symbol_reinference`,
  `partial_board_reconciliation_repository`, `virtual_grid_geometry_repository`
  (odczyt specyfikacji rewizji 0), `symbol_references_repository`,
  `scripts/build_grid_symbol_diagnostic.py`.
- Kontrakt API pionem: usunięcie `observationId` z
  `OperationalImageReviewCellResponse`; kandydat wzorca symbolu
  `observationId` → `cellReviewId`, ścieżki
  `…/approved-image-candidates/{cell_review_id}/asset|selection`; OpenAPI,
  wygenerowany klient, wrapper `packages/admin-api-client/src/index.ts`,
  Admin (`symbol-image-picker-modal.tsx`), testy.
- Migracja `0132_symbol_reference_images_cell_identity` (usunięcie
  `source_observation_id` i FK do `cell_observations`), `EXPECTED_ALEMBIC_HEAD`.

## Out of scope

- Usunięcie `cell_observations`, writerów obserwacji, adaptera legacy,
  wpisów w `cleanup_repository`, `game_deletion_policy_v1`,
  `symbol_review_statistics` (S5, TASK-0759).
- Narzędzia historyczne (`image_geometry_rollout_backfill_repository`,
  `additive_virtual_geometry_diagnostics`) i backfill manifestów (czyta
  obserwacje jako źródło; po S5 zbędny).
- Konwersja 461 plansz legacy i zmiana polityki importu (S6).

## Acceptance criteria

- [x] `git grep "CellObservationModel\|cell_observations"` w `services/*/src`
      zwraca tylko: model, writery, adapter legacy, listy tabel
      cleanup/usuwania/statystyk, narzędzia historyczne, backfill manifestów,
      fixture benchmarków (writery) i komentarze (lista w Outcome).
- [x] Test równoważności PostgreSQL: komórki mappera (wszystkie pola
      `ImageReviewCell`), rekordy przeliczania, dokument wyszukiwarki,
      wersja croppera i werdykt stale-base-crop identyczne dla starego
      (git `f2336115`) i nowego kodu.
- [x] Próbka tylko do odczytu na bazie operatora: ok. 1 100 plansz, 0 różnic
      poza udokumentowaną poprawką przeliczania.
- [x] Reguła braku manifestu pokryta testami jednostkowymi każdej funkcji.
- [x] Kontrakt API: backend, OpenAPI, klient, wrapper, Admin, test żądania.

## Technical notes

- **Decyzja dla plansz legacy.** Plansze `legacy_file` z rewizją > 0 (461
  w 777) czytają cropy z `crop_artifacts` bieżącej rewizji (jak dotąd) i
  predykcje z `cells_prediction` (zamiast obserwacji; dane zweryfikowane 1:1).
  Tylko plansza `legacy_file` na rewizji 0 czyta obserwacje (ścieżka, suma,
  wersja croppera, predykcja) przez `legacy_cell_observation_adapter` — w
  mapperze, wersji croppera, kontroli stale-base-crop, wyszukiwarce,
  przeliczaniu i diagnostyce v19. Takich plansz w bazie operatora jest 0.
  S5 usuwa adapter; warunek: 0 takich plansz i brak ścieżki, która je tworzy
  (TASK-0760 przed S5 albo blokada importu `legacy` i fixture benchmarków w
  S5); wtedy mapper odmawia (`IMAGE_REVIEW_CELL_COUNT_INVALID`).
- **Wirtualne plansze.** Komórki z manifestu bieżącej rewizji
  (`cropSampleId`, klucze v1/v2, `renderSpec`, sumy;
  `source_geometry_revision_id` i `extractor_version` z wiersza), predykcje
  importu z `cells_prediction` po pozycji (`rowIndex`, `columnIndex`) albo z
  najnowszej rewizji predykcji. Dla rewizji 0 `cropSampleId` manifestu jest
  sprawdzany względem wyliczenia z `renderSpecChecksumSha256`. Suma cropa =
  `renderedPixelChecksumSha256` (writer i backfill gwarantują równość z
  dawną `crop_checksum_sha256`). Brak manifestu: zero komórek, gdy plansza
  nie ma dostępnych komórek, inaczej `IMAGE_REVIEW_RENDER_MANIFEST_MISSING`.
- **Stale-base-crop.** Wirtualne plansze na rewizji 0: porównanie komórki
  weryfikacji z rozwiniętymi komórkami manifestu rewizji 0
  (`jsonb_array_elements`, jedno rozwinięcie na manifest); brak manifestu
  albo komórki = nieaktualna (jak brak obserwacji). Pomiar tylko do odczytu:
  rozwinięcie 61 tys. manifestów 777 trwało 6,6 s (ok. 40 s dla 372 tys.).
  Legacy rewizja 0: dotychczasowe zapytanie w adapterze.
- **Przeliczanie predykcji.** Rekordy `_virtual_records` z manifestu
  (prawdziwy `cellIndex`); dawna ścieżka numerowała komórki rewizji 0
  porządkowo i odrzucała plansze częściowe z maską w środku
  (`IMAGE_SYMBOL_REINFERENCE_CELLS_INCOMPLETE`) — na bazie operatora 10 z
  105 plansz częściowych (V3); teraz są przeliczane poprawnie.
- **Wyszukiwarka.** Predykcje importu z `cells_prediction`; dawne
  porównanie sumy obserwacji legacy z cropem rewizji zastąpiono wymogiem
  cropa rewizji dla każdej widocznej pozycji.
- **Rekonsyliacja plansz częściowych.** Guard zawiera zamiast obserwacji
  skrót manifestu bieżącej rewizji (rewizja, źródło geometrii, extractor,
  suma, liczba komórek); podglądy sprzed zmiany trzeba wygenerować ponownie
  (inny `guardSha256`).
- **Tożsamość komórki.** `ImageReviewCell.observation_id` usunięte
  (tożsamość = `recognized_board_id` + `cell_index`); manifest kohorty legacy
  traci klucz `observationId`. Kandydat wzorca = `image_symbol_review_cells.id`;
  kursor stronicowania ma ten sam kształt (4. element = id komórki).
  Kandydaci nie wymagają już obserwacji (komórki kwalifikowanej rewizji bez
  obserwacji stają się kandydatami).
- **Migracja `0132`.** Upgrade: `LOCK … ACCESS EXCLUSIVE`, odmowa
  `SYMBOL_REFERENCE_OBSERVATION_MISMATCH`, gdy obserwacja wiersza nie jest
  obserwacją jego komórki, potem `DROP COLUMN source_observation_id` (FK,
  klony partycji i indeks znikają razem z kolumną). Downgrade odtwarza
  kolumnę z `cell_observations` po (`board`, `cell_index`), odmawia
  `SYMBOL_REFERENCE_OBSERVATION_UNRECOVERABLE`, dodaje indeks i FK o
  dawnych nazwach. W bazie operatora tabela ma 0 wierszy. Migracja S5
  (DROP `cell_observations`) to teraz `0133`, S6 `0134`, S7 `0135`.
- **Fixture benchmarków** (`real_workbench_fixture.py`,
  `workbench_acceptance.py`): oznaczone jako legacy-only; seedują plansze
  `legacy_file` na rewizji 0, czytane przez adapter; S5 musi je przepiąć albo
  usunąć.

## Expected files

- Nowe: `services/api/src/game_predictor_api/storage/board_render_manifest_reader.py`,
  `storage/legacy_cell_observation_adapter.py`,
  `storage/current_board_cell_sources.py`,
  `services/api/alembic/versions/0132_symbol_reference_images_cell_identity.py`,
  `services/api/tests/integration/test_render_manifest_readers_postgres.py`,
  `services/api/tests/test_symbol_reference_cell_identity_migration.py`.
- Zmienione: `storage/image_review_repository.py`,
  `storage/image_symbol_review_repository.py`,
  `storage/board_search_projection_repository.py`,
  `storage/partial_board_reconciliation_repository.py`,
  `storage/virtual_grid_geometry_repository.py`,
  `storage/symbol_references_repository.py`, `storage/models.py`,
  `storage/schema_readiness.py`, `domain/image_reviews.py`,
  `domain/image_review_cohorts.py`, `domain/image_symbol_reviews.py`
  (docstring), `domain/symbol_references.py`, `schemas/image_reviews.py`,
  `schemas/symbol_references.py`, `api/symbol_references.py`,
  `application/symbol_references.py`,
  `worker/images/pending_symbol_reinference.py`,
  `worker/images/real_workbench_fixture.py`,
  `worker/images/workbench_acceptance.py`,
  `scripts/build_grid_symbol_diagnostic.py`, OpenAPI + klient +
  `packages/admin-api-client/src/index.ts`,
  `apps/admin/src/features/symbols/symbol-image-picker-modal.tsx`, testy.

## Test cases

- PostgreSQL (`test_render_manifest_readers_postgres.py`): plansze wirtualne
  rewizja 0 pełna, częściowa z maską na końcu i w środku (V1), rewizja 1
  (kopia `virtual_render_spec`), legacy rewizja 1 (manualna rezolucja),
  legacy rewizja 0; manifesty z prawdziwego backfillu; porównanie z kodem
  `f2336115` (moduły z `git show`, usunięty tylko argument `observation_id`):
  komórki mappera z predykcją modelu i z rewizją predykcji, wersja croppera,
  dokument wyszukiwarki, rekordy przeliczania (plansza z maską w środku:
  stary kod odmawia, nowy zwraca prawdziwe indeksy), `rebuild_game`, pełny
  backfill weryfikacji symboli, stale-base-crop (puste, po zmianie komórki
  wirtualnej/częściowej/legacy — identyczne, po usunięciu manifestu tylko
  nowy kod zgłasza planszę). Migracja `0132`: drop, downgrade z odtworzeniem
  obserwacji i FK, odmowa przy niezgodnej obserwacji, ponowny upgrade.
- Jednostkowe: brak manifestu (zero komórek / błąd), manifest innej rewizji
  lub bez komórki, wersja croppera z manifestu i placeholder planszy bez
  komórek, kontekst ręcznej geometrii z manifestu i bez niego, wyszukiwarka
  (predykcje z `cells_prediction`, legacy rewizja 0 przez adapter, legacy
  rewizja bez cropa widocznej pozycji), `_virtual_records` z manifestem,
  SQL offline migracji `0132`, kontrakt API `cellReviewId`.

## Verification

```powershell
$env:PYTHONPATH = "services/worker/src;services/api/src"
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m ruff check <zmienione pliki>
.\.venv\Scripts\python.exe -m mypy --strict <zmienione moduły src>
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_symbol_review_virtual_source.py services/api/tests/test_board_search_projection_repository.py services/worker/tests/test_pending_symbol_reinference.py
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_render_manifest_readers_postgres.py
npm run test --workspace @game-predictor/admin-api-client
npm run typecheck --workspace @game-predictor/admin
```

## Cutover

Jak TASK-0757: zatrzymanie API, workerów i Reviewera we wszystkich
checkoutach, merge, `npm run db:migrate` (`0132`), start. Przed startem
kodu TASK-0758 backfill manifestów (`--execute`) dla 777 i `cf300bc1…`
musi być zakończony (`preview_counts`: 0 do zbudowania i skopiowania), bo
plansze wirtualne bez manifestu przestają się materializować. Wycofanie:
stary kod + `alembic downgrade 0131_board_render_manifests` (odtwarza
`source_observation_id`, póki istnieją obserwacje).

## Risks / open questions

- Koszt kontroli stale-base-crop: pomiar po audycie na 777 (2,3 mln komórek
  rewizji 0 wobec 155 tys. manifestów) przekracza 100 s na wywołanie —
  tak samo jak dawne zapytanie na obserwacjach z `f2336115`, więc nie jest
  to regresja. Kontrola działa wyłącznie w workerze backfillu weryfikacji
  symboli (bez `statement_timeout`), nigdy w żądaniu HTTP; po audycie
  zapytania stale-check filtrują jawnie po `game_id` komórek (pruning
  partycji; rola sesji omija RLS). Dalsza optymalizacja (porównanie per
  plansza zamiast per komórka) odłożona; `_selected_problem_items` liczy
  zbiór w każdej porcji, bo porcja zmienia zbiór problemów.
- Kursory kandydatów wzorca wydane przed cutoverem mają na 4. pozycji id
  obserwacji; stronicowanie przez wdrożenie może pominąć albo zdublować
  elementy. Okno modala jest efemeryczne, więc bez migracji kursora.
- Manifest kohorty legacy v1 traci `observationId` bez podbicia
  `schemaVersion`: `find_by_manifest` na ścieżce bez źródła komórek nie
  odnajdzie kohorty o dawnej sumie i utworzy nową iterację o tej samej
  treści. Konsumentów w repo brak; akceptowane.
- Manifest kohorty legacy bez `observationId` (format v1 bez podbicia
  wersji); konsumentów w repo brak.
- Test równoważności zależy od historii git (`f2336115`); bez niej się
  pomija. Do usunięcia razem z obserwacjami w S5.
- Strażnik `ALEMBIC_HEAD_MISMATCH` oczekuje teraz `0132`: skrypt backfillu
  manifestów z kodu TASK-0758 nie wystartuje na bazie `0131`. Trwający
  backfill trzeba dokończyć/wznawiać kodem `v1.7.111` albo najpierw
  zastosować `0132` (zatrzymanie procesów jak w Cutover).

## Outcome

### Changed

- Nowe moduły odczytu manifestu, adapter legacy i pakiet wejść mappera;
  przepięte wszystkie czytelniki runtime z listy zadania; kontrakt API bez
  `observationId` (Reviewer) i z `cellReviewId` (kandydaci wzorca symbolu)
  pionem; migracja `0132` i `EXPECTED_ALEMBIC_HEAD`.
- Fixture testów `test_verified_cell_search_projection` i
  `test_image_batch_store` dostały realistyczne `cells_prediction` (planszę
  legacy z rewizją czytamy już z niego).
- Pozostałe wystąpienia w `services/*/src` (`git grep --untracked`):
  model (`storage/models.py`); writery: `worker/images/pipeline_store.py`
  (import, w tym odczyt idempotencji), `storage/virtual_grid_geometry_repository.py`
  (ręczna geometria wirtualna), `storage/board_cell_geometry_pending_repository.py`
  (ręczna rezolucja legacy); adapter `storage/legacy_cell_observation_adapter.py`;
  listy `storage/cleanup_repository.py`, `storage/game_deletion_policy_v1.py`,
  `storage/symbol_review_statistics.py`; narzędzia historyczne
  `storage/image_geometry_rollout_backfill_repository.py`,
  `storage/additive_virtual_geometry_diagnostics.py`; backfill manifestów
  `storage/board_render_manifest_backfill.py`; fixture benchmarków (writery)
  `worker/images/real_workbench_fixture.py`, `worker/images/workbench_acceptance.py`;
  komentarze w `domain/board_render_manifests.py`, `domain/image_reviews.py`,
  `domain/image_symbol_reviews.py`, `domain/symbol_references.py`.

### Verification results

- `alembic heads` = `0132_symbol_reference_images_cell_identity`.
- ruff check: czysto; ruff format: czysto dla zmienionych plików poza dwoma
  plikami niesformatowanymi już na HEAD (`schemas/image_reviews.py`,
  `tests/test_symbol_references_domain.py`, zmiany poza zadaniem);
  mypy --strict: 0 błędów w 24 zmienionych modułach src/skryptach.
- PostgreSQL: `test_render_manifest_readers_postgres.py` 2/2 (równoważność +
  migracja `0132`); `test_verified_cell_search_projection.py` 4/4;
  `test_board_render_manifests_postgres`, `test_partial_board_reconciliation_postgres`,
  `test_board_search_approximate_win_repository`, `test_game_data_v2_postgres`,
  `test_symbol_visibility_groups_postgres`, `test_catalog_repository`,
  `test_symbol_review_query_cancellation` zielone. Niepowodzenia identyczne
  z czystym HEAD `v1.7.111` (uruchomione w osobnym worktree):
  `test_image_batch_store` 5, `test_cleanup_repository` 2,
  `test_outside_current_owner_postgres` 1, `test_resumable_game_deletion` 1,
  `test_review_repository` 1, `test_game_storage_routing_postgres`
  (`grid_review_source_asset`) 1. Jedna regresja fixture
  (`test_symbol_cell_mutations_close_and_reopen_one_board_atomically`:
  plansza legacy z pustym `cells_prediction` dostaje rewizję) usunięta
  realistycznym `cells_prediction` w fixture.
- Unit (api + worker, bez integracji): 3 713 passed, 58 failed, 13 skipped —
  zbiór 58 niepowodzeń identyczny z czystym HEAD (worktree tymczasowy bez
  ignorowanych artefaktów; m.in. `test_reviews` 6, `test_openapi_contract` 2,
  `test_virtual_grid_geometry` 2, `test_image_symbol_reviews_api` 1,
  `test_image_import_geometry_guard_api` 7, testy korpusu workera).
- TS: `admin-api-client` 70/70, Admin 597/597 + typecheck + lint (0 błędów),
  Reviewer 192/192 + typecheck; `export_admin_openapi.py --check` i
  `check:generated` aktualne.
- Próbka tylko do odczytu na bazie operatora (transakcja `READ ONLY`,
  stary kod z `f2336115` vs nowy): 777 — ok. 690 plansz rewizji 0 (w tym
  wszystkie częściowe z manifestem), 300 rewizji > 0, 100 legacy; `cf300bc1`
  — 26 plansz; 2 114 porównań mappera (predykcja modelu i bieżąca rewizja
  predykcji), dokument wyszukiwarki, wersja croppera: 0 różnic. Przeliczanie:
  10 różnic, wszystkie to plansze V3 z maską w środku, na których stary kod
  odmawiał (`IMAGE_SYMBOL_REINFERENCE_CELLS_INCOMPLETE`).

### Audit (Opus 5.5, high)

- Werdykt PASS, bez P0/P1. P2-1 (plan nie przenosił warunku S4 do zakresu
  S5) — opis TASK-0759 w planie D-467 uzupełniony o blokadę importu
  `legacy`, usunięcie pisarzy obserwacji, fixture i adaptera oraz preflight
  0 plansz `legacy_file` na rewizji 0. P2-2 (koszt stale-check i brak
  pruningu partycji) — zapytania stale-geometry i stale-base-crop (w tym
  adapter legacy) filtrują jawnie po `game_id` komórek; pomiar po zmianie:
  stale-geometry 6,7 s, stale-base-crop nadal >100 s (jak stare zapytanie);
  wpis w Risks. P3: `game_id` w `_infer_board` wymagany; strażnik
  `asset_mode = legacy_file` w `save_geometry_revision`
  (`IMAGE_REVIEW_GEOMETRY_ASSET_MODE_UNSUPPORTED`) i w `_run_v1`
  (filtr zapytania + kontrola po blokadzie); kursory i manifest kohorty
  opisane w Risks; `schemas/image_reviews.py` i
  `tests/test_symbol_references_domain.py` sformatowane. Luki testu
  równoważności (plansza V3, wirtualna kwalifikowana na rewizji > 0,
  `prediction_override` end-to-end) odłożone — próbka na bazie operatora
  pokryła plansze V3 (10 różnic = naprawa błędu).

### Not completed

- Migracja `0132` i cutover na bazie operatora (po commicie, jak w
  sekcji Cutover).
- Rozszerzenie testu równoważności o planszę V3 i kwalifikowaną rewizję > 0
  (test znika w S5 razem z obserwacjami).

### Documentation updates

- `DECISION_LOG.md` D-467 (nota TASK-0758: źródła czytelników, decyzja
  legacy, kontrakt `cellReviewId`, `0132`, numeracja S5–S7), plan D-467
  (S4 wykonanie, S5 `0133`, S6 `0134`, S7 `0135`).

### Recommended next task

- Audyt TASK-0758, commit, po zakończeniu backfillu manifestów cutover
  (`0132`), potem TASK-0759 (S5).
