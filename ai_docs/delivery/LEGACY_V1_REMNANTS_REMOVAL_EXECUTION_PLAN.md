---
title: Plan usunięcia pozostałości V1/legacy z aplikacji i bazy (D-467)
status: accepted
last_updated: 2026-09-30
---

# Plan usunięcia pozostałości V1/legacy z aplikacji i bazy

## Stan obecny

Fakty z inwentaryzacji tylko do odczytu (2026-09-30, gra `777`
`bfc4f949-5c14-4850-b02a-db99610bcfa5`, baza 87 GB, `alembic_version`
`0128`):

- Ruting magazynu jest V2-only: `GameStorageSchema` ma tylko `V2`
  (`services/api/src/game_predictor_api/storage/game_storage_routing.py`),
  generacja 1 jest odrzucana, wszystkie 3 wpisy `game_storage_locations` to
  `game_data_v2`. Migracja `0125` usunęła 65 pustych tabel legacy z `public`;
  plan D-448 został zamknięty w TASK-0752.
- W schemacie V2 zostały **dane i kod z ery V1**:
  - `cell_observations` — 28 GB (7,66 mln wierszy; 19 GB to `render_spec`
    ok. 2,5 KB na komórkę). Dla 372 355 plansz z `geometry_revision = 0` jest
    to jedyne źródło specyfikacji renderu; dla 138 035 plansz z rewizją > 0
    źródłem jest `image_board_geometry_revisions.virtual_render_spec`.
    Czytają ją: mapper `materialize_current_image_review_cells`
    (`storage/image_review_repository.py`), odbudowa projekcji i kontrola
    stale-base-crop (`storage/image_symbol_review_repository.py`), projekcja
    wyszukiwania plansz (`storage/board_search_projection_repository.py`),
    przeliczanie predykcji (`worker/images/pending_symbol_reinference.py`),
    ręczna geometria (`storage/virtual_grid_geometry_repository.py`),
    `symbol_usage_summary` (`storage/catalog_repository.py`), FK
    `symbol_reference_images.source_observation_id` (0 wierszy).
  - `image_symbol_review_cells` — 34 GB, z czego 19 GB to ten sam
    `render_spec` skopiowany do każdej komórki. Od specyfikacji zależą
    `render_spec_checksum_sha256`, `crop_sample_id`, `render_identity_v2`,
    `logical_cell_key_v2`, `crop_manifest_checksum` rewizji predykcji i
    manifesty kohort treningowych.
  - `image_symbol_prediction_revisions` — 8,6 GB (613 tys.); 86 453
    zastąpionych rewizji modelu to kotwice `apply-revert` dla zapisów
    biblioteki wzorców (D-466). Payload `predictions[].virtualCell` (3,2 KB
    na komórkę) powiela specyfikację renderu.
  - `public.image_pipeline_stage_results` — 6,8 GB (5,36 GB to etap
    `board_crops`). Retencja istnieje: job `storage_pipeline_compaction`
    (`services/worker/src/game_predictor_worker/pipeline_state_compaction.py`),
    nigdy nie uruchomiony (`image_pipeline_terminal_manifests` = 0 wierszy).
  - Martwe gałęzie V1 w kodzie: `_uses_logical_current_cell_identity`
    (`storage/image_symbol_review_repository.py:380`) zawsze zwraca `True`;
    `uses_current_projection=False` (21 miejsc w `services/api/src`) i
    `_prediction_confidence_expression` z `coalesce` z obserwacji istnieją
    tylko dla magazynu `public`.
  - `asset_mode = legacy_file` to **żywy drugi tryb danych**: 461 plansz w 777
    (25–27.09.2026) z ręcznej rezolucji odroczonych plansz
    (`storage/board_cell_geometry_pending_repository.py`, route
    `POST …/{pending_id}/manual-resolution`, allowlista reviewera), 3 960
    komórek; polityka importu nowej gry domyślnie `legacy`
    (`domain/image_import_engine_policy.py`, `application/jobs.py`,
    `storage/game_partition_lifecycle.py`, `storage/catalog_repository.py`).
    `legacy_board_search_archive_*` mają 0 wierszy.
  - Bazy `diag_search_path_test`, `diag_search_path_test2`, `diag_raw_test`
    (razem 42 MB, 0 referencji w repo); 7 osieroconych funkcji triggerów w
    `public` (`guard_image_review_queue_topology`,
    `populate_image_review_item_sequence_scope`,
    `project_image_review_queue_{insert,delete,status}`,
    `synchronize_image_review_item_sequence_number`,
    `synchronize_image_review_job_status`; 0 triggerów); historyczne skrypty
    i testy legacy/v0.9 (`scripts/preview_legacy_game_managed_asset_gc.py`,
    `audit_legacy_public_game_store.py`, `preview_legacy_game_cleanup.py`,
    `delete_legacy_game_resumable.py`, `backfill_v09_schema.py`,
    `report_v09_storage_cleanup.py`, `build_legacy_board_search_archive.py` i
    ich testy); ok. 60 ignorowanych katalogów scratch w root.
