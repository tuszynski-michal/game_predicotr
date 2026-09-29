# TASK-0727 — Usunięcie procesu „Walidacja gotowych siatek”

## Status

todo

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

- [ ] Żaden kod produkcyjny ani klient nie wywołuje usuniętych ścieżek; grep
      bez trafień poza historią dokumentacji.
- [ ] Allowlista lokalnego originu nie zawiera ścieżek akceptacji ani zapisu
      całego źródła; testy bezpieczeństwa to potwierdzają.
- [ ] OpenAPI i klient zgodne (`npm run openapi:check`).
- [ ] Testy API, integracyjne dotknięte zmianą, Reviewera i Admina przechodzą
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

Wypełnia agent po pracy.
