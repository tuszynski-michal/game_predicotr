# TASK-0726 — Jeden ekran „Korekta cięcia siatki” na porcie 3001

## Status

done

## Goal

Lokalny Reviewer pokazuje jedną planszę i jej siatkę naraz z kolejki
`correction`, zapisuje korektę i przechodzi do następnej planszy, bez
walidacji gotowych siatek.

## Context

D-462 R4/R5, scenariusz 8. Dziś `LocalReviewerWorkspace` przełącza tryby
„Walidacja gotowych siatek” (całe zdjęcie, dziewięć plansz, zakładki) i
„Niepełne siatki do ręcznej korekty” (`OperationalReviewWorkspace`).

## Dependencies / entry conditions

TASK-0725 done (widok `correction`, `reportedCellIndices`).

## Recommended execution

claude-opus-5-5, high — UI na istniejącym edytorze, kontrakt z T5. Audyt:
claude-opus-5-5, high (subagent, poziom warunkowy).

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` D-462
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/delivery/CELL_LEVEL_VERIFICATION_EXECUTION_PLAN.md`

## Scope

- Adapter `BoardGeometryCorrectionTarget` (slot odroczony: istniejące akcje
  `board-cell-geometry-pending`; plansza zgłoszona: `image-reviews/{id}`
  preview/revisions i `source-asset`).
- Ogólny `BoardGeometryCorrectionEditor` wydzielony z edytora odroczonej
  geometrii; `DeferredBoardCellGeometryEditor` zostaje nakładką (zdalny
  Reviewer bez zmian).
- `BoardGeometryCorrectionWorkspace` (kolejka `correction`, limit 1, licznik,
  `Poprzednia` / `Pomiń na razie`, po zapisie następna plansza, wyróżnienie
  zgłoszonych pól).
- `LocalReviewerWorkspace` renderuje wyłącznie nowy ekran.
- Admin: nazwa „Korekta cięcia siatki”, licznik kolejki w launcherze, teksty
  importu, link bez `gridView`; przewodnik operatora i `ADMIN_APP.md`.

## Out of scope

- Usunięcie modułów `grid-reviews` i endpointów akceptacji (TASK-0727).
- Zdalny Reviewer (P3).

## Acceptance criteria

- [x] Ekran 3001 pokazuje jedną planszę, bez zakładek walidacji i akcji
      zatwierdzania (scenariusz 8).
- [x] Zapis wysyła geometrię tej jednej planszy i przechodzi do następnej.
- [x] Zgłoszone pola są widoczne w metadanych i podglądzie cropów.
- [x] Dotychczasowy edytor odroczonej geometrii zachowuje zachowanie (testy).
- [x] Typecheck, lint, testy Reviewera i Admina.

## Expected files

- Nowe: `apps/reviewer/src/features/operational-reviews/board-geometry-correction-target.ts`,
  `.../board-geometry-correction-workspace.tsx`,
  `apps/reviewer/test-interactions/board-geometry-correction.test.mjs`.
- Istniejące: `.../deferred-board-cell-geometry-editor.tsx`,
  `apps/reviewer/src/features/access/local-reviewer-workspace.tsx`,
  `apps/reviewer/test/operational-review-workspace-contract.test.mjs`,
  `apps/admin/src/features/reviewer-access/reviewer-access-launcher.tsx`,
  `apps/admin/src/features/catalog/catalog-workspace.tsx`,
  `apps/admin/src/features/imports/image-folder-import-panel.tsx`,
  `apps/admin/src/features/imports/import-geometry-review-summary.tsx`,
  `apps/admin/test/reviewer-access-launcher-contract.test.mjs`,
  `ai_docs/requirements/ADMIN_APP.md`, `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`.

## Verification

Katalog: root repozytorium; każdy krok z timeoutem ≤180 s.

```powershell
npm run typecheck --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
npm run test --workspace @game-predictor/reviewer
npm run test:geometry --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/admin
npm run test --workspace @game-predictor/admin
```

## Risks / open questions

