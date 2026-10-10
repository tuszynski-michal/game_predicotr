# TASK-0725 — Jedna kolejka ręcznej korekty (backend)

## Status

done

## Goal

API kolejki siatek udostępnia widok `correction` z jedną pozycją na slot
planszy: każdą odroczoną geometrię `pending` i każdą bieżącą planszę ze
zgłoszeniem `Zła siatka`, wraz z indeksami zgłoszonych komórek.

## Context

D-462 R4. Dziś zgłoszenia `Zła siatka` trafiają do `needs_correction`, a
odroczone sloty są rozdzielone między `needs_validation` (z propozycją
automatu) i `needs_correction`. Ekran 3001 (TASK-0726) potrzebuje jednej
kolejki.

## Dependencies / entry conditions

Etap A ukończony (`v1.7.53`).

## Recommended execution

claude-opus-5-5, high — kontrakt API, deduplikacja slotu. Audyt:
claude-opus-5-5, high (subagent, poziom warunkowy).

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` D-462
- `ai_docs/architecture/API_CONTRACT.md` (grid reviews)
- `ai_docs/delivery/CELL_LEVEL_VERIFICATION_EXECUTION_PLAN.md`

## Scope

- Widok `ImageGridReviewView.CORRECTION`: bieżące plansze z `grid_issue` ∪
  odroczone sloty `pending` bez żywej planszy w tym samym `(source_image_id,
  position_index)` (z propozycją automatu albo bez).
- `counts.correction` i `reportedCellIndices` (bieżące komórki z
  `grid_issue` i pełnym źródłem).
- OpenAPI, wygenerowany klient, test żądania klienta, testy API i PostgreSQL.
- Decyzja: zapis korekty używa istniejących ścieżek jednej planszy
  (`image-reviews/{id}/geometry-*` i `board-cell-geometry-pending/{id}/manual-resolution`);
  nowy endpoint zapisu slotu nie jest potrzebny — żadna z tych ścieżek nie
  zmienia innych plansz zdjęcia.

## Out of scope

- UI (TASK-0726), usunięcie widoków i endpointów szybkiej akceptacji
  (TASK-0727), zapis całego źródła.

## Acceptance criteria

- [x] Kilka zgłoszeń jednej planszy daje jedną pozycję z listą komórek
      (scenariusz 5).
- [x] Zgłoszenie z weryfikacji symboli kieruje planszę do kolejki
      (scenariusz 4).
- [x] Slot odroczony pojawia się w kolejce niezależnie od propozycji
      automatu; odroczenie slotu z żywą planszą nie tworzy drugiej pozycji, a
      niezgłoszone rodzeństwo zdjęcia nie trafia do kolejki (scenariusz 3).
- [x] Kontrakt: backend, OpenAPI, klient, test żądania; istniejące widoki bez
      zmian.

## Expected files

- `services/api/src/game_predictor_api/domain/image_grid_reviews.py`
- `services/api/src/game_predictor_api/storage/image_grid_review_repository.py`
- `services/api/src/game_predictor_api/schemas/image_grid_reviews.py`
- `packages/admin-api-client/openapi/openapi.json`,
  `packages/admin-api-client/src/generated/types.gen.ts`,
  `packages/admin-api-client/test/client.test.mjs`
- Testy: `services/api/tests/test_image_grid_review_api.py`,
  `services/api/tests/integration/test_verified_cell_search_projection.py`
- `ai_docs/architecture/API_CONTRACT.md`

## Verification

Katalog: root repozytorium; każdy krok z timeoutem 120 s.

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_grid_review_api.py services/api/tests/test_image_grid_reviews_domain.py -q
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_verified_cell_search_projection.py -q
npm run openapi:check
npm run test --workspace @game-predictor/admin-api-client
```

## Risks / open questions

- Wygenerowany `openapi.json` zawiera też niezacommitowaną zmianę
  użytkownika (limit spinów 100 000); commit zawiera tylko hunki tego taska.

## Outcome

### Changed

- `ImageGridReviewView.CORRECTION`: current boards with a current
  `grid_issue` ∪ pending deferred slots whose source slot has no board
  (`_live_board_in_slot`, mirroring the manual-resolution guard). One entry per
  slot; siblings are never routed.
- `counts.correction` (same filter as the list) and `reportedCellIndices`
  (current revision, own board, available source) in the item response.
- OpenAPI, generated types, client request test; `API_CONTRACT.md`; plan
  (T5 decision and closed risk, R4 wording).
- Decision: no new slot-save endpoint — the 3001 screen saves through the
  existing single-board paths (`image-reviews/{id}/geometry-*`,
  `board-cell-geometry-pending/{id}/manual-resolution`); none touches sibling
  boards. A deferred slot resolved manually becomes a `legacy_file` board, as
  before (461 such resolutions on `virtual_source` photos).

### Verification results

- `test_image_grid_review_api.py`, `test_image_grid_reviews_domain.py`: PASS.
- PostgreSQL `test_correction_queue_lists_one_reported_board_per_slot`
  (photo with slots 0–2, reports on slot 0, sibling slot 1, deferred slot 2,
  stale deferral of slot 0): PASS; whole file 4/4.
- `npm run openapi:check`: PASS; `@game-predictor/admin-api-client`: 66/66.
- Audit claude-opus-5-5 (subagent, reasoning level inherited): cycle 1 —
  1× P1 (dedup could hide a slot entirely, masked by a test without a source
  geometry revision), 3× P2; cycle 2 — „Brak uwag P0–P2”; P3 notes on the live
  board rule, plan R4 and keyset wording applied.
- Read-only EXPLAIN (audit): correction list 9–187 ms, count up to 347 ms on
  game 777 scoped to an import; the screen always passes `importJobId`.

### Not completed

- The in-memory API test repository does not model deferred slots with
  proposals; that case is covered by SQL-text and PostgreSQL tests.
- Two failures in `test_openapi_contract.py` (`cells.minItems`) exist on HEAD
  and are unrelated.

### Documentation updates

- `API_CONTRACT.md`, plan, `CURRENT_STATE.md`.

### Recommended next task

- TASK-0726.
