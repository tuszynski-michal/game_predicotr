---
title: TASK-0797 — ścieżki bez związanej gry, równoległość funkcji polityki RLS i resztka CHECK `legacy_file`
status: done
last_updated: 2026-10-01
---

# TASK-0797 — ścieżki bez związanej gry, równoległość funkcji polityki RLS i resztka CHECK `legacy_file`

## Status

`done` (audyt pominięty — decyzja operatora 2026-10-01; commit v1.7.135; migracja `0138` na bazie operatora po commicie)

## Goal

Każda ścieżka runtime, która dziś kończy się błędem z powodu braku
związanej gry (m.in. uwierzytelnienie sesji Reviewera tokenem), działa na
roli aplikacyjnej; funkcja polityki RLS nie blokuje planów równoległych;
CHECK zatwierdzeń komórek nie ma gałęzi `legacy_file`.

## Context

Następstwa D-467 zgłoszone w TASK-0795 i TASK-0796 (2026-10-01). Baza
operatora: `0137`, usługi działają rolą `game_predictor_app`
(`NOSUPERUSER NOBYPASSRLS`), tabele gry tylko w `game_data_v2` z wymuszonym
RLS (`game_id = game_data_v2.current_game_id_v1()`), `search_path`
ustawiany dopiero przy wiązaniu gry (`GameStorageRouter`).

Zgłoszone ścieżki, które według sondy TASK-0795 kończą się błędem dla obu
ról od migracji `0125` (tabele gry zniknęły z `public`):

1. Uwierzytelnienie sesji Reviewera tokenem na trasach bez `/games/{id}/`
   w ścieżce: `application/reviewer_access.py` (linia ok. 253) →
   `storage/reviewer_access_repository.py::find_by_token_hash` czyta
   `reviewer_access_sessions` (tabela gry) bez wiązania gry; dotyczy m.in.
   tras `image-review-items` (gra w parametrze `gameId`), czyli głównego
   obszaru pracy Reviewera przez tunel.
2. Podgląd storage GC.
3. Snapshot i release (`dataset_versions`) oraz `release_snapshot` w
   cleanupie; powiązane testy PG czerwone na HEAD
   (`test_production_snapshot_store`, `test_release_workflow_integration`,
   `test_mobile_release_repository`, `test_cleanup_repository`).
4. Inne znalezione tą samą metodą (zadanie ma je wyszukać testem, nie
   zgadywać).

Wydajność po przełączeniu roli: `current_game_id_v1()` jest `PARALLEL UNSAFE`
(plpgsql z blokiem `EXCEPTION`), więc zapytania roli aplikacyjnej nie
dostają workerów równoległych; pomiar TASK-0795 na 777: liczenie
oczekujących komórek wg symbolu 1,4 s → 3,6 s.

Resztka: `ck_image_symbol_review_cells_approved_provenance` ma gałąź
`approved_asset_mode IS NULL OR approved_asset_mode = 'legacy_file'`
(historyczne zatwierdzenia plikowe); na bazie operatora 0 wierszy z
`approved_asset_mode = 'legacy_file'` (TASK-0796) — sprawdzić także
gałąź `IS NULL` z niepustym `approved_crop_sample_id`.

## Dependencies / entry conditions

- Fakt: HEAD `v1.7.130` (TASK-0795), usługi na roli aplikacyjnej.
- Decyzja operatora 2026-10-01 („leć po kolei”): naprawić zgłoszone
  usterki; audyty zawieszone.
