---
title: TASK-0759 — S5 — manifest magazynu v4 i usunięcie `cell_observations` oraz `legacy_board_search_archive_*`
status: done
last_updated: 2026-10-01
---

# TASK-0759 — S5 — manifest magazynu v4 i usunięcie `cell_observations` oraz `legacy_board_search_archive_*`

## Status

`done` (audyt Opus FAIL→PASS, commit v1.7.115; cutover `0134` na bazie operatora po commicie)

## Goal

Schemat `game_data_v2` nie ma tabel `cell_observations`,
`legacy_board_search_archive_documents` i `legacy_board_search_archive_states`,
manifest magazynu v4 opisuje tylko żywe tabele, a w kodzie nie ma żadnego
odwołania do tych tabel ani do adaptera legacy.

## Context

D-467, etap S5. Po TASK-0757/0758 (manifest renderu, czytelnicy) i
TASK-0790 (jeden tryb danych w pisarzach, migracja `0133`) tabela
`cell_observations` (7 656 207 wierszy, ok. 28 GB) jest czytana wyłącznie
przez: `storage/legacy_cell_observation_adapter.py` (plansze `legacy_file`
na rewizji 0 — takich plansz jest 0), narzędzia historyczne
(`storage/image_geometry_rollout_backfill_repository.py`,
`storage/additive_virtual_geometry_diagnostics.py`,
`scripts/build_grid_symbol_diagnostic.py`,
`scripts/build_legacy_board_search_archive.py`), backfill manifestów
(`storage/board_render_manifest_backfill.py`, `scripts/backfill_board_render_manifests.py`
— źródło rewizji 0 znika razem z tabelą), fixture benchmarków
(`worker/images/real_workbench_fixture.py`, `workbench_acceptance.py`),
listy w `storage/cleanup_repository.py`, `storage/game_deletion_policy_v1.py`,
`storage/symbol_review_statistics.py`, test równoważności
`tests/integration/test_render_manifest_readers_postgres.py` i migracja
`0132` (downgrade odtwarza kolumnę z obserwacji). Tabele
`legacy_board_search_archive_*` mają 0 wierszy; czyta je tryb
`LEGACY_ARCHIVE` projekcji wyszukiwarki (`storage/board_search_projection_repository.py`,
`application/board_search.py`, `application/board_search_assets.py`,
`api/board_search.py` — endpoint `archive-assets/{sequence_number}`,
`domain/board_search.py` enum `BoardSearchAssetMode`, `main.py`,
`packages/admin-api-client/src/index.ts`).

Fakty z bazy operatora (2026-10-01 po `0133`, tylko `SELECT`):

- `cell_observations`: 7 656 207 wierszy (3 partycje); 0 FK wskazujących
  na tabelę (`pg_constraint.confrelid`), kolumna
  `symbol_reference_images.source_observation_id` usunięta w `0132`.
- `legacy_board_search_archive_documents` i `_states`: 0 wierszy.
- Plansz `virtual_source` z dostępnymi komórkami bez manifestu bieżącej
  rewizji: 0. Plansz `legacy_file` na rewizji 0: 0 (461 na rewizjach 1–2
  czytają cropy z `image_board_geometry_revisions.crop_artifacts`).
- Kopia zapasowa wykonana przez orkiestratora przed zadaniem:
  `C:\game_predictor_backup\cell_observations-20261001-0404.dump`
  (`pg_dump -Fc -Z 1 --table-and-children=game_data_v2.cell_observations`,
  4,37 GB, 470 s, 7 656 207 wierszy w chwili zrzutu). Wolne miejsce na C:
  ok. 11 GB po zrzucie.

## Dependencies / entry conditions

- Fakt: HEAD `v1.7.114` (TASK-0790), `alembic heads` = `0133`, baza
  operatora na `0133`; API 8000/8010 działają na tym kodzie.
- Fakt: pisarze nie tworzą obserwacji (TASK-0790); fixture benchmarków
  nadal je tworzą — to zadanie je przepina albo usuwa.
- Decyzja operatora (2026-10-01): „Wyrzuć wszystko, co jest legacy… Co do
  pustych tabel, usuń je”; „dokończ wszystkie zadania jeśli przejdą
  audyt”. Wykonanie migracji na bazie operatora robi orkiestrator po
  audycie (cutover), nie implementer.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo). Audyt: `claude-opus-5-5`,
