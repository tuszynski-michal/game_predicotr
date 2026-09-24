---
title: TASK-0637 — bindowanie magazynu gry na trasach /image-reviews/{id}/…
status: done
last_updated: 2026-09-24
---

# TASK-0637 — bindowanie magazynu gry na trasach `/image-reviews/{review_item_id}/…`

## Status

`done`

## Goal

`source-asset`, `geometry-preview`, `geometry-approval` i `geometry-revisions`
czytają i zapisują w magazynie gry wskazanej przez `gameId` (query), także dla
gier na `game_data_v2`, tak że podgląd oryginału i cropów w Reviewerze
(„Zatwierdzanie cięcia siatki”) działa dla gry 777.

## Context

Reviewer nie ładuje oryginału ani cropów na ekranie „Zatwierdzanie cięcia
siatki” dla żadnej zakładki. Diagnoza (analiza 2026-09-24, dowody F1–F7 w
przekazanym planie) ustaliła przyczynę: middleware `bind_game_storage_request`
binduje `game_storage_scope` tylko dla tras, których **ścieżka** zawiera
`games/<uuid>/`. Cztery trasy pod `/admin/image-reviews/{review_item_id}/…`
przenoszą `gameId` wyłącznie w query, więc scope nigdy nie jest ustawiony;
`ImageGridReviewRepository.require_game` czyta wtedy pustą tabelę
`public.image_symbol_review_states` (gra 777 ma dane w `game_data_v2`) i
zwraca `IMAGE_GRID_REVIEW_PROJECTION_INCOMPLETE` (409), zanim handler dotknie
pliku obrazu. Oryginały i geometria są kompletne (potwierdzone read-only) —
to wyłącznie błąd routingu, nie utrata danych. Ten sam mechanizm i to samo
obejście (`with game_storage_scope(game_id): ...`) już istnieje dla
operacyjnych endpointów Reviewera (`OperationalImageReviewService.get_item`,
`application/image_reviews.py:437`).

## Dependencies / entry conditions

- Brak zależności od innych tasków.
- Fakt: `services/api/src/game_predictor_api/api/image_grid_reviews.py` ma 4
  handlery bez `game_storage_scope`: `get_image_grid_review_source_asset`,
  `approve_image_grid_review_geometry`, `preview_image_grid_review_geometry`,
  `create_image_grid_review_geometry_revision` (sprawdzone w kodzie
  2026-09-24).
- Fakt: wzorzec bindowania (`game_storage_scope` z
  `game_predictor_api.storage.game_storage_routing`) jest już użyty w
  `application/image_reviews.py:415-438` i ma test
  `test_operational_review_item_reads_v2_in_a_new_unscoped_session`
  (`services/api/tests/integration/test_game_storage_routing_postgres.py:576`).

## Recommended execution

claude-sonnet-5, reasoning: high. Mała zmiana w jednym routerze, ale dotyka
routingu magazynu gry i zapisów geometrii; test integracyjny Postgres wymaga
ostrożnego przygotowania partycji `game_data_v2`. Dodatkowy review:
claude-opus-5-5, reasoning: medium — przegląd diffu pod kątem kompletności 4
tras i braku zmian kontraktu API/OpenAPI.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- W `services/api/src/game_predictor_api/api/image_grid_reviews.py` owinąć
  całe ciało (łącznie z wywołaniami serwisów i `resolve_grid_review_source_asset`)
  każdego z 4 handlerów w `with game_storage_scope(game_id):`, reużywając
  istniejący `game_storage_scope` z `game_predictor_api.storage.game_storage_routing`.
- Dodać test jednostkowy (fałszywe repozytorium) potwierdzający, że wszystkie
  4 trasy widzą poprawny `game_storage_scope` podczas wywołania repozytorium.
- Dodać test integracyjny Postgres potwierdzający, że `source_asset` czyta
  grę na `game_data_v2` w nowej, niezbindowanej sesji.

## Out of scope

