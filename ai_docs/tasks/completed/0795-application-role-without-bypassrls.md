---
title: TASK-0795 — rola aplikacyjna bazy bez `SUPERUSER` / `BYPASSRLS`
status: done
last_updated: 2026-10-01
---

# TASK-0795 — rola aplikacyjna bazy bez `SUPERUSER` / `BYPASSRLS`

## Status

`done` (audyt pominięty — decyzja operatora 2026-10-01; commit v1.7.130; provisioning roli i przełączenie usług na bazie operatora po commicie)

## Goal

API i worker łączą się z bazą rolą `NOSUPERUSER NOBYPASSRLS`, dla której
RLS `game_data_v2` rzeczywiście izoluje gry; migracje i narzędzia
utrzymaniowe używają osobnej roli właściciela; test integracyjny
uruchomiony na roli aplikacyjnej potwierdza, że zapytanie bez związanej gry
nie widzi ani nie zmienia danych innej gry.

## Context

D-467 (dopisane po audycie S3). Fakty z bazy operatora (2026-10-01,
`0137`, tylko `SELECT`):

- Jedyna rola: `game_predictor` — `rolsuper = t`, `rolbypassrls = t`
  (tworzona przez `POSTGRES_USER` w `infra/docker/compose.yaml`), właściciel
  wszystkich obiektów.
- `game_data_v2`: 252 relacje (63 rodzice + partycje), RLS włączone i
  wymuszone (`FORCE ROW LEVEL SECURITY`) na 63 tabelach, 63 polityki
  `game_scope_v1`: `game_id = game_data_v2.current_game_id_v1()` (funkcja
  nie jest `SECURITY DEFINER`; czyta `game_predictor.game_id` ustawiane
  przez `GameStorageRouter._set_transaction_scope`). `public`: 45 tabel bez
  RLS.
- Superuser omija RLS, więc dziś każde zapytanie bez jawnego predykatu
  `game_id` czyta lub zmienia dane wszystkich gier (także ścieżki Reviewera
  przez tunel). W S3–S7 dopisywano jawne filtry `game_id` tam, gdzie
  znaleziono brak (kompaktacja pipeline, stale-check, sklep jobów).
- Konfiguracja: `GAME_PREDICTOR_DATABASE_URL` (jeden URL dla API, workera,
  skryptów i Alembica — `services/api/alembic/env.py` bierze go z
  `ApiSettings`), domyślnie `postgresql+psycopg://game_predictor:game_predictor_local@127.0.0.1:5432/game_predictor`.
- Testy PG tworzą bazy `*_test` jako superuser i działają jako superuser.

## Dependencies / entry conditions

- Fakt: HEAD `v1.7.125`, baza operatora `0137`, etapy S1–S8 zamknięte.
- Decyzja operatora 2026-10-01 („leć po kolei”): wykonać; audyty zawieszone.
- Założenie do zweryfikowania: istnieją ścieżki, które działają tylko dzięki
  obejściu RLS (zapytania między grami bez wiązania gry: katalog gier,
  lifecycle partycji, kompaktacja, statystyki, cleanup, skrypty) — zadanie
  musi je znaleźć (testem na roli aplikacyjnej), a nie zgadywać.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo). Audyt: zawieszony.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md` (TASK-0795)
- `ai_docs/process/DECISION_LOG.md` (D-467, decyzje o `game_data_v2` i RLS)
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`, `DATA_MODEL.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`, `DATABASE_MAINTENANCE.md`

## Scope

- Role: migracja Alembic (kolejny wolny numer, `0138`) albo skrypt
  provisioningu ról wołany z `db:up` tworzy rolę aplikacyjną
  `game_predictor_app` (`LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE`,
  hasło z konfiguracji lokalnej — nigdy w repo poza wartością domyślną dev
  analogiczną do obecnej) z uprawnieniami: `USAGE` na schematach,
  `SELECT/INSERT/UPDATE/DELETE` na tabelach `public` i `game_data_v2`,
  `USAGE` na sekwencjach, `EXECUTE` na potrzebnych funkcjach, domyślne
  uprawnienia dla przyszłych obiektów właściciela; bez własności, bez DDL.
  Operacje wymagające DDL w runtime (lifecycle partycji nowej gry /
  usuwanie gry, `VACUUM`/`ANALYZE` po kompaktacji, statystyki) — wskazać i
  rozstrzygnąć: osobne połączenie rolą właściciela dla tych ścieżek
  (`GAME_PREDICTOR_OWNER_DATABASE_URL`) albo funkcje `SECURITY DEFINER`;
  wybrać wariant o mniejszej powierzchni i opisać.
