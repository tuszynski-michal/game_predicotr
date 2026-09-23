---
title: TASK-0629 — Definicja „planszy dodanej”, indeksy i repozytorium pokrycia
status: done
last_updated: 2026-09-24
---

# TASK-0629 — Definicja „planszy dodanej”, indeksy i repozytorium pokrycia

## Status

`done`

## Goal

Czysta domena i repozytorium zwracają poprawne liczniki, powody i segmenty
pokrycia importu plansz dla dowolnego okna numerów sekwencji, zgodnie z D-437.

## Context

Zakładka „Import plansz” nie pokazuje, których numerów sekwencji gry jeszcze
brakuje. Istniejąca karta „Kompletność zaakceptowanych plansz” liczy tylko
plansze zatwierdzone przez człowieka. Plan
(`ai_docs/tasks/0630-board-import-coverage-endpoint.md`,
`ai_docs/tasks/0631-missing-boards-admin-ui.md`) zastępuje ją sekcją
„Brakujące plansze” liczącą braki względem `1..expected_layout_count`. Ten
task dostarcza definicję i silnik obliczeniowy; endpoint i UI są kolejnymi
taskami.

## Dependencies / entry conditions

- Brak zależności od innych tasków.
- **Warunek wstępny wykonania:** przed napisaniem kodu domeny sprawdzić (grep)
  wszystkich twórców `ImageReviewItemModel`. Jeżeli którykolwiek żywy item
  powstaje bez kompletu 15 `cell_observations`, task się zatrzymuje i zgłasza
  konflikt z niezmiennikiem I1 zamiast kontynuować.
  - **Wynik sprawdzenia (2026-09-24):** jedyne miejsce tworzące
    `ImageReviewItemModel` to
    [pending_sequence_ownership.py](../../services/api/src/game_predictor_api/storage/pending_sequence_ownership.py)
    (`create_owned_pending_review_item`), wywoływane wyłącznie z
    [board_cell_geometry_pending_repository.py:575](../../services/api/src/game_predictor_api/storage/board_cell_geometry_pending_repository.py:575)
    i
    [virtual_grid_geometry_repository.py:816](../../services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py:816).
    Oba miejsca wołania wstawiają dokładnie 15 `CellObservationModel` (`zip(...,
    strict=True)` nad listą 15 komórek) przed wywołaniem funkcji tworzącej
    item. I1 potwierdzone — task odblokowany.

## Recommended execution

claude-opus-5-5, reasoning high. Uzasadnienie: semantyka danych, niezmiennik
I1 we wszystkich ścieżkach zapisu, SQL gaps-and-islands, routing
`game_data_v2` i migracja na dużej tabeli; błąd daje fałszywe braki lub
fałszywe „dodane”. Dodatkowy review: tak — claude-opus-5-5, xhigh (weryfikacja
definicji D-437, niezmiennika I1 i planu zapytań).

