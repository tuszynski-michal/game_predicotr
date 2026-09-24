---
title: TASK-0638 — rozróżnialny błąd podglądu w Reviewerze + log API
status: done
last_updated: 2026-09-24
---

# TASK-0638 — rozróżnialny błąd podglądu w Reviewerze + log API

## Status

`done`

## Goal

Operator widzi w Reviewerze, *dlaczego* podgląd oryginału siatki nie działa
(zamiast jednego ogólnego komunikatu), a backend zostawia log korelowalny
z konkretnym zasobem, gdy odmawia dostępu do assetu.

## Context

Kontynuacja TASK-0637 (D-442). Po naprawie bindowania scope w T1, ekran
„Zatwierdzanie cięcia siatki” może nadal odmówić z różnych, odróżnialnych
powodów (brak pliku, checksum drift, projekcja niegotowa, plansza
nieaktualna, błąd sieci, obraz 200 ale nie do zdekodowania). Przed tym
taskiem `<img>.onerror` zawsze pokazywał ten sam tekst „Nie udało się
wczytać oryginalnego obrazu źródłowego.”, niezależnie od przyczyny.

## Dependencies / entry conditions

- TASK-0637 (D-442) ukończony — cztery trasy `/image-reviews/{id}/…` bindują
  `game_storage_scope`.
- Fakt: `apps/reviewer/src/features/grid-reviews/grid-review-editor.tsx`
  miało jeden statyczny komunikat w `image.onerror` (linia ok. 526–529
  przed zmianą).
- Fakt: klient miał już `api.getImageGridReviewSourceAsset`
  (`packages/admin-api-client/src/index.ts:2225`).

## Recommended execution

claude-sonnet-5, reasoning: high. Frontend + log backendu, łatwy do
testowania; ryzyko głównie stanu wyścigu przy zmianie planszy w trakcie
opisywania błędu. Dodatkowy review: nie.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-442)

## Scope

- `apps/reviewer/src/features/grid-reviews/grid-review-actions.ts`: nowa
  funkcja `describeGridSourceAssetFailure(api, item)` — woła
  `getImageGridReviewSourceAsset` i mapuje `error.code` na jeden z pięciu
  komunikatów (patrz Technical notes), z fallbackiem na `apiErrorMessage`
  i `disconnected()` dla sieci.
- `apps/reviewer/src/features/grid-reviews/grid-review-editor.tsx`:
  `image.onerror` woła `describeGridSourceAssetFailure` zamiast ustawiać
  statyczny tekst; efekt ładowania obrazu dostaje flagę `cancelled`, żeby
  spóźniony wynik nie nadpisał błędu innej (już wybranej) planszy.
- `services/api/src/game_predictor_api/application/image_review_assets.py`:
  `logger.warning` przed każdym z 4 `raise ImageReviewNotFoundError` w
  `_resolve`, z `asset_kind`, kodem i **względną** ścieżką (nigdy
  absolutną).
- `services/api/src/game_predictor_api/api/image_grid_reviews.py`:
  handler `get_image_grid_review_source_asset` loguje `review_item_id` i
  `game_id` razem z kodem błędu przy `ImageGridReviewError`/
  `ImageReviewNotFoundError`, przed ponownym `raise` (bez zmiany
  kodu/statusu).

## Out of scope

- Kontrakt API, URL obrazu, cache headers, proxy allowlist Reviewera — bez
  zmian.
