# TASK-0945 — Migracja 0153, status `reverted` i cofnięcie korekty slotu odroczonego

## Status

`done`

## Goal

Operacja aplikacyjna cofa ostatnie ręczne rozstrzygnięcie odroczonego slotu (przypadek B) w jednej transakcji, przywracając stan sprzed zapisu i zapisując audyt z migawką.

## Context

Operator chce cofać pomyłkowe zapisy z ekranu „Korekta cięcia siatki”. Przykład: slot `378a273f-…` (Mumie, sekwencja 69004) rozstrzygnięty 2026-10-09 08:39:41 UTC. Plan: `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`, sekcje „Model domenowy”, „Przypadek B”, „Rewizja źródła `reverted`”, „Audyt i powtórzenia”.

## Dependencies / entry conditions

- Head migracji `0152_super_game_series` na gałęzi integracyjnej; sprawdź, czy nie ma nowszej (kolizje numerów).
- Operator wykonuje migrację na swojej bazie dopiero w TASK-0951.

## Recommended execution

`claude-opus-5-5`, reasoning `high`: migracja, zmiana semantyki „latest” i fizyczne usuwanie grafu wierszy. Eskalacja: niejednoznaczny wpływ na bramkę kompletności (D-484/D-485) → zatrzymaj i zapytaj operatora. Review: Codex `gpt-6-astra`, `high`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md` — D-462, D-484, D-485, D-488

## Scope

- Migracja `0153_geometry_correction_revert` (schemat `game_data_v2`, wzorzec strażnika `0145_neural_page_geometry_binding.py:44`):
  - `ck_image_source_geometry_revisions_state`: dodaj `reverted`;
  - UNIQUE `(source_image_id, geometry_checksum_sha256)` → indeks unikalny częściowy `WHERE status <> 'reverted'`;
  - `ck_image_board_geometry_review_events_action`: dodaj `geometry_reverted`;
  - `ck_image_symbol_review_events_action`: dodaj `geometry_reverted`;
  - `image_symbol_review_events.previous_assignment_source` (nullable, ten sam CHECK wartości co `assignment_source` komórki);
  - `image_board_geometry_pending`: status `rejected`, kolumny `rejection_reason` (`cropped`, `blurred`, `other`), `rejection_note`, `rejected_at`, `rejected_by`; aktualizacja `ck_image_board_geometry_pending_lifecycle` (W7; logika w TASK-0949, w tym tasku tylko schemat i model);
  - tabela `image_geometry_correction_reverts` (kolumny z planu; UNIQUE `(game_id, idempotency_key)`; indeks `(game_id, import_job_id, created_at DESC)`; brak FK do usuwanych wierszy; FK do gry i joba).
  - Zaktualizuj `storage/models.py`, bazowy schemat testów migracji, jeśli wymagany, oraz strażnika schematu startowego (wymagana rewizja `0153`).
- Semantyka „latest” rewizji źródła (pomijaj `reverted`) we wszystkich miejscach:
  `storage/virtual_grid_geometry_repository.py` (`_pending_context` ~1893, `legacy_conversion_plan` ~721),
  `storage/image_grid_review_repository.py` (`_pending_statement` ~406),
  `storage/image_geometry_completeness_repository.py` (~108, ~237, ~281),
  `storage/image_geometry_completeness_state_repository.py` (`_REPOINT_PLAN_SQL` ~470),
  `storage/grid_shadow.py` (~79),
  `storage/superseded_import_image_removal_repository.py` (~716).
  Numeracja w `storage/image_geometry_v2_repository.py:155` nadal liczy wszystkie wiersze. Deduplikacja po checksumie (`image_geometry_v2_repository.py:140`, worker `services/worker/src/game_predictor_worker/images/pipeline_store.py:295` i `:420`) pomija `reverted`.
- `previous_assignment_source` zapisywane przez każde tworzenie zdarzenia komórki (`_apply_symbol_cell_review_transition` i ścieżki `geometry_invalidated`/`board_synchronized`).
- Nowy moduł aplikacyjny (proponowany) `application/geometry_correction_reverts.py`: `GeometryCorrectionRevertService` z metodami `list_recent(game_id, import_job_id, limit)`, `preview(…, board_geometry_revision_id)`, `revert(…, idempotency_key, expected_geometry_revision, expected_resolution_revision, actor)`; port repozytorium; czysta funkcja domenowa `evaluate_revert_eligibility(facts) -> RevertBlockingReason | None` w `domain/geometry_correction_reverts.py` (proponowane).
- Repozytorium (proponowane) `storage/geometry_correction_revert_repository.py`: fakty dla warunków, migawka, usunięcia, przywrócenie slotu, status `reverted`, odwrotne przepięcie (nowy planner + istniejące `apply_board_repoint`), liczniki, wyszukiwarka, bramka kompletności, wiersz audytu. Dla przypadku A (`kind = board_revision`) w tym tasku `revert` zwraca `GEOMETRY_REVERT_NOT_SUPPORTED` (implementacja w TASK-0946), ale `list_recent` i warunki wspólne obejmują oba rodzaje.
- Strażnik powtórzeń: `_find_replay` (`application/virtual_grid_geometry.py:911`) zwraca 409 `GEOMETRY_CORRECTION_REVERTED`, gdy klucz należy do cofniętego zapisu.
- Punkt zapisu wersji wejścia supergry `geometry_correction_revert` w `SUPER_GAME_INPUT_WRITE_POINTS`.

## Out of scope

- Przypadek A (TASK-0946), HTTP (TASK-0947), UI (TASK-0948), wykonanie migracji na bazie operatora i cofnięcie 69004 (TASK-0951).

## Acceptance criteria

- [ ] Migracja `0153` przechodzi upgrade/downgrade na bazie `*_test`; downgrade odmawia, gdy istnieją wiersze `reverted` albo audytu (bez cichej utraty danych).
- [ ] Cofnięcie slotu przywraca stan sprzed zapisu: slot `pending` z wyzerowanymi polami rozstrzygnięcia, brak planszy/pozycji/komórek/rewizji planszy/manifestu/zdarzeń, rewizja źródła `reverted`, sąsiedzi wskazują poprzednią rewizję, kolejka przeglądu, status joba, wyszukiwarka, `count_projection`, `cell_count` i stan bramki zdjęcia równe stanowi sprzed zapisu (porównanie migawek w teście).
- [ ] Slot wraca do widoku `correction` z propozycją poprzedniej rewizji źródła.
- [ ] Każdy kod blokady z planu ma test odmowy bez zapisu.
- [ ] Ponowny zapis tej samej geometrii po cofnięciu tworzy nową rewizję źródła (nie wskrzesza `reverted`).
- [ ] Powtórzenie żądania cofnięcia z tym samym kluczem zwraca ten sam wynik; powtórzenie starego zapisu korekty → 409 `GEOMETRY_CORRECTION_REVERTED`.
- [ ] Istniejące testy bramki kompletności i korekty slotu przechodzą bez zmian asercji.

## Technical notes

- Kolejność blokad jak przy zapisie: `acquire_image_sequence_locks` → `source_images FOR UPDATE` → slot `FOR UPDATE` → plansza/pozycja.
- Warunki oceniaj po zablokowaniu, z faktów z bazy; nie ufaj danym klienta poza tokenami CAS.
- „Przed zapisem” dla sąsiadów: przepnij tylko plansze, które wskazują cofaną rewizję, mają `geometry_revision = 0`, nie są `rejected`, i których wpis slotu jest identyczny w obu rewizjach (porównanie jak `_REPOINT_PLAN_SQL` ~486); inna sytuacja → `GEOMETRY_REVERT_SHARED_SOURCE_REVISION`.
- `GEOMETRY_REVERT_SEQUENCE_OWNERSHIP`: wykryj zastąpienie (zdarzenie `superseded` innej pozycji tej sekwencji z czasem transakcji korekty lub późniejszym) i przejęcie komórek (komórki pozycji z `created_at` wcześniejszym niż transakcja korekty albo zdarzenie `board_synchronized` zmiany właściciela).
- `GEOMETRY_REVERT_IMAGE_ADMITTED`: zdjęcie `geometry_complete`/`geometry_exception`, a ocena bez cofanego slotu daje inny stan.
- `source_images.status`: `waiting_for_review`, gdy zdjęcie ma oczekujący slot albo pozycję `pending`; inaczej bez zmiany.
- Migawka: JSON wierszy w kolejności usuwania, kolumny jak w bazie (UUID i daty jako tekst ISO), `snapshot_checksum_sha256` z kanonicznego JSON (sortowane klucze).
- Nie maskuj błędów: konflikt FK lub `rowcount` ≠ oczekiwany → wyjątek i rollback całości.

## Expected files

- Nowe (proponowane): `services/api/alembic/versions/0153_geometry_correction_revert.py`, `services/api/src/game_predictor_api/domain/geometry_correction_reverts.py`, `services/api/src/game_predictor_api/application/geometry_correction_reverts.py`, `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py`, testy `services/api/tests/test_geometry_correction_reverts.py`, `services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py`.
- Zmieniane: `storage/models.py`, zapytania „latest” wymienione w Scope, `storage/image_geometry_v2_repository.py`, `services/worker/src/game_predictor_worker/images/pipeline_store.py`, `storage/image_symbol_review_repository.py` (`previous_assignment_source`), `application/virtual_grid_geometry.py` (`_find_replay`), `storage/super_game_input_version.py`, strażnik schematu.

## Test cases

- Rozstrzygnięty slot (baza: `test_virtual_deferred_resolution_postgres.py::_seed`) → cofnięcie → pełne porównanie stanu z migawką sprzed zapisu.
- Slot z symbolami D-488 na części komórek (bez pełnego rozstrzygnięcia) → cofnięcie usuwa komórki i zdarzenia.
- Każdy kod blokady: późniejsza weryfikacja symbolu, rozstrzygnięta pozycja, nowsza rewizja źródła, zastąpiona pozycja sekwencji, przejęte komórki, dopuszczone zdjęcie, kohorta, CAS, drugie cofnięcie.
- Ponowny zapis identycznej geometrii po cofnięciu → nowa rewizja źródła, sąsiedzi przepięci do przodu.
- Zapytania „latest” z wierszem `reverted` na szczycie → wybierają poprzednią rewizję (testy repozytorium kompletności i kolejki).
- Worker: deduplikacja checksumy pomija `reverted`.

## Verification

```powershell
# z katalogu worktree, timeout 120 s na komendę
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/test_geometry_correction_reverts.py services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py -q
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_virtual_deferred_resolution_postgres.py services/api/tests/integration/test_image_geometry_completeness_gate.py services/api/tests/integration/test_image_geometry_completeness_repository.py -q
npm run db:baseline:verify
npm run python:lint
npm run python:typecheck
```

## Risks / open questions

- Zmiana semantyki „latest” dotyka bramki kompletności; każda rozbieżność istniejących testów zatrzymuje task.

## Outcome

Wykonawca: claude-opus-5-5 (high), 2026-10-09. Bez commita (commit i audyt
Codex należą do leada).

### Changed

- Migracja `0153_geometry_correction_revert` (`services/api/alembic/versions/`):
  status `reverted` w `ck_image_source_geometry_revisions_state`; zamrożone
  UNIQUE `v2_uq_fd29b81bdd3878e81e86` (strażnik sprawdza jego definicję)
  zastąpione indeksem częściowym `v2_uq_source_geometry_revisions_live_checksum`
  `WHERE status <> 'reverted'`; akcje `geometry_reverted` w obu tabelach
  zdarzeń; kolumna `image_symbol_review_events.previous_assignment_source` z
  CHECK słownika `assignment_source`; slot `rejected` (kolumny
  `rejection_reason`/`rejection_note`/`rejected_at`/`rejected_by`, nowy
  `ck_image_board_geometry_pending_rejection`, rozszerzone `_status` i
  `_lifecycle`; `superseded` może zachować pola odrzucenia jako historię,
  `other` wymaga notatki); tabela `image_geometry_correction_reverts`
  (partycjonowana, RLS, FK tylko do gry i joba, UNIQUE `(game_id,
  idempotency_key)` i `(game_id, reverted_board_geometry_revision_id)`, indeksy
  `(game_id, import_job_id, created_at DESC)` i `(game_id,
  reverted_idempotency_key)`). Downgrade odmawia
  (`GEOMETRY_CORRECTION_REVERT_DOWNGRADE_HAS_HISTORY`) przy wierszu audytu,
  rewizji `reverted`, zdarzeniu `geometry_reverted`, wypełnionym
  `previous_assignment_source` albo odrzuconym slocie.
- **Manifest v7** (decyzja wykonawcy, wymagana przez wzorzec D-448/0152): nowa
  tabela gry wymaga nowego zamrożonego manifestu
  (`storage/game_data_v2_manifest_v7.py`); routing, cykl życia partycji,
  katalog, `domain/catalog.py`, `scripts/delete_archived_v2_game.py` i testy
  importują v7; `schema_readiness.EXPECTED_ALEMBIC_HEAD = 0153`. Zmieniły się
  asercje wersji manifestu/heada w `test_game_data_v2_schema.py`,
  `test_catalog_api.py`, `test_schema_readiness.py` i
  `integration/test_super_game_series_postgres.py` (świadoma zmiana kontraktu,
  jak w 0152); w pozostałych ~18 testach zmienił się tylko import v6 → v7.
- ORM: `storage/models.py` (CHECK-i, indeks częściowy, kolumny), nowy
  `storage/geometry_correction_revert_models.py`.
- Semantyka „latest” (pomija `reverted`): `virtual_grid_geometry_repository`
  (`_pending_context`, `legacy_conversion_plan`), `image_grid_review_repository`
  (`_pending_statement`), `image_geometry_completeness_repository` (trzy
  zapytania oraz `has_source_geometry`), `image_geometry_completeness_state_repository`
  (`_REPOINT_PLAN_SQL`), `grid_shadow.pin_source`,
  `superseded_import_image_removal_repository`,
  `scripts/vision_lab_geometry_export.py`. Deduplikacja po checksumie pomija
  `reverted`: `image_geometry_v2_repository.append` (numeracja nadal liczy
  wszystkie wiersze) i worker `pipeline_store.py` (wyszukanie rewizji importu
  po checksumie; ścieżka `:295` korzysta z `append`).
- `previous_assignment_source` zapisywane przez `_append_symbol_cell_event`
  (`_CellPreviousState.assignment_source`) i oba zdarzenia
  `geometry_invalidated` w `virtual_grid_geometry_repository`.
- Domena `domain/geometry_correction_reverts.py`: rodzaje korekt, kody blokad
  z komunikatami po polsku, `evaluate_revert_eligibility` (kolejność tabeli
  planu, fail-closed), `predicted_status_after_slot_revert`,
  `image_admission_blocks_revert`, kanoniczna checksuma migawki.
- Aplikacja `application/geometry_correction_reverts.py`:
  `GeometryCorrectionRevertService` (`list_recent` 1–50, domyślnie 20;
  `preview`; `revert` z walidacją aktora i tokenów CAS), port repozytorium,
  wyniki.
- Repozytorium `storage/geometry_correction_revert_repository.py`: lista
  zdarzeń `geometry_saved` importu z warunkami dla obu rodzajów, podgląd bez
  zapisu, cofnięcie przypadku B wg planu (blokady jak zapis → fakty pod
  blokadą → migawka `to_jsonb` w kolejności usuwania + wiersze aktualizowane →
  `_apply_count_deltas(before=komórki)`, `cell_count` jak
  `_availability_snapshot` tylko dla zapisu kwalifikowanego → usunięcia z
  kontrolą `rowcount` → slot `pending` → źródło `reverted` → odwrotne
  przepięcie przez `apply_board_repoint` + `sync_review_items` →
  `reconcile_sequence` → przeliczenie bramki (odmowa, gdy dopuszczone zdjęcie
  zmieniłoby status) → `source_images.status` → wersja supergry i
  `synchronize_after_cell_mutation` → wiersz audytu). Przypadek A:
  `GEOMETRY_REVERT_NOT_SUPPORTED`. `_selected_available_count` wydzielony do
  funkcji `selected_available_cell_count`.
- Strażnik powtórzeń: `SqlAlchemyVirtualGridGeometryRepository.virtual_geometry_replay`
  (wołany przez `_find_replay`) oraz ponownie po blokadach w obu ścieżkach
  zapisu zwraca `ImageGridReviewError("GEOMETRY_CORRECTION_REVERTED")`;
  `main.py` mapuje kod na 409. Port `VirtualGridGeometryRepository` bez zmian
  (fałszywe repozytoria testów nienaruszone).
- Punkt zapisu wersji wejścia supergry `geometry_correction_revert`
  (`SqlAlchemyGeometryCorrectionRevertRepository._revert_pending_slot`).

Decyzje wykonawcy (do audytu):

- „Transakcja korekty” `T` = `board_render_manifests.created_at` rewizji
  korekty (serwerowe `now()`; potwierdzone odczytem na 69004: manifest,
  rewizja źródła i komórki mają ten sam czas). Rewizja źródła uznana za
  utworzoną przez korektę, gdy jej `created_at = T` (bez manifestu:
  `manual_v1` i autor korekty); rewizja zdeduplikowana (wcześniejsza) →
  `SHARED_SOURCE_REVISION`.
- B: `CELLS_CHANGED` = komórka z `created_at`/`updated_at > T` albo zdarzenie
  komórki po `T`; `SEQUENCE_OWNERSHIP` = zdarzenie `superseded` innej pozycji z
  `ownerReviewItemId` = cofana pozycja, komórka sprzed `T` albo zdarzenie
  `board_synchronized`; `RESOLVED` = pozycja nie `pending` albo dowolne jej
  zdarzenie rozstrzygnięcia; `SHARED_SOURCE_REVISION` obejmuje też brak
  poprzedniej żywej rewizji, sąsiada nieprzepinalnego (warunki lustrzane do
  `_REPOINT_PLAN_SQL`, w tym `rejected`) i każde inne odwołanie do rewizji
  (rewizje innych plansz, manifesty, komórki, kohorty).
- `IMAGE_ADMITTED`: lista i podgląd przewidują status (otwarty slot =
  `incomplete_missing`, wyjątek operatora zostaje), cofnięcie liczy go
  naprawdę i wycofuje transakcję przy zmianie dopuszczonego statusu.
- Fakty przypadku A (RESOLVED/REOPENED/PINNED) są wstępne; finalizuje je
  TASK-0946. Wpis A na liście dostaje pierwszy niespełniony warunek, a przy
  braku innych `GEOMETRY_REVERT_NOT_SUPPORTED`.
- Nieprzywracane: `source_images.processed_at` (brak wartości sprzed korekty),
  leniwie utworzony przez zapis wiersz `image_symbol_review_states`
  (`rebuilding`, pusty) oraz liczniki monotoniczne (`queue_version`,
  `catalog_revision`, `count_projection_revision`, wersja wejścia supergry).

### Verification results

Z katalogu worktree, `PYTHONPATH` = `services/api/src;services/worker/src;services/test_support`
worktree, Python `..\..\.venv\Scripts\python.exe`:

- `pytest services/api/tests/test_geometry_correction_reverts.py` — 22 passed.
- `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 pytest services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py`
  — 6 passed: pełne porównanie stanu gry przed zapisem i po cofnięciu (D-488
  symbole, przepięty sąsiad), podgląd bez zapisu, STALE, powtórzenie klucza,
  drugie cofnięcie → NOT_LATEST, retry starego zapisu →
  `GEOMETRY_CORRECTION_REVERTED`, ponowny zapis → nowa rewizja 2, worker
  wybiera żywą rewizję (test sprawdzony: bez filtra w `pipeline_store` failuje),
  kolejka `correction` i raport kompletności na rewizji 0, SOURCE_ADVANCED z
  łańcuchem cofnięć, CELLS_CHANGED, SHARED_SOURCE_REVISION, IMAGE_ADMITTED —
  każdy bez zapisu; slot bez komórek i sąsiadów; downgrade 0153 odmawia przy
  historii i round-trip v7 → v6 → v7.
- PG `test_virtual_deferred_resolution_postgres.py`,
  `test_image_geometry_completeness_gate.py`,
  `test_image_geometry_completeness_repository.py` — 42 passed, bez zmian asercji.
- PG `test_postgres_baseline.py::test_upgrade_downgrade_upgrade_cycle_on_postgres`
  i `test_super_game_series_postgres.py::test_migration_downgrade_refuses_decisions_and_round_trips`
  — passed (29 passed w jednym przebiegu z dwoma plikami TASK-0945).
- PG `test_application_role_isolation_postgres.py`,
  `test_board_render_manifests_postgres.py`,
  `test_game_partition_lifecycle_postgres.py`,
  `test_game_storage_routing_postgres.py`, `test_grid_shadow_rls_postgres.py`,
  `test_per_game_isolation_new_game.py`,
  `test_reviewer_operational_geometry_postgres.py`,
  `test_superseded_import_image_removal.py` — 68 passed, 4 skipped, 1 error w
  teardownie `test_v2_parents_have_scope_default_rls_and_runtime_triggers`
  (otwarte połączenie przy `DROP DATABASE` pod obciążeniem równoległych
  przebiegów); ten test uruchomiony osobno: 1 passed.
- Testy jednostkowe API (`services/api/tests` bez `integration`, 4 porcje):
  2571 passed, 6 skipped, 1 error
  (`test_operational_image_reviews.py::test_asset_resolution_logs_missing_file_with_asset_kind_and_relative_path`
  potrzebuje `caplog`, a przebieg miał `-p no:logging`; bez tej flagi: 1 passed).
- Testy workera (`services/worker/tests`, 4 porcje): 2820 passed, 43 skipped.
- `python -m ruff check services/api services/worker services/test_support scripts`
  — All checks passed; `ruff format --check` zmienionych plików — czyste.
- `python -m mypy services/api/src services/worker/src scripts` — Success
  (862 pliki).
- `python scripts/generate_code_map.py`, potem `--check` — up to date.
- Pełne `npm run db:baseline:verify` (cały katalog integracyjny) nie było
  uruchomione w całości; uruchomiono test cyklu migracji i zestawy powyżej.

### Not completed

- Przypadek A (TASK-0946), HTTP (TASK-0947), UI (TASK-0948), logika
  odrzucenia slotu (TASK-0949), wpisy D-538/D-539 (TASK-0951).
- `GEOMETRY_REVERT_REOPENED_RESOLUTION` nie ma testu PG (wyłącznie test
  funkcji domenowej) — patrz „Runda poprawek audytu”, P1-1.
- Commit i `CURRENT_STATE.md` — lead.

### Documentation updates

- `ai_docs/architecture/DATA_MODEL.md` — podsekcja „Cofnięcie korekty cięcia
  siatki (TASK-0945, migracja `0153`)”.
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md` — sekcja „Manifest v7”.
- `ai_docs/architecture/CODE_MAP.md`, `CODE_MAP_SYMBOLS.md` — zregenerowane.

