# TASK-1056 — Publiczne trasy serii supergry udostępnionej wyszukiwarki

## Status

`in_progress`

## Goal

Cztery trasy `/api/v1/board-search-shares/super-game-series/...` z grą z
sesji, `seriesId` w markerach publicznych udostępnienia i
`superGameTriggerCount` w symbolach publicznych; eksport OpenAPI, wygenerowany
klient, testy żądań.

## Context

Plan `ai_docs/delivery/SHARE_SUPER_GAME_SERIES_EXECUTION_PLAN_20261018.md`,
sekcje 3–4 (decyzje A–D). Odbiorca linku ma definiować super symbol serii
(D-564, TASK-1060) i przeglądać plansze serii; publiczny marker celowo nie
miał `seriesId`, a trasy serii były tylko pod `/admin`.

## Dependencies / entry conditions

- Fakt: `SuperGameSeriesService` (`application/super_game_series.py`)
  filtruje `boards` i `set_super_symbol` po grze (`get_series(game_id,
  series_id)` → 404 `SUPER_GAME_SERIES_NOT_FOUND`); handler
  `SuperGameSeriesError` w `main.py` jest globalny.
- Fakt: korekty odbiorcy mają aktora `board-search-share:<sessionId>`
  (`storage/board_search_share_correction_repository.py`).
- Fakt: `listSuperGameSeriesBoards` Admina zwraca `reviewItemId`,
  `recognizedBoardId`, `importJobId` — klucze zabronione przez filtr proxy;
  trasa publiczna potrzebuje własnych modeli.

## Recommended execution

