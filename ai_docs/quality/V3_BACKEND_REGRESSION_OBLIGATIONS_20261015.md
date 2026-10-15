---
title: V3 — obowiązki regresyjne ujawnione w kontroli TASK-1002
status: open
last_updated: 2026-10-15
---

# Regresje wcześniejszych części planu

Kontrola TASK-1002 wykazała poniższe błędy także na jego bazie wykonawczej
v1.7.381 / `477bf91ae3d3ab81bf6fc8d96cec38bc0dfef192`. Nie powstały w kodzie
TASK-1002, lecz dotyczą wcześniejszych zadań tego samego planu. Samo określenie
„wcześniejszy błąd” nie zwalnia z ich rozliczenia przed odbiorem całego planu.
Ten dokument nie jest werdyktem audytora ani raportem jakości modelu.

## Izolacja trzech tabel

Dokładny test z `services/api/tests/integration/test_per_game_isolation_new_game.py`
odtwarza FAIL dla `grid_reinference_sources`, `grid_reinference_targets`
i `grid_geometry_proposals`. Źródła eksportu HEAD381 zweryfikowano względem
Git przed i po wykonaniu (1123 pliki, bez wliczania wygenerowanego pycache).

Pierwsze dwie tabele wprowadził TASK-0999, commit
`62e9f71986a74d67776eabad6e99154f4d18c0b2`; trzecią TASK-1013, commit
`a688a40108f33ede3a894002a6fc8a8ed53d8141`. Wszystkie powstały po bazie planu
`171e23799ebdbee4ed4590a53376bf870c6741c2`.

Manifesty v12/v13 i lifecycle opisują te relacje jako game-owned. Dalszy
odczyt ustalił konkretną przyczynę: test importuje `GAME_TABLES`, `VERSION`
i `ownership` z v8 (linia59), mimo że jego fixture migruje do head, a guard
w liniach115–121 sprawdza bieżące ORM. Aktualizacja tego konsumenta do v14
wchodzi do korekty P1-1 TASK-1002, z zachowaniem wszystkich asercji.
Nie wolno uznać tabel za shared ani zmieniać ich izolacji dla zielonego testu.
Zamknięcie tej uwagi wymaga rzeczywistego wyniku po aktualizacji.

## Niezarejestrowana granica cofania 0158

Dokładny przypadek
`services/api/tests/integration/test_postgres_baseline.py::test_upgrade_downgrade_upgrade_cycle_on_postgres`
odtworzył na HEAD381 `GAME_CREATE_DOWNGRADE_REFUSED` w migracji0158. Ten sam
błąd wystąpił w aktualnym cyklu po poprawnym przejściu przez pustą0161.
Historyczny eksport1291 plików źródeł, testów, migracji i danych SQL zachował
identyczne SHA przed i po wykonaniu.

Historyczny test uruchomiono z jawnym nadpisaniem wyłącznie
`TEST_DATABASE_NAME` na własny UUID oraz kontrolą absence/createdHere/OID/PID
i cleanup. Asercje i migracje pozostały oryginalne. Jest to dowód zachowania
starego kodu w bezpiecznym harnessie, nie uruchomienie bez żadnego nadpisania.
Nie wykonano operacji na bazie operatora.

Migrację0158 wprowadził TASK-1004, commit
`70058ee5b71ec6e7383d7038648bd5c0dc6a2ead`. Odmowa chroni historię tworzenia
gier. Framework cyklu rejestruje granice0136/0150, lecz pomija0158. Naprawa
powinna zachować ochronę0158 oraz sprawdzić odmowę i dalszy upgrade.

## Obowiązek dalszej pracy

Przed TASK-1001 trzeba rozliczyć rzeczywisty wynik poprawki konsumenta manifestu
w1002 oraz ustalić i wykonać osobną poprawkę pominiętej granicy0158 z audytem
i commitem. TASK-1002 nie zmienia polityki0158 ani nie ukrywa tych FAIL.
Numer i model nowego taska należy utrwalić przed jego implementacją.

Dowody wykonawcze pozostają w ignorowanym `artifacts/audits/`:
`TASK-1002_R1_HEAD381_REPRO.json`, odpowiadający verbose log,
`TASK-1002_R1_HEAD381_CYCLE_PROOF.json`, log i receipt zasobów oraz
`TASK-1002_PRIOR_REGRESSION_ATTRIBUTION.json`. Ich źródła Git i zakresy
umożliwiają ponowne przygotowanie reprodukcji. Nie są snapshotem bazy operatora.

