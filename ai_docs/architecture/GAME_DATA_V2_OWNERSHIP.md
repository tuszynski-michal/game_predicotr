---
title: Game data v2 ownership manifest
status: accepted
last_updated: 2026-09-21
---

# Własność tabel game_data_v2 — TASK-0518

Wersja `game-data-v2-manifest-v1` jest zamrożonym kontraktem migracji 0105.
Źródło wykonawcze: `game_data_v2_manifest_v1.py`; struktura tabel i FK jest
zamrożona w `services/api/alembic/sql/game_data_v2_schema_v1.sql`, bez importu
bieżących modeli ORM przez migrację. Nowa tabela wymaga nowej wersji manifestu
oraz migracji. Test odrzuca niezaklasyfikowaną tabelę ORM.

## Control plane po manifeście v1 — TASK-0605

`game_data_v2_manifest_v2.py` zachowuje bez zmiany 65 partycjonowanych tabel
i ich lifecycle z v1, a klasyfikuje późniejsze tabele publiczne jako `shared`.
W szczególności `global_geometry_profile_versions`,
`global_geometry_evidence_samples` i `global_geometry_profile_write_receipts`
są biblioteką control plane. Nie mają `game_id`, nie mogą wejść do partycji
gry ani uruchomić `GameStorageRouter`; `source_game_ref` jest wyłącznie
opisową proweniencją. Nie przechowują danych obrazu ani semantyki gry.

## Reguły i granice

- `catalog`: pojedynczy wspólny katalog/koordynator w `public`. `jobs` pozostaje
  wspólny, ponieważ jego `UNIQUE(execution_slot)` serializuje globalny worker lane.
  FK z v2 do `jobs`, `symbols` i `rules_versions` używa `(game_id, id)`.
- `game`: 65 rodziców `LIST(game_id)` w `game_data_v2`; wszystkie mają NOT NULL
  game_id i klucze z prefiksem gry. Małe metadane związane FK z tymi danymi są
  w tym samym magazynie. Relacje do publicznych historycznych kopii są zabronione.
- `shared`: globalne wykonania content-addressed, zdalna/półautomatyczna selekcja,
  wielogrowe release metadata, utrzymaniowe receipty i registry. Wspólna referencja
  do treści lub wydania nie przenosi własności gry.
- `browser_selection_retention_states` ma historycznie także NULL game_id.
  Globalny staging pozostaje w `public`; tylko rekord z ustaloną grą może wejść
  do v2. Nie wolno kopiować globalnych stagingów przez odgadywanie właściciela.
- Globalne `mobile_releases.build_job_id`, `storage_gc_runs.job_id` oraz joby
  półautomatu wskazują ten sam publiczny koordynator; nie wymagają wyboru tabeli.
- Poniższa tabela wskazuje istniejących rodziców; v2 dodaje bezpośredni FK do games
  także tam, gdzie poprzednio własność wynikała wyłącznie z pośredniego rodzica.
  Wszystkie game-owned FK mają game_id po obu stronach i indeks prefiksowy.
- Kolejność identyfikatorów w manifestach jest deterministyczna, ale nie jest
  kolejnością kopiowania danych. Migrator musi respektować poniższe zależności
  i jawne self-reference runs/groups; `sequence_number` pozostaje domeną.

## Pełna mapa

