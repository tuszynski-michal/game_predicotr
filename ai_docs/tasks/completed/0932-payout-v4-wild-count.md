# TASK-0932 — Ewaluator `payout-v4-wild-count`

## Status

`done`

## Goal

Dla gry z symbolem uruchamiającym supergrę kalkulator liczy wygraną jako
linie (Wild podmienia per linia) plus wypłatę za liczbę sztuk symbolu
uruchamiającego na planszy; dla gier bez takiego symbolu wyniki są identyczne
z `payout-v3-unknown-prefix-stop`.

## Context

Po TASK-0931 Mumia może być Wild i symbolem uruchamiającym, ale ewaluator
nadal traktuje ją jak zwykły symbol liniowy. Plan: etap S-A. Po tym zadaniu
operator włącza Wild i testuje w modalu linii.

## Dependencies / entry conditions

- TASK-0931 zacommitowany i zaudytowany (role w domenie i API).
- Fakt: ewaluator w `services/worker/src/game_predictor_worker/domain/payout.py`
  jest współdzielony przez API (`PreparedPayoutEvaluator`); TS odpowiednik w
  `packages/shared-ts/src/validation.ts`; złote przypadki w
  `packages/domain-fixtures/payout-golden-cases.json` wykonują oba języki.

## Recommended execution

