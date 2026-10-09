---
title: TASK-0961 — Tanie liczniki korekty, filtr realnych braków i flaga zatwierdzenia ręcznego
status: todo
last_updated: 2026-10-10
---

# TASK-0961 — Tanie liczniki korekty, filtr realnych braków i flaga zatwierdzenia ręcznego

## Status

`todo`

## Goal

Reviewer w zakresie całej gry dostaje z API (a) licznik `correction` w czasie
≤ 3 s, (b) listę zdjęć z realnymi brakami jednym zapytaniem (`gapsOnly`) w
czasie ≤ 12 s na stronę oraz (c) flagę `humanApproved` przy każdej pozycji.

## Context

Plan: `ai_docs/delivery/REVIEWER_GEOMETRY_GAPS_EXECUTION_PLAN.md`, decyzje 7 i 8.
`GET /api/v1/admin/games/{game_id}/grid-reviews?view=correction&limit=1` trwa
dziś 23 s (Mumie) i 45 s (777), bo `ImageGridReviewService.list` zawsze liczy
komplet liczników (`grid_review_counts`). Reviewer woła ten endpoint po każdej
planszy. `incomplete-images` filtruje jednym stanem; „realne braki” to cztery
stany, więc bez nowego filtra potrzebne byłyby cztery zapytania po ~5–11 s.

## Dependencies / entry conditions

- Fakty: patrz plan, „Stan obecny”. Pomiary z 2026-10-10 są punktem odniesienia.
- Brak migracji z założenia. Jeśli budżet czasu wymaga indeksu — numer
  migracji sprawdzić na końcówce `v1.1-vision-lab-hybrid-geometry`
  (w chwili planowania head = `0153_merge_compact_super_games`), a decyzję o
  indeksie zapisać w `Outcome` z planem EXPLAIN.
- Nie uruchamiaj benchmarków ani pętli obciążeniowych; pomiar to najwyżej 3
  pojedyncze żądania na endpoint.

## Recommended execution