- Konfiguracja: `ApiSettings` z dwoma URL-ami (aplikacyjny dla API/workera,
  właścicielski dla Alembica, skryptów utrzymaniowych i ścieżek DDL);
  walidacja loopback bez zmian; `alembic/env.py` i skrypty migracyjne
  używają URL właściciela; dokumentacja zmiennych w `.env.example`.
- Kod: każda ścieżka dotykająca tabel gry wiąże grę przez
  `GameStorageRouter` zanim wykona zapytanie; ścieżki między grami
  (lista gier, raporty zajętości, kompaktacja, cleanup, joby bez gry)
  iterują po grach z osobnym wiązaniem albo używają połączenia
  właścicielskiego — jawnie, z komentarzem dlaczego.
- Testy: tryb uruchamiania testów PG na roli aplikacyjnej (fixture tworzy
  rolę w bazie `*_test`, sesje testowe łączą się jako ta rola); nowy test
  izolacji: dwie gry, zapytanie/UPDATE bez wiązania → 0 wierszy; zapytanie
  z wiązaniem gry A nie widzi B; próba DDL rolą aplikacyjną odmawia;
  istniejące testy PG kluczowych ścieżek (import wirtualny, rezolucja
  odroczonej planszy, weryfikacja symboli, wyszukiwarka, biblioteka
  wzorców, kompaktacja, lifecycle) przechodzą na roli aplikacyjnej —
  lista przebiegów i wyników w Outcome.
- Runbook `LOCAL_OPERATION_GUIDE.md`: cutover (utworzenie roli, zmiana
  `GAME_PREDICTOR_DATABASE_URL` we wszystkich checkoutach/worktree,
  restart usług, wycofanie = powrót do URL właściciela), wpływ na inne
  sesje (API 8110 itp.).
- Dokumentacja: `DECISION_LOG.md` (nowa decyzja albo nota D-467),
  `REMOTE_REVIEWER_THREAT_MODEL.md` (izolacja gier egzekwowana przez RLS),
  `GAME_DATA_V2_OWNERSHIP.md`, plan, Outcome.

## Out of scope

- Zmiana hasła/roli na bazie operatora i przełączenie URL-i (orkiestrator
  po zadaniu, według runbooka).
- Zmiana modelu partycji i polityk RLS; szyfrowanie; role per gra.

## Acceptance criteria

- [ ] Rola aplikacyjna bez `SUPERUSER`/`BYPASSRLS`; API i worker startują
      i przechodzą testy PG na tej roli.
- [ ] Test izolacji gier zielony; zapytanie bez wiązania gry nie zwraca
      danych gry.
- [ ] Migracje i ścieżki DDL działają przez URL właściciela; brak DDL na
      roli aplikacyjnej.
- [ ] Lista ścieżek naprawionych (brak wiązania gry) w Outcome; `git grep`
      nie znajduje zapytań na tabelach gry poza wiązaniem bez uzasadnienia.
- [ ] ruff, mypy --strict, pytest zielone poza znanymi niepowodzeniami
      HEAD; `--collect-only` OK.

## Technical notes

- RLS jest wymuszone także dla właściciela, ale superuser je omija —
  rola właścicielska do migracji może pozostać superuserem lokalnie;
  runtime nie.
- `current_game_id_v1()` rzuca przy braku ustawienia — zapytanie bez
  wiązania kończy się błędem albo 0 wierszy; testy muszą ustalić które i
  kod ma traktować to jako błąd programisty (jawny kod), nie pusty wynik.
- Pule połączeń: wiązanie gry jest `SET LOCAL` w transakcji (zostaje).
- Wydajność: polityki RLS dodają predykat `game_id` → pruning partycji;
  zmierzyć 2–3 gorące zapytania 777 przed/po (tylko odczyt).
- Chronione: dane operatora; żadnych zmian ról na `game_predictor` w tym
  zadaniu poza testami na bazach `*_test`.

## Expected files

- Nowe: migracja `0138_application_role.py` albo `scripts/provision_database_roles.py`
  (+ wpis `package.json`), test izolacji
  `services/api/tests/integration/test_application_role_isolation_postgres.py`.
