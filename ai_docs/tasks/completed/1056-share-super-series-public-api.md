# TASK-1056 — Publiczne trasy serii supergry udostępnionej wyszukiwarki

## Status

`done`

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

Commit: v1.7.426 / `3f73d3d282a662faf3f358e07cd3e197c728ca14`.

### Changed

- `api/board_search_share_public.py`: cztery trasy
  `/board-search-shares/super-game-series/{state,next-undefined,{id}/boards,
  {id}/super-symbol}` za `_require_share_proxy`, `authenticate` i
  `_reject_game_parameter`, gra z sesji, `game_storage_scope`; zapis z aktorem
  `board_search_share_actor(session_id)`; trasa `approximate-win` bez
  `response_model_exclude` (udostępnienie zwraca `seriesId`); `symbols` z
  `superGameTriggerCount`.
- `schemas/board_search_shares.py`: `BoardSearchSharePublicSeriesResponse`,
  `…SeriesBoardResponse`, `…SeriesBoardsResponse`,
  `…UndefinedSeriesResponse` (bez `gameId`, `definedBy`, `generationId`,
  `reviewItemId`, `recognizedBoardId`, `importJobId`, `assetMode`); wynik
  `search` z `SuperGameMarkerResponse`; `superGameTriggerCount` w symbolu.
- `schemas/super_game_markers.py`: usunięte
  `to_super_game_public_marker_response`; nowe `PUBLIC_SEARCH_EXCLUDE` dla
  panelu zarządzania (`api/management_public_stakes.py`, trasa `search`),
  którego strażnik `public_payload` odrzuca klucz `seriesId` nawet pusty.
- `domain/board_search_shares.py`: `board_search_share_actor`,
  `BOARD_SEARCH_SHARE_ACTOR_PREFIX`; docstring bez „no write capability”.
  `storage/board_search_share_correction_repository.py` używa helpera.
- `api/router.py`, `main.py`: zależność serwisu serii przekazana do routera
  publicznego (fabryka `default_super_game_series_service_dependency`).
- OpenAPI i klient zregenerowane; `packages/admin-api-client/src/index.ts`
  eksportuje cztery nowe typy, `SuperGamePublicMarkerResponse` znika ze
  schematu (żadna trasa go nie serwuje).
- Testy: `test_board_search_share_public_api.py` (5 nowych testów serii,
  `SharedGamesSeriesRepository` dwóch gier, `superGameTriggerCount`,
  `definedby`/`generationid` w kluczach zabronionych zamiast `seriesid`);
  `test_board_search_super_game_api.py` (udostępnienie niesie `seriesId`,
  panel zarządzania go pomija, OpenAPI).

### Verification results

- `pytest services/api/tests/test_board_search_share_public_api.py
  services/api/tests/test_board_search_super_game_api.py
  services/api/tests/test_super_game_series_api.py`: 38 passed.
- `npm run openapi:generate` + `npm run openapi:check`: OK; testy
  `@game-predictor/admin-api-client`: 131 passed; typecheck admin, reviewer,
  board-search-ui, admin-api-client: OK.
- `npm run python:lint`: OK. `npm run python:typecheck`: 4 błędy wyłącznie w
  `scripts/run_m4_import_acceptance.py`, obecne także na bazowym commicie
  (sprawdzone przez `git stash`); brak błędów w zmienionych modułach.
- Pełny `pytest services/api/tests` nie mieści się w limicie 600 s jednego
  polecenia (po 10 min około 14 %); przerwany bieg zatrzymał się na
  `test_format_edited_file_hook.py`, który osobno przechodzi (34 passed;
  padł w czasie równoległych edycji plików przez hook formatera). Pełny bieg
  jest częścią odbioru planu (`npm run quality`).
- `npm run api:test` (`run_python_tests.ps1 -Suite Api`) zbiera 0 testów
  (znana usterka, `CURRENT_STATE.md`); użyto bezpośredniego `pytest`.

### Audit

- Raport: `ai_docs/quality/TASK-1056_AUDIT_codex.md` (Codex, medium,
  runda 1, werdykt REVISE). P1-1 (brak testów `game_id`/`rulesVersionId` dla
  czterech tras, symbolu uruchamiającego, zarchiwizowanego, gry `none` i
  aktora audytu) zamknięte: testy rozszerzone (cztery parametry na każdej
  trasie, trzy odmowy `SUPER_SYMBOL_NOT_ORDINARY`, nowy
  `test_a_game_without_a_super_game_has_no_series`, `actors` w repozytorium
  testowym). P2-1 (opis `seriesId` w OpenAPI) zamknięte: opis poprawiony,
  OpenAPI i klient zregenerowane. Poprawki nie zmieniają zachowania objętego
  P0/P1, więc bez drugiej rundy.

### Not completed

- Dokumentacja kontraktu i modelu zagrożeń: TASK-1060 (zgodnie z planem).

### Documentation updates

- Brak w tym tasku (TASK-1060). Mapa kodu z nowymi symbolami API wchodzi do
  commita TASK-1058 (zregenerowana raz dla obu tasków na tej gałęzi).

### Recommended next task

- TASK-1058 (równolegle) i TASK-1057 (allowlista proxy na nowym OpenAPI).
