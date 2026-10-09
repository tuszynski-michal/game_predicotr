---
title: TASK-0961 — Tanie liczniki korekty, filtr realnych braków i flaga zatwierdzenia ręcznego
status: done
last_updated: 2026-10-10
---

# TASK-0961 — Tanie liczniki korekty, filtr realnych braków i flaga zatwierdzenia ręcznego

## Status

`done`

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

- [x] `counts=all` (domyślne) zwraca dokładnie te same liczniki co przed zmianą.
- [x] `counts=correction` zwraca `counts.correction` równe wartości z `all`
      (Mumie 0, 777 255 w dniu planowania) i trwa ≤ 3 s na obu grach.
- [x] `gapsOnly=true` zwraca zdjęcia czterech stanów, bez `uncertain` i
      `superseded`; Mumie: 4 zdjęcia, 777: 76; strona ≤ 12 s.
- [x] `gapsOnly=true&imageState=…` → 422 z kodem konfliktu.
- [x] `humanApproved` zgodne z `geometry_approved` na planszach testowych.
- [x] `npm run openapi:check`, `npm run python:lint`, `npm run python:typecheck`
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

Wykonawca: `claude-fable-5-1`, 2026-10-10, worktree
`worktrees/reviewer-geometry-gaps` (gałąź `feat/reviewer-geometry-gaps`, baza
`v1.7.300`). Bez migracji i bez zmian klasyfikacji D-484. Commit i wersję
dopisuje orkiestrator po audycie.

### Changed

- `domain/image_grid_reviews.py`: enum `ImageGridReviewCountsMode` (`all`,
  `correction`).
- `application/image_grid_reviews.py`: `ImageGridReviewService.list(...,
  counts=ALL)`; protokół repozytorium ma `grid_review_correction_count`; w
  trybie `correction` serwis nie woła `grid_review_counts` i zwraca
  `ImageGridReviewCounts(correction=N)` z pozostałymi licznikami `0`.
- `storage/image_grid_review_repository.py`: nowa metoda
  `grid_review_correction_count` (dwa zliczenia: zgłoszone plansze przez
  `_visible_statement(CORRECTION)` i sloty odroczone przez
  `_pending_statement(CORRECTION)`); `grid_review_counts` używa jej dla pola
  `correction` (ten sam wynik co dotąd).
- `api/image_grid_reviews.py`: parametr zapytania `counts` z opisem w
  OpenAPI; `schemas/image_grid_reviews.py`: opis schematu
  `ImageGridReviewCountsResponse` (zera w trybie `correction`).
- `domain/image_geometry_completeness.py`: stała `REAL_GAP_IMAGE_STATES`
  (`incomplete_missing`, `incomplete_partial`, `import_failed`,
  `no_source_geometry`).
- `storage/image_geometry_completeness_repository.py`:
  `incomplete_images(..., gaps_only=False)` z filtrem `image_state IN (...)`
  budowanym wyłącznie z wartości enumu (`_state_in_sql`), konflikt z
  `image_state`/`completeness_status` →
  `IMAGE_GEOMETRY_COMPLETENESS_FILTER_CONFLICT`
  (`geometry_completeness_filter_conflict`); `GeometryImagePosition.human_approved`
  z faktu `geometry_approved` wiersza `_POSITIONS_SQL` (bez dodatkowego
  zapytania); `IncompleteGeometryImagePage.gaps_only`.
- `application/image_reviews.py`: `incomplete_geometry_images(...,
  gaps_only=False)` z tym samym sprawdzeniem konfliktu (422 przed dostępem do
  repozytorium); protokół `ImageGeometryCompletenessRepository`.
- `api/image_reviews.py`: parametr `gapsOnly` z opisem;
  `schemas/image_geometry_completeness.py`: pola `humanApproved` (pozycja) i
  `gapsOnly` (strona).
