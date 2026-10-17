# Audyt TASK-1002 — Nagrania, aliasy i role kontrolne

Werdykt: REVISE
Audytor: claude-fable-5-1, reasoning high
Wykonawca: gpt-6.1-sol, reasoning high
Zakres: 477bf91ae3d3ab81bf6fc8d96cec38bc0dfef192...477bf91ae3d3ab81bf6fc8d96cec38bc0dfef192 oraz zmiany niezacommitowane, data 2026-10-15
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano cały pion: domenę, aplikację, schematy, router, zamrożony SQL v1, migrację 0161, uprawnienia capability, providerów, import LAB, skrypty wdrożeniowe, klienta OpenAPI, panel Admina oraz testy jednostkowe, PG i mounted. Sam mechanizm rejestru jest zgodny z kontraktem przed kodem: aliasy byte/pixel między grami, ochrona odziedziczonych holdoutów, fail-closed przy braku deklaracji, trwałość ról w PostgreSQL, trzy wejścia DEFINER i dokładne wyjątki uprawnień są poprawnie zaimplementowane i pokryte realnymi testami PG. Główne ryzyko leży poza nowym pionem: podniesienie manifestu do v14, nowe modele ORM oraz twardy warunek wstępny i bezwarunkowa odmowa downgrade w 0161 unieważniają istniejące testy regresyjne (jednostkowe i PG), suitę `db:baseline:verify` oraz kolejność kroków w kanonicznych komendach `db:migrate` i `db:reset:local`. Wykonawca uruchomił wyłącznie testy skoncentrowane, więc te regresje nie zostały wykryte ani zapisane w Outcome.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/api/tests/test_game_data_v2_schema.py:81` — test wymaga `set(Base.metadata.tables) <= known`, a `known` buduje z modułu v13; po zarejestrowaniu modeli `recording_*` w `storage/models.py` (`services/api/src/game_predictor_api/storage/models.py:6992-6994`) asercja nie może przejść. Analogicznie `services/api/tests/test_game_storage_routing.py:6` i `:28-36` porównują `_in_memory_v2` z `VERSION` v13, podczas gdy `game_storage_routing.py:18` używa v14; `services/api/tests/test_grid_geometry_proposals.py:74-77` wymaga `game_partition_lifecycle.VERSION == current.VERSION` (v13); `services/api/tests/test_grid_reinference_schema.py:48-49` wymaga równości `VERSION` trzech modułów runtime z v13. Skutek: `npm run python:test` i `npm run quality` są czerwone, czego Outcome nie zapisuje (uruchomiono tylko testy skoncentrowane). Poprawka: zaktualizować te testy do manifestu v14 według wzorca z TASK-1003 (w tym literał `game-data-v2-manifest-v13` tylko tam, gdzie testowany jest sam moduł v13), uruchomić pełny `npm run python:test` i zapisać wynik w Outcome.

- [P1-2] `services/api/alembic/versions/0161_source_recording_groups.py:22` oraz `:92-93` — migracja wymaga wcześniej sprovisionowanej roli capability i bezwarunkowo odrzuca downgrade, także dla pustego rejestru. Istniejące fixture PG migrują do `head` bez provisioningu (`services/api/tests/integration/test_postgres_baseline.py:184`, `services/api/tests/integration/test_board_search_share_repository.py:76`, `services/api/tests/integration/grid_reinference_schema_support.py:71` i dalsze wystąpienia `command.upgrade(config, "head")`), a wiele z nich wykonuje downgrade przez 0161 (`test_postgres_baseline.py:189`, `grid_reinference_schema_support.py:70`, `test_grid_model_publication_postgres.py:388`, `test_grid_model_registry_postgres.py:389`, `test_historical_grid_acceptance_postgres.py:68`). Skutek: suita integracyjna i `npm run db:baseline:verify` (`scripts/verify_postgres_baseline.ps1:44` uruchamia cały katalog) zatrzymują się na `RECORDING_CAPABILITY_REQUIRED` albo `RECORDING_DOWNGRADE_REFUSED`; dostosowano wyłącznie `_application_role_database.py`. Zachowanie jest też niezgodne z dokumentacją „Downgrade usuwający historię ochrony jest odrzucany” (`ai_docs/guides/SOURCE_RECORDING_GROUPS.md:24`), która sugeruje odmowę warunkową jak w `0160_grid_geometry_proposals.py:147-160`. Poprawka: wspólny helper provisionujący capability w fixture tworzących bazę do `head` (lub wywołanie `provision_recording_capability` w `isolated_database` i pokrewnych), downgrade odrzucany tylko przy istniejącej historii (puste tabele można usunąć i oddać własność) albo jawne zarejestrowanie 0161 jako nowej granicy nieodwracalności w stałych `test_postgres_baseline.py` wraz z dostosowaniem wszystkich wymienionych testów; po zmianie uruchomić `npm run db:baseline:verify` i zapisać wynik.

- [P1-3] `package.json:50` — `db:migrate` wykonuje `alembic upgrade head` przed `scripts/provision_database_roles.py` i bez flagi `--recording-capability`; `scripts/reset_local_admin_database.ps1:86-91` ma tę samą kolejność. Instrukcja (`ai_docs/guides/SOURCE_RECORDING_GROUPS.md:13-17`) wymaga kolejności odwrotnej. Skutek: kanoniczne komendy repozytorium kończą się blokerem `RECORDING_CAPABILITY_REQUIRED` na bazie deweloperskiej i operatora; naprawa jest opisana wyłącznie jako ręczny krok, co narusza regułę trwałości rozwiązań z `AGENTS.md` (sekcja „Trwałość rozwiązań”). Poprawka: dodać krok `provision_database_roles.py --recording-capability` przed `alembic upgrade head` w `db:migrate` i w skrypcie resetu (zachowując dotychczasowy provisioning roli aplikacyjnej po migracji), zaktualizować `LOCAL_OPERATION_GUIDE.md` i zapisać w `CURRENT_STATE.md`, że wdrożenie 0161 wymaga tej kolejności.

### P2

- [P2-1] `services/api/src/game_predictor_api/storage/source_recording_sql_v1.py:473-488` — dla `assign_role` head roli, zdarzenie i inkrement rewizji są zapisywane przed obliczeniem widoku, a dopiero potem `RECORDING_ROLE_CONFLICT`/`RECORDING_PROTECTED` daje 409. Stan jest więc utrwalony mimo odmowy (zachowawczo blokuje obie strony), ale kontrakt opisuje takie zachowanie tylko dla aliasu, a panel po 409 zachowuje starą rewizję, więc następne polecenie kończy się `RECORDING_REVISION_CONFLICT` do czasu odświeżenia. Propozycja: opisać to w instrukcji i Technical notes albo wykonywać upsert head po kontroli widoku; ryzyko można też zaakceptować jako świadomie konserwatywne.

- [P2-2] `services/api/src/game_predictor_api/storage/source_recording_permissions.py:62-67` i `:122-130` — tożsamość capability jest związana z nazwą i OID bazy, a po restore/rename/clone obiekty pozostają własnością starej roli; `provision_application_role` wtedy fail-closed (`:owner` w `recording_permission_errors`), a w repozytorium nie ma polecenia przenoszącego własność na nową rolę. Instrukcja zapowiada „jawny reprovision”, którego nie ma. Propozycja: zapisać ograniczenie w Outcome i instrukcji jako znane ryzyko wdrożeniowe albo zaplanować osobne narzędzie re-own w kolejnym tasku.

- [P2-3] `services/api/src/game_predictor_api/storage/source_recording_sql_v1.py:119-120` oraz `services/api/src/game_predictor_api/application/source_recording_groups.py:192` — atestacja strony jest „wszystko albo nic”: jedno zdjęcie bez zaufanego pixelSHA lub rewizji geometrii blokuje całą rejestrację importu kodem `RECORDING_SOURCE_IDENTITY_UNRESOLVED`, bez liczników nierozstrzygniętych źródeł, których wymaga kontrakt („Brak zaufanej tożsamości pokazuje własne unresolved counts”). Zachowanie jest bezpieczne, ale operator nie widzi, ile źródeł blokuje. Propozycja: przy `prepare` policzyć atestowalne źródła i zwrócić liczbę w widoku, albo odnotować odstępstwo w Technical notes.

- [P2-4] `services/api/src/game_predictor_api/storage/source_recording_sql_v1.py:267-268` — `RECORDING_BINDING_INVALID` jest podnoszone bez `ERRCODE` i nie ma go w mapie `_call` (`services/api/src/game_predictor_api/storage/source_recording_groups.py:82-96`), więc trafi do klienta jako 500. Osiągalne dopiero z producentami 0995/0997. Propozycja: dodać kod do mapy jako 422 przy kolejnym tasku producenta.

- [P2-5] `services/api/tests/integration/test_source_recording_groups_postgres.py:112` — fixture zapisuje `artifacts/audits/TASK-1002_PG_CLEANUP.json` ścieżką względną do CWD; przy innym katalogu roboczym lub braku `artifacts/audits` `write_text` w bloku `finally` podniesie wyjątek maskujący wynik testów. Propozycja: pisać do `tmp_path` albo ścieżki z jawnej zmiennej środowiskowej, a dowód kopiować poza testem.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Alias w innej grze zachowuje rolę. | spełnione | `source_recording_sql_v1.py:124-146` (domknięcie po byteSHA i pixelSHA bez filtra gry), `:189-194` (PROTECTED przy roli kontrolnej w komponencie); test `test_source_recording_groups_postgres.py:230-279` (VALIDATION w grze A blokuje TRAIN w grze B, bez ujawnienia obcych ID). |
| Holdout rodzica nie trafia do TRAIN dziecka. | spełnione | `source_recording_sql_v1.py:381-384` i `:407-431` (zapis ancestor/use z providera, TRAIN jako `use`), `source_recording_lab_import.py:563-593`; testy `test_source_recording_groups_postgres.py:627-706` i `:780-893`, `test_source_recording_lab_import.py:204-228`. |
| Brak deklaracji nie daje niezależności. | spełnione | `source_recording_sql_v1.py:181-183` (DECLARATION_REQUIRED dla każdej grupy komponentu), `:367-370` (declare wymaga kompletnego członkostwa); `domain/source_recording_groups.py:73-103` (brak providera = unresolved); testy `test_source_recording_groups_postgres.py:162-227`, `:323-363`. |
| Role przeżywają restart. | spełnione | head w `public.recording_role_heads` (`source_recording_sql_v1.py:58-63`), receipt replay z nowego procesu `test_source_recording_groups_postgres.py:280-320`, replay CLI `:950-985`. |
| Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu. | niespełnione | Outcome nie zapisuje pominięcia pełnego `python:test` i regresji manifestu v14 (P1-1), ani wpływu 0161 na istniejące fixture PG i `db:baseline:verify` (P1-2); instrukcja i `db:migrate` opisują sprzeczną kolejność (P1-3); opis downgrade w `SOURCE_RECORDING_GROUPS.md:24` nie odpowiada bezwarunkowej odmowie w `0161_source_recording_groups.py:92-93`. |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): nie dotyczy, runda 1.

Otwarte: P1-1, P1-2, P1-3, P2-1, P2-2, P2-3, P2-4, P2-5.

## Proponowane testy

- Pełny `npm run python:test` (lub `.\.venv\Scripts\python.exe -m pytest services/api/tests -q`) po aktualizacji testów manifestu do v14; dowód do Outcome.
- `npm run db:baseline:verify` z zapisanym wynikiem po dostosowaniu fixture PG i polityki downgrade 0161; w `services/api/tests/integration/test_postgres_baseline.py` dodać przypadek dowodzący albo warunkowego downgrade pustego rejestru, albo jawnej odmowy jako nowej granicy nieodwracalności.
- Test skryptowy kolejności `db:migrate` i `scripts/reset_local_admin_database.ps1` na izolowanej bazie: provisioning capability przed `alembic upgrade head`, potem provisioning roli aplikacyjnej, z asercją `recordingPermissionErrors == []`.
- Test PG dla `assign_role` kończącego się 409: asercja, czy head i rewizja mają pozostać zapisane, oraz test panelu sprawdzający odświeżenie rewizji po typed 409 (`apps/admin/test-interactions/recording-groups-panel.test.mjs`).
- Test PG dla `prepare` z importem zawierającym jedno źródło bez rewizji geometrii: oczekiwany widoczny stan nierozstrzygnięty z liczbą źródeł zamiast zablokowanej rejestracji, jeśli wykonawca wybierze realizację kontraktu z P2-3.

## Zakres przeglądu i ograniczenia

Przeczytano w całości: domenę, aplikację, schematy, router, `source_recording_sql_v1.py`, migrację 0161, `source_recording_permissions.py`, `source_recording_providers.py`, `source_recording_lab_import.py`, `source_recording_group_models.py`, manifest v14, zmiany w `database_roles.py`, `main.py`, `config.py`, `provision_database_roles.py`, oba skrypty wdrożeniowe, fixture `_application_role_database.py`, wszystkie nowe testy Pythona (jednostkowe i PG), wrapper klienta z testem żądania, pliki Admina (`recording-groups-panel.tsx`, `recording-registration.ts`, `recording-groups-command.ts`, `recording-groups-state.ts`, `recording-import-picker.tsx`) i test mounted panelu, diff plików śledzonych oraz dokumenty taska, D-554, instrukcję i fragmenty wymagań/architektury. Istniejące testy referencjonujące manifest v13 sprawdzono wyłącznie statycznie (`rg` i odczyt asercji); nie uruchamiano żadnych testów, migracji, generatora OpenAPI ani lintera, więc wyniki 78/8/19 PASS z Outcome przyjęto na podstawie plików dowodowych, a znaleziska P1-1 i P1-2 wynikają z analizy asercji, nie z wykonania. Nie weryfikowano `CODE_MAP_SYMBOLS.md` poza obecnością nowych modułów ani pełnej suity mounted Admina poza plikami tego taska.
