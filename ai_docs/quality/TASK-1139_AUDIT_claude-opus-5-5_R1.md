# Audyt TASK-1139 — Przyrostowy podział i prawdziwe liczniki

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: HEAD...3562ab1a868ae26cb2c36bf453197c1790561015 oraz zmiany niezacommitowane, data 2026-11-03
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem politykę `application-grid-corrections-v2` (solver chronionych wysp), migrację 0172 z historią zwolnień i nowymi funkcjami SQL rejestru, adapter podziału, liczniki `progressCounts` (backend → OpenAPI → klient → test żądania) oraz zmiany w workerze dotyczące v1/v2. Logika domenowa i atomowość freeze są spójne z D-582: preview tylko czyta, a zwolnienia i przydziały zapisują się w jednej transakcji freeze. Rzeczywiste użycia, bufory i rezerwy v2 są twardo chronione.

Commit blokują dwa problemy:
- migracja 0172 bezwarunkowo odmawia downgrade, przez co psuje istniejące testy PostgreSQL, które schodzą z head;
- brakuje wymaganego testu ochrony holdout/ancestor/sesji w ścieżce zwolnień SQL.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/api/alembic/versions/0172_grid_correction_growth.py:52` — `downgrade()` zawsze rzuca `RuntimeError`, także przy pustej historii zwolnień i braku wierszy `incremental-v2`.
  - Kilka istniejących testów PostgreSQL migruje bazę do head, a potem schodzi poniżej 0172: `services/api/tests/integration/grid_reinference_schema_support.py:72` (fixture modułów `test_grid_reinference_postgres.py` i `test_grid_reinference_stats_postgres.py`), `test_recording_migration_lifecycle_postgres.py:72`, `test_source_crop_runs_postgres.py:192`, `test_grid_model_evaluation_bridge_postgres.py:70`. Dla tych testów `_application_role_database.py:123` ma domyślnie `revision="head"`.
  - Skutek: te testy i cykl migracji (`db:baseline:verify`) przestaną przechodzić. To łamie kryterium „Testy … PostgreSQL … przechodzą”. Wykonawca uruchomił tylko jeden plik PG, więc tego nie wykrył.
  - Wzorzec 0170/0171 to odmowa wyłącznie przy istniejącej historii.
  - Poprawka:
    - downgrade odmawia tylko wtedy, gdy istnieją wiersze w `recording_photo_reservation_releases` albo `reservation_policy='incremental-v2'`;
    - w przeciwnym razie odtwarza ciała `recording_photo_context_v1`, `recording_photo_cohort_v1` i wrappera v5, usuwa `recording_photo_context_v2` i `recording_photo_context_data_v2`, tabelę zwolnień oraz kolumnę `reservation_policy`;
    - następnie trzeba uruchomić wymienione pliki PG na disposable DB.

- [P1-2] `services/api/src/game_predictor_api/storage/source_recording_sql_v6.py:73` — o tym, czy rezerwację można zwolnić, decyduje między innymi `external_protection` (linie 73–85): `recording_role_heads`, `recording_evidence` rodzajów `holdout`, `ancestor` i `use` oraz domknięcie grup sesji.
  - Task wymaga przypadków testowych „alias/sesja/holdout/ancestor”. Test PG `_assert_incremental_release` (`services/api/tests/integration/test_grid_correction_registry_postgres.py:289`, komentarz w linii 300) pokrywa tylko rezerwę v2, użytą kopię bajtową i bufor. Nie ma testu, w którym nieużyta rezerwacja legacy w komponencie z holdoutem, ancestorem, role head albo użytą sesją (`group_ids`) pozostaje niezwolniona i zachowuje `priorRoles`. Brakuje też testu, w którym sprzeczna lub bezrolowa ochrona daje `GRID_CORRECTION_PROTECTION_CONFLICT`.
  - Skutek: główna gwarancja bezpieczeństwa D-582 („tylko bez żadnej ochrony komponentu”) nie jest zweryfikowana tam, gdzie jest zaimplementowana, czyli w SQL.
  - Poprawka: dodać te scenariusze do testu PG rejestru, z asercjami zerowej liczby zwolnień po register i niezmienionego proof.

### P2

- [P2-1] `services/api/src/game_predictor_api/storage/source_recording_sql_v6.py:111` — `recording_photo_context_v1` zastąpiono widokiem na `context_data_v2(preview=false)`. Zmienia to semantykę v1: proof zawiera teraz `uses` i `released`, dochodzi przechodnie domknięcie przez `photo_uses.group_ids` i pole `aliasComponentIds`. To ostatnie dołącza też adapter v1 (`storage/grid_correction_split.py:242`).
  - Skutek: kohorty v1 przygotowane przed 0172 i jeszcze niezamrożone zakończą się `GRID_CORRECTION_REGISTRY_CHANGED` (fail-closed). Podział v1 może też dać inny wynik niż przed migracją.
  - Proponuję jawnie opisać to w notatkach operatorskich i API_CONTRACT albo nie dołączać `aliasComponentIds` dla v1.

- [P2-2] `services/api/src/game_predictor_api/domain/grid_correction_progress.py:38` — każdy reprezentant VALIDATION/REGRESSION z zerem plansz liczy się jako `*Reserve`. Dotyczy to także chronionych nieopisanych rezerwacji, nieopisanych członków komponentu kontroli (np. importu nierozdzielnego) i kontroli z wycofanym zatwierdzeniem.
  - Jest to sprzeczne z `API_CONTRACT.md` („Rezerwa oznacza wyłącznie zdjęcia oczekujące na korektę”).
  - Dodatkowo `usedTrainLabels` jest filtrowane po `u.source_id=s.id` (`source_recording_sql_v6.py:98`). Gdy reprezentantem jest inna kopia niż zdjęcie użyte wcześniej, użyte etykiety pokażą się jako `newTrain`.
  - Proponuję liczyć rezerwę z `pendingCorrection` i dodać jawny powód dla pozostałych przypadków, a etykiety porównywać po tożsamości kopii.

- [P2-3] `services/api/src/game_predictor_api/storage/source_recording_sql_v6.py:101` — `aliasComponentIds` zwraca roli runtime sumy `byte:`/`pixel:` zdjęć z innych gier, połączonych przez sesje lub kopie. Jest to sprzeczne z komentarzem w liniach 36–37 („Never expose their rows to runtime”).
  - Proponuję zwracać skróty nieprzezroczyste (jak `recording_proof_v1`) albo tylko identyfikatory własnej gry.

- [P2-4] `services/api/src/game_predictor_api/domain/grid_correction_incremental_split.py:93` — wybór rezerwy kosztuje O(liczba oczekujących × długość importu) na rolę. Przy około 1200 lub więcej zdjęciach `grid_issue` w jednym imporcie budżet 3 000 000 zostanie przekroczony i `GRID_CORRECTION_SPLIT_WORK_LIMIT` zablokuje cały preview, choć rezerwa jest opcjonalna.
  - Dziś to ryzyko akceptowalne: dane Mumie A2 mają 102 takie zdjęcia na 788.
  - Proponuję odnotować ryzyko albo przy wyczerpaniu budżetu dla fazy rezerwy dawać jawny brak rezerwy zamiast blokady.

- [P2-5] `services/api/src/game_predictor_api/storage/source_recording_sql_v6.py:157` — pomijanie kontroli ról dla nieużytych, niebuforowych członków historycznych kohort v1 działa bezwarunkowo. Nie jest ograniczone do członków, których rezerwacja ma wpis w `recording_photo_reservation_releases`, jak w nocie technicznej taska („po legalnym zwolnieniu”).
  - Proponuję warunek `EXISTS` na release dla tej ścieżki albo akceptację ryzyka w D-582.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Stare metadane bez użycia mogą bezpiecznie zwiększyć TRAIN | spełnione (statycznie) | `source_recording_sql_v6.py:82-87`, `grid_correction_incremental_split.py:82-84`, `test_grid_correction_incremental_split.py:27`, `test_grid_correction_registry_postgres.py:289` |
| Rzeczywiste kontrole i historia pozostają chronione i weryfikowalne | niezweryfikowane (częściowo) | Użycia, bufory i rezerwy v2 są chronione oraz walidacja starej i nowej kohorty przechodzi (test PG od linii 289). Ścieżka holdout/ancestor/role head/sesja jest bez testu (P1-2). |
| Freeze atomowo zapisuje zwolnienia i przydziały; preview niczego nie zmienia | spełnione | `grid_training_cohort_freeze.py:173-188`, `source_recording_sql_v6.py:166-176`; test PG: 0 zwolnień po preview, rollback savepointu |
| Rezerwa nieopisanych kontroli najwyżej pięć zdjęć na rolę | spełnione dla nowych rezerw | `grid_correction_incremental_split.py:110-115`, `test_grid_correction_incremental_split.py:71`; zastrzeżenie licznika w P2-2 |
| Minima, atesty, nierozdzielne grupy i bufory dziesięciu zdjęć obowiązują | spełnione (statycznie) | `grid_correction_incremental_split.py:117-151`, `domain/grid_correction_split.py:229-319`, testy domenowe w liniach 27, 55 i 66 |
| Jednostki liczników, deduplikacja i powody wyłączeń są jawne | spełnione z zastrzeżeniem | `schemas/grid_correction_learning.py`, `grid_correction_progress.py`, OpenAPI i test żądania; P2-2 |
| Testy domenowe, PostgreSQL, kontrakt i wymagane kontrole przechodzą | niespełnione | P1-1 psuje istniejące testy PG. Wykonawca uruchomił tylko wybrane pliki. Zastany test `test_shared_candidate_rejects_correction_policy_before_creating_plan` nadal FAIL (zgłoszony jako baseline, statycznie niepotwierdzony). |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P1-1, P1-2, P2-1, P2-2, P2-3, P2-4, P2-5.

## Proponowane testy

- Guarded downgrade 0172: pusta historia pozwala zejść do 0171 i wrócić do head; historia zwolnień albo wiersz `incremental-v2` powoduje odmowę. Następnie, z limitem 120 s na plik, trzeba uruchomić na disposable DB: `test_recording_migration_lifecycle_postgres.py`, `test_source_crop_runs_postgres.py`, `test_grid_model_evaluation_bridge_postgres.py`, `test_grid_reinference_postgres.py` i `test_grid_reinference_stats_postgres.py`. Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/<plik>` przy `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'`.
- W `test_grid_correction_registry_postgres.py`: nieużyta rezerwacja legacy w komponencie z holdoutem, ancestorem, role head albo użytą sesją pozostaje niezwolniona, a register nie dopisuje wierszy do `recording_photo_reservation_releases`. Ochrona sprzeczna lub bezrolowa daje `GRID_CORRECTION_PROTECTION_CONFLICT`.
- `test_grid_correction_incremental_split.py`: licznik rezerwy nie obejmuje kontroli z zerem plansz, która nie czeka na korektę. Reprezentant będący kopią wcześniej użytego zdjęcia TRAIN nie zawyża `newTrain`.

