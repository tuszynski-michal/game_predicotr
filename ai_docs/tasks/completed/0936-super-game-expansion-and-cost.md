# TASK-0936 — Rozwinięcie super symbolu i koszt per pozycja w prognozie Adminu

## Status

`done`

## Goal

Plansze w serii supergry są liczone według rodzaju `wild_super_spins`
(rozwinięcie super symbolu na kolumny, koszt spinu 0), a przybliżona wygrana
i stawki panelu sumują koszt per pozycja; gry bez supergry dają wyniki
identyczne jak dotąd.

## Context

Plan: etap S-C, sekcja „Wypłata planszy w serii”. Reguły operatora:
rozwinięcie przykrywa symbole, liczy kolumny (niesąsiednie), próg =
minimum symbolu, wypłata × liczba linii, koszt 0, brakująca plansza = pusta.

## Dependencies / entry conditions

- TASK-0932 (ewaluator v4) i TASK-0933 (serie) zacommitowane.
- Założenie Z-1: wypłaty za sztuki w kredytach bezwzględnych.

## Recommended execution

claude-opus-5-5 / high (subagent z tej sesji; wykonanie zamiast Codex na
decyzję operatora 2026-10-08). Logika rozwinięcia, koszt per pozycja, trzech
konsumentów, regresja 777, dokumenty domenowe. Eskalacja do claude-fable-5-1
/ high przy niezgodności z obserwowanymi wygranymi na pierwszej serii.
Audyt: gpt-6-astra / high; do czasu CLI zamiennik claude-fable-5-1 / high.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`
- `ai_docs/requirements/ALGORITHMS.md` (§B, §D)
- `ai_docs/requirements/MANAGEMENT_PANEL.md` (stawki)
- `ai_docs/process/DECISION_LOG.md` (wpis dla tego planu)

## Scope

- `super_games/wild_super_spins.py`: `evaluate_series_board(board,
  super_symbol, rules)` według kroków 1–4 planu (przekształcenie planszy
  tylko przy `k ≥ minimum(X)`); wynik z osobnymi składowymi: linie, sztuki,
  rozwinięcie, oraz `payout_kind` według reguły: w trybie `super`
  `provisional`, gdy `super_symbol` jest `null`, gdy
  `superGameState.fresh = false`, albo gdy plansza ma **jakąkolwiek**
  nieznaną komórkę. Uzasadnienie: nieznana komórka poza kolumnami X może
  dodać kolumnę, przekroczyć próg i przykryć wcześniejszą wygraną; nieznana
  komórka wewnątrz kolumny już przykrytej nie zmienia linii po rozwinięciu,
  ale nadal może zmienić wypłatę za sztuki i retrigger (sztuki liczone na
  planszy oryginalnej), więc żadna składowa nie jest bezpieczna. `exact`
  tylko dla planszy w pełni znanej; `confirmed_minimum` w trybie `super`
  nie występuje.
- Projekcja per pozycja (`mode`, `super_symbol_id`, `remaining_spins`,
  `spin_cost_credits`, `payout_credits`, `payout_kind`) budowana z serii
  i kanonicznych plansz; przybliżona wygrana §D i kalkulator stawek panelu
  sumują koszt per pozycja; podsumowanie pokazuje osobno sumę wyników
  prowizorycznych i liczbę takich pozycji.
- Modal linii: dla planszy w serii pokazuje planszę rozwiniętą i wiersz
  „Rozwinięcie K ×3 kolumny → 10 × 5 linii = 50”.
- Golden cases (Python + TS): K w kolumnach 2,4,5; K w 2,4 (brak); przykrycie
  usuwa wygraną symbolu pod spodem; zastąpienie wygranych liniowych X;
  retrigger w serii; `k < minimum(X)` bez przekształcenia planszy; seria bez
  symbolu = wynik prowizoryczny; nieznana komórka poza kolumnami X przy
  `k = minimum − 1` → `provisional`, a po uzupełnieniu jej jako X wynik
  zmienia się przez przykrycie (test przekroczenia progu); dwie znane Mumie
  i nieznana komórka w kolumnie przykrytej przez K → `provisional`, a po
  uzupełnieniu jej jako Mumii dochodzi wypłata za trzy sztuki i retrigger
  przy niezmienionych liniach (test składowej sztuk); plansza w pełni znana
  → `exact`; `superGameState.fresh = false` → `provisional`.
- `ALGORITHMS.md` §B/§D i `MANAGEMENT_PANEL.md`: opis trybu; wpis
  `DECISION_LOG.md` (następny wolny numer).

## Out of scope

- Aplikacja mobilna i snapshot. Inne rodzaje supergry.

## Acceptance criteria

- [x] Golden cases z zakresu przechodzą w Pythonie i TS z identycznymi wynikami.
- [x] Dla 777 wyniki przybliżonej wygranej i stawek panelu są bajt w bajt
      identyczne z wynikami przed zmianą (test porównawczy na fixture).
- [x] Seria bez super symbolu: wynik `provisional` liczony osobno w
      podsumowaniu; test pokazuje, że po definicji wynik może wzrosnąć i może
      zmaleć (przykrycie), więc nie jest prezentowany jako minimum.
- [x] Koszt serii = 0 w podsumowaniu; pozycja wyzwalająca ma koszt normalny.

## Technical notes

- `k` liczone na planszy oryginalnej; przekształcenie tylko przy
  `k ≥ minimum(X)`; linie na planszy rozwiniętej, sztuki Mumii na
  oryginalnej.
- Wygrane liniowe X są zastępowane rozwinięciem, gdy `k ≥ minimum(X)`.

## Expected files

- Nowe: `services/worker/src/game_predictor_worker/domain/super_games/wild_super_spins.py`
  (rozszerzenie z TASK-0931), `domain/sequence_mode_projection.py` (proponowany).
- Istniejące: `services/api/src/game_predictor_api/domain/board_search_approximate_win.py`,
  `application/board_search_approximate_win.py`, `domain/management_stakes.py`,
  `packages/shared-ts/src/validation.ts`, `packages/domain-fixtures/payout-golden-cases.json`,
  `packages/board-search-ui/src/board-search-board-lines-modal.tsx`,
  `ai_docs/requirements/ALGORITHMS.md`, `ai_docs/process/DECISION_LOG.md`.

## Test cases

- Jak w kryteriach; dodatkowo: X = symbol z minimum 2 (Sarkofag) w jednej
  kolumnie → brak rozwinięcia; w dwóch → rozwinięcie × 5.

## Verification

```powershell
# katalog worktree, timeout 120 s każda
.\.venv\Scripts\python.exe -m pytest services/worker/tests -k "payout or super_game" -q
.\.venv\Scripts\python.exe -m pytest services/api/tests -k "approximate_win or management_stakes" -q
npm run test --workspace @game-predictor/shared-ts
npm run test --workspace @game-predictor/board-search-ui
npm run quality
```

## Risks / open questions

- Reguła „× liczba linii” jest deklaracją operatora; pierwsza seria z pełnymi
  zdjęciami i znanymi wygranymi ją zweryfikuje. Rozbieżność → korekta
  rodzaju w kodzie, nie w danych.

## Outcome

Wykonawca: claude-opus-5-5 / high (subagent sesji prowadzącej) w worktree
`worktrees/mumie-super-game` (gałąź `feat/mumie-super-game-plan`, start na
v1.7.279 = `7062cdc3`). Commit, audyt krzyżowy, `CURRENT_STATE.md` i
przeniesienie taska wykonuje sesja prowadząca. Bez migracji, bez
uruchamiania serwerów i bez zmian danych.

### Changed

- Commit v1.7.280 / 8629be40e01d49a230ec703d27b89057d37d6d73 (zapis dodany po commicie przez leada).

- **Ocena planszy serii (worker).**
  `services/worker/src/game_predictor_worker/domain/super_games/wild_super_spins.py`:
  `evaluate_series_board(cells, super_symbol_mobile_code, evaluator, *,
  generation_fresh=True)` według czterech kroków planu: `k` = kolumny planszy
  oryginalnej z `X`; przy `k < minimum(X)` ocena jak w trybie bazowym; przy
  `k ≥ minimum(X)` plansza rozwinięta (kolumny w całości `X`, przykrywa też
  Wildy), linie na planszy rozwiniętej z usunięciem wygranych liniowych `X`,
  sztuki na planszy oryginalnej, rozwinięcie `payout_line(X, k) × liczba
  linii`. Minimum `X` = najmniejsza długość reguły `X` (zwalidowana macierz
  ma komplet długości od minimum do liczby kolumn). Wynik
  `SeriesBoardEvaluation` (`evaluated_cells`, `matches`, `count_matches`,
  `expansion`, `total_payout`, `payout_kind`, `retrigger`); `exact` tylko dla
  planszy w pełni znanej ze zdefiniowanym symbolem i świeżą generacją, inaczej
  `provisional`. Super symbol, który w liczonych regułach nie jest zwykłym
  symbolem liniowym, jest traktowany jak niezdefiniowany. Typy wyniku i
  protokół `SeriesBoardEvaluator` w `definition.py`;
  `SuperGameKindDefinition.evaluate_series_board` (rejestr: `wild_super_spins`
  ma ocenę, `none` nie).
- **Lustro TS.** `packages/shared-ts/src/super-game.ts` (`evaluateSeriesBoard`,
  `WILD_SUPER_SPINS_CODE`, typy), eksport w `src/index.ts`; test
  `test/super-game.test.mjs`.
- **Złote przypadki.** `packages/domain-fixtures/payout-golden-cases.json`,
  nowa sekcja `wildSuperSpinsScenario` (gra jak Mumie, 5 linii, K/10/J/Q/A
  minimum 3, Sarkofag minimum 2, Mumia = Wild + trigger 3) z 16 przypadkami:
  przykład planu (K w kolumnach 2,4,5 → 50), K w 2,4 bez przekształcenia,
  przykrycie usuwającej wygraną A, zastąpienie wygranych liniowych K (80 → 50),
  retrigger w serii (4 Mumie → 200 + 50), brak symbolu → `provisional`
  (wynik może wzrosnąć 15 → 50 i zmaleć 65 → 25), nieznana komórka poza
  kolumnami X przy `k = minimum − 1` (15 `provisional` → 50 `exact` po
  uzupełnieniu jako K), dwie Mumie i nieznana komórka w kolumnie przykrytej
  (50 `provisional` → 70 `exact` z retriggerem przy niezmienionych liniach),
  nieaktualna generacja → `provisional`, Sarkofag w jednej kolumnie (0) i w
  dwóch (25), wygrana innego symbolu na planszy rozwiniętej zostaje (55).
  Python: `services/worker/tests/test_super_game_payout.py`.
- **Projekcja per pozycja (API).** Nowy
  `services/api/src/game_predictor_api/domain/sequence_mode_projection.py`
  (`SequenceMode`, `PositionMode` z `mode`, `super_symbol_code`,
  `remaining_spins`, `spin_cost_credits`, `generation_fresh`;
  `SequenceModeProjection.at`). Budowana z jednego odczytu znaczników
  TASK-0935: `BoardSearchApproximateWinService` czyta znaczniki raz dla
  wszystkich pozycji zakresu (projekcja, znaczniki wierszy i `superGameState`
  z jednego snapshotu). `SuperGameMarkers.kind_code` (rodzaj gry z tego samego
  zapytania). Zapytanie znaczników jest teraz tekstowym SELECT-em
  (`text(...).columns(...)`), więc router magazynu gry wiąże je z intencją
  odczytu (wcześniej jako zapis z `FOR SHARE`, co padało w migawce tylko do
  odczytu zapisu stawki).
- **Domena §D.** `calculate_approximate_win(..., modes, evaluate_super)`:
  koszt sumowany per pozycja (darmowy spin w serii, także brakująca plansza
  w serii), wypłaty `provisional` poza rozpoznanymi wypłatami, narastającymi
  sumami i bilansem, podsumowanie z `provisional_count` (wszystkie ocenione
  plansze serii z wynikiem prowizorycznym, także z wypłatą 0) i
  `provisional_payout_credits`; wiersze z `mode` i `spin_cost_credits`;
  odcisk danych rozszerzany tylko dla pozycji serii; wynik niesie
  `super_spin_ranges` i `super_spin_cost`. Aplikacja:
  `evaluate_position_series_board`, `count_matches_with_codes`.
- **Szczegóły planszy (modal).** `BoardSearchBoardDetailService(repo,
  super_game_markers=None)`: plansza serii ma `mode = super`,
  `spinCostCredits = 0`, linie z planszy rozwiniętej, `expandedSymbolCodes`,
  `expansion` (`symbolCode`, `columns`, `columnCount`, `linePayoutCredits`,
  `paylineCount`, `payoutCredits`), `countMatches` z planszy oryginalnej,
  `payoutKind` `provisional` (także przy 0) albo `exact`/`none`. `main.py` i
  adapter panelu podłączają źródło znaczników.
- **Panel zarządzania.** `SqlAlchemyManagementGameAdapter._snapshot` liczy z
  projekcją w tej samej migawce `REPEATABLE READ` tylko do odczytu; nowa
  metoda `preview` zwraca bieżącą kalkulację (ze znacznikami, `mode`,
  `spinCostCredits`, `countMatches`), którą zapis by zamroził;
  `super_game_row_markers` usunięte. `management_result_snapshots.py`:
  format 1 z opcjonalnymi polami podsumowania `superSpinRanges`/`superSpinCost`
  (od rundy poprawek) i niezerowymi polami prowizorycznymi (pomijane, gdy puste, więc
  777 bez zmian); `expand_result` odtwarza `mode`/`spinCostCredits` wierszy z
  zakresów; `pin_values` liczy koszt z darmowymi spinami; punkty wykresu nie
  skaczą na wierszu prowizorycznym. Zamrożona historia nie jest przeliczana.
- **Schematy, OpenAPI, klient.** `summary.provisionalCount`,
  `summary.provisionalPayoutCredits` (domyślnie 0), wiersz `mode`,
  `spinCostCredits` (null tylko w historii), `payoutKind` z `provisional`;
  szczegóły: `mode`, `spinCostCredits`, `expandedSymbolCodes`,
  `BoardSearchExpansionResponse`, `payoutKind` z `provisional`; publiczne
  szczegóły udostępnienia i panelu mają te same pola (bez `seriesId`).
  `npm run openapi:generate` (13 plików generowanych z samymi końcami linii
  przywrócone `git checkout`), eksport `BoardSearchExpansionResponse` w
  `packages/admin-api-client/src/index.ts`, test żądań w
  `test/client.test.mjs`. Trasy bez zmian, więc wrappery funkcji bez zmian.
- **UI (`board-search-ui`).** Przybliżona wygrana: dopisek „prowizoryczny”
  (wyróżniony) i „darmowy spin” w kolumnie wygranej, komunikat
  `ApproximateWinProvisionalSummary` („Wyniki prowizoryczne (supergra): N
  plansz, razem X…”, eksportowany, użyty też w zapisanym wyniku panelu).
  Modal: fioletowe pola rozwiniętych kolumn z nazwą symbolu, sekcja
  „Supergra: rozwinięcie” z wierszem „Rozwinięcie K ×3 kolumny → 10 × 5 linii
  = 50” (`boardExpansionLabel`, kwoty przez formatter okna), spójność z
  tabelą uwzględnia rozwinięcie, nagłówek z „prowizoryczny” i „darmowy spin”.
  Stan wykresu: `approximateWinBalancePayout` (wypłata prowizoryczna nie
  przesuwa bilansu), punkt dowolnego spinu przy darmowych spinach kotwiczy
  koszt na ostatnim wierszu. Panel: rodzaj „Prowizoryczna (supergra)”.
- **Testy.** API: `test_super_game_payout_api.py` (18: projekcja, koszt per
  pozycja, wynik prowizoryczny, stale, zmniejszenie po definicji symbolu,
  odcisk, HTTP, zamrożony wynik i piny, wykres, modal z rozwinięciem i
  sztukami z planszy oryginalnej, trigger w trybie bazowym, symbol spoza
  reguł i symbol, który stał się Wildem), `test_super_game_777_regression.py`
  (2: skrót treści, kanoniczny skrót payloadu, podsumowania, pinów i
  odpowiedzi identyczne z kodem v1.7.279 — wartości wyliczone tym samym
  builderem na wyeksportowanym `git archive HEAD` i na nowym kodzie; brak
  nowych kluczy w payloadzie 777). Zmienione kontrakty testów:
  `test_board_search_approximate_win_api.py` (nowe pola podsumowania i
  wiersza), `test_board_search_super_game_api.py` (jeden odczyt znaczników
  obejmuje cały zakres), PG `test_board_search_super_game_postgres.py`
  (`kind_code`, projekcja, odczyt w migawce tylko do odczytu, adapter przez
  `super_game_markers.markers`), PG `test_management_stakes_postgres.py`
  (sygnatura `_snapshot` z repozytorium znaczników). TS: board-search-ui
  `test/board-search-super-game-payout.test.mjs` (6) i test interakcji
  serii (wiersz prowizoryczny, komunikat, modal z 9 polami rozwinięcia).

### Verification results

Komendy z katalogu worktree, po rundzie poprawek audytu.

- `.\.venv\Scripts\python.exe -m pytest services/worker/tests -k "payout or super_game" -q`
  — 118 passed, 2733 deselected.
- `.\.venv\Scripts\python.exe -m pytest services/api/tests -k "approximate_win or board_search or management_stakes or super_game" -q`
  — 305 passed, 53 skipped (PG bez zmiennej), 2492 deselected.
- `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_board_search_approximate_win_repository.py services/api/tests/integration/test_board_search_super_game_postgres.py services/api/tests/integration/test_management_stakes_postgres.py -q`
  — 13 passed. Dodatkowo PG `test_management_postgres.py`,
  `test_management_sessions_postgres.py`,
  `test_board_search_share_corrections.py` — 3 passed;
  `test_management.py`, `test_management_sessions.py` — 19 passed.
- `npm run test --workspace @game-predictor/shared-ts` — 65/65 pass.
- `npm run test --workspace @game-predictor/board-search-ui` — 94/94 pass;
  `npm run test:interactions --workspace @game-predictor/board-search-ui` —
  62/62 pass.
- `npm run test --workspace @game-predictor/admin-api-client` — 105/105 pass.
- `npm run test --workspace @game-predictor/admin` — 733/733 pass;
  `npm run test:geometry --workspace @game-predictor/admin` — 188/188 pass.
- `npm run test --workspace @game-predictor/reviewer` — 240/240 pass;
  `npm run test:geometry --workspace @game-predictor/reviewer` — 40/40 pass.
- `npm run openapi:generate` (13 plików z samymi końcami linii przywrócone
  `git checkout`), potem `npm run openapi:check` — artefakt i klient
  aktualne, exit 0.
- `npm run fixture:validate` — `"status": "ok"`.
- `npm run typecheck` — exit 0 (wszystkie workspace, w tym mobile; mypy
  strict: „no issues found in 851 source files”); `mypy` na 17 zmienionych
  modułach źródłowych — bez uwag.
- `npm run lint` — exit 0 (0 błędów; 5 + 1 istniejących ostrzeżeń ESLint,
  ruff „All checks passed”).
- `npm run format:check` — „All matched files use Prettier code style!”.
- `ruff check` i `ruff format --check` na 24 zmienionych plikach Python —
  czysto; `git diff --check` — czysto.

### Not completed

- Punkty wykresu na kartach panelu zarządzania (`chartPoints` w podsumowaniu
  zapisanego wyniku, najwyżej 256 punktów) nadal powstają tylko z wierszy z
  wypłatą i końca zakresu, więc odcinek darmowych spinów rysują jako prostą
  linię; wartości pinów, wykres pełny i etykiety wkładu liczą z
  `superSpinRanges` dokładnie.
- Prekomputacja wydań i snapshot mobilny dla supergry poza zakresem.
- Nie uruchamiano API, Admin ani workerów; pełne `npm run quality` nie było
  uruchamiane (uruchomione jego składowe powyżej).

### Audyt i runda poprawek

Audyt Codex gpt-6-astra / high (`ai_docs/quality/TASK-0936_AUDIT_gpt-6-astra.md`):
REVISE, 3 × P0, bez P1/P2. Jedna runda poprawek wykonana przez tego samego
wykonawcę (claude-opus-5-5 / high) według poleceń leada:

- **P0-1 (koszt darmowych spinów w wykresie i pinach).** Podsumowanie
  odpowiedzi przybliżonej wygranej ma `superSpinRanges` (`{startSpin,
  endSpin}`, włączne) i `superSpinCost` (Admin, udostępnienie, publiczny
  panel, podgląd i zapisany wynik panelu); OpenAPI i klient zregenerowane
  (`ApproximateWinSpinRangeResponse`, eksport w wrapperze, test żądania).
  Zamrożony wynik trzyma zakresy w tym samym podsumowaniu (tylko gdy są,
  777 bez zmian; dotychczasowe klucze najwyższego poziomu payloadu usunięte
  przed commitem, więc nie powstały zapisane dane w starym kształcie).
  `board-search-approximate-win-state.ts`: `approximateWinCostSchedule`,
  `approximateWinCostAtSpin`; `approximateWinPointAtSpin` liczy dokładny
  koszt z zakresów zamiast wnioskować z wierszy; wykres dostaje punkty
  narożne na granicach serii (płaski odcinek darmowych spinów). Zapisany
  wynik panelu (`management-result-view.tsx`) używa tych samych zakresów z
  odtworzonego podsumowania. Testy: bilans po spinie 6 = 45, seria bez
  dodatniej wypłaty (punkt końcowy = podsumowanie, pin po serii, punkty
  narożne), test interakcji odtworzonych pinów supergry.
- **P0-2 (wkład przy starcie w serii).** `approximateWinStakeToPoint` i
  `approximateWinMachineCashAtPoint` przyjmują harmonogram kosztów; wkład to
  minimum rzeczywistego bilansu od zera z kosztem pierwszego spinu według
  jego trybu (0 w serii) zamiast `Math.min(-spinCost, …)`. Testy: start w
  serii, pierwszy darmowy spin płaci 50 → wkład 0, kredyty 50; pierwszy płatny
  spin po serii → wkład 50, kredyty 0; bez darmowych spinów wkład = koszt
  pierwszego spinu jak dotąd.
- **P0-3 (jedna migawka odczytu).** `SqlAlchemyBoardSearchApproximateWinRepository.begin_read_snapshot`
  (REPEATABLE READ na pierwszym użyciu sesji żądania, bez READ ONLY, bo
  router wiąże nieznane instrukcje z intencją zapisu; poza PostgreSQL nic;
  wywołanie po wcześniejszym użyciu sesji to `RuntimeError`).
  `BoardSearchApproximateWinService` i `BoardSearchBoardDetailService` mają
  `read_snapshot` (w `main.py` włączone; `refresh` po zapisie korzysta z
  `_detail` bez nowej migawki; zapis stawki panelu już działa w migawce).
  Szczegóły planszy panelu zarządzania czytają w osobnej migawce
  REPEATABLE READ (`_snapshot_reader`). Migawka jest stosowana dla
  wszystkich gier: dla gry bez supergry zmienia tylko spójność odczytu,
  liczby i skróty 777 pozostają identyczne (test regresji bez zmian
  stałych). Testy: PG z dwiema sesjami (odczyt w migawce, korekta i
  publikacja generacji w innej sesji, znaczniki ze starej generacji ze
  spójnym `fresh`; kontrola bez migawki widzi nowy trigger), PG „migawka musi
  być pierwszym użyciem sesji”, test jednostkowy kolejności wywołań obu
  serwisów.
- **Decyzja leada (pytanie 1).** Przy `superGameState.fresh = false`
  prowizoryczna jest **każda** oceniona plansza gry, także w trybie bazowym
  (plan ma pierwszeństwo przed pierwotnym brzmieniem D-537). Zmienione:
  domena zakresu, szczegóły planszy, testy (zakres i szczegół bazowej
  planszy), D-537, `ALGORITHMS.md` §D, `API_CONTRACT.md`,
  `MANAGEMENT_PANEL.md`, `ADMIN_APP.md`.
- Weryfikacja po poprawkach: wyniki w „Verification results”.

### Documentation updates

- `ai_docs/requirements/ALGORITHMS.md` — §B: podsekcja „Plansza w serii
  supergry `wild_super_spins`” (cztery kroki, przykład, wynik dokładny albo
  prowizoryczny); §D: „Tryb pozycji i koszt per pozycja”, podsumowanie z
  osobnymi wynikami prowizorycznymi.
- `ai_docs/requirements/MANAGEMENT_PANEL.md` — stawki z darmowymi spinami,
  podgląd, format zamrożonego wyniku.
- `ai_docs/requirements/ADMIN_APP.md` — akapit „Supergra w prognozie”.
- `ai_docs/architecture/API_CONTRACT.md` — nowe pola zakresu i szczegółów,
  akapit o trybie pozycji i koszcie, podgląd panelu, suma z rozwinięciem.
- `ai_docs/process/DECISION_LOG.md` — D-537.

### Recommended next task

- Weryfikacja reguły „× liczba linii” i Z-1 na pierwszej serii Mumii z
  pełnymi zdjęciami i znanymi wygranymi (plan, ryzyka). Dalej według planu:
  etap S-D (TASK-0937) albo T (TASK-0938/0939) na polecenie operatora.