- Middleware `bind_game_storage_request`, `game_id_from_path`,
  `_route_orm_statement`, resolver `resolve_grid_review_source_asset`/`_resolve`.
- Trasy `/games/{game_id}/…` (już działają).
- Endpointy `image-review-items` z D-440 (osobny, odłożony zakres).
- Frontend Reviewera (TASK-0638).
- Dane, reimport, regeneracja cropów, zmiany geometrii/zatwierdzeń na
  żywych danych.
- Storage GC i skrypt legacy GC (TASK-0640, wymaga osobnej zgody).

## Acceptance criteria

- [ ] 4 handlery w `image_grid_reviews.py` wykonują całe ciało w
      `game_storage_scope(game_id)`.
- [ ] Nowy test jednostkowy w `test_image_grid_review_api.py` czerwony przed
      zmianą, zielony po zmianie (mutation check).
- [ ] Nowy test integracyjny w `test_game_storage_routing_postgres.py`
      potwierdza odczyt V2 w nowej sesji.
- [ ] `openapi:check` bez różnic (kontrakt HTTP niezmieniony).
- [ ] Na żywym API (jeśli dostępne w tej sesji) `GET
      /api/v1/admin/image-reviews/0b9166a1-b860-4859-b28f-eacee097ef2c/source-asset?gameId=bfc4f949-5c14-4850-b02a-db99610bcfa5&expectedSourceChecksumSha256=befcf58db7dc0a3a4c1e527d3250a7a6891bea9618797eda13b23b29f47b32f4`
      → 200 `image/jpeg`.

## Technical notes

Aktualne zachowanie: handler woła `service.source_asset(...)` /
`service.approve(...)` / `_require_expected_source(...)` bez otwartego scope
→ `require_game` czyta `public` → 409. Wymagane zachowanie: całe ciało
handlera (w tym zagnieżdżone wywołania `virtual_service`/`operational_service`
w `preview`/`create_revision`) w jednym `with game_storage_scope(game_id):`.
`game_storage_scope` jest reentrantny (ContextVar) — zagnieżdżone wywołania z
tym samym `game_id` są bezpieczne (`GameStorageRouter._require_same_binding`).
`FileResponse` można skonstruować wewnątrz bloku; strumieniowanie odpowiedzi
nie dotyka bazy, więc wyjście z bloku po `return` jest bezpieczne.

Błędy po zmianie (bez zmiany kodów/statusów): nieistniejąca gra → 404
`GAME_NOT_FOUND`; item z innej gry → 404 `IMAGE_GRID_REVIEW_ITEM_NOT_FOUND`;
zła checksuma → 409 `IMAGE_GRID_REVIEW_SOURCE_DRIFT`; brak pliku na dysku →
`IMAGE_REVIEW_ASSET_NOT_FOUND`; projekcja naprawdę niegotowa (V2 bez `ready`)
→ nadal 409 `IMAGE_GRID_REVIEW_PROJECTION_INCOMPLETE` (to nie jest błąd do
ukrycia).

## Expected files

- Istniejące: `services/api/src/game_predictor_api/api/image_grid_reviews.py`
  — 4 handlery.
- Istniejące: `services/api/tests/test_image_grid_review_api.py` — nowy test.
- Istniejące: `services/api/tests/integration/test_game_storage_routing_postgres.py`
  — nowy test.
- Istniejące: `ai_docs/process/DECISION_LOG.md` — nowy wpis D-442.

## Test cases

- Fałszywe repozytorium zapisuje `current_game_storage_scope()` przy
  `require_game`/`get_grid_review_source_asset`; wywołanie 4 tras z `gameId`
  → asercja, że repozytorium widziało scope z tym `game_id`.