- Manifest magazynu v1 jest zamrożony (`GAME_TABLES` = 65 tabel); usunięcie
  tabeli z V2 wymaga manifestu nowej wersji w jednej migracji razem z
  `game_storage_table_manifest`, `game_storage_locations`,
  `game_deletion_policy_v1`, `cleanup_repository`, provisioningiem w
  `game_partition_lifecycle` i listą ANALYZE w `symbol_review_statistics`.

## Cel

Aplikacja i baza bez pozostałości V1: jedno źródło specyfikacji renderu per
plansza, brak `cell_observations`, brak gałęzi kodu istniejących tylko dla
magazynu `public`, jeden tryb danych (`virtual_source`), działająca retencja
wyników pipeline i narzędzia sprzątania. Docelowo ok. 60 GB mniej z 87 GB.

## Zakres i reguły

- Etapy S1–S8 w kolejności zależności. S1–S2 nie dotykają danych gier i mogą
  iść równolegle z przebiegami zapisu biblioteki wzorców (D-466). S3–S8
  wymagają zakończenia przebiegów zapisu (TASK-0750 i ewentualny przebieg
  100%), bo zmieniają sumy kontrolne planów albo przepisują tabele.
- Wzorzec bezpieczeństwa jak w D-448: przed DDL lub dużym UPDATE świeży
  read-only inventory, próba na izolowanej bazie `*_test`, kopia zapasowa
  (`pg_dump`, ostatnia pełna 22 GB), osobna jawna zgoda operatora na każdy
  DROP i każdy skrypt z `--execute`. Migracje Alembic od `0129`, konwencje
  z `0125`/`0126`: `SET LOCAL lock_timeout` 2–5 s, `statement_timeout`
  ≤ 120 s, zamrożone listy bez importu ORM, downgrade odmawia, gdy nie
  odtwarza danych.
- Kotwice `apply-revert` (zastąpione rewizje modelu pod rewizją biblioteki)
  nie są usuwane. Decyzje człowieka i historia zdarzeń pozostają.
- Zmiana kontraktu API (zawężenie enumów `assetMode`, `cellAssetMode`,
  `BoardSearchAssetMode`) idzie pionem: backend + OpenAPI + klient + wrapper
  + test.
- Każde zadanie: osobny audyt (`claude-opus-5-5`), commit `vX.Y.N`, Outcome,
  `CURRENT_STATE.md`; wpis w `DECISION_LOG.md` przy zmianie schematu.

## Decyzje

- **D-467** (ten plan): manifest renderu per plansza zastępuje
  `cell_observations`; `render_spec` w komórkach zostaje tylko jako suma
  kontrolna; `legacy_file` przestaje być trybem docelowym (ręczna rezolucja
  przechodzi na ścieżkę wirtualną, nowe gry domyślnie `virtual_default`).
- Wyliczanie specyfikacji renderu w locie z geometrii źródłowej odrzucono:
  quady są liczone numerycznie, a sumy kontrolne muszą się zgadzać bajt w
  bajt; zapis manifestu jest deterministyczny i tańszy (ok. 12 KB na
  planszę, ok. 4,5 GB dla revision 0).
- Retencja rewizji predykcji ograniczona do rewizji zastąpionych review
  items bez komórek (0,12 GB); reszta zostaje jako historia i kotwice.

## Etapy i zadania

### S1 — porządki bez wpływu na dane gier