claude-opus-5-5 / high (subagent z tej sesji; wykonanie zamiast Codex na
decyzję operatora 2026-10-08). Ewaluator w Pythonie i TS, złote przypadki,
regresja 777. Eskalacja do claude-fable-5-1 / high przy rozbieżności wyników
Python/TS. Audyt: gpt-6.1-sol / high; do czasu CLI zamiennik
claude-fable-5-1 / high (niezależny subagent, tylko odczyt).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`
- `ai_docs/requirements/ALGORITHMS.md` (§B, §D)
- `ai_docs/architecture/DATA_MODEL.md` (wersjonowanie algorytmu)

## Scope

- `payout.py`: symbole z `super_game_trigger_count` wyłączone z
  `_ordinary_symbols_by_display_order`; Wild bez zmian; nowy rodzaj
  dopasowania `count` (symbol, liczba sztuk, komórki, kredyty) z reguł
  symbolu uruchamiającego; `total = linie + count`. Nieznane komórki (`0`)
  nie liczą się jako sztuki (nie zgadujemy; w trybie bazowym nadal dolne
  ograniczenie).
- Wersja algorytmu `payout-v4-wild-count` wybierana per gra: gra bez symbolu
  uruchamiającego używa `v3` bez zmian (identyczne wyniki i audyt).
- Kontrakty: `PayoutMatch` (linia) bez zmian; `PayoutEvaluation` dostaje
  osobną listę `count_matches` (`symbol_mobile_code`, `count`,
  `matched_cells`, `payout_credits`), więc dopasowanie za sztuki nie udaje
  linii i nie wymaga `payline_id`. Pion: schemat odpowiedzi szczegółu
  planszy (`countMatches[]`), OpenAPI, `npm run openapi:generate`, klient,
  wrappery `board-search-ui`, request test; modal renderuje sekcję „Sztuki
  na planszy” obok linii.
- Podgląd draftu w Adminie: `GET …/boards/{sequenceNumber}` i przybliżona
  wygrana przyjmują opcjonalny `rulesVersionId` (wersja tej gry, `draft`
  albo `published`); domyślnie najnowsza opublikowana; udostępniony panel
  i Reviewer nie przekazują parametru (walidacja odrzuca). Admin: select
  „Wersja reguł” w modalu i przybliżonej wygranej z etykietą „draft”.
- `packages/shared-ts/src/validation.ts` i kalkulator TS: ta sama reguła;
  złote przypadki w `payout-golden-cases.json`.
- Admin: modal linii pokazuje wiersz „Mumia ×3 (sztuki na planszy) → 20”;
  przybliżona wygrana używa nowej wersji dla gier ze symbolem uruchamiającym.
- `ALGORITHMS.md` §B: opis `payout-v4-wild-count`; „Joker” → „Wild”.

## Out of scope

- Rozwinięcie super symbolu i koszt per pozycja (TASK-0936).
- Przeniesienie ról do wersji reguł (odłożone).
- Serie (TASK-0933). Aplikacja mobilna.

## Acceptance criteria

- [x] Złote przypadki: Wild jako dwa różne symbole na dwóch liniach; sztuki
      3/4/5; sztuki + linie na jednej planszy; same Wildy bez wygranej;
      nieznana komórka nie liczy się jako sztuka; plansza bez symbolu
      uruchamiającego identyczna z v3.
- [x] Wszystkie istniejące złote przypadki 777 bez zmian wyników.
- [x] Python i TS dają identyczne wyniki na wszystkich przypadkach.
- [x] Modal linii i przybliżona wygrana pokazują wypłatę za sztuki w osobnej
      sekcji; odpowiedź API ma `countMatches[]`; request test pokrywa oba
      rodzaje.
- [x] Admin liczy modal i przybliżoną wygraną z wybranej wersji `draft`;
      panel udostępniony i Reviewer odrzucają `rulesVersionId`.

## Technical notes

Wejście → wynik (Mumie, Mumia = Wild + trigger 3, reguły Mumii 3→20):
`[10, Mumia, 10, 10, J / K, K, Mumia, Q, Q / Mumia, A, A, A, 10]` →
linia A: `10 ×4` (Mumia jako 10); linia B: `K ×3` (Mumia jako K);
linia C: `A ×4` (Mumia w kolumnie 1 jako A; ciąg kończy się na `10`);
sztuki Mumii = 3 → 20; suma = payout(10,4) + payout(K,3) + payout(A,4) + 20.
Ciąg złożony wyłącznie z Mumii nadal nie wygrywa jako linia.

## Expected files

- Istniejące: `services/worker/src/game_predictor_worker/domain/payout.py`,
  `domain/contracts.py`, `domain/validation.py`,
  `services/worker/tests/test_payout.py`, `test_payout_batch.py`,
  `packages/shared-ts/src/validation.ts`, `packages/shared-ts/src/contracts.ts`,
  `packages/domain-fixtures/payout-golden-cases.json`,
  `services/api/src/game_predictor_api/domain/board_search_board_detail.py`,
  `packages/board-search-ui/src/board-search-board-lines-modal.tsx`,
  `ai_docs/requirements/ALGORITHMS.md`.

## Test cases

- Jak w kryteriach akceptacji; dodatkowo: symbol uruchamiający bez reguł
  → brak wypłaty za sztuki, brak błędu; sztuki = 2 przy regule od 3 → 0.

## Verification

```powershell
# katalog worktree, timeout 120 s każda
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_payout.py services/worker/tests/test_payout_batch.py -q
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_search_board_detail_api.py services/api/tests/test_board_search_approximate_win_domain.py -q
npm run test --workspace @game-predictor/shared-ts
npm run test --workspace @game-predictor/board-search-ui
npm run quality
```

## Risks / open questions

- Raporty wydania 777 muszą odtwarzać `v3`; nowa wersja nie może zmienić
  `algorithm_version` gier bez symbolu uruchamiającego.

## Outcome

Wykonane w worktree `worktrees/mumie-super-game` (gałąź
`feat/mumie-super-game-plan`, start na v1.7.268 = `1aef5870`) przez subagenta
claude-opus-5-5. Commit, wersję i hash, `CURRENT_STATE.md`, przeniesienie
taska oraz audyt krzyżowy zapisuje prowadzący sesję.

### Instrukcja operatora: test Wilda na drafcie Mumii

Warunek wstępny jak w TASK-0931: po scaleniu operator zatrzymuje API, Admin i
workery, wykonuje `npm run db:migrate` (jeśli baza nie ma jeszcze `0151`) i
uruchamia ponownie `npm run api:dev` oraz `npm run admin:dev`. TASK-0932 nie
dodaje migracji.

1. Ustaw role według instrukcji z TASK-0931 (gra Mumie: Supergra „Wild super
   spins”; symbol Mumia: „Wild” i „Uruchamia supergrę” = trzy symbole).
   Sprawdź w zakładce reguł, że wypłaty Mumii w drafcie to wypłaty za sztuki
   na planszy (3/4/5 → 20/200/2000) i że pozostałe symbole mają komplet
   wypłat liniowych; niekompletny draft daje komunikat „reguły są
   nieprawidłowe” (`APPROXIMATE_WIN_RULES_INVALID`).
2. Admin → gra Mumie → sekcja „Wyszukaj plansze” → wyszukaj wzór i wybierz
   wynik.
3. W „Przybliżonej wygranej” w selekcie „Wersja reguł” wybierz wersję
   oznaczoną „draft” (np. „v1 · draft”). Pojawi się nota „Podgląd wersji
   roboczej”; zakres liczy się z draftu bez publikacji. W kolumnie
   „Wygrana” wiersze z wypłatą za sztuki mają dopisek „w tym sztuki: Mumia ×3
   → 20”.
4. Kliknij „Pokaż planszę” w wierszu. Okno liczy tę samą wersję draft (select
   „Wersja reguł” w nagłówku okna), rysuje linie z Wildem (znacznik „W”,
   w legendzie „(Wild: n)”) i pokazuje sekcję „Sztuki na planszy” z wierszem
   „Mumia ×3 → 20”; policzone pola Mumii są podświetlone na pomarańczowo.
   Plansze bez wyniku w tabeli można też otworzyć z wyników wyszukiwania
   (przycisk planszy) i tam wybrać draft w selekcie okna.
5. Powrót do „Najnowsza opublikowana” w selekcie liczy z ostatniej
   opublikowanej wersji (dla Mumii, która ma tylko draft, kalkulacja zgłosi
   brak opublikowanych reguł — to oczekiwane).
6. Publikację reguł Mumii operator wykonuje świadomie po testach. Uwaga:
   prekomputacja wydania (`layout_payouts`, snapshot mobilny) nie obsługuje
   jeszcze `payout-v4-wild-count` i dla gry z symbolem uruchamiającym zwraca
   `PAYOUT_ALGORITHM_GAME_MISMATCH` (patrz „Not completed”). Udostępniony
   panel online i panel zarządzania liczą zawsze z najnowszej opublikowanej
   wersji i nie mają selectu.

Gra 777 nie wymaga żadnej akcji: brak symbolu uruchamiającego oznacza
algorytm `payout-v3-unknown-prefix-stop` i wyniki identyczne jak przed
zadaniem.

### Changed

- Ewaluator workera (`services/worker/src/game_predictor_worker/domain/`):
  `payout.py` ma stałe `PAYOUT_V3_ALGORITHM_VERSION` i
  `PAYOUT_V4_ALGORITHM_VERSION`, funkcję `payout_algorithm_version(game)`
  (v4 tylko przy symbolu uruchamiającym) i właściwość
  `PreparedPayoutEvaluator.algorithm_version`. Symbole z
  `super_game_trigger_count` są wyłączone z `_ordinary_symbols_by_display_order`;
  nowe `_evaluate_count_matches` liczy komórki symbolu uruchamiającego na całej
  planszy (kod `0` nigdy się nie liczy) i wypłaca regułę największej liczby
  sztuk nieprzekraczającej wyniku; `total = linie + sztuki`. Wild bez zmian
  (jedna komórka Wilda może być różnymi symbolami na różnych liniach, prefiks
  z samych Wildów nie wygrywa).
- Kontrakty: `SymbolDefinition.super_game_trigger_count: int | None = None`,
  nowy `CountMatch` (`symbol_mobile_code`, `count`, `matched_cells`,
  `payout_credits`), `PayoutEvaluation.count_matches = ()`; `PayoutMatch` bez
  zmian. Eksport w `domain/__init__.py`.
- Walidacja workera (`validation.py`): `is_super_game_trigger`,
  `is_ordinary_line_symbol`; symbol uruchamiający nie może mieć
  `PayoutSymbolDefinition` (nowy kod `super_game_trigger_payout_symbol`), jego
  reguły to liczby sztuk `2..rows × columns` (`invalid_match_length` poza
  zakresem), bez wymogu kompletu, ściśle rosnące (`non_increasing_payout`);
  symbol uruchamiający nie jest liczony jako zwykły symbol w kompletności.
  `trigger_count` musi być dodatnią liczbą całkowitą.
- Payout job (`payouts/handler.py`): zlecenie v2/v3 dla gry z symbolem
  uruchamiającym kończy się `PAYOUT_ALGORITHM_GAME_MISMATCH` (wynik v4 nie
  trafi do `layout_payouts` pod etykietą v3). `payouts/store.py` czyta
  `super_game_trigger_count` symbolu.
- TS (`packages/shared-ts`): `SymbolDefinition.superGameTriggerCount?`,
  `CountMatch`, `PayoutEvaluation.countMatches`, kod błędu
  `super_game_trigger_payout_symbol`, lustrzana walidacja w `validation.ts`
  (`isSuperGameTrigger`, `isOrdinaryLineSymbol`) oraz nowy lustrzany
  ewaluator `src/payout.ts` (`evaluatePayout`, `payoutAlgorithmVersion`,
  stałe wersji) z testem `test/payout.test.mjs` wykonującym wszystkie złote
  przypadki v3 i v4.
- Złote przypadki (`packages/domain-fixtures/payout-golden-cases.json`): nowa
  sekcja `wildCountScenario` (gra jak Mumie, Mumia = Wild + symbol
  uruchamiający 3, reguły 3/4/5 → 20/200/2000) z 10 przypadkami: przykład z
  taska (linia C `A ×4`, suma 70), Wild jako dwa różne symbole na dwóch
  liniach, sztuki 3/4/5, same Wildy bez wygranej liniowej, nieznane pole nie
  liczone, 2 sztuki przy regule od 3 → 0, plansza bez symbolu
  uruchamiającego identyczna z v3, symbol uruchamiający bez reguł → brak
  wypłaty i brak błędu. Istniejące przypadki 777 bez zmian.
- API: `domain/board_search_board_detail.py` (`BoardCountMatch`, opis
  `board_payout_kind` — wypłata za sztuki jest wliczona, plansza częściowa
  pozostaje `confirmed_minimum`), `domain/board_search_approximate_win.py`
  (`ApproximateWinRow.count_matches`, `ApproximateWinSpinEvaluation`;
  `evaluate` może nadal zwracać `int`), `application/board_search_approximate_win.py`
  (`resolve_rules_configuration`, `board_count_matches`,
  `SELECTABLE_RULES_STATUSES`, parametr `rules_version_id`, raportowana wersja
  z ewaluatora), `application/board_search_board_detail.py` (parametr
  `rules_version_id`, `count_matches`), repozytorium
  `storage/board_search_approximate_win_repository.py`
  (`rules_configuration` — tylko `draft`/`published` tej gry), schematy
  (`BoardSearchCountMatchResponse`; `countMatches` wymagane w szczegółach
  planszy i publicznych szczegółach, z domyślną pustą listą w wierszach
  zakresu), trasy Admina `board-search/approximate-win` i
  `board-search/boards/{n}` z opcjonalnym `rulesVersionId`, `main.py`
  (`APPROXIMATE_WIN_RULES_VERSION_NOT_FOUND` → 404).
- Odrzucanie parametru poza Adminem: udostępnienie online rozszerza istniejącą
  listę zakazanych parametrów (`rulesVersionId`/`rules_version_id` →
  `422 BOARD_SEARCH_SHARE_PARAMETER_FORBIDDEN` na wszystkich trasach
  udostępnienia); publiczny panel zarządzania (`approximate-win`,
  `boards/{sequence}`) odrzuca go zależnością `reject_rules_version_query`
  (`422 BOARD_SEARCH_RULES_VERSION_NOT_ALLOWED`). Obie powierzchnie używają
  wspólnej stałej `RULES_VERSION_QUERY_NAMES` (`rulesversionid`,
  `rules_version_id`, porównanie bez rozróżniania wielkości liter). Allowlisty Reviewera
  (`board-search-share-proxy.ts`, `management-proxy.ts`) już przepuszczają
  tylko dokładne parametry, więc nie wymagały zmian — dodano testy, że
  `rulesVersionId` daje 403 bez wywołania API.
- Zamrożone wyniki panelu zarządzania (`storage/management_result_snapshots.py`):
  `rules_snapshot` pomija `super_game_trigger_count = None`, więc snapshot i
  skrót treści gier bez symbolu uruchamiającego (777) pozostają bajtowo
  identyczne jak przed zadaniem; format v1 wierszy nie przechowuje
  `countMatches` (wypłata wiersza nadal je zawiera).
- OpenAPI i klient: `npm run openapi:generate` (`openapi.json`,
  `generated/index.ts`, `sdk.gen.ts`, `types.gen.ts`); wrapper
  `packages/admin-api-client/src/index.ts`: `GetBoardSearchApproximateWinOptions.rulesVersionId?`,
  nowy `GetBoardSearchBoardDetailOptions`, `getBoardSearchBoardDetail(gameId,
  sequenceNumber, options?)`, eksport `BoardSearchCountMatchResponse`; testy
  żądań w `test/client.test.mjs`. 13 wygenerowanych plików `client/*`,
  `core/*` i `client.gen.ts` zmienia się tylko końcami linii.
- `packages/board-search-ui`: nowe `board-search-rules-versions.ts` (opcje
  wersji, etykiety „vN · draft”/„vN · opublikowana”, etykieta „Mumia ×3”) i
  `board-search-rules-version-select.tsx` (hook `useBoardSearchRulesVersions`
  i select „Wersja reguł”); capability w `BoardSearchDataSource` przez
  opcjonalne `listRulesVersions` (Admin przekazuje pełny klient, Reviewer i
  panel zarządzania go nie mają, więc nie pokazują selectu) i opcjonalne
  `options` w `getBoardSearchBoardDetail`. Modal linii: select wersji, sekcja
  „Sztuki na planszy”, podświetlenie policzonych pól, spójność liczona z
  liniami i sztukami, „Wild” zamiast „joker”/„J”. Przybliżona wygrana: select
  wersji (klucz żądania zawiera wybraną wersję), dopisek „w tym sztuki” w
  wierszu, przekazanie wersji do modalu. Wyniki wyszukiwania przekazują listę
  wersji do modalu. Style w `board-search.css`.
- Testy: `services/worker/tests/test_payout.py` (sekcja v4, walidacje),
  `test_payout_batch.py` (odrzucenie v2/v3 dla gry z symbolem uruchamiającym),
  `services/api/tests/test_board_search_board_detail_api.py`,
  `test_board_search_approximate_win_api.py`,
  `test_board_search_approximate_win_domain.py`,
  `test_board_search_share_public_api.py`, `test_management_stakes.py`,
  `packages/board-search-ui/test/board-search-rules-versions.test.mjs`,
  dwa testy interakcji w `test-interactions/board-search-approximate-win.test.mjs`,
  testy proxy Reviewera (`board-search-share-proxy.test.mjs`,
  `management-proxy.test.mjs`).

### Verification results

Komendy z katalogu worktree.

- `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_payout.py services/worker/tests/test_payout_batch.py services/worker/tests/test_payout_readiness.py services/worker/tests/test_snapshot.py -q`
  — 88 passed.
- `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_search_board_detail_api.py services/api/tests/test_board_search_approximate_win_domain.py services/api/tests/test_board_search_approximate_win_api.py services/api/tests/test_board_search_share_public_api.py -q`
  — 90 passed.
- Dodatkowo: `pytest services/api/tests/test_management_stakes.py
  test_board_search_board_view.py test_board_search_share_access.py
  test_board_search_stale_refresh.py services/worker/tests/test_domain_contracts.py -q`
  — 54 passed, 1 skipped (dowiązania symboliczne niedostępne na koncie);
  wszystkie testy importujące kontrakty payoutu (`test_domain_contracts`,
  `test_payout*`, `test_board_search_*`, `test_rules_api`, `test_rules_domain`)
  — 153 passed; `test_m1_fixture.py`, `test_representative_v01_release.py`,
  `test_release_workflow.py` — 29 passed.
- `npm run test --workspace @game-predictor/shared-ts` — 46/46 pass
  (w tym 18 złotych przypadków v3 i 10 v4 w TS); `npm run typecheck` tego
  pakietu — exit 0.
- `npm run test --workspace @game-predictor/board-search-ui` — 80/80 pass;
  `npm run test:interactions --workspace @game-predictor/board-search-ui` —
  51/51 pass; typecheck i lint — exit 0.
- `npm run openapi:generate`, potem `npm run openapi:check` — „OpenAPI
  artifact is current”, „Generated Admin API client is current”, exit 0.
- `npm run test --workspace @game-predictor/admin-api-client` — 102/102 pass.
- `npm run test --workspace @game-predictor/admin` — 679/679 pass;
  `npm run typecheck --workspace @game-predictor/admin` — exit 0;
  `npm run lint --workspace @game-predictor/admin` — 0 errors, 5 istniejących
  ostrzeżeń.
- `npm run typecheck --workspace @game-predictor/reviewer` — exit 0; testy
  proxy Reviewera (`node --experimental-strip-types --test
  test/board-search-share-proxy.test.mjs test/management-proxy.test.mjs`) —
  23/23 pass. `npm run typecheck --workspace @game-predictor/mobile` — exit 0
  (bez zmian w aplikacji mobilnej).
- `npm run fixture:validate` — `"status": "ok"`, exit 0.
- `ruff check` i `ruff format --check` na 26 zmienionych plikach Python —
  czysto. `mypy --strict` na zmienionych modułach źródłowych — jedyny błąd
  to istniejący `main.py:2005` (`no-untyped-call`, plik z listy 7 plików z
  błędami sprzed zadania); pozostałe moduły bez uwag.
- Pełny przebieg Reviewera (`npm run test --workspace @game-predictor/reviewer`,
  uruchomiony przy audycie) — 235/237; dwa błędy to istniejące testy kontraktu
  źródeł `test/local-reviewer-workspace-contract.test.mjs:63` i
  `test/operational-review-workspace-contract.test.mjs:151` (źródła bez zmian w
  tym zadaniu, ostatnio zmieniane w v1.7.183 i v1.7.143).
- Istniejące, niezwiązane błędy zauważone przy szerszym przebiegu:
  `test_board_search_share_access_api.py::test_invalid_lifetime_is_rejected_before_starting_the_ingress`
  (1441 minut jest od TASK-0925 dozwolonym czasem) oraz dwa testy kontraktu
  Reviewera wymienione wyżej; żadna zmiana tego zadania ich nie dotyczy.
  Błędy `services/api/tests/test_management.py` (SQLite i CHECK z `~` z
  TASK-0931) usunęła osobna poprawka v1.7.269.
- Runda poprawek po audycie (claude-fable-5-1 / high: PASS, 4 × P2, wszystkie
  naprawione): wspólna stała `RULES_VERSION_QUERY_NAMES` dla udostępnienia i
  panelu zarządzania z testem `rules_version_id`/`RULES_VERSION_ID` na trasach
  publicznego panelu, usunięta nieużywana stała
  `APPROXIMATE_WIN_PAYOUT_ALGORITHM_VERSION`, opis braku rozbicia
  `countMatches` w całym panelu zarządzania w `API_CONTRACT.md`, uzupełniona
  lista istniejących błędów. Ponowna weryfikacja:
  `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_search_share_public_api.py services/api/tests/test_management_stakes.py services/api/tests/test_board_search_approximate_win_api.py -q`
  — 40 passed; `ruff check` i `ruff format --check` na zmienionych plikach —
  czysto; `mypy --strict` na `api/board_search.py`,
  `api/board_search_share_public.py`, `api/management_public_stakes.py`,
  `application/board_search_approximate_win.py`,
  `application/board_search_board_detail.py` — bez uwag;
  `npm run openapi:check` — artefakt i klient aktualne, exit 0.

### Not completed

- Prekomputacja wydania dla `payout-v4-wild-count` (worker `layout_payouts`,
  audyt JSONL z `count_matches`, `create_payout_job` w API, snapshot mobilny
  i jego `CURRENT_ALGORITHM_VERSION`) nie jest zaimplementowana; zamiast tego
  zadanie payout jawnie odrzuca zlecenie v2/v3 dla gry z symbolem
  uruchamiającym. Aplikacja mobilna jest poza zakresem planu.
- Cały panel zarządzania (także świeże podglądy, które rozwijają snapshot v1
  z `ROW_FIELDS`) pokazuje wiersze bez rozbicia `countMatches`; wypłata
  wiersza i bilans już zawierają wypłaty za sztuki. Zaakceptowane do czasu
  formatu wyniku v2.
- Nie uruchamiano API, Admin, workerów ani migracji; dane Mumii nie były
  zmieniane. Pełne `npm run quality` nie było uruchamiane (znane, niezwiązane
  błędy formatowania CRLF w worktree, testy V7 i baseline).

### Documentation updates

- `ai_docs/requirements/ALGORITHMS.md` — §B: wyjście z `count_matches`,
  nowa podsekcja `payout-v4-wild-count` z przykładem z taska, „Joker” →
  „Wild” w treści algorytmu, sumowanie i precomputing z regułami za sztuki,
  ograniczenie prekomputacji; §D: wypłaty za sztuki jako dolne ograniczenie,
  `countMatches` w wierszach i modalu, podgląd wersji roboczej tylko w
  lokalnym Adminie.
- `ai_docs/architecture/API_CONTRACT.md` — `rulesVersionId` i `countMatches`
  w przybliżonej wygranej i szczegółach planszy, błąd
  `APPROXIMATE_WIN_RULES_VERSION_NOT_FOUND`, reguła sumy z `countMatches`,
  odrzucanie parametru w udostępnieniu i publicznym panelu zarządzania.
- `ai_docs/requirements/ADMIN_APP.md` — select „Wersja reguł” w przybliżonej
  wygranej i modalu, dopisek „w tym sztuki”, sekcja „Sztuki na planszy” i
  podświetlenie pól.
- `ai_docs/architecture/DATA_MODEL.md` — `layout_payouts`: gra z symbolem
  uruchamiającym jest liczona v4, job odrzuca v2/v3
  (`PAYOUT_ALGORITHM_GAME_MISMATCH`), 777 bez zmian.

### Recommended next task

- TASK-0933 (etap S-B) według planu. Osobno do decyzji operatora: obsługa
  `payout-v4-wild-count` w prekomputacji wydania i snapshocie, zanim Mumie
  dostanie wydanie (dziś job ją jawnie odrzuca).
