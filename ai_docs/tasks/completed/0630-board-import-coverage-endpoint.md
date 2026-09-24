---
title: TASK-0630 — Endpoint board-import-coverage i klient
status: done
last_updated: 2026-09-24
---

# TASK-0630 — Endpoint `board-import-coverage` i klient

## Status

`done`

## Goal

Admin może pobrać stronicowaną stronę pokrycia importu plansz przez
wygenerowany klient TypeScript.

## Context

Część planu „sekcja Brakujące plansze” w „Import plansz”. Definicja i silnik
obliczeniowy powstają w `TASK-0629`
(`ai_docs/tasks/completed/0629-board-import-coverage-definition.md`); ten task dodaje
wyłącznie warstwę API zgodnie z istniejącym wzorcem kontraktu.

## Dependencies / entry conditions

- `TASK-0629` musi być `done`: domena `board_import_coverage.py` i metoda
  repozytorium muszą istnieć i przechodzić testy.

## Recommended execution

claude-sonnet-5, reasoning medium. Uzasadnienie: mechaniczny pion API według
istniejących wzorców (schema, router, OpenAPI, wrapper); logika już jest w
TASK-0629. Dodatkowy review: nie.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/tasks/completed/0629-board-import-coverage-definition.md`

## Scope

- Pydantic schema odpowiedzi (`schemas/`), zgodny z polami niżej.
- Use case `OperationalImageReviewService.board_import_coverage` w
  `services/api/src/game_predictor_api/application/image_reviews.py`: 404 dla
  brakującej gry, walidacja `from`/`to`/`limit` (1..100), `view ∈ {missing,
  added}`.
- Router: rozszerzenie istniejącej grupy `image-review-items` (tam gdzie już
  jest `dataset-completeness`) o
  `GET /api/v1/admin/image-review-items/board-import-coverage/{gameId}?view=&from=&to=&afterSequenceNumber=&limit=`,
  `operation_id` = `getBoardImportCoverage`.
- `npm run openapi:generate`; wrapper `getBoardImportCoverage` w
  `packages/admin-api-client/src/index.ts` (wzorem `listImageGridReviews`).
- Test żądania wrappera klienta.
- Aktualizacja `ai_docs/architecture/API_CONTRACT.md`.

## Out of scope

- Zmiana lub usunięcie `dataset-completeness` — zostaje bez zmian (DU-2).
- UI Admina (`TASK-0631`).

## Acceptance criteria

- [x] Odpowiedź endpointu zawiera: `gameId, expectedLayoutCount,
      counts{expected, added, missing, approved, outOfRange}, missingByReason{…7
      kodów}, notices{unnumberedCutBoardCount, failedSourcesWithoutRangeCount,
      activeImportJobCount, activeSourcesWithoutRangeCount}, view,
      range{from,to} | null, rangeCounts{added, missing} | null,
      segments[{start, end, count, state, errorCode?, geometryReasonCode?,
      importJobId?}], nextAfterSequenceNumber, computedAt`.
- [x] 404 dla nieznanej gry.
- [x] 422 dla `from > to`, `limit` 0 lub 101, nieznanego `view`.
- [x] `dataset-completeness` nie zmienia zachowania (test regresyjny).
- [x] `npm run openapi:check` przechodzi.

## Technical notes

Wzorować się na istniejącym endpoincie `dataset-completeness` w tej samej
grupie routera co do stylu autoryzacji, błędów i paginacji keyset (wzorzec
`listImageGridReviews`). Mapowanie pól na camelCase przez istniejący
mechanizm Pydantic/OpenAPI, bez ręcznych typów w kliencie.

## Expected files

- Nowe: schema Pydantic (plik w `services/api/src/game_predictor_api/schemas/`,
  nazwa do ustalenia zgodnie z konwencją sąsiednich plików).
- Istniejące: `application/image_reviews.py`, `api/image_reviews.py` (router),
  `packages/admin-api-client/src/index.ts`, `ai_docs/architecture/API_CONTRACT.md`.

## Test cases

- 404 dla nieznanej gry.
- 422 dla `from > to`, `limit` 0/101, nieznanego `view`.
- mapowanie camelCase pełnej odpowiedzi.
- `nextAfterSequenceNumber` przy stronie pełnej (`limit+1`).
- test wrappera klienta (ścieżka i query params).
- regresja: `dataset-completeness` bez zmian w zachowaniu i kontrakcie.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests -k "board_import_coverage or image_dataset_quality" --timeout=120
npm run openapi:generate
npm run openapi:check
npm run python:lint
npm run python:typecheck
```