- OpenAPI `packages/admin-api-client/openapi/openapi.json`, wygenerowane
  `src/generated/{index.ts,types.gen.ts}` (`ImageGridReviewCountsMode`,
  `gapsOnly`, `humanApproved`), wrapper `src/index.ts`
  (`ListImageGridReviewsOptions.counts`, `ListIncompleteGeometryImagesOptions.gapsOnly`,
  eksport typu `ImageGridReviewCountsMode`), test żądań w
  `test/client.test.mjs`.
- Testy: `services/api/tests/test_image_grid_review_api.py` (atrapa
  repozytorium z rejestrem wywołań liczników; `counts=correction` nie woła
  `grid_review_counts`, `counts=all` i domyślne wołają, nieznana wartość 422;
  test serwisu), `test_image_geometry_completeness_api.py` (`gapsOnly`
  przekazany i echo w stronie, konflikt z `imageState` i
  `completenessStatus` → 422 bez wywołania repozytorium, `humanApproved` w
  odpowiedzi), `tests/integration/test_image_geometry_completeness_repository.py`
  (nowy świat „geo-d”: `gaps_only` zwraca cztery stany bez `uncertain` i
  `superseded`, stronicowanie kursorem, konflikt filtrów, `human_approved`
  true dla zatwierdzonej planszy `partial`, false dla niezatwierdzonej i dla
  slotów bez planszy).
- `ai_docs/architecture/CODE_MAP_SYMBOLS.md` zregenerowane (dwa wiersze
  zmienionych modułów).

### Verification results

Uruchomione (korzeń worktree, `PYTHONPATH` na `services/api/src` i
`services/worker/src` worktree):

- `pytest services/api/tests/test_image_grid_review_api.py
  test_image_geometry_completeness_api.py test_image_geometry_completeness_domain.py
  test_image_grid_reviews_domain.py -q` → 148 passed (142 s).
- `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 pytest
  services/api/tests/integration/test_image_geometry_completeness_repository.py -q`
  → 30 passed (21,5 s; własna baza `game_predictor_task0806_*`, usunięta po
  teście).
- `ruff check services/api services/worker services/test_support scripts` →
  All checks passed; `ruff format --check` zmienionych plików → 13 already
  formatted.
- `npm run openapi:generate` → OK; `npm run check:generated --workspace
  @game-predictor/admin-api-client` → „Generated Admin API client is
  current”; `npm run test --workspace @game-predictor/admin-api-client`
  (build `tsc` + `tsx --test`) → 107 passed.
- `scripts/generate_code_map.py --check` → po regeneracji aktualna;
  `scripts/check_decision_links.py` → OK.
- `mypy services/api/src services/worker/src scripts` (`--strict` z
  konfiguracji) → Success: no issues found in 862 source files (291 s).
- `pytest services/api/tests -k "grid_review or geometry_completeness"`
  (bez katalogu `integration`) → 149 passed, 2437 deselected (156 s).
- `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 pytest services/api/tests/integration
  -k "geometry_completeness or grid_review"` → 38 passed, 284 deselected
  (174 s; sekwencyjnie, po testach jednostkowych).
- `npm run openapi:check` → „OpenAPI artifact is current”, „Generated Admin
  API client is current”, exit 0.
- `scripts/check_current_state_window.py` → OK (10 sekcji `done`, 70 642 B);
  `git diff --check` → czysto.
- `npm run typecheck --workspace @game-predictor/admin` (konsument
  `listIncompleteGeometryImages`; nowe pola są opcjonalne) → exit 0 (23 s).

Pomiar (pojedyncze żądania GET, 2026-10-10; nowy kod: tymczasowa instancja z
worktree na porcie 8011, ta sama baza lokalna; stary kod: działająca instancja
z głównego checkoutu na porcie 8000; PID instancji 8011 zapisany i proces
zatrzymany po pomiarze, port bez osieroconego procesu):