Uwaga wykonawcza: faktyczna implementacja tego taska (2026-09-24) wykonana
przez claude-sonnet-5 na wyraźną decyzję użytkownika, mimo niezgodności z
powyższym przypisaniem. Rekomendowany dodatkowy review (opus-5-5, xhigh)
pozostaje otwarty — patrz `Risks / open questions`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/process/DECISION_LOG.md` (wpis D-437)
- `ai_docs/requirements/ADMIN_APP.md`

## Scope

- Migracja `services/api/alembic/versions/0122_board_import_coverage_indexes.py`:
  - `ix_image_review_items_game_sequence_status` na `image_review_items(game_id,
    sequence_number, status)`;
  - częściowy `ix_recognized_boards_pending_partial` na `recognized_boards(id)
    WHERE completeness_status = 'pending_partial'`;
  - te same indeksy dla schematu `game_data_v2`
    (`services/api/alembic/sql/game_data_v2_schema_v1.sql`), jeśli zawiera
    odpowiedniki tych tabel;
  - `CONCURRENTLY` + `autocommit_block`, wzorem
    `0104_game_deletion_access_paths.py`; downgrade usuwa indeksy.
- `services/api/src/game_predictor_api/domain/board_import_coverage.py`
  (nowy): czyste typy i funkcja `build_coverage_page` + `count_missing_by_reason`
  wg definicji D-437 poniżej.
- Metoda repozytorium `board_import_coverage(game_id, window)` w zakresie
  `GameStorageRouter` (nowy plik
  `services/api/src/game_predictor_api/storage/board_import_coverage_repository.py`
  albo metoda w `image_review_repository.py` — wybór zostawiony wykonawcy,
  zgodnie z istniejącym stylem sąsiednich repozytoriów).
- Wpis `D-437` w `ai_docs/process/DECISION_LOG.md`.
- Aktualizacja `ai_docs/architecture/DATA_MODEL.md` (nowe indeksy, definicja
  „dodanej”).

## Out of scope

- Zmiany w pipeline, preflight, geometrii, cięciu, zatwierdzaniu.
- Manifest preflightu i guard jako źródło powodów braku.
- Endpoint HTTP i klient (`TASK-0630`).
- UI Admina (`TASK-0631`).

## Definicja D-437 (streszczenie; pełny wpis w DECISION_LOG.md)

**Plansza `n` gry `g` jest dodana** ⇔ `1 ≤ n ≤ expected_layout_count` oraz:

- (a) istnieje `image_sequence_canonical(g, n)`, albo
- (b) istnieje żywy `image_review_items` (`status ∈ {pending, accepted,
  corrected}`) z `game_id=g`, `sequence_number=n`, którego
  `recognized_boards.completeness_status = 'complete'`.

`added = (live ∪ canonical) − (partialPending − canonical)`. Zatwierdzenie
symboli nie wpływa na status. **Brakujące** = `{1..E} − added`.

**Powód braku**, pierwszy pasujący wg priorytetu:

| Prio | Kod | Warunek |
|---|---|---|
| 1 | `import_in_progress` | numer w zakresie `seq_*` pliku `processing` aktywnego joba importu gry |
| 2 | `waiting_for_geometry` | `image_board_geometry_pending.status='pending'` dla `n` |
| 3 | `partial_source` | żywy item `pending_partial`, brak canonical |
| 4 | `failed` | plik `failed` z zakresem `seq_*` obejmującym `n` |
| 5 | `rejected` | item `rejected` dla `n`, brak żywego |
| 6 | `unknown` | inny ślad w DB |
| 7 | `no_source` | żaden ślad |

Pełne przykłady wejście → wynik, tabela sygnałów i uzasadnienie — patrz treść
planu przekazana przez użytkownika 2026-09-24 (zachowana w historii sesji;
streszczenie trwałe żyje w D-437 i w tym pliku).

## Technical notes

- Domena działa jako sweep po posortowanych przedziałach: dopełnienie `added`
  w oknie, cięcie po granicach powodów, wybór powodu wg priorytetu, scalanie
  sąsiednich segmentów o tym samym powodzie, `limit+1` →
  `nextAfterSequenceNumber`.
- Repozytorium liczy wyspy `added` przez gaps-and-islands
  (`n - row_number() OVER (ORDER BY n)`) na `DISTINCT` numerach z `live ∪
  canonical − partial-only`, w oknie żądania.
- Jeden odczyt w jednej transakcji tylko do odczytu, żeby liczniki i lista
  segmentów były spójne między sobą.
- Routing: zapytania muszą działać w tym samym zakresie `GameStorageRouter`
  co istniejące `SqlAlchemyOperationalImageReviewRepository.dataset_completeness`.

## Expected files

- Nowe: `services/api/alembic/versions/0122_board_import_coverage_indexes.py`.
- Nowe: `services/api/src/game_predictor_api/domain/board_import_coverage.py`.
- Nowe: `services/api/tests/test_board_import_coverage.py`.
- Nowe (jeśli PG dostępny do uruchomienia): integracyjny test repozytorium.
- Istniejące: `ai_docs/process/DECISION_LOG.md`, `ai_docs/architecture/DATA_MODEL.md`.

## Test cases

Domena (unit, bez DB):

- przykłady wejście → wynik z tabeli w treści planu (4 scenariusze E=20);
- priorytet powodów przy nakładających się sygnałach;
- scalanie sąsiednich segmentów o tym samym powodzie;
- okno i kursor (`afterSequenceNumber`, `limit+1`);
- `E = 1`;
- segment `1..E` przy pustych danych (brak jakichkolwiek śladów).

Repozytorium (integracja PG, `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'`):

- item `pending`, board `complete`, bez canonical → dodana;
- tylko `geometry_pending`, żywy `pending_partial` → brakująca z właściwym
  powodem;
- numer bez żadnych rekordów → `no_source`;
- braki na początku, w środku i na końcu, `E = 20`;
- dwa nakładające się joby, superseded i canonical dla tych samych numerów →
  `added` liczone `DISTINCT`, `added + missing = E`;