## Risks / open questions

- Brak, poza zależnością od stabilnego kontraktu domeny z TASK-0629.

## Outcome

### Changed

- [domain/board_import_coverage.py](../../services/api/src/game_predictor_api/domain/board_import_coverage.py):
  nowy `BoardImportCoverageView` (`str, Enum`: `missing`/`added`) dla
  query param `view`.
- [storage/board_import_coverage_repository.py](../../services/api/src/game_predictor_api/storage/board_import_coverage_repository.py):
  `BoardImportCoverageReport` zyskał pole `computed_at: datetime`
  (ustawiane `datetime.now(UTC)` przy każdym odczycie) — brakowało go z
  TASK-0629, a kontrakt endpointu go wymaga.
- [application/image_reviews.py](../../services/api/src/game_predictor_api/application/image_reviews.py):
  nowy Protocol `BoardImportCoverageRepository`; `OperationalImageReviewService`
  przyjmuje opcjonalny `board_import_coverage_repository`; nowa metoda
  `board_import_coverage` — 422 `BOARD_IMPORT_COVERAGE_LIMIT_INVALID` /
  `BOARD_IMPORT_COVERAGE_RANGE_INVALID` (przez bazowy `ImageReviewError`,
  nie `ImageReviewConflictError`, żeby dostać 422 a nie 409), 404
  `IMAGE_REVIEW_GAME_NOT_FOUND`, 422 `BOARD_IMPORT_COVERAGE_UNAVAILABLE`
  gdy repozytorium nie jest skonfigurowane.
- [schemas/image_reviews.py](../../services/api/src/game_predictor_api/schemas/image_reviews.py):
  `BoardImportCoverageResponse` + 5 pomocniczych modeli i
  `to_board_import_coverage_response`. `BoardImportCoverageRangeResponse`
  ma pole `from_` z `Field(alias="from")` (`from` jest słowem kluczowym
  Pythona) — konstruowane przez `**{"from": ..., "to": ...}`, bo mypy bez
  wtyczki pydantic wymaga aliasu jako nazwy parametru `__init__`, a `from=`
  jest błędem składni.
- [api/image_reviews.py](../../services/api/src/game_predictor_api/api/image_reviews.py):
  `GET /admin/image-review-items/board-import-coverage/{game_id}`,
  `operation_id=getBoardImportCoverage`, query `view`/`from`/`to`/
  `afterSequenceNumber`/`limit` (`Query(ge=1, le=100)` dla `limit`).
- [main.py](../../services/api/src/game_predictor_api/main.py): wpięcie
  `SqlAlchemyBoardImportCoverageRepository(session)` do domyślnej fabryki
  `OperationalImageReviewService`.
- `packages/admin-api-client/src/index.ts`: wrapper `getBoardImportCoverage`
  + `GetBoardImportCoverageOptions`, wzorem `listImageGridReviews`; nowe typy
  re-eksportowane. Wygenerowany klient (`src/generated/*`) i
  `openapi/openapi.json` zaktualizowane przez `npm run openapi:generate`.
- `ai_docs/architecture/API_CONTRACT.md`: nowa sekcja opisująca endpoint,
  kontrakt query/response i relację do `dataset-completeness`.