| Tabela | Klasa | Rodzice (FK) |
|---|---|---|
| `alembic_version` | shared | — |
| `browser_selection_retention_states` | game | `games`, `jobs` |
| `cell_observations` | game | `image_source_geometry_revisions`, `recognized_boards` |
| `cleanup_operations` | shared | — |
| `curated_image_import_batches` | game | `curated_image_import_sources`, `jobs` |
| `curated_image_import_sources` | game | `games`, `image_selection_runs` |
| `dataset_versions` | game | `games`, `jobs` |
| `game_deletion_batches` | shared | — |
| `game_deletion_operations` | shared | — |
| `game_grid_profile_activations` | game | `games`, `grid_calibration_profiles` |
| `global_geometry_evidence_samples` | shared | `global_geometry_profile_versions` |
| `global_geometry_profile_versions` | shared | — |
| `global_geometry_profile_write_receipts` | shared | `global_geometry_profile_versions` |
| `game_storage_locations` | shared | `games` |
| `game_storage_migrations` | shared | — |
| `game_storage_table_manifest` | shared | — |
| `game_storage_table_progress` | shared | `game_storage_migrations`, `game_storage_table_manifest` |
| `game_symbol_model_activations` | game | `games`, `symbol_model_iterations` |
| `games` | catalog | `rules_versions` |
| `grid_calibration_profiles` | game | `games`, `grid_geometry_cohorts` |
| `grid_geometry_cohorts` | game | `games` |
| `image_board_geometry_pending` | game | `games`, `image_review_items`, `jobs`, `recognized_boards`, `source_images` |
| `image_board_geometry_review_events` | game | `image_review_items`, `recognized_boards` |
| `image_board_geometry_revisions` | game | `image_review_items`, `image_source_geometry_revisions`, `recognized_boards` |
| `image_board_search_candidates` | game | `games`, `image_review_items`, `jobs`, `recognized_boards` |
| `image_board_search_fast_documents` | game | `games`, `image_board_search_candidates` |
| `image_board_search_projection_states` | game | `games` |
| `image_file_executions` | shared | — |
| `image_geometry_rollout_states` | game | `games`, `jobs`, `source_images` |
| `image_import_geometry_guard_decisions` | game | `browser_selection_retention_states`, `games`, `jobs` |
| `image_import_geometry_guard_resolution_manifests` | game | `browser_selection_retention_states`, `games`, `jobs` |
| `image_import_job_files` | game | `image_file_executions`, `jobs` |
| `image_layout_staging_rows` | game | `image_review_items`, `jobs`, `recognized_boards` |
| `image_page_geometry_overrides` | game | `games` |
| `image_page_source_exclusions` | game | `browser_selection_retention_states`, `games` |
| `image_pipeline_stage_results` | shared | `image_file_executions` |
| `image_pipeline_terminal_manifests` | shared | `image_file_executions` |
| `image_review_items` | game | `games`, `jobs`, `recognized_boards` |
| `image_review_queue_items` | game | `image_review_items`, `jobs` |
| `image_review_queue_states` | game | `jobs` |
| `image_review_resolution_events` | game | `image_review_items` |
| `image_selection_candidates` | game | `image_selection_groups`, `image_selection_runs` |
| `image_selection_groups` | game | `image_selection_groups`, `image_selection_runs` |
| `image_selection_manual_decisions` | game | `image_selection_candidates`, `image_selection_groups`, `image_selection_runs` |
| `image_selection_runs` | game | `games`, `image_selection_runs`, `jobs` |
| `image_sequence_alternatives` | game | `games`, `jobs` |
| `image_sequence_canonical` | game | `games`, `image_review_items`, `jobs`, `recognized_boards`, `source_images` |
| `image_sequence_source_override_events` | game | `games`, `image_review_items` |
| `image_source_geometry_revisions` | game | `games`, `rules_versions`, `source_images` |
| `image_symbol_prediction_revisions` | game | `games`, `image_review_items`, `jobs`, `recognized_boards`, `symbol_model_iterations` |
| `image_symbol_review_bulk_operations` | game | `games`, `jobs`, `symbols` |
| `image_symbol_review_bulk_targets` | game | `image_review_items`, `image_symbol_review_bulk_operations`, `image_symbol_review_cells`, `recognized_boards` |
| `image_symbol_review_cells` | game | `games`, `image_review_items`, `image_source_geometry_revisions`, `image_symbol_prediction_revisions`, `jobs`, `recognized_boards`, `symbols` |
| `image_symbol_review_events` | game | `image_review_items`, `image_source_geometry_revisions`, `image_symbol_review_bulk_operations`, `image_symbol_review_cells`, `symbols` |
| `image_symbol_review_states` | game | `games` |
| `image_verified_cohort_exports` | game | `games`, `jobs` |
| `jobs` | catalog | `games` |
| `layout_import_normalized_rows` | game | `jobs`, `layout_import_rows`, `rules_versions` |
| `layout_import_rows` | game | `jobs` |
| `layout_payouts` | game | `layouts`, `rules_versions` |
| `layouts` | game | `dataset_versions` |
| `legacy_board_search_archive_documents` | game | `games` |
| `legacy_board_search_archive_states` | game | `games` |
| `legacy_game_operational_cleanup_receipts` | shared | `games` |
| `mobile_release_games` | game | `dataset_versions`, `games`, `mobile_releases`, `rules_versions` |
| `mobile_releases` | shared | `jobs` |
| `paylines` | catalog | `rules_versions` |
| `payout_rules` | catalog | `rules_version_symbols` |
| `recognized_boards` | game | `image_source_geometry_revisions`, `source_images` |
| `remote_manual_selection_audit_events` | shared | `remote_manual_selection_batches`, `remote_manual_selection_sessions` |
| `remote_manual_selection_batches` | shared | `remote_manual_selection_collections`, `remote_manual_selection_sessions` |
| `remote_manual_selection_collections` | shared | `remote_manual_selection_sessions` |
| `remote_manual_selection_files` | shared | `remote_manual_selection_batches` |
| `remote_manual_selection_host_actions` | shared | `remote_manual_selection_files`, `remote_manual_selection_transfers` |
| `remote_manual_selection_operations` | shared | `remote_manual_selection_batches`, `remote_manual_selection_files`, `remote_manual_selection_operations` |
| `remote_manual_selection_sessions` | shared | — |
| `remote_manual_selection_transfers` | shared | `remote_manual_selection_files` |
| `representative_ranking_activations` | game | `games`, `representative_ranking_iterations` |
| `representative_ranking_cohorts` | game | `games` |
| `representative_ranking_iterations` | game | `representative_ranking_cohorts` |
| `review_batches` | game | `games` |
| `review_feedback_exports` | game | `games`, `review_batches` |
| `review_items` | game | `review_batches` |
| `review_resolutions` | game | `review_items` |
| `reviewer_access_audit_events` | game | `reviewer_access_sessions` |
| `reviewer_access_sessions` | game | `games`, `jobs` |
| `reviewer_work_assignments` | game | `games`, `jobs`, `reviewer_access_sessions` |
| `rules_version_symbols` | catalog | `rules_versions`, `symbols` |
| `rules_versions` | catalog | `games` |
| `semi_automatic_filename_verification_reviews` | shared | `semi_automatic_image_selection_runs` |
| `semi_automatic_image_selection_ranges` | shared | `semi_automatic_image_selection_runs` |
| `semi_automatic_image_selection_runs` | shared | `jobs` |
| `source_images` | game | `image_file_executions`, `jobs` |
| `storage_gc_runs` | shared | `jobs` |
| `storage_usage_snapshots` | shared | — |
| `symbol_model_iterations` | game | `games`, `jobs`, `verified_training_cohorts` |
| `symbol_reference_images` | game | `cell_observations`, `games`, `image_review_items`, `recognized_boards`, `symbols` |
| `symbols` | catalog | `games` |
| `verified_training_cohort_cells` | game | `image_review_items`, `image_source_geometry_revisions`, `image_symbol_review_cells`, `recognized_boards`, `source_images`, `verified_training_cohorts` |
| `verified_training_cohort_items` | game | `image_review_items`, `jobs`, `recognized_boards`, `source_images`, `verified_training_cohorts` |
| `verified_training_cohorts` | game | `games` |
| `worker_lane_runtime` | shared | — |