### Recommended next task

TASK-0946 (cofnięcie korekty istniejącej planszy) na bazie
`SqlAlchemyGeometryCorrectionRevertRepository._evaluate` i
`previous_assignment_source`; równolegle możliwy TASK-0947 (HTTP) nad gotowym
serwisem.

### Decyzja leada (audyt rundy 1)

Manifest v7 i zmiana czterech asercji wersji manifestu/heada
(`test_game_data_v2_schema.py`, `test_catalog_api.py`,
`test_schema_readiness.py`, `integration/test_super_game_series_postgres.py`)
zaakceptowane przez leada jako świadoma zmiana kontraktu według precedensu
migracji `0152`.

### Runda poprawek audytu

Audyt Codex (`gpt-6-astra`, `high`) runda 1: `REVISE`, raport zachowany bez
zmian w `ai_docs/quality/TASK-0945_AUDIT_gpt-6-astra_round1.md`.

- **P0-1 (historyczna korekta `legacy_file` przerywała listę).**
  `_Correction.source_geometry_revision_id` jest nullable; `list_recent`
  zwraca taką korektę jako `board_revision` z blokadą
  `GEOMETRY_REVERT_NOT_SUPPORTED`, pozostałe wpisy bez zmian; podgląd i
  cofnięcie odmawiają tym samym kodem (dawna gałąź `pragma: no cover` jest
  teraz testowana). Test PG
  `test_a_historical_legacy_correction_is_listed_as_not_revertable` (korekta
  historyczna i bieżąca korekta slotu w jednym imporcie; odmowa bez zapisu,
  potem udane cofnięcie slotu).
