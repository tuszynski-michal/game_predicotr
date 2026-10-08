# TASK-0931 — Wild, „Uruchamia supergrę” i rodzaj supergry w katalogu, regułach i grze

## Status

`done`

## Goal

Operator ustawia w Adminie per symbol checkbox **Wild** i checkbox
**Uruchamia supergrę** z selectem 3/4/5, a per gra select rodzaju supergry
(„Brak” / „Wild super spins”); domena waliduje role, a wypłaty symbolu
uruchamiającego są interpretowane jako wypłaty za liczbę sztuk.

## Context

Mumia ma dziś `is_wildcard = false` i reguły liniowe 3/4/5. Domena zabrania
wildowi wypłat i blokuje zmianę roli po wpisie w wersji reguł. Operator chce
sterować rolami sam, bez reguł wpisywanych przez agenta. Plan:
`ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`, sekcja
„Model domenowy” i etap S-A.

## Dependencies / entry conditions

- Fakt: ostatnia migracja na gałęzi to `0150_management_sessions`; sprawdzić
  wierzchołek przed numerowaniem (równoległe tory).
- Fakt: Mumie mają wyłącznie wersję reguł `draft`; 777 ma wersję opublikowaną
  i żadnych ról specjalnych.
- Założenie: nazwa rodzaju `wild_super_spins` (decyzja operatora 2026-10-08).

## Recommended execution

