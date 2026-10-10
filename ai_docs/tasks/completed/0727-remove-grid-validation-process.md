# TASK-0727 — Usunięcie procesu „Walidacja gotowych siatek”

## Status

done

## Goal

Po przejściu Reviewera na jeden ekran korekty (TASK-0726) nie istnieje już
żadna ścieżka zatwierdzania siatki planszy lub zdjęcia: ani UI, ani endpoint,
ani metoda aplikacji, ani wpis allowlisty.

## Context

D-462: zatwierdzenie geometrii nie jest warunkiem niczego (TASK-0723), a
lokalny Reviewer nie korzysta już z modułu `grid-reviews`. Pozostawione
mutacje podtrzymywałyby stary proces.

## Dependencies / entry conditions

TASK-0726 done.

## Recommended execution

claude-opus-5-5, high — usunięcie kodu i endpointów z kontrolą konsumentów.
Audyt: claude-opus-5-5, high (subagent, poziom warunkowy).

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` D-462
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/CELL_LEVEL_VERIFICATION_EXECUTION_PLAN.md`

## Scope

- API: usunięcie `POST /image-reviews/{id}/geometry-approval`,
  `POST /games/{id}/grid-reviews/source-geometry-approval` oraz endpointu HTTP
  `POST /games/{id}/grid-reviews/source-geometry-revisions` (jedynym
  konsumentem był ekran całego zdjęcia).
- Aplikacja, domena i repozytorium: metody i typy szybkiej akceptacji
  (`approve`, `approve_source`, `approve_grid_geometry`,
  `approve_source_grid_geometry`, `approve_current_geometry`,
  `approve_image_grid_review` i typy wyniku/celu akceptacji).
- Allowlista lokalnego originu Reviewera, OpenAPI, klient, wrapper, testy.
- Reviewer: usunięcie `features/grid-reviews/*`, stanu przełącznika trybów
  (`features/access/local-reviewer-workspace-state.ts`, jego test, style
  `.localReviewerMode*` w `reviewer.css`) i ich testów; potrzebne czyste
  funkcje (początkowe narożniki, komenda podglądu/zapisu planszy)
  przeniesione do modułu ekranu korekty.
- `API_CONTRACT.md`.

## Out of scope

- Serwis `VirtualGridGeometryService.save_source` i repozytorium zapisu
  całego źródła — nadal używa ich `scripts/reverify_777_grids.py`.
- Widoki listy `needs_validation`, `needs_correction`, `all` i liczniki stanów:
  zostają jako diagnostyka tylko do odczytu, bo korzysta z nich podsumowanie
  importu w Adminie (`import-geometry-review-summary.tsx`). Operacyjną kolejką
  jest wyłącznie `correction`.
- Kolumna `approved_geometry_revision`, historia
  `image_board_geometry_review_events` (bez DDL).

## Acceptance criteria

- [x] Żaden kod produkcyjny ani klient nie wywołuje usuniętych ścieżek; grep
      bez trafień poza historią dokumentacji.
- [x] Allowlista lokalnego originu nie zawiera ścieżek akceptacji ani zapisu
      całego źródła; testy bezpieczeństwa to potwierdzają.
- [x] OpenAPI i klient zgodne (`npm run openapi:check`).
- [x] Testy API, integracyjne dotknięte zmianą, Reviewera i Admina przechodzą
      (z wyjątkiem porażek istniejących na HEAD).

## Test cases

- Żądanie do usuniętego endpointu → 404/405; allowlista odrzuca stare ścieżki.
- Integracyjne scenariusze domknięcia i joba masowego bez
  `approve_current_geometry`.
- Ekran korekty nadal liczy narożniki i komendy z przeniesionych funkcji.

## Verification

