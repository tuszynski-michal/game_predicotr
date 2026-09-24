---
title: TASK-0652 — Pion API „Przybliżonej wygranej” (repozytorium, serwis, endpoint, OpenAPI, klient)
status: done
---

# TASK-0652 — Pion API „Przybliżonej wygranej”

## Status

`done`

**Uwaga o numeracji:** czwarty task planu sesji `2026-09-24` „Przybliżona
wygrana” w „Wyszukaj plansze”. [TASK-0649](completed/0649-board-search-result-limit-input.md),
[TASK-0650](completed/0650-shared-payout-evaluator-worker.md) i
[TASK-0651](completed/0651-approximate-win-domain-calculator.md) ukończone.
Taski `0653`–`0654` jeszcze nie istnieją jako pliki.

## Goal

Spójny pion: repozytorium PostgreSQL → serwis aplikacyjny → endpoint HTTP →
OpenAPI → wygenerowany i opakowany klient TS dla
`GET /api/v1/admin/games/{gameId}/board-search/approximate-win`, łączący
TASK-0650 (`PreparedPayoutEvaluator`) i TASK-0651 (czysty kalkulator zakresu)
z realnymi danymi projekcji wyszukiwania plansz.

## Context

TASK-0651 dostarczył czysty kalkulator przyjmujący `evaluate` jako
wstrzykniętą zależność. Ten task podłącza prawdziwe źródło danych
(`image_board_search_fast_documents`/`legacy_board_search_archive_documents`,
to samo co wyszukiwanie plansz), prawdziwy `PreparedPayoutEvaluator` z
najnowszej opublikowanej wersji reguł oraz wystawia to jako endpoint HTTP
gotowy dla TASK-0653 (UI).

## Dependencies / entry conditions