- Brak testu E2E na żywym Reviewerze; ekran pokryty testem interakcji jsdom.

## Outcome

### Changed

- `board-geometry-correction-target.ts`: one adapter per queue entry. A
  deferred slot uses the existing `board-cell-geometry-pending` actions; a
  board with a `Zła siatka` report uses `image-reviews/{id}` preview and
  geometry revision plus the checksum-bound `source-asset`. Both save exactly
  one board. A virtual board keeps its persisted qualification (also
  `complete`); a legacy board never sends one. Only an explicit allowlist of
  revision, owner, not-found and superseded codes reloads the queue.
- `BoardGeometryCorrectionEditor` extracted from the deferred editor;
  `DeferredBoardCellGeometryEditor` is a thin wrapper, so the remote Reviewer
  keeps its behaviour. Reported cells are outlined in the crop preview and
  listed in the metadata. The automatic preview no longer re-runs while the
  preview is current, so the error of a failed save stays visible (it was
  cleared after 150 ms before).
- `BoardGeometryCorrectionWorkspace`: queue `correction`, `limit: 1`,
  counter `Do korekty`, `← Poprzednia`, `Pomiń na razie →` / `Od początku`,
  next board after saving, one reload per conflicting board (then a notice
  to skip it or return later instead of a loop).
- `LocalReviewerWorkspace` renders only this screen; the tabs and
  „Walidacja gotowych siatek” are gone from port 3001.
- Admin: „Korekta cięcia siatki” in the catalog, launcher (counter
  `counts.correction` and deferred geometries), import texts and import
  summary; `hasReviewerWork` follows the correction queue.
- `ADMIN_APP.md` section „Korekta cięcia siatki”, operator guide.
- Beyond the expected files: `reviewer-access-state.ts` and its test,
  `grid-review-workspace-contract.test.mjs`. The launcher explains an empty
  queue and labels deferred geometries separately (they are not a subset
  count of the queue when a stale deferral has a live board).

### Verification results

- Reviewer: typecheck, lint PASS; `npm run test` 203/203;
  `test:geometry` 9/9, including 5 new interaction tests (reported board
  save, deferred save with a lost response and the same idempotency key,
  legacy/virtual qualification, skip/previous with a permanent preview
  failure and a single queue request, one reload per conflict).
- Admin: typecheck, lint PASS; `npm run test` 615/615 (614/614 on a clean
  worktree of this commit).
- Clean worktree of this commit (HEAD + staged hunks only): all Reviewer
  checks above and Admin typecheck, lint, test PASS. Admin `test:geometry`
  has 1 failure, `bulk unreadable reconciles two outside positions…`, which
  also fails on pristine HEAD `1bb37684` (symbol-review, outside this task).
  The approximate-win chart failure in the main checkout comes only from
  uncommitted user changes.
- Audit claude-opus-5-5 (subagent, reasoning level inherited): cycle 1 —
  2× P1 (red contract test, infinite reload on a permanent failure), 2× P2
  (qualification of partial boards ignored, missing regression tests),
  P3 texts; cycle 2 — „Brak uwag P0–P2”; P3 applied: a guarded load
  conflict ends in an error state, the guard notice depends on a next board,
  the launcher explains an empty queue, docs; P3 moved to TASK-0727: dead
  mode-switch state.

### Not completed

- No E2E on a live Reviewer; the screen is covered by jsdom interaction
  tests.
- Old grid-validation modules and endpoints remain until TASK-0727, including
  the now unused `local-reviewer-workspace-state.ts`, its test and the
  `.localReviewerMode*` styles.
- A deferred slot opens from the `correction-context` board quad with
  full-board flags; the automatic partial/frame proposals of the queue item
  are not preselected (the old whole-photo screen confirmed them with one
  click). Left as a product decision for the operator.

### Documentation updates

- `ADMIN_APP.md`, `LOCAL_OPERATION_GUIDE.md`, `CURRENT_STATE.md`.

### Recommended next task

- TASK-0727.