- Zmienione: `config.py` (API i worker), `alembic/env.py`, `storage/database.py`,
  ścieżki DDL/między grami, `.env.example`, runbooki, docs.

## Test cases

- Rola aplikacyjna: `SELECT` z tabeli gry bez wiązania → błąd/0 wierszy;
  z wiązaniem A → tylko A; `UPDATE` bez `game_id` w predykacie przy
  wiązaniu A nie zmienia B; `CREATE TABLE` → odmowa.
- Provisioning nowej gry i usunięcie gry (DDL) działają przez połączenie
  właścicielskie przy API na roli aplikacyjnej.
- Job workera bez `game_id` (kompaktacja) kończy się poprawnie.
- Alembic `upgrade head` na URL właściciela; start API na URL aplikacyjnym
  (`ALEMBIC_HEAD_MISMATCH` nadal działa).

## Verification

```powershell
$env:PYTHONPATH = "services/worker/src;services/api/src"
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m ruff check services/api/src services/worker/src scripts
.\.venv\Scripts\python.exe -m mypy --strict <zmienione moduły>
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_application_role_isolation_postgres.py -p no:cacheprovider --basetemp C:\Users\tuszy\AppData\Local\Temp\t795pg
# kluczowe pliki PG pojedynczo, sekwencyjnie (pamięć hosta)
```

## Risks / open questions

- Ukryte zależności od obejścia RLS — główne ryzyko regresji; cutover na
  bazie operatora dopiero po zielonych testach na roli aplikacyjnej,
  z szybkim wycofaniem (powrót do URL właściciela).
- Inne sesje/worktree używają tego samego URL-a; przełączenie wymaga
  koordynacji (runbook).

## Outcome

Stan 2026-10-01: kod i dokumentacja gotowe w worktree
`worktrees/symbol-reference-library` (gałąź `feat/symbol-reference-library-port`,
HEAD `v1.7.125`), **niezacommitowane**; audyt zawieszony przez operatora.
Status pozostaje `in_progress` do commita i cutoveru orkiestratora.

### Changed

- Decyzja: provisioning roli skryptem zamiast migracji `0138` — role są
  globalne w klastrze, a migracje biegną też na jednorazowych bazach `*_test`
  tego samego klastra (migracja tworzyłaby `game_predictor_app` przy każdym
  teście). Nowy moduł `storage/database_roles.py`
  (`provision_application_role`, `describe_application_role`, weryfikator
  SCRAM — hasło nie trafia do treści SQL) i `scripts/provision_database_roles.py`
  (`--check` tylko czyta; pomija, gdy oba URL-e mają tego samego
  użytkownika). `package.json`: `db:roles:provision`, `db:roles:check`,
  provisioning na końcu `db:up` i `db:migrate`; `db:reset:local` używa URL-a
  właściciela i provisionuje po migracji.
- Uprawnienia roli: `LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE
  NOREPLICATION NOINHERIT`, bez członkostw (odmowa, gdy istnieją), `CONNECT`,
  `USAGE` na `public`/`game_data_v2`, DML na tabelach, `public.alembic_version`
  tylko `SELECT`, `USAGE, SELECT` na sekwencjach, `EXECUTE` na funkcjach,
  `ALTER DEFAULT PRIVILEGES FOR ROLE <właściciel>` (tabele, sekwencje,
  funkcje, schematy). Raport zgodności odrzuca rolę z atrybutami, własnością
  obiektów, brakami uprawnień albo zapisem `alembic_version`.
- `config.py`: `GAME_PREDICTOR_DATABASE_URL` = rola aplikacyjna (nowa
  wartość domyślna `game_predictor_app:game_predictor_app_local`),
  `GAME_PREDICTOR_OWNER_DATABASE_URL` → `ApiSettings.owner_database_url`
  (domyślnie lokalny właściciel na bazie z URL-a runtime; obiekt tworzony w
  kodzie bez właściciela używa URL-a runtime). Walidacja loopback bez zmian
  dla obu; inny host/port/baza właściciela → `ConfigurationError`.
- `storage/database.py`: `create_owner_database_engine` (NullPool, ścieżki
  runtime), `create_maintenance_database_engine` (skrypty),
  `create_owner_session_factory` (zwykłe sesje bez routingu).
  `alembic/env.py` używa URL-a właściciela.