- **P0-2 (luka idempotencji przy równoległym zatwierdzeniu).** `revert` bierze
  na początku transakcji `pg_advisory_xact_lock` z klucza
  `sha256("geometry-correction-revert:{game_id}:{idempotency_key}")`, przed
  pierwszym odczytem audytu i korekty; powtórzenie czeka na zatwierdzenie
  pierwszego żądania i zwraca zapisany wynik. Kontrola po blokadach
  sekwencji pozostaje. Test PG dwóch połączeń
  `test_a_retry_racing_the_first_commit_returns_the_stored_result`: pierwsze
  cofnięcie bez commita, drugie żądanie czeka dokładnie na tę blokadę
  (sprawdzane w `pg_locks`), po commicie zwraca `created=False` i ten sam
  `revertId`; jeden wiersz audytu.
- **P0-3 (`AssertionError` przy cofnięciu między odczytami listy).** Wpis,
  którego korekta zniknęła po zapytaniu o identyfikatory, jest pomijany.
  Test PG `test_listing_skips_a_correction_reverted_between_its_reads`
  (cofnięcie zatwierdzane w osobnym połączeniu po zapytaniu o identyfikatory;
  lista zwraca pozostałą, teraz cofalną korektę).
- **P1-1 (brak testów PG części blokad).** Nowy plik
  `services/api/tests/integration/test_geometry_correction_revert_refusals_postgres.py`;
  każdy test porównuje pełną migawkę stanu gry przed odmową i po niej:
  `RESOLVED` (pozycja odrzucona endpointem rozstrzygnięcia),
  `SEQUENCE_OWNERSHIP` dla zastąpionej pozycji starszego importu oraz osobno
  dla 15 komórek przejętych od poprzedniego właściciela (po usunięciu w teście
  zdarzenia `superseded`, żeby wyizolować sygnał komórek), `PINNED` (rewizja
  predykcji planszy), kontrakt przypadku A (`geometry-revisions` na planszy
  slotu → wpis `board_revision` niecofalny, cofnięcie →
  `GEOMETRY_REVERT_NOT_SUPPORTED`, wcześniejszy wpis slotu →
  `GEOMETRY_REVERT_NOT_LATEST`). `REOPENED_RESOLUTION` nie jest testowane na
  PG: warunek dotyczy wyłącznie przypadku A, a bez logiki TASK-0946 jest
  nieosiągalny jako pierwszy kod — plansza z importu ma rewizję predykcji
  (`PINNED` wcześniej w kolejności), a plansza slotu po ponownym otwarciu
  zaakceptowanej pozycji wymaga zaakceptowania jej 15 komórkami, po czym
  `synchronize_board_from_cells` ją domyka (`RESOLVED` wcześniej). Kod ma test
  funkcji domenowej; test PG należy do TASK-0946.