`claude-fable-5-1`, `high` — zgodnie z tabelą planu. Eskalacja do `xhigh`, jeśli
budżet czasu nie jest osiągalny bez zmiany zapytania lub indeksu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/REVIEWER_GEOMETRY_GAPS_EXECUTION_PLAN.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md` (D-462, D-484, D-485)

## Scope

1. `GET /games/{game_id}/grid-reviews`: nowy opcjonalny parametr `counts` ze
   wartościami `all` (domyślna, zachowanie bez zmian) i `correction`. W trybie
   `correction` odpowiedź ma poprawne `counts.correction`, a pozostałe liczniki
   `0`; opis pola w OpenAPI mówi to wprost. Implementacja: osobna metoda
   repozytorium liczące wyłącznie `reported_boards + deferred_slots`
   (istniejące `_visible_statement`/`_pending_statement` dla widoku
   `CORRECTION`), wybierana w `ImageGridReviewService.list`.
2. `GET /geometry-completeness/{game_id}/incomplete-images`: nowy parametr
   boolowski `gapsOnly`. Gdy `true`, filtr stanu to
   `incomplete_missing`, `incomplete_partial`, `import_failed`,
   `no_source_geometry` (bez `incomplete_uncertain` i `superseded`).
   Połączenie z `imageState` lub `completenessStatus` → 422
   `IMAGE_GEOMETRY_COMPLETENESS_FILTER_CONFLICT`. Stała zbioru w domenie
   (`domain/image_geometry_completeness.py`, np. `REAL_GAP_IMAGE_STATES`).
3. `GeometryCompletenessPositionResponse`: nowe pole `humanApproved: bool`
   (z faktu `geometry_approved` pozycji — `approved_geometry_revision ==
   geometry_revision` planszy; `false` gdy brak planszy).
4. OpenAPI (`npm run openapi:generate`), regenerowany klient
   `packages/admin-api-client`, wrapper w `src/index.ts` (parametry `counts` i
   `gapsOnly`) i test żądania w pakiecie klienta.
5. Pomiar przed/po (≤ 3 żądania na endpoint, Mumie i 777) zapisany w `Outcome`.

## Out of scope

- Zmiana klasyfikacji D-484, nowe stany, nowe tabele.
- Zmiana domyślnego zachowania `grid-reviews` i `incomplete-images`.
- Endpointy zapisu; zmiana polityki origin Reviewera.

## Acceptance criteria

- [ ] `counts=all` (domyślne) zwraca dokładnie te same liczniki co przed zmianą.
- [ ] `counts=correction` zwraca `counts.correction` równe wartości z `all`
      (Mumie 0, 777 255 w dniu planowania) i trwa ≤ 3 s na obu grach.
- [ ] `gapsOnly=true` zwraca zdjęcia czterech stanów, bez `uncertain` i
      `superseded`; Mumie: 4 zdjęcia, 777: 76; strona ≤ 12 s.
- [ ] `gapsOnly=true&imageState=…` → 422 z kodem konfliktu.
- [ ] `humanApproved` zgodne z `geometry_approved` na planszach testowych.
- [ ] `npm run openapi:check`, `npm run python:lint`, `npm run python:typecheck`
      przechodzą.

## Technical notes

Aktualne zachowanie → wymagane: `list` zawsze woła `grid_review_counts`
(7 zapytań zliczających po ~460 tys. wierszy review) → w trybie `correction`
woła jedną metodę z dwoma zliczeniami po istniejących częściowych indeksach
(`quality_issue = 'grid_issue'`). `incomplete_images` buduje `state_filter`
jako tekst SQL z jawnej listy stałych — nowy filtr użyj tego samego
mechanizmu z listą `REAL_GAP_IMAGE_STATES` (wartości enumu, nigdy dane
wejściowe). Pozycje pobiera `_positions`; `geometry_approved` jest już faktem
klasyfikacji — przekaż je do odpowiedzi, nie licz drugi raz osobnym zapytaniem
o ile jest dostępne w tym samym przebiegu. Nie zmieniaj `classify_*`.

## Expected files

- Istniejące: `services/api/src/game_predictor_api/api/image_grid_reviews.py`
  (`list_image_grid_reviews`), `application/image_grid_reviews.py`
  (`ImageGridReviewService.list`, protokół repozytorium),
  `storage/image_grid_review_repository.py` (`grid_review_counts` + nowa
  metoda), `api/image_reviews.py` (`list_incomplete_geometry_images`),
  `application/image_reviews.py` (`incomplete_geometry_images`),
  `storage/image_geometry_completeness_repository.py` (`incomplete_images`,
  `_positions`), `schemas/image_geometry_completeness.py`,
  `domain/image_geometry_completeness.py`,
  `packages/admin-api-client/src/index.ts` oraz wygenerowane pliki OpenAPI.
- Nowe (proponowane): testy w `services/api/tests/` obok istniejących testów
  tych modułów.

## Test cases

- Serwis: `counts=correction` nie woła `grid_review_counts` (atrapa
  repozytorium); `counts=all` woła.
- PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`): zdjęcia w stanach
  missing/partial/uncertain/import_failed/superseded → `gapsOnly` zwraca
  cztery pierwsze bez `uncertain`; `humanApproved` true dla zatwierdzonej
  planszy `partial`, false dla niezatwierdzonej i dla slotu bez planszy.
- Konflikt filtrów → 422.
- Klient: żądanie zawiera `counts=correction` i `gapsOnly=true`.

## Verification

```powershell
# katalog: korzeń worktree; każda komenda z timeoutem <= 120 s
.\.venv\Scripts\python.exe -m pytest services/api/tests -k "grid_review or geometry_completeness" -q
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration -k "geometry_completeness or grid_review" -q
npm run python:lint
npm run python:typecheck
npm run openapi:generate
npm run openapi:check
```

Zaliczenie: wszystkie powyższe zielone i pomiary czasu z kryteriów w `Outcome`.
Testy planowane nie są wynikami wykonania.

## Risks / open questions

- Budżet 3 s dla `correction` może wymagać zmiany zapytania `_live_board_in_slot`
  lub indeksu; wtedy stop i aktualizacja planu (Alembic, decyzja operatora).
- Worktree nie ma `node_modules`/`.venv` — użyj `.venv` głównego checkoutu z
  `PYTHONPATH` na worktree i `npm install --prefer-offline` przed generacją
  klienta.

## Outcome

Wypełnia agent po pracy.

### Changed

- ...

### Verification results

- ...

### Not completed

- ...

### Documentation updates

- ...

### Recommended next task

- TASK-0962