- **TASK-0752** — migracja `0129`: `DROP FUNCTION` 7 osieroconych funkcji
  triggerów w `public` (lista zamrożona w migracji, preflight: 0 triggerów
  i 0 zależności, inaczej odmowa); skrypt `scripts/drop_diagnostic_databases.py`
  z podglądem i `--execute` dla dokładnie trzech baz `diag_*` (odmowa, gdy
  nazwa spoza listy albo baza ma aktywne połączenia); usunięcie historycznych
  skryptów i testów legacy/v0.9 (lista w Technical notes zadania) razem z
  wpisami w `package.json`; aktualizacja `LEGACY_PUBLIC_STORE_REMOVAL_EXECUTION_PLAN.md`
  (status wykonany, `0125` zastosowana), przewodników wskazujących te
  skrypty (`LOCAL_OPERATION_GUIDE.md`, `RESUMABLE_LEGACY_DELETION.md`) i
  D-443 (skrypt usunięty). Lista usuwanych plików jest w `Scope` zadania.
  Uruchomienie migracji na bazie operatora i `--execute` dla baz `diag_*`
  wymagają osobnej zgody.
- **TASK-0753** — sprzątanie katalogów scratch w root (`.codex-task-*`,
  `test-temp-*`, `t07-pytest-*`, `t6?`, `.test-tmp`, `.pytest-tmp`,
  `.pytest_cache`, `.test-artifacts`, `.codex-tmp`,
  `.codex-remote-attachments`): podgląd z rozmiarami,
  usunięcie za zgodą; skrypt `scripts/clean_scratch_dirs.ps1` pomija
  reparse pointy, katalogi nieczytelne i w użyciu, chroni `.tooling`,
  `.venv*`, `node_modules`, `artifacts`, `worktrees`, `work`, `.runtime`,
  `.tmp` (logi serwerów innych checkoutów).

### S2 — martwe gałęzie V1 w kodzie

- **TASK-0754** — usunięcie `_uses_logical_current_cell_identity`,
  parametru `uses_current_projection` i gałęzi `False` w
  `storage/image_symbol_review_repository.py`,
  `storage/image_symbol_review_bulk_operation_repository.py`,
  `storage/board_cell_geometry_pending_repository.py`,
  `domain/image_symbol_reviews.py`; `_prediction_confidence_expression`
  zastąpione `cell.prediction_confidence`; testy parametryzowane
  `False/True` uproszczone. Zachowanie V2 bez zmian (te same SQL dla
  `True`).
- **TASK-0755** — `symbol_usage_summary` (`storage/catalog_repository.py`)
  liczone z `image_symbol_review_cells` (`assigned_symbol_id`,
  `prediction_symbol_code`) zamiast skanu `cell_observations`; test
  porównawczy wyników na fixture.

### S3 — retencja wyników pipeline

- **TASK-0756** — uruchomienie istniejącego joba
  `storage_pipeline_compaction` dla 777 (podgląd: liczba executions,
  bajty do zwolnienia; wykonanie za zgodą), potem `VACUUM (FULL, ANALYZE)`
  `public.image_pipeline_stage_results` w oknie bez zapisów; runbook
  `ai_docs/guides/DATABASE_MAINTENANCE.md` (VACUUM po dużych przebiegach,
  raport zajętości per gra, kompaktowanie `docker_data.vhdx` przy
  wyłączonym Dockerze).

- **TASK-0765** (dopisane po audycie S3) — rola aplikacyjna bez
  `SUPERUSER`/`BYPASSRLS`: lokalna rola `game_predictor` jest superuserem,
  więc RLS `game_data_v2` nie izoluje gier i każde zapytanie bez jawnego
  `game_id` czyta lub zmienia dane wszystkich gier (także ścieżki Reviewera
  przez tunel). Zakres: osobna rola aplikacyjna `NOSUPERUSER NOBYPASSRLS`
  bez własności tabel (migracje na roli właściciela), konfiguracja API i
  workera, test integracyjny na tej roli, audyt zapytań na `GAME_TABLES`
  bez predykatu `game_id`. Osobna decyzja operatora (zmiana ról w bazie).

### S4 — manifest renderu per plansza

- **TASK-0757** — migracja `0130`: tabela V2 `board_render_manifests`
  (proponowana; `recognized_board_id`, `geometry_revision`, `cells` JSONB w
  kształcie `virtual_render_spec.cells`, `manifest_checksum_sha256`);
  backfill porcjami z `cell_observations` dla plansz revision 0 z kontrolą
  równości sum kontrolnych per komórka; writer importu
  (`worker/images/pipeline_store.py`) i ręczna geometria
  (`storage/virtual_grid_geometry_repository.py`) piszą manifest zamiast
  obserwacji.
