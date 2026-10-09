# TASK-0935 — Oznaczenie supergry w wyszukiwaniu plansz

## Status

`done`

## Goal

Wyniki wyszukiwania plansz i wiersze przybliżonej wygranej pokazują złote
oznaczenie serii supergry (trigger, pozycja w serii, super symbol lub „do
zdefiniowania”) z linkiem do widoku serii w Adminie.

## Context

Operator chce widzieć wygrane supergry w wyszukiwaniu plansz i wchodzić z
nich w definicję super symbolu. Plan: etap S-B.

## Dependencies / entry conditions

- TASK-0933 (serie) i TASK-0934 (widok serii) zacommitowane.
- Fakt: `packages/board-search-ui` jest współdzielony przez Admin, Reviewer i
  publiczny panel zarządzania; projekcja wyników pochodzi z API wyszukiwania.

## Recommended execution

claude-sonnet-5-5 / high. Znacznik w projekcji API i współdzielonym UI,
trzech konsumentów. Eskalacja do claude-opus-5-5 / high przy zmianie
kontraktu publicznego panelu. Audyt: gpt-6.1-sol / high; do czasu CLI zamiennik claude-opus-5-5 / high.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`
- `ai_docs/requirements/ADMIN_APP.md` (wyszukiwanie plansz)
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- API: odpowiedź wyniku wyszukiwania i wiersza przybliżonej wygranej
  dostaje opcjonalne `superGame`: `{ kind: 'trigger' | 'in_series',
  seriesId, spinIndex, seriesLength, superSymbolCode | null,
  completeness, runVerification }`; brak pola = tryb bazowy **według
  obowiązującej generacji**. Niezależnie od pola per plansza odpowiedź
  wyszukiwania i przybliżonej wygranej niesie na poziomie odpowiedzi
  `superGameState: { fresh, inputVersion, generationInputVersion }`
  (TASK-0933); przy `fresh = false` UI pokazuje ostrzeżenie „serie w
  trakcie przeliczania” dla całego wyniku, także dla plansz bez `superGame`.
  Publiczny panel: te same pola, bez `seriesId`.
- UI (`board-search-ui`): złote wyróżnienie karty wyniku i wiersza; etykieta
  „Supergra: spin 3/10, symbol K” lub „Supergra: super symbol do
  zdefiniowania”; w Adminie link „Zdefiniuj super symbol” do TASK-0934;
  Reviewer i panel tylko etykieta.
- Testy: stan wyników, kontrakt renderu, request testy API.

## Out of scope

- Zmiana wypłat (TASK-0936); wartości nadal z aktualnego ewaluatora.

## Acceptance criteria

- [x] Plansza wyzwalająca i plansze serii mają oznaczenie w wynikach i w
      wierszach przybliżonej wygranej.
- [x] Link prowadzi do właściwej serii; w Reviewerze i panelu brak linku.
- [x] Gra `none` nie ma pola i oznaczeń; testy istniejące bez zmian.

## Technical notes

- Źródło: tabela `super_game_series`; dołączenie po `sequence_number` w
  zakresie serii; indeks na `(game_id, start_sequence_number)`.

## Expected files

- Istniejące: `services/api/src/game_predictor_api/domain/board_search.py`,
  `board_search_approximate_win.py`, schematy wyszukiwania,
  `packages/board-search-ui/src/board-search-results.tsx`,
  `board-search-approximate-win.tsx`, `board-search.css`, testy pakietu,
  `apps/reviewer` (proxy allowlist bez zmian, jeśli pole jest w istniejących
  odpowiedziach).

## Test cases

- Wynik na pozycji 105 w serii 101–120 → `in_series`, `spinIndex 5`.
- Pozycja 100 (trigger) → `trigger`.
- Seria bez symbolu → `superSymbolCode null`, etykieta „do zdefiniowania”.
- Nowy trigger przed uruchomieniem joba → brak `superGame` dla pozycji,
  `superGameState.fresh = false`, ostrzeżenie widoczne.

## Verification

```powershell
# katalog worktree, timeout 120 s każda
.\.venv\Scripts\python.exe -m pytest services/api/tests -k "board_search" -q
npm run test --workspace @game-predictor/board-search-ui
npm run test:interactions --workspace @game-predictor/board-search-ui
npm run test --workspace @game-predictor/reviewer
npm run openapi:check
```

## Risks / open questions

- Złoty kolor musi być czytelny obok istniejących wyróżnień jokera/wilda w
  modalu linii.

## Outcome

Wykonawca: claude-sonnet-5-5 (subagent sesji prowadzącej). Commit, audyt
krzyżowy i `CURRENT_STATE.md` wykonuje sesja prowadząca. Poprawki po audycie
Codex (runda 1: P0-1, P1-1, P2-1) naniesione w jednej rundzie. Bez migracji i bez uruchamiania serwerów.

### Changed

- Commit v1.7.278 / bf0dd8617b449da7109b4b438f46b6ea7433bb3c (zapis dodany po commicie przez leada).

- **Domena i port.** `domain/super_game_markers.py`: `SuperGameMarker`
  (`kind` `trigger|in_series`, `series_id`, `spin_index` = pozycja − trigger,
  `null` dla triggera, `series_length`, `super_symbol_code`, `completeness`,
  `run_verification`), czysta `marker_for_position` (seria obejmuje
  `trigger … trigger + length`) i `SuperGameMarkers` (stan + znaczniki
  pozycji). `application/super_game_markers.py`: port `SuperGameMarkerSource`.
- **Odczyt z jednego snapshotu.** `storage/super_game_marker_repository.py`:
  **jedno zapytanie** czyta rodzaj gry, stan wyprowadzania i dla każdej
  pozycji serię o największym triggerze `≤ pozycja` (sonda
  `uq_super_game_series_trigger`, `LATERAL`), z kodem super symbolu. Jedno
  zapytanie = jeden snapshot w każdym poziomie izolacji, więc znacznik nigdy
  nie łączy się ze świeżością innej generacji (publikacja generacji zmienia
  serie i stan w jednej transakcji). Bez migracji i bez nowego indeksu
  (unikalny indeks `(game_id, trigger_sequence_number)` z 0152 wystarcza,
  serie się nie nakładają). Poza PostgreSQL (SQLite w testach) zwraca stan
  świeży bez znaczników.
- **Serwisy.** `BoardSearchService(repo, super_game_markers=None)` +
  `search_with_super_game()` → `BoardSearchOutcome` (`search()` bez zmian);
  `BoardSearchApproximateWinService(repo, super_game_markers=None)` wypełnia
  `ApproximateWinCalculation.super_game` dla pozycji wierszy z wygraną (jedno
  wywołanie). Bez źródła: brak znaczników, `superGameState` `null` (kalkulacja)
  albo świeży `{0, null}` (wyszukiwanie).
- **Schematy i trasy.** `schemas/super_game_markers.py`:
  `SuperGamePublicMarkerResponse` (bez `seriesId`) i
  `SuperGameMarkerResponse` (+ `seriesId`, w kontrakcie opcjonalne, żeby
  znacznik publiczny był też poprawnym znacznikiem bez linku).
  `BoardSearchResultResponse.superGame`, `BoardSearchResponse.superGameState`,
  `ApproximateWinRowResponse.superGame`, `ApproximateWinResponse.superGameState`
  (wszystkie opcjonalne z domyślnym `null`; zawsze ustawione w odpowiedziach
  na żywo, `null` tylko w zamrożonej historii panelu i w potwierdzeniu
  wyszukiwania zapisanym przed zmianą). Publiczne wyszukiwanie ma osobne
  modele wyniku/odpowiedzi (`superGame` bez `seriesId`, `superGameState`);
  przybliżona wygrana udostępniania online i panelu zarządzania pomija
  `seriesId` przez `response_model_exclude` (`PUBLIC_APPROXIMATE_WIN_EXCLUDE`);
  `seriesid` dopisane do `_FORBIDDEN` strażnika `public_payload` panelu.
  `main.py` podłącza `SqlAlchemySuperGameMarkerRepository` do obu domyślnych
  serwisów; `SqlAlchemyManagementGameAdapter` używa go w wyszukiwaniu panelu
  i w żywym podglądzie przybliżonej wygranej (`apply_super_game_markers`).
- **Migawki panelu zarządzania.** `freeze_result` odrzuca `superGameState`
  przed skrótem treści: skróty i `expand_result` zamrożonych wyników bez zmian
  (znaczniki nie należą do `ROW_FIELDS`).
- **OpenAPI i klient.** `npm run openapi:generate` (po nim przywrócone
  `git checkout` 13 plików generowanych, tylko końce linii), nowe typy
  wyeksportowane z `packages/admin-api-client/src/index.ts`
  (`SuperGameMarkerKind`, `SuperGameMarkerResponse`,
  `SuperGamePublicMarkerResponse`). Trasy bez zmian, więc wrappery klienta bez
  zmian.
- **UI (`board-search-ui`).** `board-search-super-game.ts` (etykiety, notatki
  „Seria niepełna…”/„Trigger lub retrigger oparty na predykcji modelu.”,
  `superGameSeriesAdminHref`, `superGameMarkerLink`),
  `board-search-super-game-marker.tsx` (`SuperGameMarkerBadge`,
  `SuperGameStateBanner`). Złote wyróżnienie karty wyniku
  (`boardSearchResultsSuperGame`) i wiersza (`boardSearchSuperGameRow`),
  etykiety „Supergra: trigger”, „Supergra: spin 3/10, symbol K”, „Supergra:
  super symbol do zdefiniowania” (spin w osobnym `(spin 5/10)`), ostrzeżenie
  „Serie w trakcie przeliczania” dla całego wyniku wyszukiwania i całego
  zakresu przybliżonej wygranej przy `fresh = false`, także dla plansz bez
  znacznika. Link tylko przy możliwości źródła danych
  `BoardSearchDataSource.superGameSeriesHref` i znaczniku z `seriesId`: etykieta
  „Zdefiniuj super symbol” (seria bez symbolu) albo „Pokaż serię” (z
  symbolem), URL `?workspace=games&game=<gameId>&section=super-games&series=<seriesId>`,
  otwierany w nowej karcie (nie gubi szkicu wyszukiwania). Modal linii bez
  zmian (złoto tylko na kartach i wierszach, kolory pomarańczowy i żółty modalu
  nietknięte).
- **Admin.** `apps/admin/src/features/board-search/board-search-workspace.tsx`
  dokłada `superGameSeriesHref` do pamiętanego klienta; jedyne miejsce w
  Adminie i Reviewerze, które go deklaruje (pilnuje test).
- **Reviewer.** Adaptery publiczne przenoszą `superGame` i `superGameState`
  (bez `seriesId`); odpowiedź udostępnionego wyszukiwania ze `fresh = false`
  nie trafia do 5-minutowej pamięci podręcznej. Decyzja po audycie (P2-1):
  pamięć podręczna omija każdą odpowiedź wyszukiwania ze znacznikiem na
  dowolnym wyniku albo z `fresh = false` (nie jest z niej serwowana ani w niej
  zapisywana); odpowiedzi bez znaczników są nadal pamiętane 5 minut. Dzięki temu
  ponowne wyszukanie po zmianie super symbolu zwraca nowy znacznik. Allowlisty
  proxy bez zmian
  (zmiana tylko w ciele odpowiedzi GET).
- **Pusty wynik (audyt P0-1).** `BoardSearchResults` pokazuje ostrzeżenie
  „Serie w trakcie przeliczania” także dla `results: []`, obok komunikatu o
  braku dopasowań.
- **Testy.** `services/api/tests/test_board_search_super_game_api.py` (12
  testów: trigger, spin z `spinIndex`, symbol niezdefiniowany, nowy trigger
  przed jobem → brak znacznika i `fresh=false`, gra `none`, brak źródła,
  wiersze przybliżonej wygranej, publiczne udostępnianie i panel bez
  `seriesId`, trasa Admina z `seriesId`, skrót migawki, schemat OpenAPI),
  `integration/test_board_search_super_game_postgres.py` (5 testów na roli
  aplikacyjnej z RLS), rozszerzony `test_board_search_approximate_win_repository.py`,
  `test_board_search_share_public_api.py` (`seriesid` w zabronionych kluczach),
  testy jednostkowe i interakcyjne `board-search-ui`, test Admina
  `board-search-super-game-link.test.mjs` (link czytany przez
  `parseAdminNavigation`), testy Reviewera i klienta API; po audycie: test
  interakcyjny pustego wyniku z `fresh = false` i test źródła danych „ponowne
  wyszukanie po zmianie super symbolu zwraca nowy znacznik”.

### Verification results

Katalog worktree, `PYTHONPATH` na źródła worktree.

- `.\.venv\Scripts\python.exe -m pytest services/api/tests -k "board_search or super_game or management_stakes" -q`:
  281 passed, 48 skipped (testy PG bez zmiennej), 248,6 s.
- Dodatkowo `test_openapi_contract.py`, `test_management_sessions.py`,
  `test_api_entrypoint.py`: 47 passed (103 s).
- PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`, bazy `*_test`):
  `integration/test_super_game_series_postgres.py`,
  `test_board_search_approximate_win_repository.py`,
  `test_board_search_super_game_postgres.py` (przed dopisaniem 2 testów): 35
  passed (293 s); po dopisaniu: nowy plik + `test_board_search_approximate_win_repository.py`
  8 passed (79 s); `test_management_stakes_postgres.py`,
  `test_management_postgres.py`: 2 passed.
