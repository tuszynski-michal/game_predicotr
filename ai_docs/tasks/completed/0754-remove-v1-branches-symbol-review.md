---
title: TASK-0754 — S2 — usunięcie martwych gałęzi V1 z weryfikacji symboli
status: done
last_updated: 2026-09-30
---

# TASK-0754 — S2 — usunięcie martwych gałęzi V1 z weryfikacji symboli

## Status

`done`

## Goal

Ścieżka V2 jest jedyną ścieżką odczytu i zapisu komórek weryfikacji
symboli: znika `_uses_logical_current_cell_identity`, pole
`uses_current_projection` i gałęzie `False`, a skompilowany SQL ścieżki V2
pozostaje bajt w bajt taki sam.

## Context

D-467, S2. Magazyn jest V2-only (`GameStorageSchema` ma tylko `V2`), więc
`_uses_logical_current_cell_identity()` zawsze zwracało `True`, a
`SymbolCellReviewListFilter.uses_current_projection` w runtime zawsze było
`True`. Gałęzie legacy (join `image_board_search_fast_documents`, pewność z
`cell_observations`/`image_symbol_prediction_revisions` przez `coalesce`,
klucz konfliktu `review_item_id + cell_index`) były martwym kodem.

## Dependencies / entry conditions

- Fakt: `GameStorageSchema` = `{V2}`; `GameStorageRouter._in_memory_v2` i
  `_unavailable` też zwracają `V2`.
- Fakt: `GameStorageRouter.bind` ma efekt uboczny (ustawia `search_path`,
  `game_predictor.game_id`, `game_predictor.storage_generation` dla
  transakcji i sprawdza zgodność wiązania). Usunięta funkcja wykonywała go
  przy każdym wywołaniu — zachowanie trzeba utrzymać.