TASK-0650 i TASK-0651 ukończone. Decyzje D1–D6 nadal jako założenia robocze
(patrz TASK-0651's Technical notes) — ten task je konkretyzuje w kontrakcie
API bez zmiany semantyki domenowej.

## Recommended execution

Sonnet 5, reasoning `high`, z dodatkowym review: Opus 5.5 `high` —
najbardziej ryzykowny task serii: routing `game_data_v2` (D-440), kontrakt
API/OpenAPI/klient, mapowanie błędów domenowych na kody HTTP, gwarancja
braku zapisów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/API_CONTRACT.md` (§„Wyszukiwanie plansz częściowym
  układem” — wzorzec sąsiedniego endpointu)
- `ai_docs/process/DECISION_LOG.md` D-440, D-442 (jawne `GameStorageRouter().bind()`
  jako defense-in-depth, nawet gdy ścieżka pasuje do middleware)

## Scope

- `services/api/src/game_predictor_api/storage/board_search_projection_repository.py`:
  wydzielony `_document_source(game_id)` (dawny inline blok w `search()`, bez
  zmiany zachowania) + nowa metoda `range_documents(game_id, first, last)` →
  `(BoardSearchAssetMode, tuple[ApproximateWinDocument, ...])`, jawny
  `GameStorageRouter().bind(..., READ)` (D-440, defense-in-depth — trasa i
  tak pasuje do middleware `/admin/games/{gameId}/...`).
- Nowy `services/api/src/game_predictor_api/storage/board_search_approximate_win_repository.py`:
  `SqlAlchemyBoardSearchApproximateWinRepository` — `game_sequence_length`,
  `latest_published_rules` (→ `RulesPayoutConfiguration` z TASK-0650, bez
  datasetu), deleguje `range_documents` do powyższego.
- `services/worker/src/game_predictor_worker/payouts/contracts.py` +
  `payouts/store.py`: dodane pole `version: int` do `RulesPayoutConfiguration`
  (potrzebne dla `rules.rulesVersion` w odpowiedzi; jedyne miejsce
  konstrukcji zaktualizowane, zero innych callsite'ów).
- Nowy `services/api/src/game_predictor_api/application/board_search_approximate_win.py`:
  `BoardSearchApproximateWinService.calculate(...)` — waliduje `spinCount`
  (≤ `APPROXIMATE_WIN_SPIN_COUNT_MAX = 10_000`), planuje pozycje (TASK-0651),
  ładuje regułę, buduje `PreparedPayoutEvaluator`, czyta zakres w 1 lub 2
  zapytaniach (zależnie od zawinięcia) + 1 zapytanie o status planszy
  startowej (D3), woła `calculate_approximate_win`, mapuje
  `DomainValidationError` na `BoardSearchError`.
- Nowy `services/api/src/game_predictor_api/schemas/board_search_approximate_win.py`:
  `ApproximateWinResponse` i pola zagnieżdżone (camelCase przez `ApiModel`).
- `services/api/src/game_predictor_api/api/board_search.py`,
  `api/router.py`, `main.py`: nowa trasa
  `GET /{game_id}/board-search/approximate-win` na tym samym routerze co
  istniejące wyszukiwanie, nowe kody błędów w `handle_board_search_error`.
- `npm run openapi:generate` (OpenAPI + wygenerowany klient TS).
- `packages/admin-api-client/src/index.ts`: wrapper
  `getBoardSearchApproximateWin(gameId, { startSequenceNumber, spinCount })`.

## Out of scope

- Podsekcja UI Admina (TASK-0653).
- Naprawa pre-existing czerwonego `test_payout_store.py` (zgłoszona osobno,
  chip `task_4008a087`, TASK-0650).
- Zmiana rankingu/kontraktu istniejącego `GET .../board-search`.
- Naprawienie pre-existing braku `prettier --check` w
  `packages/admin-api-client/src/index.ts`/`test/client.test.mjs`
  (potwierdzone jako sprzed tego taska — patrz Technical notes).

## Acceptance criteria

- [x] Kompletna plansza daje wynik identyczny z payout-v3 (parytet
      zweryfikowany end-to-end na realnym PostgreSQL, TASK-0650's core).
- [x] Brak opublikowanych reguł → `409 APPROXIMATE_WIN_RULES_NOT_PUBLISHED`.
- [x] Reguły o wymiarach innych niż 3×5 → `409 APPROXIMATE_WIN_RULES_INVALID`.
- [x] Nieprawidłowa konfiguracja reguł (np. niekompletna macierz) →
      `409 APPROXIMATE_WIN_RULES_INVALID` z kodem domenowym w komunikacie.
- [x] Symbol na planszy spoza aktywnych symboli reguł →
      `409 APPROXIMATE_WIN_BOARD_SYMBOL_OUTSIDE_RULES`, cała kalkulacja
      przerwana (fail-closed), nie tylko pominięta jedna plansza.
- [x] `startSequenceNumber` poza `1..sequenceLength` →
      `409 APPROXIMATE_WIN_START_OUT_OF_RANGE`.
- [x] `spinCount` poza `1..10000` → `422` (FastAPI `Query` + serwis).
- [x] Projekcja/archiwum nie `ready` → te same kody co istniejące
      wyszukiwanie (`409 BOARD_SEARCH_PROJECTION_INCOMPLETE`/
      `BOARD_SEARCH_ARCHIVE_INCOMPLETE`), bez duplikowania logiki.
- [x] Zakres zawijający się przez koniec sekwencji czyta dokładnie 2 zakresy
      (przed i po granicy), nie N pojedynczych zapytań.
- [x] `startBoardStatus` odzwierciedla status planszy `S` (lub `null`, gdy
      brak dokumentu), niezależnie od tego, że `S` nie wchodzi do zakresu.
- [x] Cała kalkulacja jest czysto do odczytu — potwierdzone integracyjnie
      (liczba wierszy `recognized_boards`/`image_review_items`/
      `image_board_search_candidates`/`image_board_search_fast_documents`
      identyczna przed i po wywołaniu serwisu w osobnej transakcji).
- [x] `openapi:check` i wygenerowany klient TS spójne; nowy wrapper
      `getBoardSearchApproximateWin` przetestowany.
- [x] `mypy --strict`, `ruff check`/`format` czyste dla zmienionych plików
      (zero nowych błędów względem baseline 69/13 sprzed taska).

## Technical notes

**Dlaczego repozytorium dodaje jawny `GameStorageRouter().bind()`, mimo że
trasa i tak pasuje do middleware:** `/admin/games/{gameId}/board-search/approximate-win`
zawiera segment `games/<uuid>/`, więc `bind_game_storage_request` w
`main.py` już ustawia `game_storage_scope`, a `do_orm_execute`/`before_flush`
w `storage/database.py` automatycznie wołają `GameStorageRouter().bind()`
przed każdym zapytaniem ORM. Dodatkowe jawne wywołanie w
`range_documents` jest więc redundantne dla TEGO endpointu, ale
idempotentne (`bind()` z tym samym `game_id` w tej samej transakcji zwraca
istniejące bindowanie) i chroni metodę, gdyby kiedyś była wywołana z innej
ścieżki (D-440: dokładnie ten brak złamał `board-import-coverage`, którego
trasa nie pasowała do wzorca).

**Dlaczego `GameConfig.code`/`.name` nie mogą być puste:**
`validate_game_config` (worker) wymaga niepustych `code`/`name`;
`prepare_payout_evaluator` woła ją przez `validate_paylines`. Serwis używa
stabilnego placeholdera `f"approximate-win-{game_id}"` — pole nigdy nie
trafia do odpowiedzi ani logiki payoutu, tylko przez walidację. (Ten błąd
został złapany przez własne testy API tego taska — wszystkie scenariusze,
w tym happy path, początkowo failowały z `APPROXIMATE_WIN_RULES_INVALID`,
zanim naprawiono.)

**Dlaczego zakres zawijający czyta dokładnie 2 zapytania, nie N:**
`plan_approximate_win_positions` (TASK-0651) już definiuje zawinięcie jako
`(S+1..L)` i `(1..S+N-L)` — dwa rozłączne, ciągłe podzakresy. Serwis liczy
tę samą arytmetykę (`unwrapped_end = S + evaluated_spin_count`) bez
generowania pełnej listy pozycji, i woła `repository.range_documents` raz
lub dwa razy w zależności od `unwrapped_end <= sequence_length`.

**Dlaczego `RulesPayoutConfiguration` zyskało `version: int` (rozszerzenie
kontraktu TASK-0650):** odpowiedź API wymaga `rules.rulesVersion` (numer
wersji), którego `RulesPayoutConfiguration` wcześniej nie niosło. Jedyne
miejsce konstrukcji (`load_rules_payout_configuration`) zaktualizowane;
zero innych callsite'ów (zweryfikowane grepem), zero regresji w testach
payout (`test_payout.py`/`test_payout_batch.py`/`test_payout_readiness.py`
60/60 bez zmian).

**Znaleziony, nienaprawiony pre-existing problem:** `prettier --check`
failuje na `packages/admin-api-client/src/index.ts` i
`test/client.test.mjs` **niezależnie od tego taska** — potwierdzone przez
uruchomienie `prettier --check` na wersji tych plików z `git show HEAD`
(commitowanej przed tym taskiem). Nie naprawiono (masowe przeformatowanie
ogromnego, częściowo generowanego pliku wykracza poza zakres i ryzykowałoby
nieczytelny diff). `ruff format`/`ruff check` dla Pythona są czyste.

## Expected files

- Istniejące: `storage/board_search_projection_repository.py`,
  `api/board_search.py`, `api/router.py`, `main.py`,
  `payouts/contracts.py`, `payouts/store.py`,
  `packages/admin-api-client/src/index.ts`.
- Nowe: `storage/board_search_approximate_win_repository.py`,
  `application/board_search_approximate_win.py`,
  `schemas/board_search_approximate_win.py`,
  `services/api/tests/test_board_search_approximate_win_api.py`,
  `services/api/tests/integration/test_board_search_approximate_win_repository.py`.

## Test cases

- API (fałszywe repozytorium, `test_board_search_approximate_win_api.py`,
  10 testów): podsumowanie/kompletność/wiersze dla mieszanego zakresu;
  status planszy startowej `pending`; zawinięcie przez koniec sekwencji z
  dokładnie 2 wywołaniami zakresowymi; brak/nieprawidłowe parametry (422);
  `startSequenceNumber` poza zakresem (409); brak opublikowanych reguł
  (409); niezgodne wymiary planszy (409); nieznany symbol (409);
  niegotowa projekcja (409, reużyty kod istniejącego wyszukiwania); pusty
  zakres bez żadnej wypłaty.
- Integracyjny PostgreSQL (`test_board_search_approximate_win_repository.py`,
  1 test, gra routowana do `game_data_v2`): plansza kompletna → payout
  dokładny (parytet z payout-v3); plansza częściowa → potwierdzone minimum;
  brakująca pozycja; kompletność/podsumowanie/wiersze/narastające sumy
  zgodne z ręcznym wyliczeniem; **brak zapisów** (liczniki wierszy
  identyczne przed/po w osobnej transakcji).
- Klient TS (`packages/admin-api-client/test/client.test.mjs`): nowy test
  potwierdzający `gameId` w ścieżce i `startSequenceNumber`/`spinCount` w
  query string.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/ services/worker/tests/ -k "board_search or payout" -q
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/ services/worker/tests/ -k "board_search or payout" -q
npm run python:lint
npm run python:typecheck
npm run openapi:generate
npm run openapi:check
npm run typecheck --workspace @game-predictor/admin-api-client
npm run test --workspace @game-predictor/admin-api-client
```

Timeout: 120 s na komendę (PostgreSQL run ~60 s, w granicach limitu).

## Risks / open questions

- Założenia D1–D6 z TASK-0651 pozostają robocze do jawnej akceptacji
  użytkownika. Konkretyzacja w tym tasku (kody błędów, limity, pola
  odpowiedzi) jest zgodna z nimi, ale zmiana którejkolwiek decyzji
  wymagałaby korekty kontraktu API przed TASK-0653.
- Limit `APPROXIMATE_WIN_SPIN_COUNT_MAX = 10 000` jest oszacowaniem bez
  pomiaru realnego czasu odpowiedzi (D5 z planu) — do weryfikacji przy
  odbiorze na żywych danych (TASK-0654) i ewentualnej korekty.

## Outcome

### Changed

- [storage/board_search_projection_repository.py](../../services/api/src/game_predictor_api/storage/board_search_projection_repository.py):
  `_document_source` wydzielony z `search()` (zero zmiany zachowania —
  34/34 istniejących testów board-search bez zmian), nowa `range_documents`.
- [storage/board_search_approximate_win_repository.py](../../services/api/src/game_predictor_api/storage/board_search_approximate_win_repository.py)
  (nowy).
- [application/board_search_approximate_win.py](../../services/api/src/game_predictor_api/application/board_search_approximate_win.py)
  (nowy): `BoardSearchApproximateWinService`, `ApproximateWinCalculation`.
- [schemas/board_search_approximate_win.py](../../services/api/src/game_predictor_api/schemas/board_search_approximate_win.py)
  (nowy).
- [api/board_search.py](../../services/api/src/game_predictor_api/api/board_search.py),
  [api/router.py](../../services/api/src/game_predictor_api/api/router.py),
  [main.py](../../services/api/src/game_predictor_api/main.py): nowa trasa,
  nowa zależność serwisu, nowe kody błędów w `handle_board_search_error`.
- [payouts/contracts.py](../../services/worker/src/game_predictor_worker/payouts/contracts.py),
  [payouts/store.py](../../services/worker/src/game_predictor_worker/payouts/store.py):
  `RulesPayoutConfiguration.version`.
- `packages/admin-api-client/openapi/openapi.json`,
  `packages/admin-api-client/src/generated/*` (wygenerowane),
  `packages/admin-api-client/src/index.ts`: nowy wrapper i typy.
- Testy: 10 nowych w `test_board_search_approximate_win_api.py`, 1 nowy
  integracyjny w `integration/test_board_search_approximate_win_repository.py`,
  1 nowy w `packages/admin-api-client/test/client.test.mjs`.

### Verification results

```
.venv\Scripts\python.exe -m pytest services/api/tests/ services/worker/tests/ -k "board_search or payout" -q
  → 169 passed, 3 skipped (Postgres-gated, run separately)

GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 .venv\Scripts\python.exe -m pytest services/api/tests/ services/worker/tests/ -k "board_search or payout" -q
  → 171 passed, 1 failed (test_payout_store.py — pre-existing, sprzed TASK-0650,
    zgłoszone osobno, chip task_4008a087; NIE dotyczy tego taska)

npm run python:lint   → 1 pre-existing błąd w nietkniętym
  test_page_geometry_preflight.py (potwierdzone niezmienione od TASK-0650)
npm run python:typecheck → 69 błędów w 13 nietkniętych plikach (identyczny
  baseline jak przed tym taskiem; zero nowych błędów w zmienionych plikach)
npm run openapi:generate → sukces, wygenerowano getBoardSearchApproximateWin
npm run openapi:check    → "Generated Admin API client is current."
npm run typecheck --workspace @game-predictor/admin-api-client → czysty
npm run test --workspace @game-predictor/admin-api-client → 62/62 (1 nowy)
```

### Not completed

- Nic w zakresie tego taska. Prettier na `packages/admin-api-client/src/index.ts`/
  `test/client.test.mjs` pozostaje czerwony — potwierdzone jako pre-existing
  (patrz Technical notes), poza zakresem.

### Documentation updates

- Brak zmian w `ai_docs/architecture/API_CONTRACT.md`/`ALGORITHMS.md` w tym
  tasku — zaplanowane w TASK-0654 razem z odbiorem, żeby udokumentować
  finalny, użyty w produkcji kontrakt (a nie roboczy stan D1–D6).

### Recommended next task

- TASK-0653 — podsekcja UI Admina „Przybliżona wygrana”: rozwijana sekcja,
  debounce/zatwierdzanie inputu zakresu, ignorowanie spóźnionych
  odpowiedzi, stany ładowania/błędu, tabela wyników z stronicowaniem
  klienckim.