- Niewiadoma: który wariant odnajdywania gry dla tokenu Reviewera jest
  najmniej inwazyjny — do rozstrzygnięcia w zadaniu (patrz Scope).

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo). Audyt: zawieszony.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-467, decyzje o dostępie Reviewera)
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`
- `ai_docs/tasks/completed/0795-application-role-without-bypassrls.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`

## Scope

- Inwentaryzacja testem: uruchomić na bazie `*_test` w trybie
  `GAME_PREDICTOR_PG_TEST_ROLE=application` sondę wszystkich tras API
  (z OpenAPI) i handlerów workera pod kątem `42P01`/`42501`/
  `GAME_STORAGE_SCOPE_REQUIRED` przy braku wiązania; lista w Outcome.
- Uwierzytelnienie Reviewera: sesja Reviewera jest przypisana do gry i
  joba; trasa zna grę (ścieżka albo `gameId`) przed sprawdzeniem tokenu —
  związać grę z żądania i dopiero wtedy szukać tokenu (token z innej gry
  = brak sesji = 401/403, bez wycieku informacji); dla tras, które gry
  nie niosą, rozstrzygnąć: niewielka tabela indeksowa w `public`
  (`token_hash` → `game_id`, bez danych wrażliwych poza skrótem) albo
  funkcja `SECURITY DEFINER` zwracająca wyłącznie `game_id` dla skrótu;
  wybrać wariant o mniejszej powierzchni ataku, uzasadnić w modelu
  zagrożeń. Test PG przez prawdziwe `create_app` z sesją Reviewera na
  roli aplikacyjnej: logowanie, lista, podgląd, korekta geometrii,
  rozstrzygnięcie; token innej gry odrzucony.
- Storage GC, snapshot/release, cleanup `release_snapshot`: wiązanie gry
  per gra albo jawne połączenie właścicielskie (z komentarzem dlaczego);
  naprawa fixture testów PG tych obszarów, jeśli padają z powodu
  usuniętego magazynu `public` (testy mają wrócić do zieleni albo dostać
  uzasadnione usunięcie, gdy testują nieistniejącą już funkcję — jak
  `game_deletion_repository`/`test_resumable_game_deletion`).
- Migracja `0138_rls_policy_function_parallel_safe` (numer = kolejny
  wolny): `current_game_id_v1()` jako funkcja `STABLE PARALLEL SAFE`
  (SQL albo plpgsql bez bloku `EXCEPTION`; zachowanie bez zmian: brak
  ustawienia = błąd `GAME_STORAGE_SCOPE_REQUIRED`, nie `NULL`), polityki
  bez zmian; test PG: plan z `Gather` dla zapytania roli aplikacyjnej,
  izolacja z TASK-0795 nadal zielona. W tej samej migracji: usunięcie
  gałęzi `legacy_file` z `ck_image_symbol_review_cells_approved_provenance`
  (preflight 0 wierszy; `NOT VALID` + walidacja w runbooku jak w
  `0135`/`0136`), ORM zgodny. `EXPECTED_ALEMBIC_HEAD` + test.
- Dokumentacja: model zagrożeń Reviewera, `DECISION_LOG.md` (nota D-467),
  runbook cutoveru migracji, `CURRENT_STATE.md` zostawić orkiestratorowi,
  Outcome.

## Out of scope

- UI Reviewera (kwalifikacja częściowa w edytorze operacyjnym, błąd 500
  przy „corrected” ze zmianą numeru sekwencji) — TASK-0798.
- Zmiana modelu sesji Reviewera, tunel, nowe role.

## Acceptance criteria

- [ ] Sesja Reviewera z tokenem działa na wszystkich trasach z allowlisty
      proxy na roli aplikacyjnej (test PG przez `create_app`).
- [ ] Sonda tras: 0 ścieżek kończących się błędem braku wiązania gry
      (albo jawnie uzasadnione wyjątki w Outcome).
- [ ] `current_game_id_v1()` jest `PARALLEL SAFE`; test planu; izolacja
      gier bez regresji.
- [ ] CHECK zatwierdzeń bez `legacy_file`; ORM zgodny.
- [ ] ruff, mypy --strict, pytest zielone poza znanymi niepowodzeniami
      HEAD (lista ma się skrócić o naprawione obszary); `--collect-only` OK.

## Technical notes

- Wiązanie gry: `game_storage_scope` / `GameStorageRouter.bind`; middleware
  `game_id_from_path` wiąże tylko trasy z grą w ścieżce.
- Token Reviewera: porównanie skrótu w stałym czasie zostaje; blokady i
  licznik błędnych prób muszą działać także, gdy gra nie pasuje (nie
  wolno pozwolić na nielimitowane zgadywanie przez podanie cudzego
  `gameId`).
- Funkcja polityki: `current_setting('game_predictor.game_id', true)`
  zwraca `NULL`/pusty łańcuch przy braku — rzutowanie i jawny `RAISE`
  wymagają plpgsql; wariant SQL może użyć pomocniczej funkcji rzucającej
  błąd oznaczonej `PARALLEL SAFE`; zmierzyć plan na bazie operatora
  (tylko odczyt, `EXPLAIN` bez `ANALYZE` wystarczy).
- Chronione: dane operatora (tylko `SELECT`), polityki RLS, role.

## Expected files

- Zmienione: `application/reviewer_access.py`, `storage/reviewer_access_repository.py`,
  `api/reviewer_security.py` / zależności autoryzacji, storage GC,
  snapshot/release, cleanup, `storage/models.py`, `storage/schema_readiness.py`
  + test, testy PG wymienionych obszarów.
- Nowe: migracja `0138_…`, test PG sesji Reviewera na roli aplikacyjnej,
  sonda tras (test albo skrypt w `scripts/`).

## Verification

```powershell
$env:PYTHONPATH = "services/worker/src;services/api/src"
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m ruff check services/api/src services/worker/src scripts
.\.venv\Scripts\python.exe -m mypy --strict <zmienione moduły>
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; $env:GAME_PREDICTOR_PG_TEST_ROLE = 'application'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/<nowe i naprawione> -p no:cacheprovider --basetemp C:\Users\tuszy\AppData\Local\Temp\t797pg   # pojedynczo
```

## Risks / open questions

- Wariant wyszukiwania gry po tokenie zmienia powierzchnię ataku Reviewera
  — decyzja i uzasadnienie w modelu zagrożeń.
- Migracja funkcji polityki dotyka wszystkich zapytań roli aplikacyjnej;
  cutover jak poprzednie (stop → merge → `db:migrate` → start).

## Outcome

Stan 2026-10-01: kod, migracja `0138` i dokumentacja gotowe w worktree
`worktrees/symbol-reference-library` (HEAD `v1.7.130`), **niezacommitowane**;
audyt zawieszony. Status `in_progress` do commita i cutoveru orkiestratora.

### Changed

- Sonda: `test_unbound_game_route_probe_postgres.py` woła wszystkie 288
  operacji OpenAPI przez `create_app` na roli `LOGIN` bez `BYPASSRLS`
  (bazy `*_test`, dwie gry, ingress i wybór folderu zaślepione) i odrzuca
  każdy błąd braku wiązania gry. Stan wyjściowy: 53 trasy
  (`dataset-versions/*` 5, `image-selections/*` 19, `curated-sources*` 4,
  `browser-selections` DELETE i 5 tras `geometry-guards`, `image-review-cohort-exports`,
  `review-batches/*`, `review-items/*`, `review-feedback-exports/*` 12,
  `image-storage/gc-previews`, `mobile-releases` POST, Reviewer `unlock`,
  revoke, heartbeat/close przydziałów); wynik: 0, lista wyjątków pusta.
- Gra żądania: `game_id_from_request` — ścieżka `/games/{id}/` albo
  `gameId`/`game_id` tras `/api/v1/admin/` i `/api/v1/reviewer/` (nie tras
  publicznych udostępnienia i zdalnej selekcji).
- `GameEntityLocator` (`storage/game_entity_locator.py`): gra wiersza po
  globalnym id przez odczyty związane kolejno z każdą grą (RLS, jawny
  predykat gry, dwie gry = `GAME_SCOPED_RESOURCE_AMBIGUOUS`);
  `assign_session_game` (sesja zapamiętuje grę dla kolejnych transakcji).
  Domyślne zależności datasetów, selekcji, importu kuratorskiego, guard
  importu i przeglądu M5 wiążą grę z identyfikatora w ścieżce; brak gry →
  `404 GAME_SCOPED_RESOURCE_NOT_FOUND` (staging bez rekordu retencji —
  dalej bez gry). Guard (`get_scope`) i import kuratorski (`with
  game_storage_scope(payload.game_id)`) wiążą grę z body; `discard_unused`
  stagingu znajduje grę rekordu retencji.
- Reviewer: `SqlAlchemyReviewerAccessRepository(session, locator)` —
  `find_by_token_hash`, `get_for_update` wiążą grę żądania albo znalezioną;
  `scope_exists` wiąże podaną grę. Wariant: iteracja po grach z RLS zamiast
  tabeli indeksowej w `public` lub funkcji `SECURITY DEFINER` (model
  zagrożeń). Przydziały: `get`/`get_for_update` przez locator,
  `lock_scope` wiąże grę; limit online i decyzja o zatrzymaniu tunelu liczą
  nieprzeterminowane przydziały online **wszystkich** gier
  (`OtherGamesOnlineAssignments`), `list_active_online` ma jawny predykat
  gry; lifecycle przed każdą operacją odzyskuje przeterminowane przydziały
  innych gier w ich własnych transakcjach (gra w utrzymaniu jest pomijana z
  ostrzeżeniem).
- Ścieżki zależne od obejścia RLS znalezione po cutoverze TASK-0795 i
  naprawione: (1) limit 3 przydziałów online i zatrzymanie wspólnego tunelu
  widziały tylko bieżącą grę (tunel mógł zostać zatrzymany przy aktywnym
  przydziale innej gry); (2) `_GAME_ARTIFACTS_SQL` (pliki „shared” przy
  resecie gry), blokery `SHARED_MULTI_GAME_RELEASE` i współdzielone
  wykonania przy usuwaniu źródeł nie widziały innych gier (ryzyko usunięcia
  pliku używanego przez inną grę) — czytają teraz przez sesję właściciela.
  (3) `SHOW data_directory` w metrykach startu projekcji weryfikacji wymaga
  superusera; odmowa przerywała transakcję (`InFailedSqlTransaction`) —
  metryki w savepointach.
- Wydania (wiele gier w jednej transakcji z założenia): `CrossGameOwnerSession`
  (`create_cross_game_owner_session_factory`) — URL właściciela,
  `game_data_v2` w `search_path`, routing per instrukcja z bramą zapisu i
  domyślnym `game_id`, przełączanie gry zamiast `SCOPE_CONFLICT`, wiele gier
  w jednym flushu bez wiązania. Używają go: serwis wydań API, sprzątanie
  wydania (`/admin/mobile-releases/…`), kontrole współdzielenia w sprzątaniu
  gry, a w workerze build wydania (store, payouty wydania, snapshot).
- Storage GC: `normalization_dependency_statuses` i `browser_staging_sources`
  per gra; lista partii M5 per gra (`SqlAlchemyReviewRepository(session,
  session_factory)`).
- Migracja `0138_rls_policy_function_parallel_safe` (SQL poniżej w
  raporcie): funkcja `STABLE PARALLEL SAFE` bez bloku `EXCEPTION` (regex
  kształtu uuid), polityki bez zmian; CHECK zatwierdzeń bez gałęzi
  `legacy_file` (preflight `CELL_APPROVED_LEGACY_PROVENANCE_PRESENT`, `NOT
  VALID`); downgrade przywraca obie wersje. ORM zgodny,
  `EXPECTED_ALEMBIC_HEAD` = `0138` + test.
- Testy PG: nowe `test_reviewer_session_application_role_postgres.py`
  (2), `test_rls_policy_function_parallel_postgres.py` (4), sonda (1),
  wspólny `_application_role_database.py` (test izolacji przepięty);
  naprawione fixture `test_mobile_release_repository`,
  `test_production_snapshot_store`, `test_release_workflow_integration`,
  `test_cleanup_repository` (gry przez lifecycle, sesja wydań, aktualne
  stałe algorytmu, `expected_layout_count`), oczekiwanie w
  `test_game_storage_routing_postgres` (niezwiązana sesja = `42P01`, nie
  pusty wynik z `public`). Usunięty `test_resumable_game_deletion.py`
  (jednorazowe usunięcie gry z magazynu `public`, usuniętego w `0125`; brak
  trasy; usuwanie V2 testuje lifecycle).

### Verification results

- Tryb `GAME_PREDICTOR_PG_TEST_ROLE=application`, pojedynczo: izolacja 21/21,
  sonda 1/1 (288 tras, 0 niezwiązanych), `0138` 4/4 (`proparallel = s`,
  `Gather` z `Workers Launched` i polityką w workerach, kontrakt błędów,
  downgrade/upgrade, CHECK bez `legacy_file` + `VALIDATE`), sesja Reviewera
  2/2 (unlock, context games/jobs/symbols, lista, item, zdarzenia, źródło,
  pending, podgląd, korekta geometrii i rozstrzygnięcie z tokenem; token
  innej gry 401; blokada po 5 błędnych kodach; cudzy `gameId` = 404 bez
  sprawdzania kodu), routing 12/12, lifecycle 5/5, kompaktacja + migracja
  weryfikacji 2/2, rezolucja odroczona 9/9, geometria Reviewera 2/2,
  wyszukiwarka 9/9, projekcja 4/4, render 5/5, rekonsyliacja 5/5, katalog +
  retencja 3/3, sklep jobów 7/7, `image_batch_store` 15/15, wydania/snapshot/
  build/sprzątanie 5/5 (wcześniej czerwone), skrypty utrzymaniowe 3/3,
  remote/selekcja/raport/przegląd/payout 23/25 i game_data_v2 + coverage +
  M2 5/14 — niepowodzenia identyczne jak na HEAD (`layout_import_report` 1,
  `review_repository` 1, `board_import_coverage_repository` 8,
  `m2_admin_acceptance` 1).
- API unit: 20 niepowodzeń = znana lista HEAD; worker (CLI, backfill,
  kompaktacja, storage GC/inventory, payout, snapshot, release) 157/157.
  Ruff, mypy --strict zmienionych modułów i migracji czyste; `ruff format`
  czysty poza dwoma plikami niesformatowanymi już na HEAD;
  `--collect-only` 1902; OpenAPI bez zmian (`export_admin_openapi.py
  --check`); `git diff --check` czysty; brak pozostawionych ról i baz.
- Baza operatora (tylko odczyt, `EXPLAIN ANALYZE` w `READ ONLY`): liczenie
  oczekujących komórek 777 wg symbolu z predykatem obecnej funkcji 3,6 s
  bez workerów; z równoległym predykatem `current_setting(...)::uuid` (jak
  po `0138`) 1,7–1,9 s, `Gather Merge`, 2 workery. 0 komórek w gałęzi
  `legacy_file`.

### Not completed

- Commit, cutover `0138` na bazie operatora (orkiestrator, runbook).
- Sonda wywołuje każdą operację raz z syntetycznymi parametrami: ścieżki za
  walidacją body/nagłówków potwierdzenia (np. `X-Admin-Confirmation`) albo
  wymagające istniejących danych nie są przejęte w całości; handlery
  workera bez gry sprawdzone przeglądem i testami (GC, inventory, build
  wydania), nie osobną sondą.
- Znane czerwone testy spoza zakresu: `board_import_coverage_repository` 8
  (fixture zapisuje tabele gry bez wiązania), `m2_admin_acceptance`,
  `layout_import_report_repository`, `review_repository` (dane testowe).
- Martwy moduł `game_deletion_repository`/`game_deletion_archive` zostaje
  (bez trasy) — usunięcie to osobne sprzątanie.

### Documentation updates

- `REMOTE_REVIEWER_THREAT_MODEL.md` (wyszukanie sesji, wariant i
  odrzucone alternatywy, blokada przy cudzym `gameId`, wiersz tabeli),
  `DECISION_LOG.md` (nota TASK-0797 w D-467), `LOCAL_OPERATION_GUIDE.md`
  (cutover/wycofanie `0138`, walidacja CHECK), `GAME_DATA_V2_OWNERSHIP.md`.
  `CURRENT_STATE.md` — orkiestrator.

### Recommended next task

- TASK-0798 (UI Reviewera). Usunięcie martwego modułu usuwania gry z
  magazynu `public`; fixture `board_import_coverage_repository` przez
  wiązanie gry.