- **TASK-0758** — przepięcie odczytów: mapper
  `materialize_current_image_review_cells`, odbudowa i kontrola
  stale-base-crop, projekcja board-search (predykcje z
  `recognized_boards.cells_prediction` albo najnowszej rewizji),
  `pending_symbol_reinference`, `partial_board_reconciliation_repository`,
  `symbol_references_repository` (FK na id komórki), fixture benchmarków;
  test równoważności: dla próbki 1 000 plansz komórki zmaterializowane z
  manifestu są identyczne z komórkami z obserwacji.

### S5 — usunięcie `cell_observations`

- **TASK-0759** — manifest magazynu v3 (bez `cell_observations` i
  `legacy_board_search_archive_*`), migracja `0131`: aktualizacja
  `game_storage_table_manifest`, `game_storage_locations`, `DROP TABLE`
  partycji (preflight: manifest S4 kompletny, 0 referencji w kodzie,
  0 FK), `game_deletion_policy_v1`, `cleanup_repository`,
  `game_partition_lifecycle`, `symbol_review_statistics`; usunięcie
  `LegacyBoardSearchArchive*` z API, OpenAPI, klienta i Admina. Próba na
  bazie `*_test`, kopia zapasowa, osobna zgoda na apply.

### S6 — jeden tryb danych

- **TASK-0760** — ręczna rezolucja odroczonych plansz zapisuje geometrię
  wirtualną (jak `virtual_grid_geometry_repository`) zamiast cropów-plików;
  domyślna polityka importu nowej gry `virtual_default`; usunięcie polityk
  VERIFIED_V19 / STRUCTURED_SHADOW z workera (decyzja operatora w zadaniu,
  jeśli któraś jest nadal potrzebna, plan wraca do korekty).
- **TASK-0761** — konwersja 461 plansz `legacy_file` w 777 na
  `virtual_source` (skrypt z podglądem, zgoda na `--execute`; komórki z
  decyzją człowieka zachowują decyzje), zawężenie CHECK-ów `asset_mode` do
  `virtual_source`/`none` (migracja `0132`), zawężenie enumów API pionem.

### S7 — `render_spec` poza komórkami

- **TASK-0762** — odczyty `render_spec` z komórek (`get_assets` →
  `virtual_cell_previews`, `symbol_references_repository`,
  `symbol_cell_training_source_repository`, `virtual_grid_geometry_repository`,
  `scripts/evaluate_symbol_reference_library.py`) przepięte na manifest z
  S4 przez `(recognized_board_id, geometry_revision, cell_index)`;
  komórka zachowuje `render_spec_checksum_sha256` i klucze tożsamości.
- **TASK-0763** — migracja `0133`: kolumna `render_spec` w
  `image_symbol_review_cells` usunięta; odzyskanie miejsca przez przepisanie
  partycji (`VACUUM FULL` albo swap partycji; ACCESS EXCLUSIVE, wymaga
  ok. 15 GB wolnego miejsca, okno bez zapisów, zgoda).

### S8 — odchudzenie rewizji predykcji

- **TASK-0764** — `predictions[].virtualCell` ograniczone do sum
  kontrolnych i kluczy (bez pełnego `renderSpec`); `predictions_digest`
  planów biblioteki wzorców liczony po odchudzonej postaci (wymaga
  zakończenia wszystkich przebiegów D-466 i nowego `apply-preview` dla
  kolejnych); retencja rewizji zastąpionych review items bez komórek;
  bez usuwania kotwic `apply-revert`.

## Mapa wymaganie → zadanie → kryterium

| Wymaganie operatora | Zadania | Kryterium |
|---|---|---|
| Wyrzucić `cell_observations` i zaszłości | S4–S5 | tabela nie istnieje w manifeście v3; test równoważności komórek |
| Usunąć puste/nieużywane tabele i bazy | S1, S5 | 0 baz `diag_*`, 0 osieroconych funkcji, 0 pustych partycji archiwum |
| Przepiąć i wyrzucić duplikaty `render_spec` | S4, S7, S8 | jedno źródło specyfikacji; komórki bez kolumny |
| Brak powiązań z V1 w kodzie | S2, S6 | 0 wystąpień `uses_current_projection`, `legacy_file` poza migracjami |
| System czyszczenia miejsca | S3 | job kompaktacji uruchamialny; runbook VACUUM/VHDX |
| Gotowość na 10–30 gier | S4–S7 | rozmiar per plansza ≤ 1/3 obecnego (pomiar po S7) |