Osobno wykryte `DuplicateSchema(game_data_v2)` przy public-only reset nadal
wymaga atrybucji. Nie uznano go za naprawiony ani za potwierdzoną regresję
konkretnego taska. Atrybucję `JobConflictError` doprecyzowano poniżej. Dwa
opcjonalne testy rzeczywistych checkpointów pozostają niewykonane z powodu
wyjścia poza zatwierdzony zakres operacyjny.

## Uzupełnienie atrybucji jednostkowej

Trzy dokładne testy jednostkowe odtworzyły FAIL także na niezmienionym
HEAD381 (`TASK-1002_R1_HEAD381_UNIT_FAILURES.json`). Czwarty przypadek ma
oddzielny dowód `TASK-1002_R1_HEAD381_SYMBOL_ITERATION_FAILURE.json`.
Poniższy odczyt kodu
i historii ustala wcześniejszy kontrakt; nie zastępuje wykonania poprawki.

- `test_grid_engine_profiles_migration.py::test_0140_extends_the_constraint_with_exactly_the_domain_values`
  porównuje historyczny DDL0140 z bieżącym enumem. TASK-0994 rozszerzył enum
  o `neural_grid_v3` w `c06b7432e76e6e3d24b1cd78757d9f900bc9cac7`.
  Migracja0156, linie49–56, już rozszerza właściwy constraint. Nie wykazano
  brakującej migracji produkcyjnej. Poprawka powinna przypiąć historyczny
  test do historycznego kontraktu oraz zachować osobną kontrolę nowego DDL.
- `test_image_symbol_review_backfill_storage.py::test_start_marks_reconciliation_of_ready_projection_as_available`
  używa mocka `session.scalar.return_value=0`. Admission dodane przez
  TASK-0999 w `62e9f71986a74d67776eabad6e99154f4d18c0b2` wykonuje wcześniej
  inne zapytanie i interpretuje taki mock jako aktywny job. Minimalny kierunek
  to realistyczna granica admission w teście, z zachowaniem jego asercji.
  Nie wykazano błędu algorytmu symboli ani potrzeby osłabienia blokady.
- `test_neural_page_geometry_api.py::test_all_unbound_neural_sources_start_and_replay_without_invented_boards`
  nie przekazuje game-scoped resolvera symboli wymaganego przez TASK-1004,
  commit `70058ee5b71ec6e7383d7038648bd5c0dc6a2ead`. Należy uzupełnić fixture,
  zachowując odmowę `SYMBOL_MODEL_RESOLVER_REQUIRED` i izolację gry.
- `test_symbol_model_iteration_storage.py::test_rejected_retry_and_lost_response_replay_survive_new_repository`
  używa `_TrainingSession` bez `get_bind`. Dodany przez TASK-0999 admission
  (`job_admission.py:54`, commit `62e9f71986a74d67776eabad6e99154f4d18c0b2`)
  wymaga tego interfejsu sesji. Dokładny historyczny test zakończył się
  `AttributeError` po3.45s, przy1291 niezmienionych Gitblobach. Poprawka
  powinna dostosować test double, zachowując sprawdzenie retry i replay
  w nowym repozytorium oraz rzeczywistą ochronę admission.

Wszystkie wskazane zmiany kontraktów powstały po bazie tego planu. Ich
rozliczenie należy do osobnej poprawki regresyjnej wcześniejszych pionów,
obok granicy0158, przed TASK-1001. Nie są poprawką manifestu/provisioningu1002.

Przypadek API tworzenia gry z rzeczywistą rolą aplikacji zwrócił obecnie422
przy braku `idempotencyKey`. Historyczna próba HEAD381 zakończyła się błędem
setup przed żądaniem HTTP; nie odtworzyła tego422. Identyczność źródeł testu
i schematu jest wyłącznie dowodem statycznym. Atrybucja i korekta tego przypadku
nie wynikają z historycznego wykonania; nie wolno przedstawiać go jako
historycznie odtworzonego FAIL ani usuwać wymagania klucza idempotencji.
Dalszy odczyt ustalił przyczynę walidacji: POST w liniach447–450
`test_application_role_isolation_postgres.py` nie zawiera `idempotencyKey`,
a wymagane pole `GameCreate.idempotency_key` w `schemas/catalog.py:58–60`
wprowadził TASK-1004 / `70058ee5b71ec6e7383d7038648bd5c0dc6a2ead`.
Poprawka fixture musi użyć zgodnego żądania i rzeczywistego wymaganego
przygotowania katalogu modeli, zachowując kontrole roli i HTTP. Samo dodanie
pola nie jest dowodem zaliczenia dalszej ścieżki201.