- **Poprawka nieoczekiwanej regresji w niepowiązanym teście:**
  `services/api/tests/test_semi_automatic_selection_migration.py` asercjonował
  dosłowny tekst `drop_table("semi_automatic_selection_v7_activation_gate")`
  bez `schema="public"` — czyli sprzed poprawki `0114` z `v0.10.397`
  (TASK-0629). Zaktualizowano asercję do aktualnego, poprawnego tekstu
  źródła.

### Verification results

- `pytest services/api/tests -k "board_import_coverage or image_dataset_quality"`:
  **32 passed, 12 skipped** (skipy to integracyjne testy PG z TASK-0629,
  gated `GAME_PREDICTOR_RUN_POSTGRES_TESTS`).
- Nowy [test_board_import_coverage_api.py](../../services/api/tests/test_board_import_coverage_api.py)
  (7 przypadków: pełna odpowiedź camelCase, przekazanie
  view/range/cursor/limit, 404, 422×3) — **7/7 passed**.
- `packages/admin-api-client` — `npm run test`: **60/60 passed** (w tym nowy
  `getBoardImportCoverage passes gameId as path and options as query params`
  oraz oba testy driftu wygenerowanego klienta).
- `npm run typecheck --workspace @game-predictor/admin-api-client`: czysto.
- `npm run lint --workspace @game-predictor/admin-api-client`: czysto.
- `npm run openapi:generate` + `npm run openapi:check`: **oba przechodzą**
  („OpenAPI artifact is current", „Generated Admin API client is current").
- `npm run python:lint` (`ruff check services/api services/worker scripts`):
  **1 błąd**, w `services/worker/tests/test_page_geometry_preflight.py:345`
  (E501) — potwierdzone niepowiązane: plik bez mojego diffu, ten sam błąd na
  czystym `HEAD`.
- `npm run python:typecheck` (`mypy services/api/src services/worker/src
  scripts`): **69 błędów w 13 plikach** (spadek z 71/14 sprzed poprawki
  aliasu `from`/`to`) — żaden nie dotyczy plików tego taska; potwierdzone
  identyczne na czystym `HEAD` (`git stash` + porównanie).
- **Pełny `pytest services/api/tests`**: **21 failed, 1393 passed, 96
  skipped** (podniesione z 1392 passed przez nowe testy). Wszystkie 21
  niepowodzeń potwierdzone jako przedsesyjne i niepowiązane — każde z nich
  odtworzone identycznie na czystym `git stash` (commit `v0.10.399`, przed
  jakąkolwiek zmianą z tego taska): `test_reviews.py` (6),
  `test_image_import_geometry_guard_api.py` (6),
  `test_virtual_grid_geometry.py` (2), `test_image_grid_review_api.py` (1),
  `test_lateral_managed_reprocess.py` (1), `test_migration_baseline.py` (1 —
  stały test asercjonujący stary head `0119` sprzed migracji `0120`/`0121`,
  a nie tylko sprzed tego taska), `test_openapi_contract.py` (1, brak
  `minItems` w niepowiązanym schemacie), `test_qualified_cell_reconciliation.py`
  i `test_v09_schema_backfill_repository.py` (już udokumentowane jako
  przedsesyjne w `CURRENT_STATE.md`/D-438).

### Not completed

- Brak — zakres taska zrealizowany w całości.

### Documentation updates

- `ai_docs/architecture/API_CONTRACT.md`: nowa sekcja endpointu.

### Recommended next task

- `TASK-0631` (sekcja Admina) — zależność spełniona: endpoint i wrapper
  klienta istnieją i są zweryfikowane.
- Osobno, poza zakresem: `test_migration_baseline.py` i
  `test_openapi_contract.py` są stare i nie dotyczą tego planu — warto
  zaplanować ich naprawę (aktualizacja oczekiwanego head'a migracji i
  brakującego `minItems`) osobnym, małym taskiem porządkowym.