- aktywny job z plikiem `seq_30-38` `processing` → `import_in_progress`;
- `geometry_pending` → rozwiązanie z utworzeniem itemu → dodana; reopen
  canonical → nadal dodana; kolejny `geometry_pending` dla dodanej → nadal
  dodana;
- historyczny canonical bez projekcji symboli → dodana;
- numery `> E` → `outOfRange`, nie `added`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_import_coverage.py --timeout=120
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_board_import_coverage_repository.py --timeout=120
npm run python:lint
npm run python:typecheck
```

`npm run db:migrate` na dev DB tylko za zgodą użytkownika. `EXPLAIN` (bez
`ANALYZE` na dużych danych) zapytania wysp na DB testowej, jeśli integracyjne
testy są uruchamiane.

## Risks / open questions

- Rekomendowany dodatkowy review (claude-opus-5-5, xhigh) dla definicji D-437,
  niezmiennika I1 i planu zapytań nie został jeszcze wykonany — task
  zaimplementowany na sonnet-5 na wyraźną decyzję użytkownika. Zalecane
  zaplanowanie tego review osobno.
- Koszt zapytania wysp przy ~500 tys. numerów jest szacowany, nie zmierzony;
  polling w UI (TASK-0631) ograniczy częstotliwość odpytywania.
- Cel `expected_layout_count` może być nieaktualnym ustawieniem — UI (TASK-0631)
  pokazuje źródło celu, ta warstwa tego nie rozstrzyga.

## Outcome

### Changed

- Nowy [domain/board_import_coverage.py](../../services/api/src/game_predictor_api/domain/board_import_coverage.py):
  czysta implementacja `SequenceInterval`, `MissingReason` (7 kodów z
  priorytetem), `ReasonSpan`, `CoverageSegment`, `CoveragePage`,
  `build_coverage_page` (sweep po granicach, scalanie sąsiadów o identycznej
  metadanej, keyset `limit+1`) i `count_missing_by_reason`.
- Nowy [storage/board_import_coverage_repository.py](../../services/api/src/game_predictor_api/storage/board_import_coverage_repository.py):
  `SqlAlchemyBoardImportCoverageRepository.board_import_coverage` — wyspy
  `added` przez gaps-and-islands (`n - row_number()`), 5 kategorii powodów
  (`waiting_for_geometry`, `partial_source`, `rejected`, `unknown`
  z żywych `superseded`, `failed`/`import_in_progress` z parsowania
  `seq_*` w plikach joba), liczniki (`approved`, `outOfRange`) i notices.
- Nowa migracja
  [0122_board_import_coverage_indexes.py](../../services/api/alembic/versions/0122_board_import_coverage_indexes.py):
  `ix_image_review_items_game_sequence_status` i częściowy
  `ix_recognized_boards_pending_partial` w `public` (CONCURRENTLY w
  `autocommit_block`, wzorem 0104); `game_data_v2` ma te same dwa indeksy
  jako zwykłe transakcyjne `CREATE INDEX` (wzorem 0108) — `CONCURRENTLY`
  nie działa tam wprost, bo tabele `game_data_v2` są partycjonowane.
- **Poprawka niepowiązanej, wcześniej scalonej migracji**
  [0114_v7_semi_automatic_activation_gate.py](../../services/api/alembic/versions/0114_v7_semi_automatic_activation_gate.py):
  dodano brakujące `schema="public"` do `op.create_table(...)` (i
  `op.drop_table(...)` w downgrade). Diagnoza: migracja `0105` świadomie
  ustawia `SET LOCAL search_path = pg_catalog, public` (pg_catalog jako
  pierwszy, by wymusić jawne kwalifikowanie schematu przez wszystkie kolejne
  migracje). PostgreSQL kieruje `CREATE TABLE` bez jawnego schematu do
  **pierwszego** schematu na `search_path` — czyli `pg_catalog` — co jest
  zablokowane nawet dla superusera (`allow_system_table_mods`). `0114` była
  jedyną migracją od `0106` łamiącą tę konwencję (sprawdzone skryptem po
  wszystkich `op.create_table` w `0106`+). Na już istniejącej bazie
  deweloperskiej błąd nigdy się nie ujawnił (tabela powstała, zanim `0105`
  wprowadziła restrykcyjny `search_path`), ale **każda świeża baza budowana
  przez `alembic upgrade head` — czyli każdy test integracyjny PostgreSQL w
  repo — się na tym wywalała**. Potwierdzone reprodukcją na izolowanym,
  minimalnym przykładzie (`SET LOCAL search_path` + `CREATE TABLE` bez
  schematu, poza całym łańcuchem migracji) oraz tym, że dokładnie ten sam
  błąd na tej samej migracji blokował istniejący, niepowiązany
  `test_review_repository.py`. Naprawiona za wyraźną zgodą użytkownika
  (pytanie zadane w sesji, wybrana opcja: naprawić).
- `ai_docs/process/DECISION_LOG.md`: nowy wpis D-437.
- `ai_docs/architecture/DATA_MODEL.md`: nowa sekcja „Pokrycie importu plansz
  (D-437) — TASK-0629".
- Testy: [test_board_import_coverage.py](../../services/api/tests/test_board_import_coverage.py)
  (22 przypadki domeny, w tym wszystkie przykłady z planu) oraz
  [integration/test_board_import_coverage_repository.py](../../services/api/tests/integration/test_board_import_coverage_repository.py)
  (8 scenariuszy repozytorium na realnym PostgreSQL).

### Verification results

- `pytest services/api/tests/test_board_import_coverage.py`: **22/22 passed.**
- `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; pytest
  services/api/tests/integration/test_board_import_coverage_repository.py`:
  **8/8 passed** na realnej, świeżo zmigrowanej (od `0001` do `0122`)
  izolowanej bazie PostgreSQL 18 (utworzonej i usuniętej przez fixture,
  nigdy `game_predictor` dev DB).
- Świeża baza migruje czysto `alembic upgrade head` (0 → `0122`) po
  poprawce `0114` — zweryfikowane bezpośrednio (skrypt tworzący/usuwający
  jednorazową bazę i wołający `command.upgrade(config, "head")`), nie tylko
  pośrednio przez test.
- Regresja: `test_review_repository.py` (niepowiązany, istniejący test)
  przechodzi teraz przez migracje do końca (wcześniej padał na tej samej
  `0114`); zatrzymuje się na osobnym, przedsesyjnym niepowiązanym problemie
  (`ReviewConflictError: REVIEW_REPORT_CHECKSUM_MISMATCH` — rozjazd
  checksumy fixture'u niezależny od tej zmiany, poza zakresem tego taska).
- `ruff check` na wszystkich nowych/zmienionych plikach (domena, repo, obie
  migracje, oba pliki testów): **czysto**.
- `mypy --strict` na `board_import_coverage.py` i
  `board_import_coverage_repository.py` osobno: **brak nowych błędów**
  (potwierdzone porównaniem z czystym `git stash` — te same 79 błędów
  importu `game_predictor_worker.*` istnieją już na gałęzi bazowej, więc są
  szumem niezależnym od tej zmiany).
- `npm run python:lint` / `npm run python:typecheck` na całym repo: **nie
  uruchomione jako całość** — sprawdzono punktowo jak wyżej; zalecane przed
  scaleniem.
- `EXPLAIN` planu zapytania wysp na dużych danych — niewykonane (poza
  zakresem bez realnych danych skali i bez zgody na benchmark).
- `npm run db:migrate` na dev DB — celowo pominięte (wymaga osobnej zgody
  użytkownika na modyfikację dev DB; migracja `0122` zweryfikowana wyłącznie
  na jednorazowych izolowanych bazach testowych).

### Not completed

- Rekomendowany dodatkowy review (claude-opus-5-5, xhigh) z sekcji
  `Recommended execution` nie został wykonany.
- `npm run python:lint` / `npm run python:typecheck` na całym repo (tylko
  punktowo na nowych plikach).
- Faktyczne uruchomienie migracji `0122` (i poprawki `0114`) na dev DB —
  wymaga osobnej zgody użytkownika.

### Documentation updates

- `ai_docs/process/DECISION_LOG.md`: D-437 dodany.
- `ai_docs/architecture/DATA_MODEL.md`: nowa sekcja „Pokrycie importu plansz
  (D-437) — TASK-0629" dodana na górze pliku.

### Recommended next task

- `TASK-0630` (endpoint i klient) — zależność spełniona: domena, repozytorium
  i migracja istnieją i są zweryfikowane integracyjnie.
- Osobno: rozważyć, czy poprawka `0114` (i sam pattern „`search_path` z
  `pg_catalog` na pierwszym miejscu od `0105`") wymaga wzmianki w
  `AGENTS.md`/`PLAN_STANDARD.md` jako pułapka dla przyszłych migracji
  tworzących nowe tabele bez `schema="public"`.
