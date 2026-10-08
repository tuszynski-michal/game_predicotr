# TASK-0931 — Wild, „Uruchamia supergrę” i rodzaj supergry w katalogu, regułach i grze

## Status

`todo`

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
przy konflikcie z gotowością wydania 777. Audyt: gpt-6-astra / high.

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
  retriggerze, koszt 0; API `GET /api/v1/super-game-kinds` zwraca listę z
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

- [ ] Symbol bez opublikowanej wersji reguł może zmienić Wild i
      „Uruchamia supergrę”; symbol w opublikowanej wersji nie może.
- [ ] Ustawienie „Uruchamia supergrę” dla gry z rodzajem `none` zwraca błąd
      walidacji z czytelnym kodem.
- [ ] Walidacja reguł: Wild z rolą uruchamiającą może mieć wypłaty 3/4/5;
      Wild bez niej nie może; gotowość wydania 777 bez zmian (testy istniejące).
- [ ] `GET /super-game-kinds` zwraca `none` i `wild_super_spins`.
- [ ] OpenAPI i klient bez driftu (`npm run openapi:check`).
- [ ] Formularze Adminu renderują nowe pola; testy stanu i kontraktu renderu.

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

Wypełnia agent po pracy. Musi zawierać instrukcję operatora: gdzie kliknąć,
aby ustawić Mumiom rodzaj „Wild super spins”, a Mumii Wild + „Uruchamia
supergrę” (3 symbole).

### Changed

### Verification results

### Not completed

### Documentation updates

### Recommended next task