## Podgląd usuwania archiwalnej gry

`scripts/delete_archived_v2_game.py` importuje zamrożony manifestv8. Taki import
pochodzi z TASK-1008 / `f4ff1f4d3b0d49600ffb8fbbdd948d60ff942a65`, kiedy v8
był aktualny. TASK-0994 / `c06b7432e76e6e3d24b1cd78757d9f900bc9cac7` podniósł
manifest magazynu do v9 bez aktualizacji tego konsumenta.

Dokładny niezmieniony Gitblob `collect_blockers` z HEAD381 zwraca
`GAME_STORAGE_LOCATION_INVALID` dla aktualnego wówczas manifestuv13, podczas
gdy kontrolav8 zwraca pustą listę. Dowód
`TASK-1002_R1_HEAD381_DELETE_PREVIEW_PROOF.json` blokuje tworzenie silnika bazy;
jest wykonaniem czystego predykatu, nie historycznym testem PG ani usunięciem.

To wcześniejsza regresja tego planu. Osobna poprawka powinna uzgodnić aktualny
kontrakt podglądu z właściwym manifestem, zachowując wszystkie blokady,
potwierdzenia i zakres archiwalnej gry. Samo naprawienie mechanizmu nie
upoważnia do uruchomienia usuwania na danych operatora.

## Domyślny przebieg a opt-in PostgreSQL

Piąty FAIL domyślnego przebiegu to setup
`test_symbol_rgb_v2_writer_postgres.py::test_rgb_v2_write_filter_and_revert_on_one_board`.
Próba zakończyła się odmową połączenia przez sandbox przed wykonaniem SQL.
Nie jest to pomiar zachowania modelu ani odtworzona historyczna regresja PG.

Moduł RGB z TASK-0871 / `26db7bda7` deklaruje opt-in w docstringu, lecz
nie ma własnego `pytestmark`. Importuje fixture z `test_image_batch_store`,
którego marker modułu nie przechodzi przez import fixture. URL maintenance
pochodzi z `ApiSettings.from_environment` z nazwą bazy przełączoną na postgres;
nie wykazano stałego zaszytego URL. Czerwony dowód pochodzi z początkowej
sandboxowej partii, przed dodatkowymi osłonami późniejszych partii.

Domyślny przebieg nie otrzymuje PASS na podstawie późniejszego innego testu.
Ewentualne wykonanie tej funkcjonalności w jawnej macierzy PG jest odrębnym
dowodem na własnej fixture. Modułowy warunek opt-in wymaga osobnego rozliczenia,
z zachowaniem pełnych asercji funkcjonalnych przy jawnym włączeniu PG.


## Uzupełnienie po Claude R2 PASS TASK-1002 — 2026-10-16

P1-1/P1-2/P1-3 zadania1002 zamknięto niezależnym audytem. Nie oznacza to
pełnego PASS szerszych zestawów. Konsumenci bieżącego head49:47 PASS, stara
fixture POST422 oraz brak wymaganego trybu application-role. Reinference32:
31 PASS i zachowany wcześniejszy reset FAIL. Wszystkie asercje izolacji tabel
zachowano; dalsza naprawa nie może zmieniać game-owned na shared.

### Narzędzia wymagające zgodności z0161 (R2-P2-1)

- `scripts/run_m4_import_acceptance.py:273` — własne CREATE DATABASE → capability → head; zachować dokładną własność/cleanup.
- `scripts/prepare_m34_device_candidate.py:93` — własne CREATE DATABASE → capability → head; zachować dokładną własność/cleanup.
- `scripts/run_concurrent_worker_lane_acceptance.py:589` — własne CREATE DATABASE → capability → head; zachować dokładną własność/cleanup.
- `services/worker/src/game_predictor_worker/images/load_benchmark.py:238` — własne CREATE DATABASE → capability → head; zachować dokładną własność/cleanup.
- `services/worker/src/game_predictor_worker/images/operations_benchmark.py:281` — własne CREATE DATABASE → capability → head; zachować dokładną własność/cleanup.

Poprawić kontrakt przed odbiorem1001, z testem statycznym i małym izolowanym
testem ścieżki provisioningu. Nie uruchamiać benchmarków ani operacji danych
operatora. Implementacja nie jest zgodą na wykonanie tych narzędzi.