| Żądanie | Gra | Stary kod (8000) | Nowy kod (8011) |
|---|---|---|---|
| `grid-reviews?view=correction&limit=1&counts=correction` | Mumie | — (brak parametru) | 1,08 s / 0,08 s (`correction=0`) |
| `grid-reviews?view=correction&limit=1&counts=correction` | 777 | — | 1,00 s / 0,23 s (`correction=255`) |
| `grid-reviews?view=correction&limit=1` (domyślne `counts=all`) | Mumie | 21,77 s (`correction=0`) | 23,84 s (te same liczniki) |
| `grid-reviews?view=correction&limit=1` (domyślne `counts=all`) | 777 | 26,86 s (`correction=255`) | 33,07 s (te same liczniki) |
| `incomplete-images?gapsOnly=true&limit=25` | Mumie | — (4,29 s dla `imageState=incomplete_missing`, 1 zdjęcie) | 4,69 s / 3,85 s (4 zdjęcia, bez kursora) |
| `incomplete-images?gapsOnly=true&limit=25` | 777 | — (4,84 s dla `imageState=incomplete_partial`, 25 zdjęć) | 5,68 s / 4,93 s (25 zdjęć, jest kursor) |
| `incomplete-images?gapsOnly=true&limit=100` | Mumie | — | 4,47 s: 4 zdjęcia (1 `incomplete_missing`, 3 `import_failed`) |
| `incomplete-images?gapsOnly=true&limit=100` | 777 | — | 4,66 s: 76 zdjęć (wszystkie `incomplete_partial`; 73 z wszystkimi pozycjami `partial` zatwierdzonymi ręcznie) |
| `incomplete-images?gapsOnly=true&imageState=incomplete_partial` | obie | — | 422 `IMAGE_GEOMETRY_COMPLETENESS_FILTER_CONFLICT` (< 0,01 s) |

Budżety planu spełnione bez indeksu i migracji: `counts=correction` ≤ 1,08 s
(limit 3 s), strona `gapsOnly` ≤ 5,68 s (limit 12 s). `counts=correction`
zgadza się z `counts.correction` trybu `all` (Mumie 0, 777 255). Liczby
zdjęć zgodne z planem (Mumie 4, 777 76). Zachowanie domyślne obu endpointów
bez zmian (liczniki `counts=all` identyczne ze starym kodem; czas domyślnej
odpowiedzi nadal 22–33 s — to świadomie nie jest przedmiotem taska).

### Not completed

- Brak. Migracja/indeks nie były potrzebne (budżety spełnione), więc nie
  wykonano EXPLAIN.
- Pełna bramka `npm run quality` nie była uruchamiana (poza zakresem taska;
  uruchomiono kontrole z sekcji `Verification`).

### Documentation updates

- `ai_docs/architecture/API_CONTRACT.md`: akapity TASK-0961 przy
  `incomplete-images` (`gapsOnly`, `humanApproved`, kod konfliktu, echo
  `gapsOnly`) i przy `grid-reviews` (`counts`).
- `ai_docs/architecture/CODE_MAP_SYMBOLS.md`: regeneracja.
- `ai_docs/process/CURRENT_STATE.md`: sekcja `done` TASK-0961, usunięcie z
  aktywnych; TASK-0938 przeniesiony do `ai_docs/archive/CURRENT_STATE_2026Q4.md`.
- Bez wpisu w `DECISION_LOG.md` (zgodna z planem rozbudowa kontraktu; decyzję
  D-540 zapisuje TASK-0965).

### Recommended next task

- TASK-0962

### Audit

Niezależny audyt tylko do odczytu: subagent Claude `sonnet` (`medium`),
niższy model niż wykonawca (Codex niedostępny z powodu wyczerpanego limitu;
zastępstwo zgodne z poleceniem operatora z 2026-10-10). Werdykt: PASS z
uwagami P2, brak P0/P1. Uwagi P2 (bez zmian w kodzie, odnotowane):

- brak bezpośredniego testu PostgreSQL równości
  `grid_review_correction_count == grid_review_counts().correction`
  (pokryte pośrednio i pomiarem na żywych danych);
- `gapsOnly=true&imageState=geometry_complete` zwraca
  `IMAGE_GEOMETRY_COMPLETENESS_STATE_INVALID`, nie kod konfliktu (kolejność
  walidacji); Reviewer nie łączy tych parametrów.

Checkboxy kryteriów akceptacji zaznaczone po audycie.