## Zakres przeglądu i ograniczenia

To wznowienie tej samej rundy 1. Pierwszy odcinek przekroczył limit czasu bez werdyktu, a raport powstał z dotychczasowego kontekstu, bez nowej eksploracji.

Przeczytałem:
- cały brief: task, plan, diff i nowe pliki;
- migrację 0172 i 0170, `source_recording_sql_v4/v5/v6.py`, `source_recording_permissions_v6.py`;
- `storage/grid_correction_split.py`, `domain/grid_correction_incremental_split.py`, `domain/grid_correction_progress.py` i fragment `domain/grid_correction_split.py`;
- `application/grid_correction_learning.py` (preview/start) i `grid_training_cohort_freeze.py` (freeze);
- testy domenowe i PG taska, wybrane fixture'y migracyjne oraz `AGENTS.md`.

Nie uruchamiałem testów, lintu, typecheck ani PostgreSQL. Wnioski o wynikach testów (P1-1, baseline FAIL) wynikają z analizy kodu, nie z wykonania. Poprawność rozwinięcia łańcucha `.replace` w `PHOTO_SQL` oceniłem tekstowo względem v4; jego wykonanie potwierdza tylko deklarowany wynik testu PG wykonawcy. Liczb preflightu i symulacji na danych operatora nie weryfikowałem.