Weryfikacja po poprawkach (z katalogu worktree, `PYTHONPATH` worktree,
`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`):

- `pytest services/api/tests/test_geometry_correction_reverts.py services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py services/api/tests/integration/test_geometry_correction_revert_refusals_postgres.py services/api/tests/test_super_game_input_version.py services/api/tests/test_game_data_v2_schema.py -q`
  — 55 passed (w tym 8 nowych testów PG rundy poprawek).
- `python -m ruff check services/api services/worker services/test_support scripts`
  — All checks passed; `ruff format --check` zmienionych plików — czyste.
- `python -m mypy services/api/src services/worker/src scripts` — Success
  (862 pliki).
- `python scripts/generate_code_map.py` + `--check` — up to date.
- Poprawki dotyczą wyłącznie `geometry_correction_revert_repository.py` i
  nowych testów; wcześniejsze przebiegi zestawów kompletności, korekty slotu,
  migracji, testów jednostkowych API i workera nie były powtarzane.

### Druga runda poprawek (decyzja leada; operator polecił samodzielne rozwiązywanie problemów)

Audyt rundy 2: brak P0, otwarte P1-1 (brak testu z rzeczywistym powiązaniem
kohorty treningowej).

- Dodano testy PG w `test_geometry_correction_revert_refusals_postgres.py`
  z kohortą zasianą surowym SQL jak w istniejących testach kohort
  (`verified_training_cohorts`, `verified_training_cohort_items`,
  `verified_training_cohort_cells`):
  `test_a_corrected_board_in_a_training_cohort_refuses_the_revert`
  (plansza korekty w kohorcie → `GEOMETRY_REVERT_PINNED`) i
  `test_a_repointed_neighbour_in_a_training_cohort_refuses_the_revert`
  (przepinany sąsiad w kohorcie → `GEOMETRY_REVERT_SHARED_SOURCE_REVISION`,
  bo nie może wrócić na poprzednią rewizję źródła). Oba porównują pełną
  migawkę stanu gry oraz wiersze kohorty przed odmową i po niej.