- Brak zmian w bazie; w tle działa zapis biblioteki wzorców.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo). Audyt: `claude-opus-5-5`,
`high`, osobny agent. Eskalacja: dowolna różnica w skompilowanym SQL V2.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md` (S2)
- `ai_docs/process/DECISION_LOG.md` (D-467)

## Scope

- `domain/image_symbol_reviews.py`: pole `uses_current_projection` z
  `SymbolCellReviewListFilter` (kursor go nie zawierał — bajty kursora bez
  zmian).
- `application/image_symbol_reviews.py`: pole z
  `SymbolCellReviewCatalogState` i trzech konstrukcji filtra.
- `storage/image_symbol_review_repository.py`,
  `storage/image_symbol_review_bulk_operation_repository.py`,
  `storage/board_cell_geometry_pending_repository.py`: tylko gałąź V2,
  usunięte oba `_prediction_confidence_expression`.
- Testy parametryzowane/monkeypatchowane gałęzią legacy.

## Out of scope

- `symbol_usage_summary` (TASK-0755), czytelnicy `cell_observations` poza
  gałęziami `uses_current_projection` (S4).
- Nazwy `logical_cell_key`/`legacy_file` i inne ślady V1 poza tym zakresem.

## Acceptance criteria

- [x] `git grep "uses_current_projection\|_uses_logical_current_cell_identity\|_prediction_confidence_expression" -- services scripts` → 0 wystąpień.
- [x] Skompilowany SQL V2 (37 sekcji) identyczny przed i po zmianie.
- [x] Sekwencja wywołań `GameStorageRouter.bind` identyczna przed i po.
- [x] Test regresyjny: zapytania V2 bez `cell_observations`,
  `image_board_search_fast_documents` i `coalesce`.
- [x] Audyt bez P0–P2.

## Technical notes

- Każde miejsce, które wołało `_uses_logical_current_cell_identity(session,
  game_id)`, woła teraz `_bind_game_store(session, game_id)` w tej samej
  kolejności względem `execute`, więc wiązanie transakcji z magazynem gry
  (search_path/RLS) nie zależy od otaczającego `game_storage_scope`.
- `_visible_statement` i `_candidate_seek_statement` dzielą
  `_visible_cell_scope` (te same klauzule `WHERE` w tej samej kolejności);
  `_base_visible_statement` i parametr `require_current_geometry` (używany
  tylko przez gałąź legacy) usunięte.
- `_seek_visible_keys`: w V2 zbiór widocznych id był równy zbiorowi
  kandydatów, więc filtr członkostwa i drugie zapytanie zniknęły.
- `_list_statement`: `board_status` z `image_review_items.status`, pewność z
  `image_symbol_review_cells.prediction_confidence`.
- Bulk `_visible_cells_statement`: bez parametru; pewność z
  `cell.prediction_confidence`; join `recognized_boards` + strażnik
  `geometry_revision` zostają (były w V2).

## Expected files

- Istniejące: pliki z sekcji Scope; testy
  `test_symbol_review_extended_filters.py`,
  `test_image_symbol_review_query_storage.py`,
  `test_image_symbol_reviews_api.py`,
  `test_image_symbol_review_projection_availability.py`,
  `test_board_cell_geometry_pending.py`,
  `test_image_symbol_review_backfill_storage.py`,
  `test_qualified_cell_reconciliation.py`,
  `test_symbol_cell_source_visibility.py`,
  `integration/test_outside_current_owner_postgres.py`,
  `integration/test_symbol_visibility_groups_postgres.py`.

## Test cases

- Filtr z min/max pewności, `prediction_source`, zakresem zmian →
  `_visible_statement`, `_count_statement`, `_candidate_seek_statement`,
  bulk `_visible_cells_statement` bez legacy źródeł; FROM zapytań listy to
  sama tabela komórek, bulk ma tylko join `recognized_boards`.
- Źródło predykcji (obie wartości) kompiluje się we wszystkich czterech.

## Verification

```powershell
# dump SQL przed (kopia HEAD) i po, PYTHONHASHSEED=0, porównanie cmp
$env:PYTHONPATH = "services/worker/src;services/api/src"
.\.venv\Scripts\python.exe -m pytest -q services/api/tests --ignore=services/api/tests/integration --basetemp C:\Users\tuszy\AppData\Local\Temp\t0754 -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check <pliki>; .\.venv\Scripts\python.exe -m ruff format --check <pliki>
$env:MYPYPATH = "services/api/src;services/worker/src"; .\.venv\Scripts\python.exe -m mypy --strict --follow-imports=silent <pliki src>
```

## Risks / open questions

- Testy jednostkowe z fałszywą sesją (`Mock`, `MagicMock`, własne atrapy)
  nie modelują rutingu magazynu; zamiast łatki `_uses_logical_current_cell_identity`
  łatają teraz `_bind_game_store` na no-op.

## Outcome

### Changed

- Usunięte `_uses_logical_current_cell_identity`, pole
  `uses_current_projection` (filtr i `SymbolCellReviewCatalogState`), oba
  `_prediction_confidence_expression`, `_base_visible_statement`, gałęzie
  legacy w `get_assets`, `_locked_current_rows`, `_current_review_documents`,
  `resolve_cell`, koordynatorze zapisu (dwa miejsca), `_backfill_cell_conflict_columns`,
  repozytorium bulk (3 wywołania + `_visible_cells_statement`) i
  `_next_manual_geometry_revision`.
- Nowy `_bind_game_store` (zachowuje efekt uboczny wiązania) i
  `_visible_cell_scope` (wspólne klauzule listy/seeka).
- Zbędne importy usunięte (`Float`, `sql_cast`, `GameStorageSchema`; w bulk
  także `CellObservationModel`, `ImageBoardSearchFastDocumentModel`,
  `ImageSymbolPredictionRevisionModel`, `and_`, `cast`, `ColumnElement`).
  `CellObservationModel` i `ImageBoardSearchFastDocumentModel` zostają w
  `image_symbol_review_repository.py` (używane przez backfill/rekoncyliację).
- Testy: parametr `uses_current_projection` usunięty; usunięte testy tylko
  dla legacy: `test_backfill_conflict_target_keeps_the_legacy_unique_key`,
  `test_list_keeps_the_current_geometry_guard`; trzy testy SQL liczników
  przepisane na asercje V2; nowy
  `test_v2_scope_statements_read_only_the_current_cell_projection`.

### Verification results

- SQL przed/po (implementer): 37 sekcji, z czego 34 to SQL (6 filtrów × 4
  instrukcje, 4 warianty bulk, `get_assets`, `list_boards`/`get_board`,
  `_locked_current_rows`), pozostałe 3 to wyniki wywołań — identyczne,
  SHA-256 `cdd005e6…48f3` (`PYTHONHASHSEED=0`; skrypt zrzutu nie jest
  zachowany). Niezależne porównanie audytora (`git archive` HEAD, 102
  sekcje: 12 filtrów × 5 instrukcji, bulk z wykluczeniami / kolumnami /
  jawnymi celami, `_backfill_cell_conflict_columns`) — identyczne.
- Ślad `GameStorageRouter.bind`: 6 z 11 miejsc śladem, pozostałe (3 bulk,
  2 koordynator, backfill) przeglądem audytora; wszędzie `intent=READ`
  przed pierwszą instrukcją, jak przed zmianą. Test
  `test_cell_paths_bind_the_game_store` pilnuje liczby wywołań (7/3/1).
- ruff check/format: czysto; mypy --strict na 5 plikach src: czysto.
- pytest `services/api/tests` bez integracji (uruchomione porcjami ≤120 s):
  1542 passed, 3 skipped, 19 failed. Wszystkie 19 porażek występuje
  identycznie na czystej kopii HEAD (bez tej zmiany):
  `test_image_import_geometry_guard_api.py` (7, w tym znany
  `test_board_exception_queue_is_exposed_by_the_http_contract`),
  `test_reviews.py` (6), `test_virtual_grid_geometry.py` (2),
  `test_openapi_contract.py` (2), `test_lateral_managed_reprocess.py` (1),
  znany `test_list_endpoint_uses_keyset_cursors_without_duplicates` (1).
- Integracja PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`, własne bazy
  `*_test`): `test_outside_current_owner_postgres.py`,
  `test_symbol_visibility_groups_postgres.py` — 3 passed.

### Not completed

- Brak; audyt `claude-opus-5-5` PASS (P3 wdrożone: docstringi
  `_bind_game_store` i `_visible_cell_scope`, test liczby wiązań, korekta
  tego Outcome). Otwarte P3 na osobne zadanie: czy lista/liczniki powinny
  mieć strażnik `geometry_revision` jak bulk i `_locked_current_rows`.

### Documentation updates

- Brak (D-467 obejmuje decyzję).

### Recommended next task

- TASK-0755.