### Dokładne niezweryfikowane przypadki (R2-P2-5)

Źródło: zamrożony TASK-1002_R2_PG_FAILURE_CLASSIFICATION.json i jego bezpieczna
mapowana kopia.18 incomplete i6 harness/env; nie traktować jako24 awarii
produktu. Sprawdzić dokładne cele w ograniczonych częściach do120s, przez
własne UUID bazy/role i poprawny tryb aplikacyjny tam, gdzie wymagany.
Nie powtarzać całej macierzy473/614 bez nowej uzasadnionej potrzeby.

- `services/api/tests/integration/test_board_import_coverage_repository.py::test_diagnostics_snapshot_rls_union_and_separate_request_session`
- `services/api/tests/integration/test_grid_geometry_proposals_postgres.py::test_commands_real_manual_save_and_restart[accept]`
- `services/api/tests/integration/test_grid_geometry_proposals_postgres.py::test_commands_real_manual_save_and_restart[cleanup]`
- `services/api/tests/integration/test_grid_geometry_proposals_postgres.py::test_commands_real_manual_save_and_restart[edited]`
- `services/api/tests/integration/test_grid_geometry_proposals_postgres.py::test_commands_real_manual_save_and_restart[reject]`
- `services/api/tests/integration/test_grid_geometry_proposals_postgres.py::test_commands_real_manual_save_and_restart[rollback]`
- `services/api/tests/integration/test_grid_geometry_proposals_postgres.py::test_commands_real_manual_save_and_restart[stale]`
- `services/api/tests/integration/test_grid_geometry_proposals_postgres.py::test_current_live_merge_rechecks_sibling_after_render`
- `services/api/tests/integration/test_grid_geometry_proposals_postgres.py::test_discovery_skips_only_invalid_candidate`
- `services/api/tests/integration/test_grid_geometry_proposals_postgres.py::test_mixed_sibling_current_snapshot_is_preserved[False]`
- `services/api/tests/integration/test_grid_geometry_proposals_postgres.py::test_mixed_sibling_current_snapshot_is_preserved[True]`
- `services/api/tests/integration/test_grid_geometry_proposals_postgres.py::test_pixels_same_path_and_path_receipt_scope`
- `services/api/tests/integration/test_grid_geometry_proposals_postgres.py::test_real_source_cleanup_retains_proposal_and_error_receipt`
- `services/api/tests/integration/test_grid_geometry_proposals_postgres.py::test_two_game_rls_composite_reference_and_whole_game_lifecycle`
- `services/api/tests/integration/test_grid_model_publication_postgres.py::test_migration_parallel_cas_invalidation_restart_and_assignment_boundary`
- `services/api/tests/integration/test_grid_model_registry_postgres.py::test_upgrade_keeps_games_partitions_and_pins_historical_models`
- `services/api/tests/integration/test_slim_prediction_revisions_postgres.py::test_slimming_retention_and_migration_0137`
- `services/api/tests/integration/test_superseded_import_image_removal.py::test_a_second_run_deletes_nothing`
- `services/api/tests/integration/test_superseded_import_image_removal.py::test_an_invariant_violation_rolls_back_every_delete`
- `services/api/tests/integration/test_superseded_import_image_removal.py::test_execute_refuses_a_plan_that_changed_since_the_preview`
- `services/api/tests/integration/test_superseded_import_image_removal.py::test_execute_removes_only_dead_images_and_backs_up_every_row`
- `services/api/tests/integration/test_superseded_import_image_removal.py::test_preview_qualifies_only_dead_images_and_writes_nothing`
- `services/api/tests/integration/test_superseded_import_image_removal.py::test_script_preview_report_drives_the_confirmed_execute`
- `services/api/tests/integration/test_symbol_review_query_cancellation.py::test_disconnect_cancel_stops_postgres_and_keeps_the_connection_reusable`

R2-P2-4: baseline nadal ma stałą nazwę i fail-closed po nieudanym CREATE.
Osobna poprawka testframework ma użyć własnej UUID tożsamości i zachować
pierwotny błąd; żadnego DROP/FORCE na nieudowodnionej bazie. R2-P2-2 opisano
w instrukcji wdrożenia. R2-P2-3 journals zachowano świadomie jako dowody.
Literalne pełne db:baseline:verify nadal nie zostało zaliczone; odpowiednik
partiami nie daje takiego twierdzenia. Dalsze dowody i poprawki mają osobny
task/audyt/commit przed odbiorem całego planu.