- `npm run openapi:generate` + `npm run openapi:check`: aktualne.
- `npm run test --workspace @game-predictor/board-search-ui`: 85 passed;
  `test:interactions`: 60 passed (w tym 9 nowych, po audycie).
- `npm run test --workspace @game-predictor/reviewer`: 240 passed (po audycie);
  `test:geometry` (Reviewer): 40 passed.
- `npm run test --workspace @game-predictor/admin`: 733 passed;
  `test:geometry` (Admin): 188 passed.
- `npm run test --workspace @game-predictor/admin-api-client`: 104 passed.
- `npm run typecheck` (wszystkie workspace + mypy 850 plików), `npm run lint`
  (0 błędów, 6 ostrzeżeń sprzed zadania), `npm run format:check`: zielone;
  `ruff check` i `ruff format --check` na zmienionych plikach czyste.

### Not completed

- Znacznik nie jest pokazany w oknie linii planszy (`BoardSearchBoardLinesModal`)
  ani w szczególe planszy API (poza zakresem; modal wchodzi z karty/wiersza,
  które mają znacznik).
- Brak testu PG na pełnym żywym podglądzie panelu zarządzania z serią
  (`ManagementStakeRepository.preview`): pokryte testem trasy z atrapą serwisu,
  adapterem na PG (`super_game_row_markers`) i testem skrótu migawki.
- Pamięć podręczna wyszukiwania Reviewera nadal może pokazać odpowiedź bez
  znaczników (i z `fresh = true`) do 5 minut po zmianie wejścia, które dopiero
  utworzy serię (korekta w udostępnieniu czyści pamięć).

### Documentation updates

- `ai_docs/architecture/API_CONTRACT.md`: podsekcja „Oznaczenie supergry w
  wynikach (TASK-0935, D-535)” i pola `superGame` / `superGameState` w
  odpowiedzi przybliżonej wygranej; `ai_docs/requirements/ADMIN_APP.md`:
  akapit „Oznaczenie supergry” w wymaganiu wyszukiwania plansz. Do
  uzupełnienia przez prowadzącego: `CURRENT_STATE.md`.

### Recommended next task

TASK-0936 (rozwinięcie super symbolu i koszt per pozycja); wiersze
przybliżonej wygranej mają już `superGame.superSymbolCode` i kompletność
serii, więc ewaluator serii może czytać te same źródła.