- Postgres: gra V2 z partycjami (`image_symbol_review_states` w stanie
  `ready` tylko w `game_data_v2`, `public.image_review_items` = 0), 1 source +
  board + review item; w nowej sesji bez scope → `PROJECTION_INCOMPLETE`; w
  `game_storage_scope(game_id)` → poprawny `ImageGridReviewSourceAsset`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_grid_review_api.py -q
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_game_storage_routing_postgres.py -q
npm run python:lint
npm run python:typecheck
npm run openapi:check
```

Kryterium zakończenia: testy zielone; `openapi:check` bez różnic.

## Risks / open questions

- Jeżeli po zmianie któraś zakładka nadal zwróci 409
  `PROJECTION_INCOMPLETE` — to realny stan projekcji, nie routing; zatrzymać
  się i zgłosić, nie obchodzić warunku.
- D-440 (`image-review-items`, `board-import-coverage`) pozostaje osobnym,
  otwartym zakresem.

## Outcome

### Changed

- [services/api/src/game_predictor_api/api/image_grid_reviews.py](../../services/api/src/game_predictor_api/api/image_grid_reviews.py):
  `get_image_grid_review_source_asset`, `approve_image_grid_review_geometry`,
  `preview_image_grid_review_geometry`, `create_image_grid_review_geometry_revision`
  now run their whole body inside `with game_storage_scope(game_id):`.
- [services/api/tests/test_image_grid_review_api.py](../../services/api/tests/test_image_grid_review_api.py):
  new `test_item_scoped_grid_review_routes_bind_the_query_game_storage`
  (mutation-checked: red before the fix, green after).
- [services/api/tests/integration/test_game_storage_routing_postgres.py](../../services/api/tests/integration/test_game_storage_routing_postgres.py):
  new `test_grid_review_source_asset_reads_v2_in_a_new_unscoped_session`
  (real PostgreSQL, `game_data_v2`, mirrors
  `test_operational_review_item_reads_v2_in_a_new_unscoped_session`).
- `ai_docs/process/DECISION_LOG.md`: new D-442 entry.
- `ai_docs/process/CURRENT_STATE.md`: new TASK-0637 entry.

### Verification results

- `pytest services/api/tests/test_image_grid_review_api.py`: 17/18 green.
  The 1 failure (`test_image_import_engine_policy_requires_preview_and_is_per_game`)
  is pre-existing and unrelated (confirmed red on a clean checkout before
  this task's changes — a `geometryEngineVariants` content mismatch, not
  touched by this diff).
- `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 pytest services/api/tests/integration/test_game_storage_routing_postgres.py`:
  10/11 green. The 1 failure
  (`test_page_geometry_snapshot_reads_v2_in_a_new_unscoped_session`) is
  pre-existing and unrelated (confirmed red on a clean checkout — the
  shared `database` fixture is pinned to migration
  `0106_game_storage_routing_fence`, older than a column
  (`games.board_frame_quads`) the current `GameModel` mapping expects;
  same class of drift, different table, not touched by this diff).
- `npm run python:lint`: clean for the 3 changed files.
- `npm run python:typecheck`: clean for the 3 changed files (69 pre-existing
  errors elsewhere in the repo, none in touched files).
- `npm run openapi:check`: no diff — HTTP/OpenAPI contract unchanged, as
  required.
- Live-API curl verification from the acceptance criteria was **not**
  performed in this session (no running `game_predictor_api --reload`
  process was started/found in this session's environment); covered
  instead by the Postgres integration test, which exercises the same
  `ImageGridReviewService.source_asset` path against a real V2-partitioned
  database.

### Not completed

- Live curl check against `127.0.0.1:8000` (see above) — not run, no local
  API server was up in this session.
- Two pre-existing, unrelated test failures found during full-file runs
  (see Verification results) were left untouched, per AGENTS.md ("nie
  rozszerzaj automatycznie zakresu"). Both reproduce on a clean checkout,
  independent of this diff.

### Documentation updates

- `ai_docs/process/DECISION_LOG.md` — D-442.
- `ai_docs/process/CURRENT_STATE.md` — new entry, prepended.
- This task file moved to `ai_docs/tasks/completed/`.

### Recommended next task

- T2 / TASK-0638: distinguishable grid-review preview error in Reviewer +
  API log (frontend `grid-review-editor.tsx` error mapping, backend
  `image_review_assets.py` logging), per the plan's T2 section.
