---
title: Greenfield cutover na game_data_v2
status: done
last_updated: 2026-09-09
---

# TASK-0525 — Greenfield cutover na `game_data_v2`

## Goal

Po potwierdzeniu pustego katalogu gier skierować każdą przyszłą grę wyłącznie
do kompletnego, partycjonowanego magazynu `game_data_v2`, bez fallbacku zapisu
do legacy `public`.

## Dependencies / entry conditions

- TASK-0520–0524 są ukończone.
- Katalog gier jest pusty i został potwierdzony audytem TASK-0524.
- Baza użytkownika ma zastosowane migracje 0105–0110.

## Recommended execution

`gpt-6-astra high`; obowiązkowy audyt `gpt-6-astra high` obejmuje provisioning,
routing fail-closed i brak nowych zapisów game-owned do legacy.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/tasks/completed/0523-game-partition-lifecycle.md`
- zaakceptowany plan partycjonowania danych gier

## Scope

- Obowiązkowy, wznawialny provisioning 65 partycji przy tworzeniu gry.
- Registry w stanie maintenance przed utworzeniem partycji i aktywacja dopiero
  po walidacji pełnego manifestu.
- Fail-closed dla brakującego lub niekompletnego registry, bez legacy fallbacku.
- Poprawna projekcja statusu magazynu w API i blokady zapisu w Adminie.
- Odbiór pustego systemu oraz izolowane utworzenie gry testowej bez pozostawiania
  jej w bazie użytkownika.

## Out of scope

- Migrator danych, dual-write i kopiowanie danych historycznych.
- Usuwanie pustych tabel legacy lub historycznych migracji.
- Utworzenie pierwszej rzeczywistej gry użytkownika i jej pełny E2E (TASK-0526).
- Usuwanie managed assets.

## Acceptance criteria

- [x] Nowa gra nie może otrzymać aktywnego magazynu przed kompletem 65 partycji.
- [x] Każdy nowy zapis game-owned trafia do `game_data_v2`.
- [x] Brak registry lub nieaktywny registry daje kontrolowany błąd i nie używa `public`.
- [x] Retry po przerwaniu provisioningu wznawia checkpoint bez duplikatów.
- [x] Pusty katalog gier i globalne workflowy pozostają obsługiwane.
- [x] Admin pokazuje stan magazynu i blokuje akcje zapisu do aktywacji.

## Verification

Skoncentrowane testy jednostkowe i integracyjne PostgreSQL, testy API/Admina,
Ruff, scoped mypy, typecheck, OpenAPI, format check oraz kontrola rzeczywistego
manifestu bazy użytkownika bez tworzenia gry użytkownika.

## Risks / open questions

- TASK-0526 wymaga osobnej decyzji użytkownika o utworzeniu pierwszej gry.
- Historyczny odczyt bez registry jest świadomie wyłączany po potwierdzonym
  usunięciu wszystkich gier legacy.

## Outcome

### Changed

- Produkcyjny PostgreSQL nie pozwala już rejestrować nowej gry w legacy.
- Tworzenie gry uruchamia wznawialny provisioning 65 partycji i zwraca wynik
  dopiero po aktywacji V2 generacji 2.
- Brak registry jest widocznym stanem `blocked`, a data-plane zwraca
  `GAME_STORAGE_LOCATION_MISSING` bez fallbacku.
- Domyślna polityka geometrii powstaje w partycji V2 przed aktywacją location.
- Lifecycle używa jawnego control-plane SQL, dzięki czemu stan `migrating` nie
  blokuje własnego, zaufanego DDL. Błędy domenowe zachowują trwały status.

### Verification results

- Jednostkowe API/routing/lifecycle: 28 passed oraz końcowy zestaw 18 passed.
- Izolowany PostgreSQL lifecycle + greenfield create: 3 passed; routing: 4 passed.
- Admin: 448 passed.
- Ruff i scoped mypy passed; OpenAPI drift check passed.
- Prettier check zmienionej dokumentacji passed.
- Baza użytkownika: head 0110, `games=0`, manifest 65/65, parenty 65/65,
  partycje gier 0 i locations 0.
- Rzeczywisty GET `/api/v1/admin/games`: HTTP 200, `[]`.

### Not completed

- Nie utworzono pierwszej rzeczywistej gry. TASK-0526 wymaga osobnej decyzji
  użytkownika po tej bramce.
- Nie usunięto pustych tabel legacy ani managed assets.

### Documentation updates

- API_CONTRACT, DATA_MODEL, GAME_DATA_V2_OWNERSHIP, ADMIN_APP, DECISION_LOG i
  CURRENT_STATE.

### Recommended next task

- TASK-0526 po jawnej decyzji o tożsamości pierwszej gry.