- Ścieżki wymagające właściciela (znalezione testami na roli aplikacyjnej):
  1. tworzenie gry w API (`SqlAlchemyCatalogRepository`): `CREATE TABLE …
     PARTITION OF` → `permission denied for schema game_data_v2`; teraz każdy
     krok `run_next` w osobnej sesji właściciela
     (`partition_ddl_session_factory`, wstrzykiwane w `create_app`), wiersz
     gry i receipt w sesji aplikacyjnej;
  2. `VACUUM (ANALYZE)` po kompaktacji pipeline — PostgreSQL tylko ostrzega i
     pomija dla nie-właściciela; worker przekazuje silnik właściciela;
  3. `ANALYZE` po backfillu weryfikacji symboli — j.w. (cichy brak
     statystyk); handler dostaje `statistics_session_factory` właściciela
     (ANALYZE przed commitem finalizacji, nieudane odświeżenie nadal cofa
     `ready`), a `refresh_symbol_review_query_statistics` kwalifikuje tabele
     `game_data_v2.` i odmawia jawnie roli bez własności.
- Nie znaleziono ścieżki runtime, która czytałaby lub zmieniała dane innej
  gry dzięki obejściu RLS: wszystkie niekwalifikowane zapytania na tabelach
  gry już wcześniej wymagały wiązania (bez niego `search_path` nie zawiera
  `game_data_v2`), więc zachowują się tak samo dla obu ról. Zaktualizowano
  dwa nieaktualne komentarze „rola omija RLS”.
- Skrypty operatorskie (`scripts/*.py`, 30 plików) używają URL-a/silnika
  właściciela (zachowanie jak dotąd); `run_concurrent_worker_lane_acceptance`
  przekazuje procesom potomnym oba URL-e bazy testowej.
- Testy: `tests/integration/conftest.py` — tryb
  `GAME_PREDICTOR_PG_TEST_ROLE=application` (rola
  `game_predictor_app_test_<hex>` `NOLOGIN`, uprawnienia tylko w
  jednorazowych bazach, `SET LOCAL ROLE` dla każdej `GameStorageSession`
  łączącej się jako właściciel, wstrzyknięcie fabryki DDL właściciela do
  repozytorium katalogu jak w `create_app`, usunięcie roli na końcu sesji);
  nowy `test_application_role_isolation_postgres.py` (21 przypadków);
  fixture PG przełączone na `owner_database_url`; test lifecycle używa
  fabryki DDL i nie odpytuje usuniętej w `0125` tabeli publicznej; sesje
  SUT `test_board_search_approximate_win_repository` jako
  `GameStorageSession`; dwa testy jednostkowe API (`test_image_imports_api`,
  `test_lateral_managed_reprocess`) nadpisują zależność kanonu zamiast
  czytać lokalną bazę `game_predictor`; testy konfiguracji, statystyk,
  backfillu i CLI workera.

### Verification results

- Test izolacji na roli `LOGIN` (21/21, w obu trybach): bez wiązania
  `SELECT`/`UPDATE`/`DELETE` na `game_data_v2.*` → `42501
  GAME_STORAGE_SCOPE_REQUIRED` (także pusta tabela), ORM bez wiązania →
  `42P01`; związanie A widzi tylko A (ORM i surowy SQL), `UPDATE`/`DELETE`
  bez predykatu zmienia 1 wiersz A, B nietknięte; przeniesienie wiersza do B
  i `INSERT` dla B → `42501`; `SET ROLE` na właściciela, `row_security=off`,
  `CREATE TABLE`/`SCHEMA`, `ALTER/DROP` RLS i polityki, `TRUNCATE`, `DROP
  TABLE`, `ALTER TABLE`, zapis `alembic_version` → odmowa, `VACUUM` bez
  efektu; `pg_database_size` działa; `require_alembic_head` i API
  (`create_app`) na roli aplikacyjnej: lista gier, utworzenie gry przez HTTP
  (partycje należą do właściciela, rola nie ma obiektów).