Katalog: root repozytorium; każdy krok z timeoutem ≤180 s.

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_grid_review_api.py services/api/tests/test_local_admin_security.py services/api/tests/test_openapi_contract.py -q
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_verified_cell_search_projection.py -q
npm run openapi:check
npm run test --workspace @game-predictor/admin-api-client
npm run test --workspace @game-predictor/reviewer
npm run test:geometry --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/admin
```

## Risks / open questions

- Otwarte karty starego Reviewera dostaną 404 na usuniętych ścieżkach.

## Outcome

### Changed

- API: removed `POST /image-reviews/{id}/geometry-approval`,
  `POST /games/{id}/grid-reviews/source-geometry-approval` and the HTTP
  endpoint `POST /games/{id}/grid-reviews/source-geometry-revisions`, with
  their schemas and converters.
- Application, domain and repositories: removed `approve`, `approve_source`,
  `approve_grid_geometry`, `approve_source_grid_geometry`, the write-through
  `approve_current_geometry`, `approve_image_grid_review` and the approval
  result/target types. `require_ready_game` of the grid repository had no
  caller left and was removed; `virtual_source` geometry saves keep their own
  projection guard (`virtual_grid_geometry_repository`).
- Local Reviewer origin allowlist: only preview and save of one board
  (`image-reviews/{id}/geometry-preview|geometry-revisions`) and the deferred
  paths remain; the security test proves the removed paths return 403 from
  port 3001 even if a stray route existed.
- OpenAPI, generated client and wrapper without the three operations.
- Reviewer: removed `features/grid-reviews/*` (workspace, editor, actions,
  draft storage, state), `local-reviewer-workspace-state.ts`, the
  `.gridReview*` and `.localReviewerMode*` styles and their tests. The pure
  helpers used by the correction screen (initial corners, qualification,
  preview command) moved to `board-geometry-correction-state.ts` with their
  own tests. `local-reviewer-workspace-contract.test.mjs` replaces the old
  contract test and asserts the module stays gone.
- Kept (out of scope): read-only views `needs_validation`,
  `needs_correction`, `all` and their counts (Admin import summary),
  `VirtualGridGeometryService.save_source` for `reverify_777_grids.py`,
  `approved_geometry_revision` and the review event history.
- Docs: `API_CONTRACT.md`, `ITERATIVE_IMAGE_IMPORT.md` (D-462 note), plan
  (T7 decision, calibration effect), `ADMIN_APP.md`; TASK-0646 (blocked) and
  the 777 plan note that their `approve_source` step no longer exists.

### Verification results

- `test_image_grid_review_api.py`, `test_image_grid_reviews_domain.py`,
  `test_local_admin_security.py`: 26 passed (new: removed paths return
  404/405; the reviewer origin gets 403 on the removed paths).
- `test_openapi_contract.py`: 15 passed, 2 failed — the known `cells.minItems`
  failures that also exist on HEAD; the new assertion (no approval operation
  ids) passes.
- PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`): close/reopen, bulk
  operation and `test_verified_cell_search_projection.py` pass without
  `approve_current_geometry`; `test_symbol_cell_write_through_tracks_…`
  (`catalog_revision 2 == 1`) also fails on pristine HEAD.
- Whole API suite: 1550 passed, 23 failed, 132 skipped; 22 failures are the
  HEAD baseline, the 23rd (`test_approximate_win_endpoint_requires_query_
  parameters`) comes from the uncommitted user spin-limit change.
- Ruff check PASS; ruff format PASS except `local_admin.py` and
  `test_local_admin_security.py`, which were already unformatted on HEAD
  and are kept as is (only the task hunks changed). Mypy on
  `services/api/src services/worker/src`: 29 errors, all in files this task
  does not touch (v7 calibration, worker geometry).
- `npm run openapi:generate`, `openapi:check` PASS; client 66/66.
- Reviewer: typecheck, lint PASS; `npm run test` 169/169; `test:geometry`
  6/6. Admin typecheck PASS.
- Clean worktree of this commit (HEAD + staged hunks only): grid, security
  and OpenAPI tests 41 passed + the 2 known `cells.minItems` failures;
  `export_admin_openapi.py --check` and ruff PASS; Reviewer typecheck, lint,
  test 169/169, `test:geometry` 6/6; Admin typecheck, test 614/614; client
  66/66 and `check:generated` PASS.
- Audit claude-opus-5-5 (subagent, reasoning level inherited): „Brak uwag
  P0–P2”. P3 applied: exact projection-guard wording in `API_CONTRACT.md`,
  endpoint summaries without "approve"/"validation" (OpenAPI regenerated),
  dead `_require_current_review_item_id` removed, D-462 note in the 777 plan,
  calibration effect documented in the plan. P3 left: test-only helpers
  (`derive_image_grid_review`, `_geometry_review_event_board_checksum`) and
  409 mappings of codes nothing raises any more in `main.py` (harmless).

### Not completed

- An old Reviewer tab left open gets 404 on the removed paths (accepted
  risk).
- The blocked 777 re-verification (TASK-0645/0646 and its plan) still
  describes an `approve_source` step; both carry a D-462 note and are
  rewritten together with that work.
- Test-only leftovers stay: `derive_image_grid_review`,
  `_geometry_review_event_board_checksum`, and `main.py` 409 mappings for
  codes nothing raises any more.

### Documentation updates

- `API_CONTRACT.md`, `ITERATIVE_IMAGE_IMPORT.md`,
  `CELL_LEVEL_VERIFICATION_EXECUTION_PLAN.md`,
  `GAME_777_GRID_REVERIFICATION_EXECUTION_PLAN.md`, `ADMIN_APP.md`,
  `CURRENT_STATE.md`, TASK-0646.

### Recommended next task

- Stage B is finished. Stage C (TASK-0728 preview, then apply only after a
  separate consent) needs an explicit operator decision.