- Test ujawnił błąd kolejności: komórka kohorty cofanej planszy wskazuje
  rewizję źródła korekty, więc `_OTHER_REFERENCES_SQL` zgłaszał
  `SHARED_SOURCE_REVISION` zamiast `PINNED`. Poprawka minimalna: odwołania
  kohorty z samej cofanej planszy są wyłączone z warunku „inne odwołania”
  (`vc.recognized_board_id <> :board_id`); obsługuje je `_PINNED_SQL`.
- Weryfikacja: `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 pytest services/api/tests/integration/test_geometry_correction_revert_refusals_postgres.py -q`
  — 10 passed; `ruff check` i `ruff format --check` zmienionych plików —
  czyste; `mypy storage/geometry_correction_revert_repository.py` — Success.

### Zamknięcie (lead)

- Audyt Codex `gpt-6-astra`/`high`: runda 1 REVISE → poprawki; runda 2 REVISE (P1 kohorta) → druga runda poprawek (decyzja leada; operator polecił samodzielne rozwiązywanie problemów). Trzeci audyt pominięty: poprawka dotyczyła testu i jednej linii `_OTHER_REFERENCES_SQL`; do ponownego audytu Codex na końcu planu.
- Weryfikacja leada: `test_geometry_correction_reverts.py` + oba pliki PG cofania — 36 passed (przed testem kohorty); regresja `test_virtual_deferred_resolution_postgres.py`, `test_image_geometry_completeness_gate.py`, `test_image_geometry_completeness_repository.py`, `test_grid_correction_cell_symbols_postgres.py` — 43 passed.
- Commit: v1.7.291 / 25a7c099c10a11da7dec6be86aa56c2505e8d362.
