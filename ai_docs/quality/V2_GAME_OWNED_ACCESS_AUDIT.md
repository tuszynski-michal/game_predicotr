---
title: Audyt dostępu game-owned przez V2
status: accepted
last_updated: 2026-09-25
---

# Audyt TASK-0682 — dostęp game-owned przez V2

## Zakres i metoda

Audyt objął 65 relacji zamrożonego manifestu
`game-data-v2-manifest-v1` w produkcyjnych źródłach API, workera i skryptach
operatorskich. Nie opiera się na deklaracji „brak wyników `rg`”: zestawiono
importy `GAME_TABLES`, `GameStorageRouter`, `game_storage_scope`, modele
game-owned i użycia `text()`/`exec_driver_sql()`, a następnie przejrzano
każdy punkt wejścia z wynikiem poniżej.

`GameStorageSession` umie odziedziczyć scope żądania lub parametr jawnego
`session.execute`, lecz ORM z `where(Model.game_id == ...)` nie udostępnia
tego parametru listenerowi. Każdy punkt, który może uruchomić taki ORM poza
scope'em ścieżki `/games/{game_id}`, musi zatem wywołać `bind()` jawnie.

## Produkcyjne punkty wejścia

| Powierzchnia | Gwarancja routingu | Dowód / test |
|---|---|---|
| Requesty `/games/{game_id}/…` | Middleware `main.py` otwiera `game_storage_scope`; `GameStorageSession` wiąże go przed SQL. | `test_game_storage_routing.py`, testy PostgreSQL routingu. |
| Grid review z `gameId` w query | `api/image_grid_reviews.py` ustanawia scope jawnie; nie zależy od wzorca URL. | `test_grid_review_source_asset_reads_v2_in_a_new_unscoped_session`. |
| Operacyjny review obrazów | `SqlAlchemyOperationalImageReviewRepository._bind()` poprzedza każdy publiczny read/write relacji game-owned. Pomocnik bez `game_id` działa tylko wewnątrz tak związanego publicznego wywołania. | Nowy `test_operational_review_repository_binds_v2_before_game_owned_read`. |
| Board import coverage i odczyty board-search | Coverage oraz `range_documents()` wiążą router; `upsert_candidates()` wiąże zapis i odrzuca batch mieszający gry. | `test_board_search_candidate_upsert_uses_v2_composite_identity`. |
| Image job operations i page geometry | Najpierw pobierają globalny job/katalog, następnie wiążą jego `game_id`; zapis podnosi istniejący write fence. | Istniejące testy repozytoriów oraz `test_page_geometry_snapshot_reads_v2_in_a_new_unscoped_session`. |
| Symbol-cell review | Sprawdzenie tożsamości obecnej projekcji i `require_ready_game()` wiążą V2 przed dostępem do relacji game-owned. | `test_image_symbol_review_projection_availability.py`, `test_image_symbol_review_query_storage.py`. |
| Generic worker | `LocalJobWorker` utrzymuje `game_storage_scope(claimed.game_id)` przez cały handler; globalny rekord `jobs` pozostaje w `public`. | Runtime i istniejące testy workerów. |
| Image batch worker | `SqlAlchemyImageBatchStore` rozwiązuje globalny job, potem wiąże jego grę przed każdym odczytem `image_import_job_files` i przed zapisem. | Nowy `test_image_batch_store_registers_association_in_v2_store`. |
| Workerowe utrzymanie browser staging | `jobs/store.py` wiąże grę przed relacją retencji game-owned. | Istniejące testy workerów. |
| Skrypty operatorskie | `audit_staging_lifecycle.py` wiąże V2 przed zapytaniami; `vision_lab_export.py` wiąże osobno każdą grę; `reverify_777_grids.py` otacza każdą sesję scope'em. | Kod skryptów; operacje pozostają read-only, gdy taki jest ich kontrakt. |

## Raw SQL i granica nazw relacji

- Jedyny surowy zapis game-owned w `orchestration_store.py` buduje nazwę
  `image_import_job_files` przez `GameStorageRouter.qualified_game_table()`
  po `bind(..., WRITE)`. Schema ani tabela nie pochodzą z requestu, joba ani
  innego wejścia klienta.
- Surowe odczyty diagnostyczne w `audit_staging_lifecycle.py` mają stałe,
  nieklientowe identyfikatory i wykonują się dopiero po `bind(..., READ)`;
  transaction-local `search_path` routera wskazuje V2 przed `public`.
- DDL lifecycle (`game_partition_lifecycle.py`) jest świadomie control plane:
  używa zamrożonego manifestu i własnego fence'a podczas provision/delete,
  a nie routingu zwykłego dostępu do data plane.

## Świadomie nieprodukcyjne adaptery i pozostawione ścieżki historyczne

- SQLite i minimalne testowe `Session` nie są runtime PostgreSQL. Router
  modeluje tam wyłącznie wirtualną location V2; mock w teście dostępności
  symbol-cell review zwraca jawnie V2, by nie utrwalać kontraktu legacy.
- Minimalne query doubles używane przez testy `image_review_repository` nie
  są instancją SQLAlchemy `Session`; tylko one pomijają `_bind()`. Produkcyjny
  konstruktor otrzymuje `Session` i nie ma tej gałęzi.
- `game_deletion_repository.py` i archiwalny eksport starej gry są
  zamrożonymi narzędziami recovery dla stałego legacy ID, nie ścieżką aktywnej
  gry V2. D-448 nie rozszerza ich zakresu w T03; ich usunięcie po fizycznym
  dropie kopii `public` należy do T11 / TASK-0690. Nie znaleziono wywołania
  ich polityki z API ani worker runtime aktywnych gier.

## Weryfikacja wykonana 2026-09-25

```powershell
.\.venv\Scripts\python.exe -m pytest `
  services/api/tests/test_image_review_repository_job_lock.py `
  services/api/tests/test_pending_grid_reinference_preview_repository.py `
  services/api/tests/test_board_search_projection_repository.py `
  services/api/tests/test_image_symbol_review_projection_availability.py `
  services/api/tests/test_image_symbol_review_query_storage.py
# 40 passed

$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest `
  services/api/tests/integration/test_game_storage_routing_postgres.py `
  -k "operational_review_repository_binds_v2_before_game_owned_read or board_search_candidate_upsert_uses_v2_composite_identity"
# 2 passed

$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest `
  services/api/tests/integration/test_image_batch_store.py `
  -k "registers_association_in_v2_store"
# 1 passed
```

Nie uruchamiano DDL/DML na bazie użytkownika. Izolowane testy PostgreSQL
tworzyły i usuwały wyłącznie własne bazy testowe.
