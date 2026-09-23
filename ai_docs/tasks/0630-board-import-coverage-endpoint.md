---
title: TASK-0630 — Endpoint board-import-coverage i klient
status: todo
last_updated: 2026-09-24
---

# TASK-0630 — Endpoint `board-import-coverage` i klient

## Status

`todo`

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

- [ ] Odpowiedź endpointu zawiera: `gameId, expectedLayoutCount,
      counts{expected, added, missing, approved, outOfRange}, missingByReason{…7
      kodów}, notices{unnumberedCutBoardCount, failedSourcesWithoutRangeCount,
      activeImportJobCount, activeSourcesWithoutRangeCount}, view,
      range{from,to} | null, rangeCounts{added, missing} | null,
      segments[{start, end, count, state, errorCode?, geometryReasonCode?,
      importJobId?}], nextAfterSequenceNumber, computedAt`.
- [ ] 404 dla nieznanej gry.
- [ ] 422 dla `from > to`, `limit` 0 lub 101, nieznanego `view`.
- [ ] `dataset-completeness` nie zmienia zachowania (test regresyjny).
- [ ] `npm run openapi:check` przechodzi.

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

Wypełnia agent po pracy.