`high`, osobny agent.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md` (S4–S6)
- `ai_docs/process/DECISION_LOG.md` (D-467, D-443)
- `ai_docs/tasks/completed/0757-board-render-manifests.md` (manifest v3,
  migracja `0131` jako wzorzec zmiany manifestu magazynu)
- `ai_docs/tasks/completed/0758-switch-readers-to-render-manifests.md`
- `ai_docs/tasks/completed/0790-virtual-only-manual-resolution-and-import-policy.md`
- `ai_docs/guides/DATABASE_MAINTENANCE.md`

## Scope

- Manifest magazynu v4 (`storage/game_data_v2_manifest_v4.py` wzorem v3):
  bez `cell_observations`, `legacy_board_search_archive_documents`,
  `legacy_board_search_archive_states`; router (`game_storage_routing.py`)
  akceptuje wyłącznie v4; provisioning nowej gry (`game_partition_lifecycle`)
  tworzy tylko tabele v4.
- Migracja `0134_drop_cell_observations_and_legacy_archive`: `SET LOCAL
  lock_timeout` 5 s, `statement_timeout` ≤ 120 s; preflight (odmowa z kodem,
  gdy niespełnione): manifest magazynu każdej lokalizacji = v3, 0 FK do
  usuwanych tabel, 0 plansz `legacy_file` na rewizji 0, 0 plansz
  `virtual_source` z dostępnymi komórkami bez manifestu bieżącej rewizji,
  0 stanów backfillu manifestów w toku (jeśli istnieje taki stan);
  aktualizacja `game_storage_table_manifest` i `game_storage_locations`
  na v4; `DROP TABLE` partycji i tabel nadrzędnych (zamrożona lista nazw
  bez importu ORM, wyliczanie partycji z `pg_inherits`); downgrade
  odmawia (dane nieodtwarzalne). Migracja `0132`: downgrade ma odmawiać
  jawnym kodem, gdy `cell_observations` nie istnieje.
- Kod: usunięcie `CellObservationModel`,
  `LegacyBoardSearchArchiveDocumentModel`, `LegacyBoardSearchArchiveStateModel`
  z `models.py`; usunięcie `legacy_cell_observation_adapter.py` i jego
  użyć (`image_symbol_review_repository.py` — stale-check tylko wirtualny,
  `board_search_projection_repository.py`, `pending_symbol_reinference.py`
  — gałąź rewizji 0 legacy znika, rewizja > 0 legacy zostaje do TASK-0791);
  usunięcie trybu `LEGACY_ARCHIVE` wyszukiwarki pionem (enum
  `BoardSearchAssetMode`, projekcja, `application/board_search*.py`,
  endpoint `archive-assets`, OpenAPI, klient, wrapper, Admin/Reviewer jeśli
  używają); usunięcie narzędzi historycznych
  (`image_geometry_rollout_backfill_repository.py` — część zależna od
  obserwacji; jeśli cały moduł jest martwy, usunąć razem z API/testami,
  `additive_virtual_geometry_diagnostics.py`,
  `scripts/build_grid_symbol_diagnostic.py`,
  `scripts/build_legacy_board_search_archive.py`, wpisy w `package.json`);
  usunięcie backfillu manifestów (`board_render_manifest_backfill.py`,
  `scripts/backfill_board_render_manifests.py`, wpis w `package.json`,
  testy) — manifesty piszą writery; listy w `cleanup_repository.py`,
  `game_deletion_policy_v1.py`, `symbol_review_statistics.py`
  zaktualizowane; fixture benchmarków `real_workbench_fixture.py` i
  `workbench_acceptance.py` przepięte na plansze wirtualne z manifestem
  albo usunięte razem z ich skryptami i wpisami `package.json` (decyzja w
  Outcome; benchmarków nie uruchamiać).
- Testy: migracja `0134` na bazie `*_test` (preflight odmawia przy
  planszy wirtualnej bez manifestu i przy planszy legacy rewizji 0;
  upgrade usuwa tabele i przestawia manifest na v4; downgrade odmawia;
  provisioning nowej gry po `0134`), test równoważności z TASK-0758
  usunięty, testy jednostkowe dotkniętych modułów, kontrakt API bez
  `archive-assets`; `EXPECTED_ALEMBIC_HEAD` = `0134` i test.
- Dokumentacja: `DECISION_LOG.md` (nota D-467 S5; D-443 jeśli dotyczy
  archiwum), plan D-467 (S5 wykonane), `DATABASE_MAINTENANCE.md`
  (po DROP: `VACUUM`/miejsce), `LOCAL_OPERATION_GUIDE.md` (cutover
  `0134`, usunięte skrypty), `architecture/DATA_MODEL.md`
  (`cell_observations` usunięte, manifest v4), `API_CONTRACT.md`
  (`archive-assets` usunięte).

## Out of scope

- Konwersja 461 plansz `legacy_file` i zawężenie CHECK-ów `asset_mode`
  (TASK-0791, migracja `0135`).
- `render_spec` poza komórkami (S7), odchudzenie predykcji (S8).
- Wykonanie migracji na bazie operatora i kompaktowanie VHDX (orkiestrator,
  runbook).

## Acceptance criteria

- [ ] `git grep -i "cell_observations\|CellObservationModel\|legacy_board_search_archive\|LegacyBoardSearchArchive\|LEGACY_ARCHIVE"` w `services/*/src`,
      `scripts`, `apps/*/src`, `packages/admin-api-client/src` zwraca tylko
      migracje historyczne w `alembic/versions`.
- [ ] Migracja `0134` na bazie `*_test`: preflight odmawia w dwóch
      scenariuszach negatywnych, upgrade usuwa 3 tabele (z partycjami) i
      ustawia manifest v4, downgrade odmawia; nowa gra po `0134` dostaje
      tylko tabele v4.
- [ ] `alembic heads` = `0134`, `EXPECTED_ALEMBIC_HEAD` = `0134`.
- [ ] OpenAPI, klient, wrapper, Admin, Reviewer spójne (`openapi:check`,
      `check:generated`, testy TS, typecheck).
- [ ] ruff, mypy --strict, pytest (api + worker, PG dla migracji) zielone;
      niepowodzenia tylko te same co na HEAD.

## Technical notes

- Wzorzec zmiany manifestu magazynu: TASK-0757 (`0131`, manifest v3,
  `game_storage_table_manifest`, `game_storage_locations`, router v3-only).
  Migracja v4 robi to samo w drugą stronę (usuwa tabele z listy) i musi
  być jedną transakcją z `DROP TABLE`.
- `DROP TABLE` partycji zwalnia miejsce natychmiast (bez VACUUM FULL);
  orkiestrator po cutoverze sprawdza `pg_database_size` i wolne miejsce.
- Stale-check wirtualny zostaje jak w TASK-0758 (jawne filtry `game_id`);
  bez gałęzi legacy funkcja `_selected_items_with_stale_base_crop` zwraca
  tylko wynik wirtualny.
- `pending_symbol_reinference.py`: plansza `legacy_file` na rewizji 0 po
  usunięciu adaptera → jawny błąd `IMAGE_SYMBOL_REINFERENCE_LEGACY_UNSUPPORTED`
  (nie powinna wystąpić: 0 takich plansz, pisarze nie tworzą).
- Chronione: 461 plansz legacy na rewizjach 1–2 i ich komórki, decyzje
  człowieka, zdarzenia, rewizje predykcji (kotwice apply-revert).
- Niedozwolone skróty: `DROP` bez preflightu; usunięcie tabel bez zmiany
  manifestu magazynu (router odmówi każdej lokalizacji).

## Expected files

- Nowe: `services/api/src/game_predictor_api/storage/game_data_v2_manifest_v4.py`,
  `services/api/alembic/versions/0134_drop_cell_observations_and_legacy_archive.py`,
  `services/api/tests/integration/test_drop_cell_observations_postgres.py`
  (nazwy orientacyjne).
- Zmienione/usunięte: lista z Context i Scope; `storage/schema_readiness.py`
  i jego test; `package.json` (skrypty usuniętych narzędzi).

## Test cases

- `0134` preflight: plansza wirtualna z dostępnymi komórkami bez manifestu
  → odmowa z kodem, nic nie usunięte; plansza `legacy_file` rewizja 0 →
  odmowa; manifest lokalizacji ≠ v3 → odmowa.
- `0134` upgrade na bazie z trzema grami: tabele i partycje znikają,
  manifest v4 w `game_storage_table_manifest` i lokalizacjach, router
  wiąże sesję; downgrade → odmowa.
- Provisioning nowej gry po `0134`: brak partycji usuniętych tabel.
- Wyszukiwarka: `BoardSearchAssetMode` bez `LEGACY_ARCHIVE`; żądanie
  `archive-assets` → 404 (trasa nie istnieje) i brak w OpenAPI.
- Stale-check: plansza wirtualna ze zmienionym manifestem → zgłoszona;
  brak gałęzi legacy nie zmienia wyniku dla plansz wirtualnych.

## Verification

```powershell
# katalog: worktree zadania; każdy krok ≤ 120 s
$env:PYTHONPATH = "services/worker/src;services/api/src"
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m ruff check services/api/src services/worker/src scripts
.\.venv\Scripts\python.exe -m mypy --strict <zmienione moduły>
.\.venv\Scripts\python.exe -m pytest <zmienione testy> -p no:cacheprovider --basetemp C:\Users\tuszy\AppData\Local\Temp\t759
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_drop_cell_observations_postgres.py -p no:cacheprovider --basetemp C:\Users\tuszy\AppData\Local\Temp\t759pg
.\.venv\Scripts\python.exe scripts/export_admin_openapi.py --check
npm run check:generated --workspace @game-predictor/admin-api-client
npm run test --workspace @game-predictor/admin-api-client
npm run typecheck --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/reviewer
```

## Risks / open questions

- Nieodwracalność: po `DROP` jedynym źródłem obserwacji jest zrzut
  4,37 GB; przywrócenie = `pg_restore` tej tabeli do bazy pomocniczej.
- Wolne miejsce na C: ok. 11 GB; `DROP` nie potrzebuje miejsca, ale testy
  PG tworzą bazy `*_test` — trzymać je małe.
- Inne sesje (worktree `v7-t0603-v2-calibration`, API 8110) dostają
  `ALEMBIC_HEAD_MISMATCH` do czasu scalenia v1.1 (jak przy `0131`–`0133`).

## Outcome

Implementacja bez commita (commit, audyt i zamknięcie zadania robi
orkiestrator). Migracja `0134` nie była uruchamiana na bazie operatora;
na bazie operatora wykonano wyłącznie odczyty `SELECT` (preflight: 3
lokalizacje `game-data-v2-manifest-v3` `active`, 0 FK do usuwanych tabel,
0 plansz `legacy_file` na rewizji 0, 0 plansz `virtual_source` z dostępnymi
komórkami bez manifestu bieżącej rewizji, archiwum 0/0 wierszy, 3 partycje
każdej tabeli, brak triggerów i widoków zależnych, operacje lifecycle `done`).

### Audit (Opus 5.5, high)

- Werdykt FAIL→PASS. P1: `tests/integration/test_resumable_game_deletion.py`
  importował usunięty `CellObservationModel` i przerywał kolekcję całego
  zestawu API — import i wstawianie obserwacji usunięte (test sam w sobie
  jest martwy od `0125`, pada w czasie wykonania na `image_import_job_files`;
  kandydat do usunięcia razem z `game_deletion_repository`/`game_deletion_archive`).
  P2 brak. P3: runbook nie wymienia blokad ACCESS EXCLUSIVE na tabelach
  wskazywanych przez FK (`public.games`, partycje `recognized_boards`,
  `image_source_geometry_revisions`) przy `DROP` partycji — przy kolizji
  `lock_timeout` cofa całość; preflight `BOARD_RENDER_MANIFEST_MISSING`
  liczy dostępne komórki przez `cardinality` (duplikaty indeksów liczone,
  luźniejsze niż zbiór; na bazie operatora 0 takich plansz); zmiany
  `cleanup_repository` bez działającego testu (oba testy padają na HEAD);
  pliki cropów wskazywane tylko przez obserwacje zostają na dysku jako
  sieroty (osobne sprzątanie); kopia zapasowa na tym samym dysku co VHDX.
- Preflight audytora na bazie operatora (tylko odczyt): 3 lokalizacje v3
  `active`, 0 FK przychodzących, 0 plansz legacy rewizji 0, 0 plansz
  wirtualnych bez manifestu, archiwum 0/0, 9 partycji do usunięcia (28 GB).
  Audytor uznał `alembic upgrade head` za bezpieczne po zatrzymaniu
  wszystkich klientów bazy.

### Changed

- **Manifest magazynu v4** (`storage/game_data_v2_manifest_v4.py`): jawna,
  zamrożona lista 63 tabel gry (v3 bez `cell_observations`,
  `legacy_board_search_archive_documents`, `legacy_board_search_archive_states`),
  `REMOVED_GAME_TABLES` wyliczane jako różnica z v3. Router
  (`game_storage_routing`), lifecycle partycji (`game_partition_lifecycle`),
  katalog (`catalog_repository`, `domain/catalog.py`) używają wyłącznie v4.
- **Migracja `0134_drop_cell_observations_and_legacy_archive`**: `SET LOCAL
  lock_timeout 5s`, `statement_timeout 120s`; `LOCK public.game_storage_locations
  ACCESS EXCLUSIVE`; preflight (odmowa z kodem, nic nie zmienione):
  `GAME_STORAGE_LIFECYCLE_IN_PROGRESS`, `GAME_STORAGE_LOCATION_BUSY`,
  `GAME_STORAGE_MANIFEST_UNEXPECTED` (lokalizacja ≠ v3 lub schemat ≠
  `game_data_v2`), `GAME_STORAGE_DROP_TABLE_UNEXPECTED` (każda z trzech tabel
  musi istnieć jako partycjonowana w `game_data_v2`),
  `GAME_STORAGE_DROP_FOREIGN_KEY_PRESENT` (FK spoza zbioru usuwanych relacji
  — rodzice + partycje z rekurencyjnego `pg_inherits` — wskazujący na nie),
  następnie `LOCK` usuwanych tabel `ACCESS EXCLUSIVE` i
  `recognized_boards`/`board_render_manifests` `SHARE`, potem
  `CELL_OBSERVATIONS_LEGACY_REVISION_ZERO_PRESENT`,
  `BOARD_RENDER_MANIFEST_MISSING` (plansza `virtual_source`, dla której
  `15 − |wykluczone|` > 0 — wykluczone = `fullyUnavailableCellIndices` dla
  kwalifikacji v3, inaczej `unavailable_cell_indices`, jak
  `available_cell_indices` — bez wiersza manifestu bieżącej rewizji),
  `LEGACY_BOARD_SEARCH_ARCHIVE_NOT_EMPTY`. Potem w tej samej transakcji:
  wiersze rejestru `game_storage_table_manifest` v4 (z modułu v4, jak `0131`
  z v3), wymiana CHECK lokalizacji `…_v3` → `ck_game_storage_locations_manifest_version_v4`
  z `UPDATE … manifest_version = v4, revision + 1`, a na końcu blok `DO`:
  dla każdej zamrożonej nazwy `DROP TABLE` każdej partycji z `pg_inherits`,
  potem rodzica (bez `CASCADE`). Downgrade odmawia
  `CELL_OBSERVATIONS_DROP_IRREVERSIBLE`. Stan backfillu manifestów był
  checkpointem w pliku, nie w bazie — kontrolę „backfill w toku” zastępuje
  preflight `BOARD_RENDER_MANIFEST_MISSING` (opisane w docstringu).
- **Migracja `0132`**: downgrade najpierw sprawdza
  `to_regclass('game_data_v2.cell_observations') IS NULL` i odmawia
  `SYMBOL_REFERENCE_OBSERVATIONS_DROPPED`.
- `EXPECTED_ALEMBIC_HEAD` = `0134_drop_cell_observations_and_legacy_archive`
  (+ test).
- **Usunięty kod**: `CellObservationModel`, `LegacyBoardSearchArchiveDocumentModel`,
  `LegacyBoardSearchArchiveStateModel`; `storage/legacy_cell_observation_adapter.py`
  (usunięcie przez `git rm`, więc jest już w indeksie);
  `current_board_cell_sources.py` ma tylko manifest (+ `is_unsupported_legacy_base_board`);
  mapper (`image_review_repository._item_from_records`) odmawia planszy
  `legacy_file` na rewizji 0 (`IMAGE_REVIEW_CELL_COUNT_INVALID`); stale-check
  i wersja croppera w `image_symbol_review_repository` tylko wirtualne;
  projekcja wyszukiwarki traktuje predykcje planszy `legacy_file` rewizji 0
  jako brak dowodu (dokument pominięty); `pending_symbol_reinference` dla
  takiej planszy rzuca `IMAGE_SYMBOL_REINFERENCE_LEGACY_UNSUPPORTED` (przed
  jakimkolwiek odczytem); `image_geometry_rollout_backfill_repository` —
  zostaje (żywa walidacja rolloutu, API i worker), usunięta tylko część
  obserwacyjna: walidacja zawsze przez manifest, backfill tożsamości v2 tylko
  komórek review i kohort, licznik `observation_backfill_count` stale 0
  (kontrakt kroku bez zmian), strażnik `BOARD_RENDER_MANIFEST_PRESENT`
  usunięty; `storage/additive_virtual_geometry_diagnostics.py` (jedyny
  konsument — test) usunięty z testem; `storage/board_render_manifest_backfill.py`,
  `scripts/backfill_board_render_manifests.py` (nie miał wpisu w
  `package.json`), `scripts/build_grid_symbol_diagnostic.py`,
  `scripts/build_legacy_board_search_archive.py` (oba bez wpisów npm) i
  `tests/test_legacy_board_search_archive.py`.
- **Tryb `LEGACY_ARCHIVE` pionem**: `BoardSearchAssetMode` = tylko
  `operational_review`; `BoardSearchArchiveAssetReference`,
  `resolve_board_search_archive_asset`, `archive_asset` (repozytorium,
  serwis, protokół), trasa `archive-assets` i nieużywany parametr
  `artifact_root` routera, `archive_relative_path` dokumentu szczegółów,
  gałąź archiwum `_prepare_view` (i `artifact_root` serwisu szczegółów),
  kody `BOARD_SEARCH_ARCHIVE_*` w handlerze błędów; `BoardSearchArchiveAsset`
  → `BoardSearchImageAsset`. OpenAPI wyeksportowane, klient wygenerowany,
  wrapper bez `getArchivedBoardSearchAsset`/`archivedBoardSearchAssetUrl`,
  `packages/board-search-ui` bez gałęzi `legacy_archive`, Admin bez
  komunikatu `BOARD_SEARCH_ARCHIVE_INCOMPLETE`. Pola identyfikatorów wyniku
  pozostają nullable w schemacie (publiczny share je zeruje).
- **Listy**: `cleanup_repository` (licznik i `DELETE` `board_render_manifests`
  zamiast obserwacji, bez ścieżek cropów z obserwacji; nazwa licznika w
  podglądzie: `board_render_manifests`), `symbol_review_statistics`
  (`ANALYZE … board_render_manifests`). `game_deletion_policy_v1` **nie
  zmieniony** — patrz Not completed.
- **Fixture benchmarków — decyzja: usunięte**, nie przepięte:
  `worker/images/real_workbench_fixture.py`, `worker/images/workbench_acceptance.py`,
  `scripts/prepare_m65_real_workbench.py`, `scripts/run_m65_workbench_acceptance.py`,
  wpisy `m65:workbench:prepare|check|acceptance`, testy
  `test_real_workbench_fixture.py` (na HEAD i tak nie przechodził) i
  `test_operational_image_review_scale.py`. Uzasadnienie: to historyczna
  bramka G6.5 (M6.5, zakończona) mierząca Reviewer na planszach
  `legacy_file` rewizji 0 zbudowanych z obserwacji; przepięcie wymagałoby
  nowego benchmarku (geometria źródła, specyfikacje renderu i manifesty dla
  3 000 plansz), czyli zmiany mierzonego obiektu, a benchmarków nie wolno
  uruchamiać w tym zadaniu, więc nie dałoby się go nawet zweryfikować.
- **Testy**: nowe `tests/test_drop_cell_observations_migration.py` (offline
  SQL `0134`: zamrożona lista = `REMOVED_GAME_TABLES`, kolejność preflightów,
  rejestr bez usuniętych nazw, partycje przed rodzicem, brak `CASCADE`,
  downgrade odmawia) i `tests/integration/test_drop_cell_observations_postgres.py`
  (baza `*_test` na `0133`, trzy gry provisionowane kodem v3 przez
  monkeypatch lifecycle/routera: odmowy `BOARD_RENDER_MANIFEST_MISSING`,
  `CELL_OBSERVATIONS_LEGACY_REVISION_ZERO_PRESENT`,
  `GAME_STORAGE_MANIFEST_UNEXPECTED`, `GAME_STORAGE_DROP_FOREIGN_KEY_PRESENT`,
  `LEGACY_BOARD_SEARCH_ARCHIVE_NOT_EMPTY` bez zmian schematu/lokalizacji;
  plansza z wszystkimi polami poza zdjęciem przechodzi bez manifestu;
  upgrade usuwa 3 tabele i 9 partycji, lokalizacje v4 z `revision + 1`,
  rejestr v4 = 63 tabele, plansze i manifesty nietknięte, router v4 wiąże
  każdą grę; downgrade odmawia; downgrade `0132` po `stamp` odmawia
  `SYMBOL_REFERENCE_OBSERVATIONS_DROPPED`; gra provisionowana po `0134` ma
  dokładnie partycje v4). Usunięty test równoważności TASK-0758
  (`integration/test_render_manifest_readers_postgres.py`, razem z testem
  odtworzenia `source_observation_id` w downgrade `0132`, który wymagał
  modeli usuniętej tabeli). `test_board_render_manifests_postgres.py`:
  testy backfillu usunięte, writer importu + kaskada i reguła „brak
  manifestu ⇔ brak komórek” zostają, test `0131` przepisany na lokalizację
  v1 wpisaną SQL-em na `0130` (bieżący kod provisionuje v4). Nowe testy
  jednostkowe: mapper odmawia planszy legacy rewizji 0, przeliczanie
  predykcji odmawia jej bez odczytu bazy, wyszukiwarka nie ma trybu
  archiwum i trasy (404, brak w OpenAPI), projekcja pomija legacy rewizji 0.
  Fixture PG z obserwacjami dla plansz `legacy_file` rewizji 0
  (`test_image_batch_store`, `test_verified_cell_search_projection`,
  `test_game_storage_routing_postgres`) przepięte na planszę `legacy_file`
  z ręczną rewizją geometrii 1 (`crop_artifacts` z tymi samymi ścieżkami i
  sumami), w testach z kolejną korektą numery rewizji podniesione o 1;
  pozostałe fixture tylko straciły zbędne wiersze obserwacji. W
  `test_partial_board_reconciliation_postgres` geometria rewizji fixture
  odpowiada geometrii planszy (z niej liczona jest widoczność), a
  `test_virtual_deferred_resolution_postgres::test_migration_0133…`
  provisionuje gry na `0132` lifecycle'em przypiętym do manifestu v3; test
  odczytu obserwacji w tym pliku sprawdza teraz, że tabela nie istnieje.

### Verification results

- `alembic heads` = `0134_drop_cell_observations_and_legacy_archive (head)`
  (test `test_schema_readiness`).
- `ruff check services/api/src services/worker/src scripts`: czysto;
  `ruff check` testów: jedyny błąd w niezmienionym
  `services/worker/tests/test_page_geometry_preflight.py` (E501, na HEAD);
  `ruff format --check` wszystkich zmienionych plików `.py`: czysto;
  `git diff --check`: czysto.
- `mypy --strict` wszystkich zmienionych modułów src + migracja `0134`: 0 błędów w
  nich; 27 błędów w 6 niezmienionych modułach z listy znanych
  (`v7_label_geometry_calibration` api/application, `contrast_frame_grid_v12`,
  `page_geometry_preflight`, `qualified_manual_geometry`, `shape_geometry_v2/core`).
- Unit API (178 plików, porcje po 6): 1 671 passed, 20 failed, 4 skipped —
  20 niepowodzeń = znane z HEAD (`test_image_import_geometry_guard_api` 7,
  `test_reviews` 6, `test_openapi_contract` 2, `test_virtual_grid_geometry`
  2, `test_image_symbol_reviews_api` 1, `test_lateral_managed_reprocess` 1,
  `test_migration_baseline` 1; trzy ostatnie potwierdzone na czystym HEAD w
  tymczasowym worktree). Testy dodane po tym przebiegu
  (`test_image_symbol_review_virtual_source` 10/10,
  `test_pending_symbol_reinference` 5/5, `test_game_data_v2_schema` +
  `test_drop_cell_observations_migration` 8/8) zielone.
- Unit worker (196 plików, porcje po 8): 2 054 passed, 36 failed, 9 skipped —
  wszystkie 36 w zbiorze znanych niepowodzeń korpusu (37. znany,
  `test_real_workbench_fixture`, usunięty z fixture).
- PostgreSQL: izolowane bazy `*_test`, 145 testów uruchomionych pojedynczo
  (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`, każdy ≤ 115 s): nowy
  `test_drop_cell_observations_postgres` zielony; po poprawkach fixture
  (patrz niżej) 31 niepowodzeń, wszystkie czerwone także na czystym HEAD
  `v1.7.114` (tymczasowy worktree, ten sam pierwszy błąd; trzy testy
  `test_board_import_coverage_migration` odmawiają downgrade'u na `0134`
  zamiast `0133` — ta sama przyczyna): `test_board_import_coverage_migration`
  4, `test_board_import_coverage_repository` 8, `test_cleanup_repository` 2,
  `test_image_batch_store` 4, `test_postgres_baseline` 3,
  `test_game_partition_lifecycle_postgres` 1, `test_game_storage_routing_postgres`
  1 (`grid_review_source_asset`), `test_layout_import_report_repository`,
  `test_m2_admin_acceptance`, `test_mobile_release_repository`,
  `test_outside_current_owner_postgres`, `test_production_snapshot_store`,
  `test_release_workflow_integration`, `test_review_repository`,
  `test_v010_virtual_geometry_migration` po 1. Pierwszy przebieg wykazał 6
  regresji fixture (plansze legacy rewizji 0 lub provisionowanie gry na
  `0132` kodem v4); poprawione i powtórzone: `test_image_batch_store` 16
  testów (tylko 4 znane czerwone), `test_virtual_deferred_resolution_postgres`
  całość zielona, `test_partial_board_reconciliation_postgres` 5/5,
  `test_verified_cell_search_projection` 4/4. Po testach brak pozostawionych
  baz `*_test`.