## Registry i trwałość

`public.game_storage_locations` przechowuje aktywny store, generację, status i
rewizję gry. `game_storage_migrations` utrwala źródło/cel, generacje i stan
operacji; jego brak FK do games jest celowy, aby audyt przeżył usunięcie gry.
Złożony FK checkpointu łączy game_id + operation + manifest_version, a FK do
manifestu dopuszcza tylko tabelę klasy game. Cursor ma limit 64 KiB. Jeden
nieterminalny migration receipt na grę blokuje niezależny konkurencyjny run;
failed jest wznawiany, nie traktowany jako zwolnienie blokady.

Migracja 0110 dodaje osobny `game_storage_lifecycle_operations`, którego receipt
nie ma FK do usuwanej gry. Provisioning i delete zapisują po jednej tabeli
zamrożonego manifestu na transakcję. Prefiks `completed_tables` musi dokładnie
odpowiadać bieżącej kolejności; restart kontynuuje od `next_table_index`, a dryf
checkpointu blokuje operację. Partycje mają deterministyczną nazwę, jawny parent
i pojedynczy bound UUID. Po utworzeniu sprawdzane są kolumny, ustawienia
autovacuum oraz `ANALYZE`; dopiero kompletny zestaw aktywuje location V2.

Delete uzyskuje ten sam wyłączny advisory fence, ustawia location na `deleting`
i wyznacza kolejność dzieci-przed-rodzicami z FK parentów oraz ich partycji.
Każda tabela jest najpierw odłączana od parenta, następnie usuwana bez
`CASCADE`. Po ostatniej partycji w jednej transakcji usuwane są małe rekordy
katalogu, location i gra. Referencje z public/shared nie są obchodzone: FK lub
dryf zatrzymuje finalizację. Fizyczny GC plików pozostaje osobnym, zatwierdzanym
i reference-aware etapem operatorskim.