- Logowanie w handlerach `geometry-preview`/`geometry-revisions`
  (`preview_image_grid_review_geometry`, `create_image_grid_review_geometry_revision`)
  — poza minimalnym zakresem T2; ten sam mechanizm (`_resolve`'s logi) i tak
  obejmuje resolucję plików cropów wewnątrz tych serwisów.
- Odbiór na żywych danych (T3/TASK-0639).
- Dane, reimport, zmiany geometrii/zatwierdzeń.

## Acceptance criteria

- [x] `describeGridSourceAssetFailure` zwraca 5 różnych, rozróżnialnych
      komunikatów dla 5 kodów błędu + komunikat dekodowania dla 200 + komunikat
      rozłączenia dla wyjątku sieciowego.
- [x] Wynik ignorowany, jeśli plansza/zakładka zmieniła się w międzyczasie
      (`cancelled` w cleanupie efektu).
- [x] `_resolve` loguje `WARNING` z `asset_kind`, kodem i względną ścieżką
      (bez ścieżki absolutnej) dla wszystkich 4 gałęzi błędu.
- [x] Testy zielone: `apps/reviewer` (jednostkowe dla mapowania kodów),
      `test_operational_image_reviews.py` (log na `tmp_path`).
- [x] `npm run reviewer:build` przechodzi.

## Technical notes

Mapowanie kodu błędu → komunikat (zaimplementowane dokładnie wg planu):

| kod | komunikat |
|---|---|
| `IMAGE_REVIEW_ASSET_NOT_FOUND` | „Brak pliku oryginału w magazynie aplikacji.” |
| `IMAGE_REVIEW_ASSET_CHECKSUM_DRIFT` / `IMAGE_GRID_REVIEW_SOURCE_DRIFT` | „Oryginał zmienił się od wczytania kolejki — odśwież.” |
| `IMAGE_GRID_REVIEW_PROJECTION_INCOMPLETE` | „Projekcja symboli tej gry nie jest gotowa.” |
| `IMAGE_GRID_REVIEW_ITEM_NOT_FOUND` | „Plansza nie jest już aktualna — odśwież kolejkę.” |
| brak odpowiedzi / sieć | istniejący `disconnected()` |
| 200 (obraz jest, ale `<img>` się nie zdekodował) | „Nie udało się zdekodować obrazu źródłowego.” |

Wynik `getImageGridReviewSourceAsset` na 200 jest odrzucany — źródłem
obrazu pozostaje wyłącznie `<img>`, funkcja tylko diagnozuje.

## Expected files

- Istniejące: `apps/reviewer/src/features/grid-reviews/grid-review-actions.ts`
  — nowy eksport `describeGridSourceAssetFailure`.
- Istniejące: `apps/reviewer/src/features/grid-reviews/grid-review-editor.tsx`
  — efekt ładowania obrazu w linii ok. 519–551.
- Istniejące: `apps/reviewer/test/grid-review-actions.test.mjs` — 6 nowych
  testów.
- Istniejące: `services/api/src/game_predictor_api/application/image_review_assets.py`
  — `LOGGER` + 4 `logger.warning`.
- Istniejące: `services/api/src/game_predictor_api/api/image_grid_reviews.py`
  — `LOGGER` + try/except wokół `get_image_grid_review_source_asset`.
- Istniejące: `services/api/tests/test_operational_image_reviews.py` —
  nowy test `test_asset_resolution_logs_missing_file_with_asset_kind_and_relative_path`.

## Test cases

- 6 kodów/scenariuszy → 6 różnych komunikatów (jednostkowe, czysta funkcja
  z fake `api`).
- Brakujący plik w `tmp_path` → `ImageReviewNotFoundError` +
  `caplog` zawiera `IMAGE_REVIEW_ASSET_NOT_FOUND`, względną ścieżkę,
  `asset_kind="source"`, i **nie** zawiera absolutnej ścieżki `tmp_path`.

## Verification

```powershell
node --test apps/reviewer/test/grid-review-actions.test.mjs
npm run test --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
npm run reviewer:build
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_operational_image_reviews.py services/api/tests/test_image_grid_review_api.py -q
npm run python:lint
npm run python:typecheck
```

Uruchomione i zielone: `node --test` (9/9 w pliku, w tym 6 nowych),
`npm run test --workspace @game-predictor/reviewer` (199/199),
`npm run typecheck`/`lint --workspace @game-predictor/reviewer` (czyste),
`npm run reviewer:build` (sukces), pytest obu plików (31/32 zielone — 1
pre-existing, niezwiązany błąd, patrz TASK-0637 Outcome), `python:lint`
i `python:typecheck` czyste dla zmienionych plików.

## Risks / open questions

- Handlery `geometry-preview`/`geometry-revisions` nie dostały osobnego
  logu `review_item_id`/`game_id` na tym samym poziomie co `source-asset` —
  świadomie pominięte, by nie rozszerzać zakresu; błędy resolucji plików w
  tych ścieżkach nadal trafiają do loga przez `_resolve`.

## Outcome

### Changed

- [apps/reviewer/src/features/grid-reviews/grid-review-actions.ts](../../apps/reviewer/src/features/grid-reviews/grid-review-actions.ts):
  new `describeGridSourceAssetFailure`.
- [apps/reviewer/src/features/grid-reviews/grid-review-editor.tsx](../../apps/reviewer/src/features/grid-reviews/grid-review-editor.tsx):
  `image.onerror` now calls it; effect gained a `cancelled` guard.
- [apps/reviewer/test/grid-review-actions.test.mjs](../../apps/reviewer/test/grid-review-actions.test.mjs):
  6 new tests.
- [services/api/src/game_predictor_api/application/image_review_assets.py](../../services/api/src/game_predictor_api/application/image_review_assets.py):
  `LOGGER` + warning before each of the 4 `raise` branches in `_resolve`.
- [services/api/src/game_predictor_api/api/image_grid_reviews.py](../../services/api/src/game_predictor_api/api/image_grid_reviews.py):
  `LOGGER` + try/except around `get_image_grid_review_source_asset`.
- [services/api/tests/test_operational_image_reviews.py](../../services/api/tests/test_operational_image_reviews.py):
  new `test_asset_resolution_logs_missing_file_with_asset_kind_and_relative_path`.
- `ai_docs/process/CURRENT_STATE.md`: new entry.

### Verification results

- `node --test apps/reviewer/test/grid-review-actions.test.mjs`: 9/9.
- `npm run test --workspace @game-predictor/reviewer`: 199/199.
- `npm run typecheck --workspace @game-predictor/reviewer`: clean.
- `npm run lint --workspace @game-predictor/reviewer`: clean.
- `npm run reviewer:build`: succeeds.
- `pytest services/api/tests/test_operational_image_reviews.py services/api/tests/test_image_grid_review_api.py`:
  31/32 (1 pre-existing unrelated failure, same as documented in TASK-0637).
- `npm run python:lint` / `npm run python:typecheck`: clean for changed
  files.
- `npm run openapi:check` not re-run (no API contract touched in this
  task — no new/changed route, request or response schema).

### Not completed

- Did not add per-request logging to `geometry-preview`/`geometry-revisions`
  handlers beyond what `_resolve` already logs (see Risks).
- Live-server / real-browser verification deferred to T3 (TASK-0639).

### Documentation updates

- `ai_docs/process/CURRENT_STATE.md` — new entry, prepended.
- This task file moved to `ai_docs/tasks/completed/`.

### Recommended next task

- T3 / TASK-0639: live-data acceptance walkthrough in the Reviewer browser
  (read-only), per the plan's T3 section.