- TS: `export_admin_openapi.py --check` aktualne, `check:generated`
  aktualne; `admin-api-client` 71/71; Admin 597/597 + typecheck + lint
  (0 błędów, 4 ostrzeżenia); Reviewer 193/193 + typecheck;
  `board-search-ui` typecheck, lint, test 77/77, interakcje 37/37.
- Acceptance grep (`cell_observations|CellObservationModel|legacy_board_search_archive|LegacyBoardSearchArchive|LEGACY_ARCHIVE`,
  bez rozróżniania wielkości liter, w `services/*/src`, `scripts`,
  `apps/*/src`, `packages/admin-api-client/src`, łącznie z plikami
  nieśledzonymi): poza migracjami tylko zamrożone wejścia migracji
  (`storage/game_deletion_policy_v1.py`) i nazwa rewizji w
  `schema_readiness.EXPECTED_ALEMBIC_HEAD` (nazwa migracji z zadania).

### Not completed

- Migracja `0134` na bazie operatora i pomiar miejsca (cutover orkiestratora
  po audycie; runbook `LOCAL_OPERATION_GUIDE.md`).
- `storage/game_deletion_policy_v1.py` celowo **nie** został zaktualizowany,
  choć Scope go wymienia: jest zamrożonym wejściem migracji `0103` i
  manifestu v1 (`GAME_TABLES = DIRECT ∪ INDIRECT`), z którego wyprowadzone
  są `0105`, `0106` i (przez v3) `0131`. Usunięcie nazw zmieniłoby schemat
  budowany od zera i rejestry v1/v3. Jego jedyny runtime-konsument
  (`game_deletion_repository`/`game_deletion_archive`, usuwanie gry legacy
  ze schematu `public`, tylko testy, `test_resumable_game_deletion` czerwony
  już na HEAD) jest martwy od `0125` — kandydat na osobne sprzątanie.