claude-opus-5-5 / high. Migracja, walidacje domeny, rejestr rodzajów,
kontrakt API pionem i formularze Adminu. Eskalacja do claude-fable-5-1 / high
przy konflikcie z gotowością wydania 777. Audyt: gpt-6-astra / high; do czasu CLI zamiennik claude-fable-5-1 / high.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`
- `ai_docs/requirements/ADMIN_APP.md` (katalog symboli, reguły)
- `ai_docs/architecture/DATA_MODEL.md` (`symbols`, `rules_version_symbols`, `payout_rules`, `games`)
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Migracja Alembic (addytywna): `symbols.super_game_trigger_count smallint
  null` z CHECK `IN (3,4,5)`; `games.super_game_kind text NOT NULL DEFAULT 'none'`.
- Domena `catalog.py`: walidacja pól; zmiana roli dozwolona, dopóki symbol nie
  występuje w opublikowanej wersji reguł (dziś: blokada przy jakimkolwiek
  wpisie `rules_version_symbols`); zmiana `super_game_trigger_count` wymaga
  `games.super_game_kind != 'none'`.
- Domena `rules.py`: symbol z `super_game_trigger_count` ma `minimum_match_length
  = null` i reguły interpretowane jako liczba sztuk (`2 ≤ match_length ≤
  rows × columns`, rosnące wypłaty); Wild bez roli uruchamiającej jak dziś;
  gotowość do precomputingu rozszerzona o te warunki; nowe kody błędów.
- Rejestr rodzajów: `services/worker/src/game_predictor_worker/domain/super_games/`
  (`registry.py`, `wild_super_spins.py`) ze stałymi 10 spinów, +10 przy
  retriggerze, koszt 0; API `GET /api/v1/admin/super-game-kinds` zwraca listę z
  rejestru (kod, etykieta).
- API: pola w schematach gry i symbolu, OpenAPI, `npm run openapi:generate`,
  klient, wrappery Adminu, request testy.
- Admin: katalog symboli — etykieta „Wild” zamiast „Joker”, checkbox
  „Uruchamia supergrę” odsłaniający select „Trzy symbole / Cztery symbole /
  Pięć symboli”; formularz gry (tworzenie i edycja) — select „Supergra”;
  zakładka reguł — etykieta „sztuk na planszy” dla symbolu uruchamiającego.
- `Outcome` z instrukcją operatora krok po kroku dla Mumii.

## Out of scope

- Zmiana ewaluatora (TASK-0932); do czasu TASK-0932 modal linii nadal liczy
  starym algorytmem i może pokazywać Mumię jako symbol liniowy.
- Serie, wyszukiwanie plansz, aplikacja mobilna.
- Jakakolwiek zmiana danych Mumii przez agenta.

## Acceptance criteria

- [x] Symbol bez opublikowanej wersji reguł może zmienić Wild i
      „Uruchamia supergrę”; symbol w opublikowanej wersji nie może.
- [x] Ustawienie „Uruchamia supergrę” dla gry z rodzajem `none` zwraca błąd
      walidacji z czytelnym kodem.
- [x] Walidacja reguł: Wild z rolą uruchamiającą może mieć wypłaty 3/4/5;
      Wild bez niej nie może; gotowość wydania 777 bez zmian (testy istniejące).
- [x] `GET /admin/super-game-kinds` zwraca `none` i `wild_super_spins`.
- [x] OpenAPI i klient bez driftu (`npm run openapi:check`).
- [x] Formularze Adminu renderują nowe pola; testy stanu i kontraktu renderu.

## Technical notes

- Źródło prawdy ról: `symbols` (katalog gry). Interpretacja `payout_rules`
  symbolu uruchamiającego jako liczby sztuk wynika z roli, nie z nowej kolumny.
- Kolejność walidacji przy zapisie symbolu: gra istnieje → rodzaj supergry
  gry → opublikowane wersje → pola. Błąd nie zapisuje nic.
- Publikacja wersji reguł z symbolem uruchamiającym przy `super_game_kind =
  none` jest odrzucana (gotowość).

## Expected files

- Nowe: `services/api/alembic/versions/0151_super_game_roles.py` (numer do
  potwierdzenia), `services/worker/src/game_predictor_worker/domain/super_games/{__init__,registry,wild_super_spins}.py`.
- Istniejące: `services/api/src/game_predictor_api/domain/catalog.py`,
  `domain/rules.py`, `schemas/catalog.py`, `api/catalog.py`, `storage/models.py`,
  `storage/catalog_repository.py`, `packages/admin-api-client` (generowany),
  `apps/admin/src/features/symbols/*`, `apps/admin/src/features/games/*`,
  `apps/admin/src/features/rules/*`, `ai_docs/architecture/DATA_MODEL.md`,
  `ai_docs/architecture/API_CONTRACT.md`, `ai_docs/requirements/ADMIN_APP.md`.

## Test cases

- Symbol Mumii: Wild = true, trigger = 3, gra `wild_super_spins` → zapis OK.
- Symbol 777 (wersja opublikowana): Wild = true → błąd roli.
- Symbol z trigger = 4 w grze `none` → błąd.
- Reguły: Wild bez triggera z wypłatą → `WILDCARD_PAYOUT_NOT_ALLOWED`; Wild z
  triggerem z wypłatami 3/4/5 → OK; wypłata 2 < próg nadal dozwolona jako
  liczba sztuk (zakres 2…15).
- Gotowość 777: identyczne wyniki jak przed zmianą.

## Verification

```powershell
# katalog worktree, timeout 120 s każda
.\.venv\Scripts\python.exe -m pytest services/api/tests -k "rules or catalog" -q
npm run openapi:generate; npm run openapi:check
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run python:lint; npm run python:typecheck
```

## Risks / open questions

- Numer migracji może kolidować z równoległym torem; sprawdzić przed zapisem.
- Etykieta „sztuk na planszy” zmienia prezentację reguł także dla gier bez
  supergry? Nie: tylko dla symbolu z rolą uruchamiającą.

## Outcome

Wykonane w worktree `worktrees/mumie-super-game` (gałąź
`feat/mumie-super-game-plan`, start na v1.7.265, w trakcie pracy wierzchołek
przesunął się do v1.7.267 przez TASK-0929/0930). Commit, wersja i hash
zapisuje prowadzący sesję.

### Audyt i runda poprawek

Niezależny audyt claude-fable-5-1 / high (zamiennik gpt-6-astra do czasu CLI):
PASS z czterema uwagami P2; wszystkie osiem odstępstw od taska zaakceptowane.
Jedna runda poprawek usunęła wszystkie cztery uwagi:

1. Endpoint rejestru przeniesiony pod prefiks admin, jak każdy endpoint Adminu:
   `GET /api/v1/admin/super-game-kinds` (OpenAPI, klient, test żądań, dokumenty
   i ten task zaktualizowane; allowlista proxy Reviewera bez zmian).
2. Opis kolejności w katalogu symboli: „skróty 1–9 i 0 w weryfikacji symboli
   oraz 1–9 w wyszukiwarce plansz podążają za tą kolejnością” (w wyszukiwarce
   `0` nadal oznacza nieznany symbol).
3. `SymbolResponse.superGameTriggerCount` jest wymagane (`number | null`);
   dwa adaptery Reviewera budujące symbole z publicznych danych udostępnienia
   (`board-search-share-data-source.ts`, `management-public-adapter.ts`)
   ustawiają `superGameTriggerCount: null`; zbędne sprawdzenia `undefined` w
   Adminie uproszczone.
4. `domain/rules.py` używa `NO_SUPER_GAME` z `domain/catalog.py` zamiast
   lokalnej stałej.

Dodane testy z audytu: utrata obu ról na drafcie nie przywraca minimum
(`test_super_game_roles_removed_on_a_draft_do_not_restore_the_minimum`) i
raport gotowości zgłasza wtedy `INVALID_MINIMUM_MATCH_LENGTH`
(`test_symbol_without_roles_and_null_minimum_reports_invalid_minimum`);
symbol uruchamiający bez żadnych wypłat jest publikowalny
(`test_super_game_trigger_without_payouts_is_publishable`).

Zaakceptowane odstępstwa: (1) zyskanie roli Wild albo uruchamiającej czyści
minimum symbolu w wersjach `draft`, a utrata obu ról go nie przywraca —
operator ustawia minimum w zakładce reguł, raport gotowości to wymusza;
(2) nowy błąd `SUPER_GAME_KIND_IN_USE` przy zmianie rodzaju na `none`;
(3) wersje `archived` blokują role jak `published`; (4) kontrola wymiarów
obejmuje także wiersze (`payout_configuration_fits_dimensions`); (5) typ
`superGameTriggerCount` w odpowiedzi — po audycie wymagany; (6) leniwy import
rejestru w domenie katalogu, aby modele ORM i Alembic nie wymagały pakietu
workera; (7) dodatkowy `definition.py`, CHECK formatu `super_game_kind`,
„Wild” także w modalach reguł; (8) ścieżka endpointu — po audycie pod
`/admin`.

### Instrukcja operatora (Mumie)

Warunek wstępny (wykonuje operator, nie agent): po scaleniu operator zatrzymuje
API, Admin i workery, uruchamia `npm run db:migrate` (migracja
`0151_super_game_roles`; startowa kontrola schematu API wymaga teraz tego
wierzchołka i bez migracji API się nie uruchomi), a następnie uruchamia
ponownie `npm run api:dev` i `npm run admin:dev`. Migracja jest
addytywna: wszystkie istniejące gry, w tym 777, dostają `super_game_kind =
none`, a wszystkie symbole `super_game_trigger_count = null`.

1. Admin → zakładka **Zarządzanie grami** → na karcie gry **Mumie** kliknij
   **Edytuj**.
2. W formularzu gry w polu **Supergra** wybierz **Wild super spins**
   (pozostałe pola zostaw bez zmian) i kliknij **Zapisz zmiany**. Karta gry
   pokaże `Supergra: Wild super spins`.
3. Kliknij kartę gry **Mumie**, aby była aktywnym kontekstem, i rozwiń sekcję
   **Symbole**.
4. W wierszu symbolu **Mumia** kliknij **Edytuj**.
5. Zaznacz checkbox **Wild**, zaznacz checkbox **Uruchamia supergrę**, w
   odsłoniętym polu wybierz **Trzy symbole** i kliknij **Zapisz zmiany**.
   Karta Mumii pokaże znaczniki „Wild” i „Uruchamia supergrę: trzy symbole”.
   (Checkbox „Uruchamia supergrę” jest nieaktywny, dopóki krok 2 nie ustawi
   rodzaju supergry.)
6. Kontrola: rozwiń sekcję **Reguły** → **Payouty**. Mumia ma znaczniki
   „Wild” i „Uruchamia supergrę” oraz opis „Bez minimum · 3 wypłat za sztuki
   na planszy”. Po kliknięciu **Edytuj** przy Mumii pola mają etykiety
   „N sztuk na planszy” (N = 2…15). Istniejące wypłaty 3/4/5 → 20/200/2000
   pozostają bez zmian i od teraz oznaczają liczbę sztuk Mumii na planszy
   (w dowolnych miejscach), a nie długość ciągu na linii. Minimum Mumii w
   drafcie `v1` zostało wyczyszczone automatycznie w chwili zapisu roli.
7. Nie publikuj jeszcze wersji reguł Mumie. Do czasu TASK-0932 modal linii,
   przybliżona wygrana i worker liczą starym algorytmem `payout-v3` i nadal
   traktują Mumię jak symbol liniowy (a Wilda bez nowej semantyki); publikacja
   wersji z symbolem uruchamiającym przed TASK-0932 dałaby niezweryfikowane
   wyniki w tych widokach.

Role można zmieniać do czasu publikacji wersji reguł używającej symbolu; po
publikacji API odrzuca zmianę (`SYMBOL_RULES_IDENTITY_IN_USE`). Gra 777 nie
wymaga żadnej akcji (rodzaj „Brak”, brak ról specjalnych).

### Changed

- Commit v1.7.268 / 1aef5870ee22287b0e17f1278276cddf7793a9b5 (zapis dodany po commicie przez leada).

- Migracja `services/api/alembic/versions/0151_super_game_roles.py`
  (addytywna, po `0150_management_sessions`): `symbols.super_game_trigger_count
  smallint NULL` z CHECK `ck_symbols_super_game_trigger_count` (`IN (3,4,5)`),
  `games.super_game_kind text NOT NULL DEFAULT 'none'` z CHECK formatu kodu
  `ck_games_super_game_kind_format`; downgrade usuwa oba pola i oba CHECK-i.
  `storage/models.py` odwzorowuje kolumny i constrainty;
  `storage/schema_readiness.py` i `tests/test_schema_readiness.py` wskazują
  nowy wierzchołek `0151_super_game_roles`.
- Rejestr rodzajów supergry: nowy pakiet
  `services/worker/src/game_predictor_worker/domain/super_games/`
  (`__init__.py`, `definition.py` z `SuperGameKindDefinition`, `registry.py`
  z `none`/„Brak” i `wild_super_spins`, `wild_super_spins.py` ze stałymi
  `series_length = 10`, `retrigger_extension = 10`, `free_spin_cost = 0`).
  Funkcja oceny planszy serii pozostaje dla TASK-0936.
- Domena katalogu (`domain/catalog.py`, `application/catalog.py`):
  `Game.super_game_kind`, `Symbol.super_game_trigger_count`, walidacje
  `INVALID_SUPER_GAME_KIND`, `INVALID_SUPER_GAME_TRIGGER_COUNT`,
  `SUPER_GAME_KIND_REQUIRED` (trigger przy rodzaju `none`, także przy
  tworzeniu), `SUPER_GAME_KIND_IN_USE` (zmiana rodzaju na `none`, gdy symbol ma
  rolę). Blokada ról (`is_wildcard`, `super_game_trigger_count`) działa tylko
  dla symbolu w wersji `published`/`archived` (kod
  `SYMBOL_RULES_IDENTITY_IN_USE` zachowany). Zyskanie roli Wild albo
  uruchamiającej czyści w tej samej transakcji `minimum_match_length` symbolu
  we wszystkich wersjach `draft`. Kolejność walidacji: gra → rodzaj → wersje
  opublikowane → pola.
- Repozytorium katalogu (`storage/catalog_repository.py`,
  `storage/symbol_references_repository.py`): zapis i odczyt nowych pól,
  `symbol_is_used_in_published_rules`, `clear_draft_rule_minimums`,
  `game_has_super_game_trigger_symbols`.
- Domena reguł (`domain/rules.py`, `application/rules.py`,
  `storage/rules_repository.py`): `RulesSymbolDefinition.super_game_trigger_count`;
  symbol uruchamiający nie ma minimum (`SUPER_GAME_TRIGGER_MINIMUM_NOT_ALLOWED`),
  jego wypłaty to liczby sztuk `2..rows × columns`
  (`validate_count_payout_match_length`); gotowość publikacji wymaga rodzaju
  supergry (`SUPER_GAME_KIND_REQUIRED`), ściśle rosnących wypłat za sztuki,
  bez duplikatów i bez wymogu wypłaty dla każdej liczby; symbol uruchamiający
  nie liczy się jako zwykły symbol liniowy. Wild bez roli: reguły jak dotąd.
  `payout_configuration_fits_columns` zastąpiono
  `payout_configuration_fits_dimensions` (rows i columns), aby zmiana wymiarów
  nie zostawiła wypłaty za sztuki poza `rows × columns`.
- API: `superGameKind` w `GameCreate`/`GameUpdate`/`GameResponse`,
  `superGameTriggerCount` w `SymbolCreate`/`SymbolUpdate`/`SymbolResponse`
  (`schemas/catalog.py`, `api/catalog.py`; w odpowiedzi pole wymagane),
  nowy endpoint `GET /api/v1/admin/super-game-kinds` (`listSuperGameKinds`, router w
  `api/catalog.py`, rejestracja w `api/router.py`). OpenAPI i klient
  wygenerowane (`packages/admin-api-client/openapi/openapi.json`,
  `src/generated/{index,sdk.gen,types.gen}.ts`), wrapper
  `packages/admin-api-client/src/index.ts` (`listSuperGameKinds`, typ
  `SuperGameKindResponse`), test żądań
  `packages/admin-api-client/test/super-game-kinds-request.test.mjs`.
- Admin: katalog symboli (`features/symbols/*`) — etykieta „Wild” zamiast
  „Joker”, checkbox „Uruchamia supergrę” z selectem „Trzy symbole / Cztery
  symbole / Pięć symboli”, aktywny tylko przy rodzaju supergry gry ≠ „Brak”
  (zapisaną rolę zawsze można usunąć, jawne `null`), znaczniki na karcie.
  Gry (`features/games/*`) — select „Supergra” w tworzeniu i edycji z listą z
  `GET /admin/super-game-kinds` (fallback „Brak” + bieżąca wartość), znacznik na
  karcie, porównanie rodzaju przy uzgadnianiu utraconej odpowiedzi edycji.
  Reguły (`features/rules/payout-rules-*`, `rules-publication-modal.tsx`) —
  dla symbolu uruchamiającego pola „N sztuk na planszy” dla N = 2…rows×columns,
  puste pole = brak wypłaty (zapis wyłącza wcześniejszą wypłatę), bez minimum;
  etykiety Wild zamiast Joker; opisy nowych kodów gotowości.
- Testy: `services/api/tests/test_catalog_api.py`,
  `test_catalog_domain.py`, `test_rules_domain.py`, `test_rules_api.py`
  (fake'i repozytoriów), `integration/test_catalog_repository.py` (nowy test
  round-trip ról na PostgreSQL; świadomie zmieniona asercja starej blokady
  roli przy wersji `draft`), `services/worker/tests/test_super_game_registry.py`,
  testy Admin `game-catalog-*`, `symbol-catalog-*`, `payout-rules-*`,
  `rules-workspace-contract`.

### Verification results

Komendy z katalogu worktree.

- `.\.venv\Scripts\python.exe -m pytest services/api/tests -k "rules or catalog or games or super_game or schema" -q`
  — kolekcja przerywa się na istniejącym błędzie
  `services/api/tests/test_v7_independent_progress.py` (`ModuleNotFoundError:
  No module named 'test_v7_run_state'`; moduł jest w `services/worker/tests`).
  Z `--continue-on-collection-errors` (po rundzie poprawek): 125 passed,
  23 skipped, 1 failed, 1 error. Jedyny failed
  `test_game_data_v2_schema.py::test_manifest_is_exhaustive_disjoint_and_fail_closed`
  dotyczy tabel V7 (`semi_automatic_selection_v7_*`) spoza manifestu i
  istniał przed zadaniem.
- Skupione: `pytest services/api/tests/test_catalog_api.py test_catalog_domain.py
  test_rules_api.py test_rules_domain.py test_schema_readiness.py
  services/worker/tests/test_super_game_registry.py -q` — 72 passed (po
  rundzie poprawek).
- PostgreSQL (`$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'`):
  `pytest services/api/tests/integration/test_catalog_repository.py -q` —
  4 passed (w tym nowy round-trip ról, blokady po publikacji i CHECK-ów).
  `test_postgres_baseline.py::test_upgrade_downgrade_upgrade_cycle_on_postgres`
  — failed na istniejącej rozbieżności tabel `management_*` względem
  `EXPECTED_PUBLIC_TABLES` (niezwiązane). Dlatego cykl migracji sprawdzono
  osobnym skryptem na jednorazowej bazie
  `game_predictor_task0931_migration_test`: head → downgrade do
  `0150_management_sessions` (kolumny znikają) → head (kolumny wracają) — OK;
  baza usunięta. Bazy deweloperskiej `game_predictor` nie dotykano.
- `.\.venv\Scripts\python.exe -m alembic heads` — `0151_super_game_roles (head)`.
- `npm run openapi:generate`, potem `npm run openapi:check` — „OpenAPI
  artifact is current”, „Generated Admin API client is current”, exit 0.
- `npm run test --workspace @game-predictor/admin` — 679/679 pass.
- `npm run typecheck --workspace @game-predictor/admin` — exit 0;
  `npm run typecheck --workspace @game-predictor/reviewer` — exit 0 (po
  wymaganym polu i adapterach); `packages/board-search-ui` i
  `packages/admin-api-client` — exit 0.
- `npm run lint --workspace @game-predictor/admin` — 0 errors, 5 istniejących
  ostrzeżeń w plikach spoza zadania.
- `npm run test --workspace @game-predictor/admin-api-client` — 102/102 pass.
- `npx prettier --check` na zmienionych plikach TS/MJS — czysto.
- `npm run python:lint` — 2 istniejące błędy poza zadaniem
  (`storage/models.py:6940` I001 przy imporcie modeli management, obecny na
  HEAD; `services/worker/tests/test_page_geometry_preflight.py:345` E501).
  Zmienione pliki: `ruff check` i `ruff format --check` czyste.
- `mypy` zmienionych modułów API i pakietu `super_games` — „Success: no
  issues found”. Pełne `npm run python:typecheck` zatrzymuje się na
  istniejącym błędzie konfiguracji (`scripts/prepare_v7_reviewed_pilot.py`
  znaleziony pod dwiema nazwami modułu); `mypy services/api/src
  services/worker/src` — 33 istniejące błędy w 7 plikach poza zadaniem
  (`application/board_search_share_queries.py`,
  `api/v7_label_geometry_calibration.py`, `main.py`,
  `worker/images/shape_geometry_v2/core.py`, `contrast_frame_grid_v12.py`,
  `qualified_manual_geometry.py`, `page_geometry_preflight.py`).

### Not completed

- Ewaluator (`payout-v4-wild-count`), modal linii i przybliżona wygrana —
  TASK-0932. Do tego czasu modal linii liczy starym algorytmem i może
  pokazywać Mumię jako symbol liniowy; worker nie zna wypłat za sztuki.
- Nie uruchamiano API/Admin/workerów ani migracji na bazie operatora; dane
  Mumii nie były zmieniane przez agenta.
- Commit, `CURRENT_STATE.md`, przeniesienie taska i audyt krzyżowy należą do
  prowadzącego sesję.

### Documentation updates

- `ai_docs/architecture/DATA_MODEL.md` — `games.super_game_kind`,
  `symbols.super_game_trigger_count`, reguły ról, blokada po publikacji,
  czyszczenie minimum w draftach, wypłaty za sztuki w `payout_rules` i
  gotowości.
- `ai_docs/architecture/API_CONTRACT.md` — pola gry i symbolu, endpoint
  `GET /api/v1/admin/super-game-kinds`, nowe kody błędów i gotowości, Wild zamiast
  Joker w opisach UI.
- `ai_docs/requirements/ADMIN_APP.md` — select „Supergra”, checkbox „Wild” i
  „Uruchamia supergrę” z selectem, etykieta „sztuk na planszy”, gotowość,
  Wild zamiast Joker w etykietach UI (techniczne nazwy pozostały).

### Recommended next task

- TASK-0932 — ewaluator `payout-v4-wild-count` (Wild per linia, symbol
  uruchamiający poza liniami z dopasowaniem `count`), golden cases Python/TS,
  wybór wersji reguł (draft) w modalu linii i przybliżonej wygranej Adminu.