## Bezpieczeństwo wdrożenia

Audyt porównuje wszystkie domenowe kolumny oraz CHECK constraints z pełnym torem
Alembic w izolowanym PostgreSQL. Zachowuje także CHECK checksumów iteracji modelu,
obecny w migracji 0035, choć brakowało go w ORM. Jedno jawne zaostrzenie dotyczy
`image_symbol_review_events`: wymagane jest `(previous valid) AND (current valid)`
zgodnie z ORM i regułą proweniencji. Słabszy legacy CHECK z 0082 mógł przez brak
nawiasów zaakceptować niepoprawny current virtual asset, gdy previous był legacy.
Test SQL odtwarza ten przypadek i dowodzi odrzucenia przez nowy constraint.
Nie zmienia to historycznej migracji ani danych w public.

0105 tworzy pusty schemat i wpisy definicji manifestu. Nie zakłada partycji,
nie rejestruje gier, nie kopiuje danych, nie przestawia routingu i nie dotyka
plików. Brak partycji powoduje jawny błąd PostgreSQL `no partition ... found`.
Migracja 0106 dostarcza routing, write fence, transaction-local scope, RLS oraz
schema-aware triggery kolejki. Nie tworzy partycji i nie przełącza żadnej gry.
Każdy write pobiera współdzieloną blokadę advisory gry i registry; cutover
zmieniający status lub generację wymaga wyłącznej blokady advisory tego samego
klucza. Po greenfield cutoverze brak registry jest błędem i nie uruchamia
legacy fallbacku. Stary job zachowuje payload i checkpoint, ale po wznowieniu
rozwiązuje aktualną lokalizację gry. Legacy triggery nie są
kopiowane bezpośrednio do v2, bo zawierają referencje do publicznych danych
historycznych; ich odpowiedniki z 0106 jawnie rozdzielają schematy.

Downgrade najpierw blokuje wszystkie objęte tabele i sprawdza pustkę. Jakiekolwiek
dane v2, location, migration lub checkpoint zatrzymują rollback; nie używa
CASCADE. Jest odwróceniem wyłącznie pustego wdrożenia, nie rollbackiem migracji
użytkownika. Dodatkowe nieznane zależności także blokują DROP.

## Greenfield cutover

TASK-0525 zastosował migracje 0105–0110 po audycie pustego katalogu. Nowa gra
otrzymuje location `game_data_v2`, generację 2 i status `migrating` w tej samej
transakcji co pierwszy receipt provisioningu. Każda z 65 partycji jest
tworzona i checkpointowana oddzielnie. Dopiero pełna walidacja manifestu oraz
zapis domyślnej polityki geometrii do partycji gry przełączają location na
`active`.

Brak location dla istniejącej gry jest dryfem i blokuje data-plane. Nie wolno
już tworzyć produkcyjnego registry `public` ani kierować nowej gry do legacy.
Puste historyczne tabele i migracje pozostają do osobnego planu ich usunięcia.