## Odbiór całego przepływu

Po S8: `npm run quality`, testy integracyjne PostgreSQL, przegląd w Adminie
(weryfikacja symboli, wyszukiwarka plansz, ręczna rezolucja), pomiar
rozmiaru bazy per tabela przed/po, `apply-revert` jednej planszy biblioteki
nadal działa.

## Ryzyka

- S4/S5: ukryty czytelnik `cell_observations` (np. skrypt poza `services/`)
  — chroni test równoważności i grep przed DROP.
- S7: przepisanie partycji 34 GB blokuje weryfikację symboli; okno i
  miejsce na dysku muszą być potwierdzone.
- S8: zmiana `predictions_digest` unieważnia manifesty w toku — tylko po
  zakończeniu przebiegów.
- S6: jeśli polityka VERIFIED_V19 jest jeszcze potrzebna dla jakiejś gry,
  usunięcie trzeba odłożyć (decyzja w TASK-0760).

## Zakres wyłączony

Squash migracji `0017–0124`, zmiana modelu symboli, retencja zdarzeń
weryfikacji, migracja na dysk 2 TB (osobny runbook), historia decyzji.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0752 | claude-opus-5-5 | medium (warunkowo) | Migracja i skrypt z podglądem; ryzyko niskie, listy zamrożone. | Tak: claude-opus-5-5, high, osobny agent |
| TASK-0753 | claude-opus-5-5 | low (warunkowo) | Skrypt PowerShell z listą wzorców i ochroną katalogów. | Tak: claude-opus-5-5, medium, osobny agent |
| TASK-0754 | claude-opus-5-5 | high (warunkowo) | Usunięcie gałęzi w 4 repozytoriach bez zmiany SQL dla V2; wymaga porównania zapytań. | Tak: claude-opus-5-5, high, osobny agent |
| TASK-0755 | claude-opus-5-5 | medium (warunkowo) | Jedno zapytanie i test porównawczy. | Tak: claude-opus-5-5, medium, osobny agent |
| TASK-0756 | claude-opus-5-5 | medium (warunkowo) | Uruchomienie istniejącego joba i runbook; zapis w bazie za zgodą. | Tak: claude-opus-5-5, high, osobny agent |
| TASK-0765 | claude-opus-5-5 | high (warunkowo) | Zmiana ról i uprawnień w bazie; wpływ na wszystkie repozytoria. | Tak: claude-opus-5-5, high, osobny agent |
| TASK-0757 | claude-opus-5-5 | high (warunkowo) | Nowa tabela, backfill 372 tys. plansz z kontrolą sum kontrolnych, zmiana writera importu. | Tak: claude-opus-5-5, high, osobny agent |
| TASK-0758 | claude-opus-5-5 | high (warunkowo) | Przepięcie centralnego mappera i 6 czytelników; test równoważności. | Tak: claude-opus-5-5, high, osobny agent |
| TASK-0759 | claude-opus-5-5 | high (warunkowo) | Manifest v3 i DROP partycji; nieodwracalne. | Tak: claude-opus-5-5, high, osobny agent |
| TASK-0760 | claude-opus-5-5 | high (warunkowo) | Zmiana ścieżki ręcznej rezolucji i polityk importu; decyzja produktowa. | Tak: claude-opus-5-5, high, osobny agent |
| TASK-0761 | claude-opus-5-5 | high (warunkowo) | Konwersja danych 461 plansz i zawężenie CHECK-ów oraz kontraktu API. | Tak: claude-opus-5-5, high, osobny agent |
| TASK-0762 | claude-opus-5-5 | high (warunkowo) | Przepięcie odczytów `render_spec` z zachowaniem sum kontrolnych. | Tak: claude-opus-5-5, high, osobny agent |
| TASK-0763 | claude-opus-5-5 | high (warunkowo) | Usunięcie kolumny i przepisanie partycji 34 GB. | Tak: claude-opus-5-5, high, osobny agent |
| TASK-0764 | claude-opus-5-5 | high (warunkowo) | Zmiana payloadu rewizji i digestu planów biblioteki. | Tak: claude-opus-5-5, high, osobny agent |

Poziomy rozumowania są warunkowe: nie da się ich ustawić z sesji, wskazują
oczekiwaną staranność.