- Suity PG w trybie roli aplikacyjnej (pojedynczo): lifecycle 5/5, routing
  11/12 (znane `grid_review_source_asset`), kompaktacja 1/1, rezolucja
  odroczonej planszy 9/9, korekta geometrii Reviewera 2/2, przybliżona
  wygrana 2/2, udostępnianie 7/7, projekcja weryfikacji/wyszukiwarki 4/4,
  outside owner + render specs 2/2, rekonsyliacja plansz częściowych 5/5,
  manifesty renderu + migracja weryfikacji 4/4, katalog + retencja stagingu
  3/3, `test_worker_job_store` 7/7, `test_image_batch_store` 15/15,
  remote selection/selekcja/raport importu/release/review 22/25, payout 1/1,
  slim/konwersja/`0136` 3/3, game_data_v2 + coverage 5/13 (znane 8).
  Niepowodzenia identyczne w trybie właściciela (sprawdzone):
  `test_m2_admin_acceptance` (422 payload symbolu),
  `test_production_snapshot_store`, `test_release_workflow_integration`,
  `test_mobile_release_repository` (niezwiązane `dataset_versions`),
  `test_layout_import_report_repository`, `test_review_repository`.
- Provisioning na jednorazowej bazie: `--check` przed → `exists=false`, kod
  1; provision → `compliant=true`, logowanie SCRAM działa; konfiguracja
  wycofania → `skipped`; świeża baza: provisioning przed migracjami →
  po `alembic upgrade head` raport wykrył zapisywalne `alembic_version`
  (domyślne uprawnienia) — stąd provisioning po `db:migrate`.
- API unit: 20 niepowodzeń = dokładnie znana lista HEAD (`test_reviews` 6,
  `test_image_import_geometry_guard_api` 7, `test_openapi_contract` 2,
  `test_virtual_grid_geometry` 2, `test_image_symbol_reviews_api` 1,
  `test_migration_baseline` 1, `test_lateral_managed_reprocess` 1); worker:
  CLI, backfill, kompaktacja, storage GC/inventory, biblioteka wzorców,
  benchmarki skryptów — 109/109. Ruff, `ruff format --check`, mypy --strict
  zmienionych modułów czyste; `pytest services/api/tests --collect-only`
  1895; `git diff --check` czysty.
- Pomiar 777 (tylko odczyt, `EXPLAIN ANALYZE` w transakcji `READ ONLY`,
  predykat polityki dodany ręcznie do zapytania właściciela): liczba
  oczekujących komórek wg symbolu 1,40 s → 3,64 s (brak workerów
  równoległych: `current_game_id_v1()` jest `PARALLEL UNSAFE`), dokumenty
  wyszukiwarki w zakresie 20 000 sekwencji i strona review items bez zmian
  planu (index scan, ms).

### Not completed

- Cutover na bazie `game_predictor` (utworzenie roli, restart usług) —
  orkiestrator, według `LOCAL_OPERATION_GUIDE.md`.
- Ścieżki bez wiązania gry, które kończą się błędem dla **obu** ról od
  `0125` (nie zależą od RLS, nie naprawione — poza zakresem): logowanie
  tokenem Reviewera na trasach bez `/games/{id}/`
  (`SqlAlchemyReviewerAccessRepository.find_by_token_hash`), podgląd storage
  GC (`SqlAlchemyStorageGcRepository.normalization_dependency_statuses`,
  `browser_staging_sources`), magazyn snapshotu/release
  (`dataset_versions`), `SqlAlchemyCleanupRepository.release_snapshot`
  (`mobile_release_games`) — sonda na bazie testowej: `relation … does not
  exist` dla właściciela i roli aplikacyjnej. Kryterium „`git grep` bez
  zapytań poza wiązaniem” nie jest więc w pełni spełnione.
- Testy `test_image_import_geometry_guard_api` (znane 7) łączą się z lokalną
  bazą `game_predictor` przez domyślną zależność; po cutoverze zrobią to rolą
  aplikacyjną.
- Commit (bez polecenia), audyt (zawieszony).

### Documentation updates

- `DECISION_LOG.md` (nota TASK-0795 w D-467), `GAME_DATA_V2_OWNERSHIP.md`
  (role i kontrakt zapytań), `REMOTE_REVIEWER_THREAT_MODEL.md` (zagrożenie
  „dane innej gry przez błąd zapytania”), `LOCAL_OPERATION_GUIDE.md` (runbook
  cutover/wycofanie, wpływ na inne worktree, tryb testów), plan D-467,
  `CURRENT_STATE.md`, `.env.example`.

### Recommended next task

- Funkcja polityki bez bloku `EXCEPTION` i `PARALLEL SAFE` (migracja; dziś
  ok. 2,6× wolniejsze duże skany roli aplikacyjnej) — przed albo zaraz po
  cutoverze, z pomiarem.
- Wiązanie gry (iteracja po grach) dla ścieżek wymienionych w „Not
  completed”, zaczynając od logowania tokenem Reviewera.