`claude-fable-5-1` / `high` (warunkowo, według tabeli planu). Eskalacja:
niejasność w transakcjach serwisu lub w fabrykach zależności `main.py`.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- plan: `ai_docs/delivery/SHARE_SUPER_GAME_SERIES_EXECUTION_PLAN_20261018.md`
- `ai_docs/architecture/API_CONTRACT.md`, „Publiczna powierzchnia
  udostępniania”, „Serie supergry”
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`, „Udostępniona
  wyszukiwarka plansz”
- D-535, D-536, D-537, D-548 (panel) w `ai_docs/process/decisions/DECISION_LOG_2026.md`

## Scope

```text
GET /api/v1/board-search-shares/super-game-series/state
GET /api/v1/board-search-shares/super-game-series/next-undefined?afterTrigger={1..999999999}
GET /api/v1/board-search-shares/super-game-series/{seriesId}/boards
PUT /api/v1/board-search-shares/super-game-series/{seriesId}/super-symbol   { symbolId | null, expectedRevision }
```

- Modele publiczne bez identyfikatorów wewnętrznych.
- `search` i `approximate-win` udostępnienia zwracają `superGame.seriesId`;
  `symbols` zwraca `superGameTriggerCount`.
- Aktor zapisu `board-search-share:<sessionId>` (helper w domenie, użyty też
  w repozytorium korekt).
- Eksport OpenAPI, regeneracja klienta, eksport nowych typów.

## Out of scope

- Lista serii z filtrami, `derive`, wpis dziennika zapytań, zmiany tras
  Admina i panelu zarządzania, migracje, proxy Reviewera (TASK-1057).

## Acceptance criteria

- [ ] Każda trasa wymaga nagłówka proxy i cookie, odrzuca
      `gameId`/`game_id`/`rulesVersionId`, czyta grę tylko z `context.game_id`.
- [ ] Seria innej gry (i gra `none`) → 404 `SUPER_GAME_SERIES_NOT_FOUND`;
      stary `expectedRevision` → 409 bez zapisu; Wild/uruchamiający/
      zarchiwizowany → 422 `SUPER_SYMBOL_NOT_ORDINARY`; symbol spoza gry →
      422 `SUPER_SYMBOL_NOT_FOUND`.
- [ ] Zapis ustawia `defined_by = "board-search-share:<sessionId>"` i wpis
      audytu z tym aktorem; `definedBy` nie jest zwracane publicznie.
- [ ] Odpowiedzi publiczne bez `reviewItemId`, `recognizedBoardId`,
      `importJobId`, `assetMode`, `gameId`, `definedBy`, `generationId`.
- [ ] `search` i `approximate-win` udostępnienia niosą `seriesId`; panel
      zarządzania nadal bez.
- [ ] `BoardSearchSharePublicSymbolResponse.superGameTriggerCount` obecne.
- [ ] `npm run openapi:generate` + `npm run openapi:check` zielone; nowe typy
      eksportowane z `@game-predictor/admin-api-client`.

## Technical notes

- `schemas/board_search_shares.py`: `BoardSearchSharePublicSeriesResponse`
  (`id`, `triggerSequenceNumber`, `startSequenceNumber`, `endSequenceNumber`,
  `length`, `retriggerSequenceNumbers`, `completeness`, `runVerification`,
  `superSymbolId`, `definedAt`, `revision`, `updatedAt`),
  `BoardSearchSharePublicSeriesBoardResponse` (`sequenceNumber`, `role`,
  `spinIndex`, `missing`, `status`, `boardChecksumSha256`),
  `BoardSearchSharePublicSeriesBoardsResponse { series, boards,
  superGameState }`, `BoardSearchSharePublicUndefinedSeriesResponse { items
  (≤ 2), superGameState }`. Request: istniejący `SuperSymbolUpdate`.
- `BoardSearchSharePublicSearchResultResponse.super_game:
  SuperGameMarkerResponse | None`; w `board_search_share_public.py` usunąć
  `response_model_exclude` dla `approximate-win`.
- Router: parametr `super_game_series_service_dependency` w
  `create_board_search_share_public_router` → `create_api_router` →
  `main.py` (fabryka `default_super_game_series_service_dependency`).
  Trasy statyczne przed parametrycznymi. Limiter
  `BoardSearchShareRequestKind.JSON`, bez `logged(...)`.
- `next-undefined`: `service.list(game_id, SuperGameSeriesFilter(defined=False),
  cursor=str(after_trigger) | None, limit=2)`.

## Expected files

- Istniejące: `services/api/src/game_predictor_api/api/board_search_share_public.py`,
  `schemas/board_search_shares.py`, `schemas/super_game_markers.py`
  (docstring), `api/router.py`, `main.py`, `domain/board_search_shares.py`,
  `storage/board_search_share_correction_repository.py`,
  `services/api/tests/test_board_search_share_public_api.py`,
  `packages/admin-api-client/src/index.ts`, `openapi/openapi.json`,
  `src/generated/*`.
- Nowe (proponowane): `services/api/tests/support_super_game_series.py`
  (`MemorySeriesRepository` wyniesione z `test_super_game_series_api.py`).

## Test cases

- 403 bez nagłówka proxy, 401 bez cookie, 422 z `?gameId=` dla 4 tras.
- `boards`: 200 bez kluczy wewnętrznych; 404 obca seria; brak wpisu dziennika.
- `super-symbol`: 200 → `revision+1`, `defined_by == board-search-share:<id>`;
  409 stara rewizja bez zmiany; 422 Wild; 404 obca seria.
- `next-undefined` z/bez `afterTrigger`; `afterTrigger=0` → 422.
- `state` → `{fresh, inputVersion, generationInputVersion}`.
- `search`/`approximate-win` z `superGame.seriesId`; `symbols` z
  `superGameTriggerCount`.
- Regresja `test_super_game_series_api.py` (aktor Admina `local-admin`).

## Verification

```powershell
# D:\game_predicotr, timeout 120 s
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_search_share_public_api.py services/api/tests/test_super_game_series_api.py -q
npm run openapi:generate
npm run openapi:check
npm run python:lint
npm run python:typecheck
```

## Risks / open questions

- Wyniesienie `MemorySeriesRepository` do modułu wsparcia: zachować import w
  `test_super_game_series_api.py`.

## Outcome

Wypełnia agent po pracy.