- Pokrycie odtworzenia `source_observation_id` w downgrade `0132` (test
  usunięty razem z testem równoważności): ścieżka jest nieosiągalna po
  `0134`, a bieżący kod nie umie zbudować gry na `0132`.
- `test_postgres_baseline` (cykl downgrade do `base`) — nieaktualny już na
  HEAD (`0133` odmawia), bez zmian.

### Documentation updates

- `DECISION_LOG.md`: nota D-467 „Usunięcie `cell_observations` i archiwum
  wyszukiwarki (TASK-0759, S5)”; D-369 oznaczona jako superseded by D-467.
- Plan D-467 (S5: wykonanie przed audytem), `CURRENT_STATE.md` (TASK-0759 w
  toku), `guides/LOCAL_OPERATION_GUIDE.md` (sekcja cutoveru `0134`, kody
  preflightu, usunięte skrypty, uaktualniony runbook v3 bez backfillu),
  `guides/DATABASE_MAINTENANCE.md` (2.5: po `DROP` bez VACUUM, pomiar,
  VHDX), `architecture/DATA_MODEL.md` (manifest v3/v4, `cell_observations`
  i archiwum jako historyczne), `architecture/API_CONTRACT.md` (bez
  `archive-assets` i `legacy_archive`), noty w `GAME_DATA_V2_OWNERSHIP.md`,
  `VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`, `SYSTEM_ARCHITECTURE.md`,
  `quality/GRID_CROPPING_VS_SYMBOL_MODEL_DIAGNOSIS.md` (skrypt usunięty).

### Recommended next task

- Audyt TASK-0759, commit, cutover `0134` za zgodą (zatrzymanie procesów,
  merge, `npm run db:migrate`, pomiar `pg_database_size` i VHDX), potem
  TASK-0791 (`0135`). Osobno: usunięcie martwego
  `game_deletion_repository`/`game_deletion_archive` i ich testów.
