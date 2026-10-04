---
title: Local operation guide
status: active
last_updated: 2026-10-04
---

# Lokalne uruchamianie i instalacja

## Konfiguracja API do ręcznej kalibracji etykiet V7

Przed użyciem przyszłego ekranu kalibracji ustaw dla procesu API
`GAME_PREDICTOR_V7_LABEL_GEOMETRY_CORPUS_MANIFEST` na lokalny manifest korpusu.
Opcjonalne `GAME_PREDICTOR_V7_LABEL_GEOMETRY_RUNTIME_ROOT` określa katalog
trwałych sesji i profili; bez niego używany jest `.runtime`. Manifest i korpus
muszą być lokalnymi realnymi katalogami bez dowiązań oraz junctionów w całej
ścieżce. API otwiera wyłącznie case `calibration`; `reels_test` jest holdoutem
i nie może być użyty do kalibracji ani podglądu assetu. Konfiguracja nie
odblokowuje `v7_selection` i nie zapisuje plików `cut`.

### Kalibracja etykiet 777 w trybie V2 (TASK-0603, D-463)

Ten krok uczy wyłącznie położenia **numerów** w siatce 3 × 3. Nie rozpoznaje
symboli, nie zmienia geometrii plansz i nie uruchamia automatycznego wyboru
zdjęć. Tryb V2 najpierw znajduje siatkę numerów na każdym zdjęciu osobno,
dlatego oba nagrania 777 mogą mieć różne kadrowanie.

**Zasady, które decydują o wyniku**

- Grupa ujęć oznacza nagranie, nie kolejność klikania. Wszystkie zdjęcia z
  katalogu `777` (nagranie `302200`) mają grupę **Ujęcie A**; wszystkie zdjęcia
  z katalogu `777 - przysłoniete częściowo plansze` (nagranie `45164`) mają
  **Ujęcie B**. Nie używaj `Ujęcie C`.
- Grupę ustaw **przed** pierwszym kliknięciem na zdjęciu. Punkty zdjęcia bez
  grupy nie trafiają do profilu.
- Oznaczasz zdjęcie tylko wtedy, gdy widać na nim co najmniej 5 pełnych,
  czytelnych numerów w co najmniej 2 wierszach i 2 kolumnach. Zdjęcie z
  mniejszą liczbą pełnych numerów pomiń w całości. Jedno takie zdjęcie z
  punktami blokuje cały profil.
- Każda z 9 pozycji potrzebuje co najmniej 5 różnych zdjęć z pełnym numerem,
  w tym co najmniej jednego z A i jednego z B.
- Wybieraj zdjęcia rozrzucone po nagraniu (początek, środek, koniec), a nie
  kolejne klatki tej samej strony.
- Podczas sesji nie zmieniaj niczego w katalogu
  `dane testowe do planu automatycznego wyboru zdjec`, także w innych
  podkatalogach, np. `reels_test`. Każda zmiana blokuje sesję (`source drift`).

**Procedura**

1. Zatrzymaj działające API. W nowym PowerShellu w katalogu repozytorium ustaw
   manifest V2 tylko dla procesu API i uruchom API:

   ```powershell
   $env:GAME_PREDICTOR_V7_LABEL_GEOMETRY_CORPUS_MANIFEST = (Resolve-Path '.runtime\v7-label-geometry-calibration-t0603-v2.local.json')
   $env:GAME_PREDICTOR_V7_LABEL_GEOMETRY_RUNTIME_ROOT = (Resolve-Path '.runtime')
   npm run api:dev
   ```

2. W drugim PowerShellu uruchom `npm run admin:dev` i otwórz **Kalibracja
   etykiet V7**. Jeżeli ekran przywróci starą sesję (`tryb V1`), najpierw użyj
   **Porzuć niepotwierdzone**, jeśli kolejka nie jest pusta, a potem **Zacznij
   nową sesję**. Stara sesja zostaje na serwerze do audytu i nie jest używana.
3. Zostaw zaznaczone oba materiały 777 i kliknij **Utwórz sesję kalibracji**.
   Przygotowanie trwa kilkanaście sekund. Nagłówek pokazuje `Rewizja 0 · tryb V2`.
4. Dla każdego wybranego zdjęcia:
   1. Wybierz je w **Zdjęcie źródłowe** (`small_777` = katalog `777`,
      `occluded_777` = katalog z zasłoniętymi planszami).
   2. Ustaw **Grupa ujęć**: `small_777` → **Ujęcie A**, `occluded_777` →
      **Ujęcie B**.
   3. Pozycje 1–9 idą wierszami: 1–3 górny rząd od lewej, 4–6 środkowy,
      7–9 dolny. Wybierz pozycję, pozostaw **Pełny, czytelny crop** i kliknij
      dokładny środek numeru.
   4. Numer zasłonięty, ucięty przez krawędź albo nieczytelny oznacz
      checkboxem **Numer zasłonięty / nieczytelny**; nie klikaj go. Nie używaj
      opcji `Przycięty crop` ani `Niepewna widoczność`, bo nie liczą się do
      profilu.
   5. Błędny punkt popraw, klikając ponownie właściwy środek na tej samej
      pozycji. Aby wycofać całe zdjęcie, oznacz każdy jego punkt jako
      zasłonięty.
5. Każde kliknięcie pojawia się od razu, ale serwer zapisuje je około 7 s.
   **Trwała kolejka** pokazuje liczbę niezapisanych kliknięć. Karta gotowości
   liczy tylko punkty zapisane przez serwer. Można pracować dalej; odświeżenie
   strony nie gubi kolejki.
6. Karta **Gotowość do sprawdzenia profilu** ma dla każdej pozycji zielony stan
   `Gotowa do kontroli serwera` przy `Zdjęcia: 5/5` i `Grupy: 2/2`.
   Czerwony komunikat „Zdjęcia z za małą siatką” wskazuje zdjęcie do
   uzupełnienia albo wycofania.
7. Gdy kolejka ma 0, a wszystkie pozycje są zielone, kliknij **Eksportuj
   snapshot**, a potem **Sprawdź i utwórz profil**. Serwer ponownie sprawdza
   pliki, grupy, pełne cropy oraz p95 residualu `<= 0,04`. Odrzucony wynik nie
   zmienia progu; zapisz komunikat i zgłoś go.

Nie usuwaj ręcznie plików z `.runtime`. Profil sam nie odblokowuje V7: potem
potrzebny jest raport walidacji, adopcja i ponowny odbiór T12.

## Testowy wariant v0.10.4 po odbiorze TASK-0515

W Adminie można jawnie wybrać `v0.10.4 — testowy, niepełne boki` dla nowego
runu. Nie jest to ustawienie domyślne ani zmiana polityki gry. Najpierw otwórz
raport, przygotuj zgodny preflight dla tego samego stagingu/managed source i
manifestu, a dopiero potem uruchom reprocessing. Brak zgodnego artefaktu,
checksumy lub dozwolonego guard rebindu ma pozostać blockerem.

Po wykonaniu runu przejrzyj każdą automatyczną propozycję partial w istniejącym
edytorze. Sprawdź pochodzenie, quad, maskę niedostępnych indeksów i widoczne
kolumny. Dopiero jawne potwierdzenie pozwala istniejącej ścieżce renderować
dostępne pola; propozycja sama nie zapisuje decyzji człowieka. Górne/dolne
ucięcie, brak planszy i ambiguous wymagają korekty ręcznej lub źródła.

Powtórzenie bramki bez odczytu bazy:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_lateral_partial_v4.py --timing-repeats 5
```

Oczekuj `acceptancePassed: true` i wszystkich pól `gates` równych `true`.
Szczegóły korpusu, coverage i ograniczeń:
[odbiór v0.10.4](../quality/LATERAL_PARTIAL_V4_ACCEPTANCE.md).

## Rola aplikacyjna bazy bez `SUPERUSER`/`BYPASSRLS` (TASK-0795, D-467)

Od TASK-0795 API i workery łączą się z bazą rolą aplikacyjną
`game_predictor_app` (`LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE
NOREPLICATION NOINHERIT`, bez własności obiektów i bez DDL), więc wymuszone
RLS `game_data_v2` rzeczywiście izoluje gry. Rola właściciela
`game_predictor` (superuser z `POSTGRES_USER`) zostaje dla Alembica, skryptów
utrzymaniowych i nielicznych kroków runtime wymagających właściciela.

| Zmienna | Domyślnie | Używa |
| --- | --- | --- |
| `GAME_PREDICTOR_DATABASE_URL` | `postgresql+psycopg://game_predictor_app:game_predictor_app_local@127.0.0.1:5432/game_predictor` | sesje runtime API i workera |
| `GAME_PREDICTOR_OWNER_DATABASE_URL` | właściciel `game_predictor:game_predictor_local` na bazie z `GAME_PREDICTOR_DATABASE_URL` | Alembic (`db:migrate`), skrypty `scripts/*.py`, `db:reset:local`, partycje nowej gry, `VACUUM` po kompaktacji, `ANALYZE` po backfillu weryfikacji symboli |

Oba URL-e przechodzą tę samą walidację loopback; muszą wskazywać ten sam
host, port i bazę (inaczej start kończy się `ConfigurationError`). Rolę
tworzy i wyrównuje idempotentny skrypt `scripts/provision_database_roles.py`
(nazwa i hasło z `GAME_PREDICTOR_DATABASE_URL`, połączenie z
`GAME_PREDICTOR_OWNER_DATABASE_URL`, hasło wysyłane jako weryfikator
SCRAM): `npm run db:roles:provision` (także na końcu `npm run db:up`,
`npm run db:migrate` i `db:reset:local` — po migracji ponownie odbiera zapis
`alembic_version`, który domyślne uprawnienia nadałyby nowej tabeli), kontrola tylko do odczytu `npm run db:roles:check` (kod 1,
gdy rola nie istnieje albo nie spełnia kontraktu). Skrypt nadaje `CONNECT`,
`USAGE` na `public` i `game_data_v2`, `SELECT/INSERT/UPDATE/DELETE` na
tabelach (bez zapisu `public.alembic_version`), `USAGE, SELECT` na
sekwencjach, `EXECUTE` na funkcjach i domyślne uprawnienia dla obiektów,
które właściciel utworzy później (migracje, partycje nowej gry). Gdy oba URL-e
mają tego samego użytkownika (konfiguracja wycofania), skrypt nic nie robi.

Cutover (wykonuje orkiestrator; schemat bez zmian, bez migracji):

1. Zaczekaj na koniec aktywnych jobów albo zatrzymaj je bezpiecznie.
2. Zatrzymaj API, workery wszystkich lane'ów i Reviewera (także tunel) w
   checkoutcie, z którego uruchamiasz usługi; sprawdź `netstat -ano |
   findstr :8000` (i `:8010`), zakończ osierocone procesy `--reload`
   (sekcja „Przejście na manifest magazynu v3” niżej).
3. Scal kod do tego checkoutu (`npm install` niepotrzebne).
4. `npm run db:roles:provision` — utworzenie roli i uprawnień na bazie
   `game_predictor`; oczekuj `"status": "provisioned"` i `"compliant": true`.
   Potem `npm run db:roles:check`.
5. Uruchom API i workery. Start API (`ALEMBIC_HEAD_MISMATCH` nadal działa)
   czyta `alembic_version` już rolą aplikacyjną. Sprawdzenie: w `psql`
   rolą właściciela `SELECT usename, application_name, count(*) FROM
   pg_stat_activity WHERE datname = 'game_predictor' GROUP BY 1, 2;` —
   połączenia API/workera mają `usename = game_predictor_app`.
6. Dymny test: lista gier i strona weryfikacji symboli w Adminie, wyszukiwarka
   plansz 777, jeden job workera (np. podgląd kompaktacji). Utworzenie nowej
   gry tworzy partycje rolą właściciela (osobne krótkie połączenie).

Wpływ na inne sesje i worktree: zmiana jest w domyślnych wartościach kodu,
więc dotyczy tylko procesów uruchomionych z kodem po scaleniu. Procesy ze
starszych checkoutów (np. API `8110` z innego worktree) nadal łączą się rolą
właściciela (bez izolacji RLS) do czasu scalenia i restartu; nie wymagają
koordynacji, bo schemat się nie zmienia. Ustawienie `GAME_PREDICTOR_DATABASE_URL`
jako zmiennej użytkownika Windows zmieniłoby wszystkie checkouty naraz — nie
rób tego przed scaleniem kodu wszędzie (stary kod używa tej zmiennej także
dla Alembica i skryptów).

Wycofanie (bez zmian w bazie): ustaw dla procesów API i workerów
`GAME_PREDICTOR_DATABASE_URL` na URL właściciela
(`postgresql+psycopg://game_predictor:game_predictor_local@127.0.0.1:5432/game_predictor`)
i zrestartuj je; `db:roles:provision` wtedy nic nie robi. Rola
`game_predictor_app` może zostać (nie ma własności obiektów); jej usunięcie
(`DROP OWNED BY game_predictor_app; DROP ROLE game_predictor_app;` rolą
właściciela) jest osobną decyzją.

Testy PostgreSQL na roli aplikacyjnej: `$env:GAME_PREDICTOR_PG_TEST_ROLE =
'application'` obok `GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'`. Fixture z
`services/api/tests/integration/conftest.py` tworzy rolę
`game_predictor_app_test_<hex>` (`NOLOGIN`), nadaje jej uprawnienia wyłącznie w
jednorazowych bazach testowych, każda sesja `GameStorageSession` działa jako
ta rola (`SET LOCAL ROLE`), a na końcu rola jest usuwana. Test izolacji
`test_application_role_isolation_postgres.py` loguje się rolą
`LOGIN` (losowe hasło, ważne godzinę, usuwana po teście).

## Profile silnika siatek gry i migracja `0140` (TASK-0830)

Pole „Format strony” gry ma, obok „Pełna strona z ramką” i „Format wymaga
doprecyzowania”, dwa profile silnika siatek: **„777 v2”**
(`grid_profile_777_v2`) i **„Mumie”** (`grid_profile_mumie_v1`). Profil
wskazuje zamrożony model `neural_grid` (raport
`ai_docs/quality/GRID_V3_COMPARISON_REPORT_20261004.md`):

| Profil | Wersja | Model |
|---|---|---|
| 777 v2 | `v1` | run `43933ac8…`, preset A, runda 3 (eksport `2cd19738367121e6-round3`); służy też kolejnym wersjom 777 (np. „777 v3” wybiera ten sam profil) |
| Mumie | `v1` | run `5bc98156…`, doszkolenie D-490, iteracja 3 (eksport `iteration03-f896da7196431be2`) |

Dla preflightu i gotowości wspólnej geometrii profil działa dokładnie jak
„Pełna strona z ramką”: nowa gra startuje z ręczną weryfikacją pierwszego
importu. Sieć nie jest jeszcze uruchamiana w pipeline importu (tryb shadow,
TASK-0805). Wybór profilu nie jest blokowany brakiem modelu; Admin pokazuje
stan modelu przy polu i na karcie gry.

Modele leżą poza repozytorium w
`<artifact root>\models\grid-engine\<profil>\<wersja>\` (`screen.onnx`,
`board.onnx`, `bundle.json`, `preset.json`, `manifest.json`). Repozytorium
trzyma tylko rejestr SHA-256 i metadanych
(`services/api/src/game_predictor_api/domain/grid_engine_profiles.py`). Brak
pliku albo inna suma kontrolna to jawny błąd (`missing` /
`checksum_mismatch`), bez zastępowania innym modelem. Kolejny model tej samej
gry to nowa wersja w rejestrze profilu, nie nowa wartość pola.

Jednorazowa instalacja (kopiuje i weryfikuje, eksporty labu tylko czyta;
istniejący poprawny katalog zostawia, niezgodnego nie nadpisuje):

```powershell
$runs = 'C:\Users\tuszy\Documents\game_predictor_vision_data\neural-grid-runs'
.\.venv\Scripts\python.exe scripts/install_grid_engine_models.py `
  --source "grid_profile_777_v2=$runs\43933ac8d7d443c8b9079630a83de2e6\exports\2cd19738367121e6-round3" `
  --source "grid_profile_mumie_v1=$runs\5bc981568c3f42bd96f6f9238e57aedc\exports\iteration03-f896da7196431be2"
.\.venv\Scripts\python.exe scripts/install_grid_engine_models.py --check   # kod 0 = oba modele dostępne
```

Katalog artefaktów jest ustalany jak w API (`GAME_PREDICTOR_ARTIFACT_ROOT`,
domyślnie `artifacts` w katalogu startu); `--artifact-root` go nadpisuje.
Stan modeli zwraca też `GET /api/v1/admin/grid-engine-profiles`.

Migracja `0140_grid_engine_profiles` rozszerza wyłącznie CHECK
`ck_games_shape_geometry_configuration`; nie zmienia żadnego wiersza. Kod
wymaga `0140` (`EXPECTED_ALEMBIC_HEAD`), więc przejście jest takie jak dla
`0139`: zatrzymaj API, workery i Reviewera wszystkich checkoutów, scal kod,
`npm run db:migrate`, `npm run db:current` → `0140_grid_engine_profiles`,
uruchom usługi. Wycofanie: `alembic downgrade
0139_source_image_geometry_completeness` odmawia
(`GRID_ENGINE_PROFILE_IN_USE`), dopóki któraś gra używa profilu — najpierw
zmień jej format strony.

## Poprawki z audytu siatek w Reviewerze (TASK-0840)

Lista 975 plansz 777 ze złą zapisaną siatką (audyt TASK-0831,
`ai_docs/quality/SILENT_GRID_AUDIT_777_20261004.md`) jest zaimportowana jako
niezmienny artefakt API:
`artifacts\grid-audit-proposals\bfc4f949-5c14-4850-b02a-db99610bcfa5\silent-grid-777-20261004\`
(`proposals.json` + `manifest.json` z SHA-256). Import tylko czyta bazę
(`REPEATABLE READ READ ONLY`) i odmawia nadpisania istniejącego katalogu:

```powershell
.\.venv\Scripts\python.exe scripts\import_grid_audit_proposals.py `
  --audit 'C:\Users\tuszy\Documents\game_predictor_vision_data\silent-grid-audit\777-20261004' `
  --game-id bfc4f949-5c14-4850-b02a-db99610bcfa5 --artifact-root .\artifacts [--dry-run]
```

Plansza, której rewizja geometrii zmieniła się po audycie, trafia do pliku
jako `stale` bez propozycji. Grupa 231 błędów sieci (prawa górna plansza) nie
jest na liście (werdykty operatora).

Wdrożenie razem z przejściem na `0140` (sekcja wyżej): po scaleniu kodu
`npm install`, `npm run reviewer:build`, migracja, start API (nowe trasy
`grid-audit-proposals`) i Reviewera. Praca:

1. uruchom Reviewer (`Otwórz lokalnie` w Adminie dla dowolnego importu albo
   `npm run reviewer:start`),
2. otwórz
   `http://127.0.0.1:3001/?mode=local&gameId=bfc4f949-5c14-4850-b02a-db99610bcfa5&queue=grid-audit`,
3. ekran „Poprawki z audytu siatek” pokazuje jedną planszę: żółta siatka z
   narożnikami to propozycja sieci, cienki czerwony kontur to obecna siatka;
   podgląd 15 wycinków powstaje sam, także podczas wczytywania pełnego zdjęcia,
   a pierwsze dostępne pole jest od razu zaznaczone (TASK-0841),
4. gdy propozycja jest dobra — `Zapisz geometrię i dalej` (można przed tym
   wskazać symbole na kafelkach, D-488); gdy wymaga poprawki — przeciągnij
   narożniki; gdy jest zła — `Pomiń na razie →`.

Symbol możesz poprawić bez przesuwania siatki i bez „Ponów podgląd”. Kliknij
właściwy kafelek, potem symbol w palecie albo jego klawisz. W 777: `1` Wiśnia,
`5` Śliwka, `6` Arbuz; `9` oznacza „Nie wiem”. Wszystkie skróty widać przy
symbolach. Pierwsze pole jest zaznaczone automatycznie, ale nie dostaje
etykiety, dopóki jej nie wybierzesz. W katalogu z ponad ośmioma symbolami
kolejne skróty to `0`, potem litery. Wybory trafiają do bazy dopiero przy
`Zapisz geometrię i dalej`.

Zapis to zwykła korekta planszy: nowa rewizja geometrii, pola ze zmienionym
wycinkiem wracają do Weryfikacji symboli. Poprawiona plansza znika z listy
także po restarcie; pominięte wracają przy kolejnym otwarciu. Nic nie jest
oznaczane jako „Zła siatka”.

## Migracja `0139` i backfill bramki kompletności geometrii (TASK-0807, D-484)

Kod TASK-0807 wymaga `0139_source_image_geometry_completeness`
(`EXPECTED_ALEMBIC_HEAD`). Migracja dodaje na rodzicu partycjonowanym
`game_data_v2.source_images` pięć kolumn stanu bramki (`ADD COLUMN` bez
przepisywania tabeli, `ACCESS EXCLUSIVE` z `lock_timeout = 5s`), trzy CHECK-i
walidowane od razu (wszystkie wartości są `NULL`) i dwa indeksy częściowe.
Manifest magazynu (v4) i lifecycle partycji się nie zmieniają. Do czasu
backfillu każde zdjęcie ma status `NULL` i działa jak przed bramką.

Backfill (`npm run images:geometry-completeness:backfill -- --game-id <uuid>`,
skrypt `scripts/backfill_image_geometry_completeness.py`, rola właściciela):
dla każdego zdjęcia bez oceny (`geometry_completeness_evaluated_at IS NULL`)
najpierw przepina żywe plansze wskazujące starszą rewizję geometrii źródła na
najnowszą, gdy jej wpis pozycji jest identyczny (wskaźniki planszy, manifestu
renderu i komórek; piksele i decyzje bez zmian), a potem zapisuje status z
klasyfikatora domenowego. Niczego nie usuwa i nie tnie nowych plansz.
`--preview` (domyślnie) działa w transakcjach `READ ONLY` i liczy to samo bez
zapisu; `--execute` zapisuje partie po ≤ 500 zdjęć, każda w osobnej
transakcji. Oba tryby zapisują raport JSON i punkt kontrolny w
`<artifact root>/data/exports/image-geometry-completeness/<gameId>/`;
`--max-seconds` (domyślnie 100) przerywa bieg, a kolejne uruchomienie
kontynuuje (kod wyjścia `3` = nieukończone); `--restart` zaczyna od nowa.
Partia zatwierdzona wcześniej nie jest liczona drugi raz, bo ocenione zdjęcia
są pomijane. Raport końcowy (`databaseSummary`) czyta z bazy liczbę zdjęć per
status, nieocenionych i niekompletnych z istniejącymi komórkami.

Przejście (cutover):

1. Zaczekaj na koniec jobów albo zatrzymaj je bezpiecznie; zatrzymaj API,
   workery i Reviewera **wszystkich** checkoutów i worktree (`8000`, `8010`,
   `8020`, …); sprawdź `netstat -ano | findstr :80` (osierocone `--reload`).
2. Scal kod; `npm run db:migrate`, `npm run db:current` →
   `0139_source_image_geometry_completeness`.
3. Podgląd: `npm run images:geometry-completeness:backfill -- --game-id <gameId> --preview`
   (powtarzaj do `"completed": true`). Sprawdź `totals.statuses`,
   `totals.repointedBoards`, `totals.notRepointableByReason` i
   `totals.incompleteWithCells` z oczekiwaniem z raportu zadania.
4. Zapis: `npm run images:geometry-completeness:backfill -- --game-id <gameId> --execute`
   (powtarzaj do `"completed": true`); `databaseSummary.notEvaluated` = 0.
5. Uruchom usługi; w Adminie sekcja „Kompletność siatek zdjęć” pokazuje
   kolejkę siatek ze stanu w bazie.

Wycofanie: zatrzymanie usług, `alembic downgrade
0138_rls_policy_function_parallel_safe` rolą właściciela (odmawia
`SOURCE_IMAGE_GEOMETRY_EXCEPTION_PRESENT`, dopóki istnieje wyjątek operatora —
najpierw go wycofaj), kod sprzed TASK-0807. Przepięcie plansz backfillem nie
jest cofane migracją (wskaźniki prowadzą do rewizji o identycznej geometrii).

Zmiany zachowania: plansza zdjęcia `geometry_incomplete` bez komórek nie jest
cięta na symbole i trafia do wyszukiwarki bez dowodów symboli (powód
`SOURCE_IMAGE_GEOMETRY_INCOMPLETE`); po skompletowaniu siatek albo wyjątku
operatora zdjęcie jest cięte w tej samej transakcji. Nowa rewizja geometrii
źródła przepina identyczne plansze, więc ponowne odtworzenie
(`project_recognition`) tego samego pliku po przepięciu kończy się
`IMAGE_RECOGNIZED_BOARD_CONFLICT`, jak po każdej ręcznej korekcie.

## Migracja `0138`: równoległa funkcja polityki RLS i ścieżki bez gry (TASK-0797, D-467)

Kod TASK-0797 wymaga `0138_rls_policy_function_parallel_safe`
(`EXPECTED_ALEMBIC_HEAD`; stary kod nie wystartuje na nowej bazie i odwrotnie).
Migracja podmienia funkcję `game_data_v2.current_game_id_v1()` (polityki bez
zmian) i zawęża `ck_image_symbol_review_cells_approved_provenance` (bez
gałęzi `legacy_file`, `NOT VALID`). Bierze `ACCESS EXCLUSIVE` na komórkach
weryfikacji z `lock_timeout = 5s`; preflight liczy komórki z zatwierdzeniem
plikowym (baza operatora 2026-10-01: 0) i przy jakimkolwiek odmawia
`CELL_APPROVED_LEGACY_PROVENANCE_PRESENT` bez zmian.

1. Zaczekaj na koniec jobów albo zatrzymaj je bezpiecznie; zatrzymaj API
   (`8000`, `8010`, …), workery i Reviewera z tunelem; sprawdź
   `netstat -ano | findstr :8000` (osierocone procesy `--reload`).
2. Scal kod; `npm run db:migrate` (po migracji uruchamia też
   `db:roles:provision`), `npm run db:current` →
   `0138_rls_policy_function_parallel_safe`.
3. Walidacja nowego CHECK-a (skan partycji, `SHARE UPDATE EXCLUSIVE`, zapisy
   mogą trwać), rolą właściciela:
   `ALTER TABLE game_data_v2.image_symbol_review_cells VALIDATE CONSTRAINT ck_image_symbol_review_cells_approved_provenance;`
4. Kontrola: `SELECT proparallel FROM pg_proc WHERE proname = 'current_game_id_v1';`
   → `s`; uruchom usługi i sprawdź listę komórek 777, Reviewera z tokenem i
   podgląd storage GC.

Wycofanie: zatrzymanie usług, `alembic downgrade 0137_prediction_revisions_slim`
rolą właściciela (przywraca poprzednią funkcję i szerszy CHECK; każdy wiersz
nowego CHECK-a spełnia stary), kod sprzed TASK-0797.

Zmiany zachowania: trasa `/api/v1/admin/…` lub `/api/v1/reviewer/…` z
parametrem `gameId` (albo `game_id`) działa w zakresie tej gry; trasa, która
nazywa tylko identyfikator wiersza gry, znajduje jego grę (nieistniejący
identyfikator → `404 GAME_SCOPED_RESOURCE_NOT_FOUND`); wydania mobilne i
kontrole współdzielonych plików przy sprzątaniu gry działają sesją
właściciela (`CrossGameOwnerSession`).

## Przejście na manifest magazynu v3 i `board_render_manifests` (TASK-0757, D-467)

Kod od TASK-0757 wymaga migracji `0131_board_render_manifests`: router
magazynu gry akceptuje wyłącznie wersję `game-data-v2-manifest-v3`. Stary kod
nie działa na nowym schemacie, a nowy na starym. API (`npm run api:dev`) i
worker (`worker:*`) sprawdzają przy starcie `alembic_version` jednym `SELECT`
i przy niezgodności kończą się błędem `ALEMBIC_HEAD_MISMATCH` zamiast psuć
każde żądanie danych gry.

Przejście (cutover). Strażnik `ALEMBIC_HEAD_MISMATCH` działa tylko przy
świeżym starcie procesu: `api:dev --reload` przeładowuje wyłącznie proces
potomny, a już działające API i workery nie są sprawdzane po migracji —
dlatego kroki 1–2 są obowiązkowe:

1. Zaczekaj na zakończenie aktywnych jobów (import, backfille, biblioteka
   wzorców) albo zatrzymaj je bezpiecznie.
2. Zatrzymaj API, workery wszystkich lane'ów i Reviewera we **wszystkich**
   checkoutach i worktree (także tunel Reviewera). Migracja bierze
   `LOCK ... ACCESS EXCLUSIVE` na `public.game_storage_locations` z
   `lock_timeout = 5s`; aktywna transakcja innego procesu powoduje błąd
   migracji (nic nie zostaje zmienione, można powtórzyć po zatrzymaniu).
   Na Windows zatrzymanie samego procesu nadrzędnego uvicorn `--reload`
   (`Stop-Process`, `taskkill` bez `/T`) zostawia proces potomny
   `python.exe -c "from multiprocessing.spawn …"`, który dalej nasłuchuje na
   tym samym porcie ze starym kodem; Windows dopuszcza kilku słuchaczy na
   `127.0.0.1:8000`, więc żądania trafiają na przemian do starego i nowego
   procesu (objaw: `/health` 200, a dane gry raz 200, raz 500
   `GAME_STORAGE_LOCATION_INVALID` lub `ALEMBIC_HEAD_MISMATCH`). Po
   zatrzymaniu sprawdź `netstat -ano | findstr :8000` i zakończ każdy
   wymieniony PID (`taskkill /PID <pid> /T /F`) przed startem nowego kodu.
3. Scal kod (merge) do checkoutu, z którego uruchamiasz usługi.
4. `npm run db:migrate`, potem `npm run db:current` → `0131_board_render_manifests`.
   Migracja odmówi (`GAME_STORAGE_LIFECYCLE_IN_PROGRESS`,
   `GAME_STORAGE_LOCATION_BUSY`), jeśli trwa provisionowanie lub usuwanie gry.
5. Uruchom usługi nowego kodu.
6. Backfill manifestów z `cell_observations` wykonano 2026-10-01 (777 i
   `cf300bc1…`, TASK-0757). Skrypt `scripts/backfill_board_render_manifests.py`
   został usunięty w TASK-0759 razem z tabelą obserwacji (źródłem rewizji 0);
   manifesty piszą wyłącznie writery importu i ręcznej geometrii.

Wycofanie do `0130` nie jest już możliwe po `0134` (TASK-0759): migracja
`0134` usuwa obserwacje i odmawia downgrade'u.

## Tylko wirtualne polityki importu i rezolucja odroczonych plansz (TASK-0790, D-467)

Kod od TASK-0790 wymaga migracji `0133_virtual_only_import_policies`
(strażnik `ALEMBIC_HEAD_MISMATCH` jak wyżej). Migracja przestawia każdy stan
rolloutu gry w trybie `legacy` / `legacy_files` albo `structured_shadow` na
domyślny tryb nowej gry `structured_lattice_v3` / `virtual_default`
(rewizja + 1, postęp walidacji wyzerowany), zawęża CHECK-i trybów i nie ma
downgrade'u (odmawia — powrót tylko z kopii zapasowej). Odmawia też
(`IMAGE_ENGINE_POLICY_MIGRATION_BUSY`), gdy taki stan ma aktywny backfill
walidacji. Na bazie operatora dotyczy to dwóch gier (`cf300bc1…`,
`2a46d3a6…`, rewizja 0).

Przejście: zatrzymaj API, workery i Reviewera we wszystkich checkoutach (jak
w krokach 1–2 powyżej), scal kod, `npm run db:migrate`, sprawdź
`npm run db:current` → `0133_virtual_only_import_policies`, uruchom usługi.
Reviewer i API są wdrażane razem; sesja Reviewera w trakcie przejścia może
dostać błąd 4xx/5xx i wystarczy ją odświeżyć.

Zmiany zachowania:

- Admin nie oferuje już `verified_v19` ani `structured_shadow`; API odrzuca
  je kodem `IMAGE_ENGINE_POLICY_LEGACY_UNSUPPORTED` (422).
- Job importu przypięty do usuniętego silnika kończy się błędem
  `IMAGE_PIPELINE_NON_VIRTUAL_ROLLOUT_REJECTED`, a writer odmawia planszy
  niewirtualnej (`IMAGE_PIPELINE_NON_VIRTUAL_BOARD_REJECTED`).
- Ręczna rezolucja odroczonej planszy w Reviewerze (ten sam przycisk i
  endpoint `manual-resolution`) tworzy planszę `virtual_source` z manifestem
  renderu i predykcjami modelu przypiętego do importu; nie zapisuje plików
  cropów ani obserwacji. Podgląd pokazuje komórki renderu wirtualnego.

## Tylko wirtualne plansze: konwersja `legacy_file` i migracja `0135` (TASK-0791, D-467 S6)

Kod od TASK-0791 wymaga migracji `0135_virtual_only_asset_modes` (strażnik
`ALEMBIC_HEAD_MISMATCH` jak wyżej). Migracja odmawia
(`LEGACY_FILE_BOARDS_PRESENT` / `LEGACY_FILE_CELLS_PRESENT`), dopóki w bazie
jest jakakolwiek plansza albo komórka `legacy_file`, więc kolejność cutoveru
to: zatrzymanie usług (jak wyżej, z kontrolą osieroconych procesów) → merge →
konwersja → `npm run db:migrate` → start.

Konwersja (tylko z checkoutu, którego `artifacts/` zawiera oryginały zdjęć;
inaczej `IMAGE_REVIEW_ASSET_NOT_FOUND`):

```powershell
$env:PYTHONPATH = "services/worker/src;services/api/src"
# podgląd tylko do odczytu; --render-sources renderuje N źródeł w pamięci
.\.venv\Scripts\python.exe scripts/convert_legacy_boards_to_virtual.py --game-id <uuid> --preview --render-sources 3
# wykonanie: jedno źródło na transakcję, wznawialne (skonwertowane plansze
# nie są już legacy_file); --max-seconds kończy porcję, kolejne wywołanie
# kontynuuje; kod wyjścia 2, gdy jakieś źródło zostało pominięte z problemem
.\.venv\Scripts\python.exe scripts/convert_legacy_boards_to_virtual.py --game-id <uuid> --execute --max-seconds 100
```

Raport JSON trafia do `artifacts/data/exports/legacy-board-conversion/<gra>/`.
Po konwersji `SELECT count(*) FROM game_data_v2.recognized_boards WHERE
asset_mode = 'legacy_file'` musi dać 0 dla każdej gry; wtedy `db:migrate`.
Migracja dodaje CHECK komórek jako `NOT VALID` (walidacja 7,5 mln wierszy
nie mieści się w budżecie 120 s); po starcie usług zwaliduj go w tle,
blokada `SHARE UPDATE EXCLUSIVE` nie wstrzymuje zapisów:

```sql
SET statement_timeout = '1800s';
ALTER TABLE game_data_v2.image_symbol_review_cells
  VALIDATE CONSTRAINT ck_image_symbol_review_cells_asset_provenance;
```
Wycofanie: `alembic downgrade 0134_…` przywraca dawne CHECK-i, ale
skonwertowanych plansz nie cofa (nowa rewizja wirtualna zostaje; dawna
rewizja `legacy_file` jest nadal w `image_board_geometry_revisions`).
Po `0136` (niżej) downgrade poniżej `0136` nie jest już możliwy.

## Usunięcie `render_spec` z komórek weryfikacji: migracja `0136` (TASK-0793, D-467 S7)

Kod od TASK-0793 wymaga migracji `0136_drop_cell_render_spec` (strażnik
`ALEMBIC_HEAD_MISMATCH`); kod sprzed niej nie działa na `0136` (zapisuje
kolumnę, której już nie ma). Kolejność cutoveru jak dla `0134`:

1. Zakończ albo bezpiecznie zatrzymaj joby; zatrzymaj API, workery
   (wszystkie lane'y) i Reviewera we **wszystkich** checkoutach i worktree;
   sprawdź osierocone dzieci `uvicorn --reload` na portach API (sekcja
   `0134` niżej) i zakończ je.
2. Merge kodu.
3. `npm run db:migrate`, potem `npm run db:current` =
   `0136_drop_cell_render_spec`. Migracja bierze `ACCESS EXCLUSIVE` na
   komórkach (`lock_timeout = 5s` — aktywna transakcja kończy ją błędem bez
   zmian, można powtórzyć), sprawdza manifesty (ok. 7 s na 777) i odmawia
   `CELL_RENDER_MANIFEST_MISSING: N virtual review cells …`, gdy któraś
   komórka `virtual_source` nie ma manifestu renderu swojej rewizji (wtedy
   nic nie zmienia — zgłoś przed ponowieniem). `DROP COLUMN` jest
   natychmiastowe (tylko katalog); miejsce zwalnia dopiero przepisanie
   partycji (`DATABASE_MAINTENANCE.md`).
4. Start usług; kontrola: lista komórek 777 w Adminie, podgląd atlasu i
   PNG wzorca.
5. W tle (blokada `SHARE UPDATE EXCLUSIVE`, zapisy działają) zwaliduj oba
   CHECK-i dodane jako `NOT VALID`:

```sql
SET statement_timeout = '1800s';
ALTER TABLE game_data_v2.image_symbol_review_cells
  VALIDATE CONSTRAINT ck_image_symbol_review_cells_asset_provenance;
ALTER TABLE game_data_v2.image_symbol_review_cells
  VALIDATE CONSTRAINT ck_image_symbol_review_cells_source_asset;
-- oba wiersze muszą mieć convalidated = t
SELECT conname, convalidated FROM pg_constraint
WHERE conrelid = 'game_data_v2.image_symbol_review_cells'::regclass
  AND conname IN ('ck_image_symbol_review_cells_asset_provenance',
                  'ck_image_symbol_review_cells_source_asset');
```

`ck_image_symbol_review_cells_source_asset` był `NOT VALID` od `0126`; jego
walidacja jest pierwszą pełną kontrolą starych pozycji `outside` — błąd
walidacji nie cofa migracji, ale wymaga zgłoszenia przed kolejnym krokiem.

Wycofanie: brak (`CELL_RENDER_SPEC_DROP_IRREVERSIBLE`). Specyfikacje renderu
są w `board_render_manifests`; odtworzenie kolumny byłoby backfillem, nie
downgradem. Przed `db:migrate` zrób kopię zapasową (`DATABASE_MAINTENANCE.md`).

## Odchudzenie rewizji predykcji: migracja `0137` i skrypt (TASK-0794, D-467 S8)

Kod od TASK-0794 wymaga migracji `0137_prediction_revisions_slim` (strażnik
`ALEMBIC_HEAD_MISMATCH`) i pisze rewizje predykcji bez
`virtualCell.renderSpec`. Cutover jak dla `0136`: zatrzymanie wszystkich
procesów we wszystkich checkoutach (z kontrolą osieroconych dzieci
`uvicorn --reload`) → merge → `npm run db:migrate` (`npm run db:current` =
`0137_prediction_revisions_slim`; tylko nowa kolumna, bez przepisywania
danych, `lock_timeout = 5s`) → start. Żaden przebieg `apply` biblioteki
wzorców nie może trwać w trakcie cutoveru ani odchudzania.

Odchudzenie istniejących rewizji (po starcie, w tle; blokuje tylko wiersze
bieżącej porcji):

```powershell
$env:PYTHONPATH = "services/worker/src;services/api/src"
# podgląd tylko do odczytu (działa też na 0136): liczby, bajty, próbka
.\.venv\Scripts\python.exe scripts/slim_prediction_revisions.py --game-id <uuid> --preview
# wykonanie porcjami po 500; --max-seconds kończy wywołanie, kolejne
# kontynuuje od checkpointu; kod 2 = przerwane albo błąd (raport JSON)
.\.venv\Scripts\python.exe scripts/slim_prediction_revisions.py --game-id <uuid> --execute --max-seconds 100
# retencja rewizji zastąpionych review items bez komórek (bez kotwic biblioteki)
.\.venv\Scripts\python.exe scripts/slim_prediction_revisions.py --game-id <uuid> --mode retention --preview
.\.venv\Scripts\python.exe scripts/slim_prediction_revisions.py --game-id <uuid> --mode retention --execute
```

Raporty i `slim-checkpoint.json` trafiają do
`artifacts/data/exports/prediction-revision-slim/<gra>/`. `--execute`
powtarzaj, aż raport ma `completed: true`; kolejne wywołanie zwraca
`scanned: 0`. Kontrola po zakończeniu:

```sql
SELECT count(*) FILTER (WHERE legacy_predictions_sha256 IS NULL) AS left,
       pg_size_pretty(sum(pg_column_size(predictions))::bigint) AS stored
FROM game_data_v2.image_symbol_prediction_revisions WHERE game_id = '<uuid>';
```

Błąd `PREDICTION_REVISION_SLIM_DIGEST_DRIFT` / `…_VERIFY_FAILED` wycofuje
całą porcję (nic nie zapisano) — zgłoś przed ponowieniem. Miejsce zwalnia
`VACUUM (FULL, ANALYZE)` partycji rewizji (`DATABASE_MAINTENANCE.md` 2.7).
Wycofanie: `alembic downgrade 0136_…` usuwa kolumnę tylko, dopóki skrypt jej
nie wypełnił (`PREDICTION_REVISION_LEGACY_DIGEST_PRESENT`); odchudzonych
rewizji nie da się przywrócić z bazy (pełna specyfikacja bieżącej rewizji
jest w manifeście renderu, starszych rewizji geometrii 0 — tylko w kopii
zapasowej).

## Manifest magazynu v4: usunięcie `cell_observations` i archiwum wyszukiwarki (TASK-0759, D-467 S5)

Kod od TASK-0759 wymaga migracji `0134_drop_cell_observations_and_legacy_archive`
(strażnik `ALEMBIC_HEAD_MISMATCH` jak wyżej): router i provisioning gry
akceptują wyłącznie `game-data-v2-manifest-v4`. Migracja jest
**nieodwracalna** — usuwa tabelę `cell_observations` (na bazie operatora ok.
7,66 mln wierszy, 28 GB) oraz puste tabele `legacy_board_search_archive_*`
razem z partycjami, a downgrade odmawia (`CELL_OBSERVATIONS_DROP_IRREVERSIBLE`).
Jedyną kopią obserwacji jest zrzut
`C:\game_predictor_backup\cell_observations-20261001-0404.dump`
(`pg_restore` tylko do bazy pomocniczej).

Przed migracją (osobna zgoda operatora, okno bez zapisów):

1. Zatrzymaj API, workery wszystkich lane'ów i Reviewera we wszystkich
   checkoutach i worktree (jak w krokach 1–2 przejścia na v3).
2. Scal kod, potem `npm run db:migrate` i `npm run db:current` →
   `0134_drop_cell_observations_and_legacy_archive`.
3. Uruchom usługi nowego kodu.

Preflight migracji (każda odmowa nic nie zmienia, można poprawić stan i
powtórzyć): `GAME_STORAGE_LIFECYCLE_IN_PROGRESS` / `GAME_STORAGE_LOCATION_BUSY`
(provisionowanie lub usuwanie gry w toku), `GAME_STORAGE_MANIFEST_UNEXPECTED`
(lokalizacja nie jest na v3), `GAME_STORAGE_DROP_TABLE_UNEXPECTED`,
`GAME_STORAGE_DROP_FOREIGN_KEY_PRESENT` (klucz obcy spoza usuwanych tabel),
`CELL_OBSERVATIONS_LEGACY_REVISION_ZERO_PRESENT` (plansza `legacy_file` na
rewizji 0), `BOARD_RENDER_MANIFEST_MISSING` (plansza `virtual_source` z
dostępnymi komórkami bez manifestu bieżącej rewizji) i
`LEGACY_BOARD_SEARCH_ARCHIVE_NOT_EMPTY`. Migracja bierze `lock_timeout = 5s`
na rejestrze lokalizacji, usuwanych tabelach oraz `SHARE` na
`recognized_boards` i `board_render_manifests`.

Po migracji `DROP TABLE` oddaje pliki partycji od razu (bez `VACUUM FULL`);
sprawdź `pg_database_size` i wolne miejsce, a plik `docker_data.vhdx` zmniejsz
według `ai_docs/guides/DATABASE_MAINTENANCE.md` (sekcja 3).

Zmiany zachowania i usunięte narzędzia:

- Wyszukiwarka plansz ma jedno źródło (`operational_review`); endpoint
  `GET …/board-search/archive-assets/{sequenceNumber}` zwraca 404.
- Plansza `legacy_file` na rewizji 0 (na bazie operatora: 0) nie jest
  czytana: Reviewer `IMAGE_REVIEW_CELL_COUNT_INVALID`, wyszukiwarka ją
  pomija, przeliczanie predykcji `IMAGE_SYMBOL_REINFERENCE_LEGACY_UNSUPPORTED`.
- Usunięte skrypty: `scripts/backfill_board_render_manifests.py`,
  `scripts/build_grid_symbol_diagnostic.py`,
  `scripts/build_legacy_board_search_archive.py`,
  `scripts/prepare_m65_real_workbench.py`,
  `scripts/run_m65_workbench_acceptance.py` oraz wpisy npm
  `m65:workbench:prepare|check|acceptance`.

## Wdrożenie obsługi niepełnych plansz (TASK-0505–0509)

Kod od v0.10.224 wymaga migracji `0100_manual_geometry_qualification` oraz
`0101_symbol_cell_source_availability`. Nie startuj nowego workera/API na
starym schemacie. Zaczekaj na bezpieczne zakończenie aktywnych jobów,
zatrzymaj usługi, wykonaj `npm run db:migrate` i potwierdź `npm run db:current`,
a następnie uruchom usługi według poniższych instrukcji. Implementacja
tasków nie wykonała tych operacji na danych operatora.

W ręcznej korekcie Importu Plansz i Zatwierdzaniu cięcia siatki:

- `Niepełna plansza` pozwala wysunąć narożniki poza zdjęcie; brakujące pola
  otrzymują maskę, a geometria nie trafia do nowych kohort i kotwic.
- `Nie używaj do uczenia geometrii` można zaznaczyć niezależnie na kompletnej,
  lecz niepewnej siatce. Nie wyklucza to automatycznie widocznych symboli.
- Nawigacja nie zapisuje decyzji. `Zapisz i przejdź dalej`, `Zapisz decyzję`
  lub `Zatwierdź całe zdjęcie (Enter / F)` są jawnymi akcjami zapisu.
- Boczne przycięcie może być rzeczywistym brakiem źródła. Ucięta góra/dół
  sygnalizuje błąd auto-cropa i zaleca poprawienie źródłowego zdjęcia.

Pełne kroki testu, wyniki i ograniczenia:
[odbiór niepełnej geometrii](../quality/PARTIAL_GEOMETRY_ACCEPTANCE.md).
Eksperymentalny v0.10.4 jest od TASK-0515 dostępny wyłącznie jako jawny wariant
testowy. Braki nadal są wyliczane z geometrii i podparcia źródłowego, a każda
propozycja wymaga ręcznego potwierdzenia.

Instrukcja jest przeznaczona dla właściciela projektu i zakłada Windows
PowerShell oraz repozytorium:

```text
C:\Users\user\Documents\game_predicotr
```

Aplikacja mobilna działa całkowicie offline. Panel Admin, Admin API,
PostgreSQL, worker i Reviewer są lokalnymi narzędziami do przygotowywania
danych, ich weryfikacji oraz budowania APK. Telefon nie łączy się z żadnym z
tych procesów.

Audyt mutacji lokalnego Admina znajduje się w
`artifacts\admin-audit\local-admin-events.jsonl`. Plik jest append-only i należy
go objąć backupem razem z pozostałymi artefaktami. Nie edytuj go ręcznie;
zatrzymaj API przed kopiowaniem spójnej kopii operatorskiej.

## Najkrótsza procedura na kolejny dzień pracy

1. Uruchom Docker Desktop.
2. Otwórz PowerShell w katalogu repozytorium.
3. Uruchom bazę i migracje:

```powershell
npm run db:up
npm run db:migrate
```

4. Uruchom oba workery w kontrolowanym tle:

```powershell
npm run workers:start
```

5. Uruchom osobne okna PowerShell:

| Okno | Komenda | Kiedy jest potrzebne |
|---|---|---|
| 1 | `npm run api:dev` | zawsze dla Admina i Reviewera |
| 2 | `npm run admin:dev` | podczas pracy w panelu Admin |
| 3 | `npm run reviewer:dev` | podczas zatwierdzania plansz |

6. Otwórz Admin pod `http://127.0.0.1:3000/`.
7. Reviewer otwieraj wyłącznie przez link i kod utworzone w sekcji
   `Zatwierdzanie`.

## Jednorazowe przygotowanie Windows

Repozytorium wymaga Node `>=22.13 <25`, npm `>=11 <12`, Python 3.12,
Microsoft OpenJDK 17, Android SDK 36, ADB oraz Docker Desktop z Linux
containers.

W tym workspace lokalny toolchain znajduje się w ignorowanym katalogu
`.tooling`. Zapisz jego ścieżki i zmienne na stałe dla bieżącego użytkownika:

```powershell
npm run windows:environment:setup
```

Skrypt zapisuje:

- ścieżki Node.js i npm,
- `JAVA_HOME`,
- `ANDROID_HOME` i `ANDROID_SDK_ROOT`,
- `GAME_PREDICTOR_GRADLE_USER_HOME`,
- wpisy jednego kanonicznego `Path` dla Node, Javy, ADB, Android command-line
  tools i Docker CLI.

Windows traktuje nazwy `Path` i `PATH` jako tę samą zmienną. Repozytorium nie
wymaga dwóch wpisów i normalizuje odziedziczony proces do jednego `Path`.
Regresję uruchamiania procesu z przekierowanymi logami można sprawdzić przez:

```powershell
npm run windows:environment:smoke
```

Zamknij wszystkie stare okna PowerShell i otwórz nowe. Następnie sprawdź:

```powershell
node --version
npm --version
java -version
adb version
docker --version
npm run windows:environment:check
```

Aktualna konfiguracja referencyjna to Node `24.14.0`, npm `11.18.0`, JDK
`17.0.20`, Android Platform/Build Tools 36 oraz ADB `1.0.41`.

Jeżeli zależności repozytorium albo `.venv` nie istnieją, wykonaj bootstrap:

```powershell
npm install
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Polecenie `py -3.12` wymaga zainstalowanego Pythona 3.12. Jeżeli izolowanego
JDK/Android SDK brakuje, przygotuj go przed ponownym zapisaniem środowiska:

```powershell
npm run android:toolchain:setup
npm run windows:environment:setup
```

Domyślna konfiguracja aplikacji jest bezpieczna i działa bez kopiowania
[`.env.example`](../../.env.example). Plik ten jest listą opcjonalnych
zmiennych; repozytorium nie wczytuje go automatycznie do bieżącego PowerShell.

## Uruchomienie panelu Admin

Uruchom Docker Desktop. Następnie w katalogu repozytorium:

```powershell
npm run db:up
npm run db:migrate
npm run db:current
```

`db:up` czeka na healthcheck i (od TASK-0795) zapewnia rolę aplikacyjną
`game_predictor_app` z uprawnieniami (sekcja „Rola aplikacyjna bazy” wyżej);
migracje działają rolą właściciela. Dane są zachowywane w wolumenie Dockera,
więc zwykłe zatrzymanie bazy ich nie usuwa.

W pierwszym oknie PowerShell uruchom API:

```powershell
npm run api:dev
```

Tryb `api:dev` obserwuje wyłącznie `services/api/src` i automatycznie przeładowuje
API po zmianie kodu Pythona. Dzięki temu uruchomiony Admin nie korzysta ze
starszego kontraktu endpointów. Po aktualizacji repozytorium ze starszej wersji
tego skryptu zatrzymaj istniejące API raz skrótem `Ctrl+C` i uruchom je ponownie;
od kolejnych zmian ręczny restart nie jest potrzebny.

Odczyty `Weryfikacji symboli` mają domyślny serwerowy limit 20 sekund dla strony
i 15 sekund dla liczników. W razie kontrolowanych pomiarów można nadpisać je
przed uruchomieniem API; wartości muszą być dodatnimi milisekundami:

```powershell
$env:GAME_PREDICTOR_SYMBOL_REVIEW_PAGE_STATEMENT_TIMEOUT_MS = '20000'
$env:GAME_PREDICTOR_SYMBOL_REVIEW_COUNTS_STATEMENT_TIMEOUT_MS = '15000'
npm run api:dev
```

Istniejący proces API wymaga restartu, aby wczytać zmienione ustawienia.
Timeout chroni połączenie PostgreSQL, ale nie zastępuje optymalizacji zapytania.
Nie zwiększaj go jako pierwszej reakcji na stale wolne liczniki.

Możesz potwierdzić jego gotowość w drugim oknie:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

W kolejnym oknie uruchom panel:

```powershell
npm run admin:dev
```

Otwórz `http://127.0.0.1:3000/`. Dokumentacja API jest dostępna lokalnie pod
`http://127.0.0.1:8000/docs`.

Ogólne joby w stanie `created`, w tym właściwy `Import layoutów`, wymagają
general workera. Ten sam general worker wykonuje także bounded host actions
zdalnej ręcznej selekcji przed próbą pobrania zwykłego joba; po restarcie
reconciliuje istniejące verified uploady i publikuje brakujące `seq_*`.
`Selekcja zdjęć` ma odrębny lane i drugi proces. Domyślna komenda uruchamia
obecnie wyłącznie general workera w kontrolowanym tle i natychmiast zwraca
terminal:

```powershell
npm run workers:start
```

Ponowne wywołanie nie tworzy duplikatów. Status konsoli zawiera PID, czas
startu, budżet wątków oraz osobne ścieżki logów każdego lane:

```powershell
npm run workers:status
```

Oba lane korzystają z tego samego API, PostgreSQL i panelu Admin, ale nie
blokują swoich kolejek. Można uruchomić tylko potrzebny proces. Przy pracy
równoległej konkurują o CPU, RAM i dysk, więc pojedynczy job może działać wolniej
niż wtedy, gdy jest jedynym obciążeniem komputera.

Profil `npm run workers:start` oznacza `general=7` oraz zatrzymany lane
image-selection. General nadal przejmuje tylko jeden job naraz; budżet siedmiu
przyspiesza adaptery mające własną bounded równoległość, w szczególności
rejestrację geometrii stron. Biblioteki natywne pozostają jednowątkowe wewnątrz
każdej strony, aby nie tworzyć zagnieżdżonej nadsubskrypcji.

Jeżeli automatyczna Selekcja zdjęć będzie ponownie potrzebna, uruchom historyczny
bezpieczny profil `general=2`, `image-selection=5`:

```powershell
npm run workers:start:all
```

Nie przekazuj tych parametrów przez `npm run workers:start -- ...`: npm na
Windows może usunąć nazwy argumentów i PowerShell zwiąże wartość `2` z
parametrem `Lane`.

Workspace `Joby` pokazuje oba procesy niezależnie jako `Działa`, `Brak świeżego
sygnału` albo `Zatrzymany`, również gdy nie ma żadnego joba w kolejce. Status
nie zastępuje postępu konkretnego joba.

Kontrolowane zatrzymanie obu procesów:

```powershell
npm run workers:stop
```

Po restarcie komputera procesy nie uruchamiają się automatycznie. Wystarczy
ponownie wykonać `npm run workers:start`; supervisor rozpozna nieaktywny stan z
poprzedniej sesji. Jawne zarządzanie historycznym lane selekcji pozostaje
dostępne:

```powershell
npm run workers:start -- -Lane general
npm run workers:stop -- -Lane general
npm run workers:start -- -Lane image-selection
npm run workers:stop -- -Lane image-selection
```

Ręczne komendy foreground pozostają dostępne diagnostycznie w osobnych
terminalach:

```powershell
npm run worker:poll
npm run worker:image-selection:poll
```

Nie łącz ręcznego procesu i supervisora dla tego samego lane. Supervisor może
bezpiecznie zatrzymać wyłącznie proces, który sam uruchomił i zapisał w
`.runtime\worker-lanes.json`.

Do jednorazowego pobrania najwyżej jednego joba służy:

```powershell
npm run worker:once
npm run worker:image-selection:once
```

Nie uruchamiaj dwóch kopii tego samego lane ani kilku buildów Android. Poprawny
układ równoległy to najwyżej jeden general worker i jeden image-selection
worker.

Domyślne limity host action materializacji to lease 60 sekund, 5 prób i 4
akcje w jednym cyklu workera. Można je zmienić trwale w środowisku procesu:

```powershell
[Environment]::SetEnvironmentVariable('GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_LEASE_SECONDS', '60', 'User')
[Environment]::SetEnvironmentVariable('GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_MAX_ATTEMPTS', '5', 'User')
[Environment]::SetEnvironmentVariable('GAME_PREDICTOR_REMOTE_SELECTION_MATERIALIZATION_MAX_ACTIONS_PER_CYCLE', '4', 'User')
```

Po zmianie otwórz nowy PowerShell i zrestartuj general worker. Zatrzymanie
executora nie usuwa verified temp ani finalnych plików; kolejny start bezpiecznie
wznawia akcje queued/retry i wygasłe processing.

### Uruchomienie dużego runu Selekcji Zdjęć na bieżącym selektorze

Nowe runy używają `fast-image-selector-v10.14`. Po aktualizacji kodu zatrzymaj
procesy uruchomione na wcześniejszej wersji, ponieważ działający proces nie
zmienia manifestu w pamięci. W PowerShell przejdź do repozytorium:

```powershell
cd C:\Users\user\Documents\game_predicotr
npm run workers:stop
npm run db:up
npm run db:migrate
npm run workers:start
npm run workers:status
```

Komenda `workers:stop` może zgłosić, że nic nie działa — na świeżym starcie jest
to poprawne. Sprawdź aktywny manifest:

```powershell
.\.venv\Scripts\python.exe -c "from game_predictor_worker.images.selection.manifest import DEFAULT_SELECTOR_MANIFEST as m; print(m.algorithm_version); print(m.fingerprint)"
```

Oczekiwany wynik:

```text
fast-image-selector-v10.14
f74178fb612e636d3b7a501f4e0490d450f2bb69903e5dfdde47d9c5a24dc5a8
```

Pozostaw pierwszy terminal dla API:

```powershell
npm run api:dev
```

W drugim PowerShell uruchom Admin:

```powershell
cd C:\Users\user\Documents\game_predicotr
npm run admin:dev
```

Następnie otwórz `http://127.0.0.1:3000/`, wybierz grę i workspace
`Selekcja zdjęć`. Wskaż folder zawierający naturalnie uporządkowane JPEG-i,
poczekaj na zakończenie uploadu, wpisz dodatni numer pierwszego layoutu i
uruchom selekcję. Pełny run v10.14 wymaga jednoznacznych granic sekwencji; bez
kotwicy początku nie może zastosować bramki pełnej liczności.
Nie uruchamiaj w tym samym czasie Importu layoutów, jeżeli ten przebieg ma być
miarodajnym pomiarem bieżącego selektora. Postęp i stan procesu obserwuj w
workspace `Joby` albo przez:

```powershell
npm run workers:status
```

Nie zatrzymuj API ani image-selection workera do czasu osiągnięcia przez job
stanu terminalnego. Po zakończeniu pozostaw run i staging bez zmian — metryki,
liczbę grup oraz diagnostykę wykorzystamy do zamknięcia TASK-0171. Jeżeli
musisz przerwać próbę, użyj anulowania konkretnego joba w panelu; nie usuwaj
folderu uploadu ani bazy.

Rozpoczęty run zachowuje fingerprint selektora, z którym został utworzony.
Dlatego runu v10.2 nie przełącza się w locie na v10.3: należy pozwolić mu dojść
do stanu terminalnego, zakończyć jego monitor eksportu, a następnie przeładować
API i lane `image-selection` przed utworzeniem kolejnego runu. Historia oraz
galeria ręcznej selekcji wcześniejszego runu pozostają w bazie i są dostępne po
wybraniu tego runu w Adminie, o ile operator nie wyczyści danych gry lub
stagingu.

### Jak używać panelu Admin

Minimalna kolejność przygotowania danych i wydania:

1. W workspace `Zarządzanie grami` otwórz `Gry` i utwórz albo wybierz grę.
2. Otwórz `Import layoutów`, wybierz folder Windows i uruchom import zdjęć.
3. Otwórz `Symbole`, zatwierdź bootstrap i popraw nazwy lub obrazy symboli.
4. Otwórz `Reguły`, przygotuj bieżący draft, paylines, minima oraz payouty,
   opublikuj reguły i uruchom przeliczenie layoutów.
5. Otwórz `Zatwierdzanie`, wybierz gotowy import i utwórz sesję osobnej
   aplikacji Reviewer; przycisk może od razu wystawić ją przez czasowy HTTPS.
6. W osobnym workspace `Joby` obserwuj status i etap. Dla zadań
   asynchronicznych worker musi działać.
7. W osobnym workspace `Wersje Android` utwórz jedno kontrolowane wydanie dla
   aktywnej gry. Najnowsza zgodna para opublikowanego datasetu i reguł jest
   wybierana automatycznie.

Admin 0.2 nie pokazuje osobnych workspace'ów `Datasety` ani `Manual review`.
Pozostają one wewnętrznymi encjami workflow, a decyzje użytkownika prowadzą
przez import, reguły i osobną aplikację Reviewer.

### Geometria plansz i odroczone pozycje

Od TASK-0790 (D-467) importy używają wyłącznie wirtualnej geometrii
(`structured_default` albo domyślnie `structured_lattice_v3`); historyczne
tryby v18 i `verified_v19` (v20, cropy-pliki) zostały usunięte. Pozycja, dla
której silnik nie wyznaczył pewnej siatki, jest trwale odkładana (deferred)
do ręcznej korekty w Reviewerze.

Po zakończeniu importu wybierz ten sam import w `Zatwierdzaniu plansz`. Licznik
`Do korekty siatki` prowadzi do osobnego trybu Reviewera. Dla każdej pozycji:

1. wskaż zewnętrzną siatkę symboli 5 × 3 przeciągnięciem:
   naciśnij lewy górny narożnik (LT), trzymaj przycisk myszy i przeciągnij
   kursor do prawego dolnego narożnika (PD) — żywy podgląd 3 × 5 podąża za
   kursorem — a następnie puść przycisk. Escape anuluje rozpoczęte zaznaczenie,
   a zaznaczenie mniejsze niż 80 × 60 px jest odrzucane.
2. Jeśli automatyczna siatka wymaga tylko drobnej korekty, kliknij planszę na
   liście po lewej (wejście w tryb edycji), a potem przeciągnij wybrany narożnik
   lub środek siatki.
3. wygeneruj podgląd komórek planszy (render wirtualny ze źródła),
4. zapisz dopiero po sprawdzeniu, że żaden symbol nie jest ucięty ani przesunięty
   do sąsiedniego pola,
5. wróć do zwykłej kolejki i zatwierdź symbole utworzonej planszy.

Snapshot działającego joba jest niezmienny. Nie usuwaj ręcznie rekordów
deferred ani historycznych artefaktów v20.

Kandydat modelu symboli wytrenowany na cropach v19 został odrzucony przez
bramkę błędów wysokiej pewności. Nie wymaga ręcznego rollbacku, ponieważ nigdy
nie został aktywowany; nowe joby nadal przypinają dotychczasowy aktywny model.

Końcową techniczną bramkę 0.2 można powtórzyć bez użycia danych roboczych:

```powershell
npm.cmd run v02:admin:acceptance
```

Nie archiwizuj źródeł używanych przez przygotowywane wydanie. Zmiana reguł lub
danych nie aktualizuje aplikacji już zainstalowanej na telefonie — wymaga
nowego wydania APK z wyższym `VersionCode`.

## Uruchomienie aplikacji Reviewer

Do pracy wyłącznie lokalnej Reviewer wymaga działających PostgreSQL, API i
własnego procesu Next.js. Po zbudowaniu Reviewera panel może uruchamiać ten
proces samodzielnie. Jednorazowo po zmianie jego kodu wykonaj:

```powershell
npm run reviewer:build
```

Następnie:

1. w Adminie otwórz `Korekta cięcia siatki`,
2. wybierz aktywną grę i jej import zdjęć,
3. kliknij `Otwórz lokalnie`,
4. Reviewer uruchomi się pod `http://127.0.0.1:3001` i od razu otworzy wybrany
   import bez tunelu oraz kodu w widoku `Korekta cięcia siatki` — jedna
   plansza naraz z kolejki plansz odrzuconych przez algorytm albo zgłoszonych
   jako `Zła siatka` (D-462).

Lokalny widok geometrii jest obowiązującym workflowem i nie ma zmiennej
przywracającej poprzedni ekran. Sekcja nie tworzy linków online, assignmentów,
sesji ani kodów dostępu. Przycisk najpierw uruchamia albo weryfikuje lokalny
proces przez `reviewer-local/start`, a po jego gotowości ponownie otwiera
dokładny URL wybranej gry i importu. Dzięki ponownej nawigacji karta nie
pozostaje na `ERR_CONNECTION_REFUSED`, gdy port 3001 był zatrzymany przed
kliknięciem.

Aktualizacja do 0.9 (raport zajętości i resumowalny backfill schematu) jest
procedurą historyczną: jej skrypty `report_v09_storage_cleanup.py` i
`backfill_v09_schema.py` usunięto w TASK-0752 (D-467), bo wszystkie gry są w
magazynie V2. Migracje wykonuje się jak zawsze przez `alembic upgrade head`
przy wyłączonych API, workerze, Adminie i Reviewerze. Nie uruchamiaj
`VACUUM FULL` jako części aktualizacji.

## Kontrola zajętości i pierwsze czyszczenie storage

Po migracji do `0081` nowe importy nie utrwalają pełnowymiarowych
`normalized.png`. Panel Admina `Pamięć i czyszczenie` pokazuje ostatni trwały
inwentarz; zwykłe otwarcie strony nie skanuje milionów plików. Przycisk
`Odśwież inwentarz` uruchamia bounded job w general lane. Skan zapisuje wynik
po każdej przestrzeni nazw i po restarcie wznawia się od następnej.

Pierwszy kontrolowany cleanup z 29 sierpnia 2026 wykonano i odebrano. Tryb
obserwacyjny pozostaje dostępny do diagnostyki lub kolejnego ręcznego rollout'u:

```powershell
$env:GAME_PREDICTOR_STORAGE_GC_OBSERVE_ONLY = 'true'
npm run api:dev
```

W panelu wybierz `Przygotuj raport czyszczenia`. Raport jest dry-runem: zawiera
dokładne ścieżki, rozmiary, mtime, klasy, powody ochrony, checksumę manifestu i
token, ale niczego nie usuwa. Dopiero jawne `Usuń bezpieczne dane` uruchamia
wznawialny job GC. Kandydat zmieniony po raporcie otrzymuje konflikt i nie jest
usuwany. `data/originals`, referencjonowane cropy, modele, kohorty, snapshoty,
release'y, eksporty audytowe i dane ręcznej selekcji nie są kandydatami.

Browserowy staging może zostać usunięty dopiero po checksumowanym handoffie
wszystkich JPEG-ów do managed originals i po 24 godzinach od ostatniej
zależności. Historyczny staging bez trwałego stanu lifecycle jest widoczny w
raporcie jako chroniony; nie naprawiaj tego przez ręczne kasowanie katalogu.

Odtwarzalne payloady PostgreSQL mają oddzielny, również checksum-bound dry-run:

```powershell
.venv\Scripts\python.exe scripts\compact_image_pipeline_state.py preview --retention-hours 24
```

Polecenie zwraca ścieżkę manifestu, checksumę i token. Wykonanie jest dozwolone
wyłącznie po sprawdzeniu raportu oraz świadomym podaniu wszystkich wartości:

```powershell
.venv\Scripts\python.exe scripts\compact_image_pipeline_state.py start `
  --manifest-relative-path <MANIFEST> `
  --manifest-checksum-sha256 <SHA256> `
  --preview-token <TOKEN> `
  --confirm DELETE_REPRODUCIBLE_PIPELINE_PAYLOADS
```

Kompakcja usuwa tylko odtwarzalne późne payloady i uruchamia
`VACUUM (ANALYZE)`. Zwolnione strony stają się dostępne do ponownego użycia
przez PostgreSQL, ale rozmiar pliku VHDX nie musi się zmniejszyć. `VACUUM FULL`,
zatrzymanie Dockera i kompaktowanie `docker_data.vhdx` nie są częścią GC i
wymagają osobnej, jawnej operacji operatorskiej. Procedury opisuje
[runbook utrzymania bazy](DATABASE_MAINTENANCE.md).

Po odbiorze pierwszego cleanupu automatyczne GC jest domyślnie aktywne.
`GAME_PREDICTOR_STORAGE_GC_OBSERVE_ONLY=true` służy do jego jawnego,
tymczasowego wyłączenia. Poniżej 60 GiB system tworzy jeden idempotentny GC;
poniżej rezerwy 30 GiB blokuje nowe operacje zapisujące obrazy. Brak
bezpiecznych kandydatów pozostawia blokadę i wymaga decyzji użytkownika —
system nie rozszerza wtedy automatycznie zakresu usuwania.

Podczas rozwoju można nadal jawnie uruchomić `npm run reviewer:dev`; przycisk
lokalny wykorzysta gotowy proces na porcie 3001. Przycisk
`Utwórz link i wystaw online` zachowuje osobny zdalny workflow: uruchamia tunel,
tworzy sesję i pokazuje link oraz jednorazowy kod.

Kod jest pokazywany tylko przy tworzeniu sesji online. Taka sesja jest trwała,
ważna przez 8 godzin, ma limit pięciu błędnych prób i może zostać unieważniona.

Nie wysyłaj lokalnego adresu `127.0.0.1`. Zdalny dostęp używa wyłącznie
kontrolowanego trybu HTTPS opisanego niżej; nie przekierowuj portów routera.

## Zbudowanie mobilnego APK z bieżącego snapshotu

Ta procedura buduje snapshot znajdujący się aktualnie w
`apps\mobile\assets\snapshot`. Jeżeli dane zostały zmienione w Adminie, użyj
workflow `Wydania Android`, aby najpierw wygenerować nowy snapshot i APK.

Sprawdź środowisko i zależności:

```powershell
npm run windows:environment:check
```

Kontrola obejmuje również zmienne użytkownika Windows i wpisy `PATH` zapisane
trwale w profilu. Dzięki temu wynik `passed` obowiązuje także dla nowego
terminala i po ponownym uruchomieniu komputera, a nie tylko dla bieżącej sesji.
Jeżeli kontrola zgłosi brak trwałej konfiguracji, wykonaj:

```powershell
npm run windows:environment:setup
```

Jeżeli katalog `node_modules` nie istnieje, wykonaj wcześniej `npm install`.

Sprawdź wersję już zainstalowaną na podłączonym telefonie:

```powershell
adb shell dumpsys package com.gamepredictor.mobile | Select-String 'versionCode|versionName'
```

Ustaw nowy numer. `VersionCode` musi być większy od zainstalowanego:

```powershell
$versionName = '0.1.3'
$versionCode = 4
npm run android:build:offline -- --VersionName $versionName --VersionCode $versionCode
```

Skrypt używa jednego workera Gradle, wyłącza równoległy build, ogranicza natywny
CMake do dwóch zadań i uruchamia kompilator Kotlin w procesie Gradle, aby nie
pozostawiać drugiego daemona zajmującego pamięć. Te ustawienia generuje również
plugin Expo, więc nie znikają po odtworzeniu katalogu `android`. Expo prebuild ma
domyślny limit 5 minut, a Gradle 30 minut.
Build kończy target aplikacji `:app:assembleRelease`; nie publikuje osobnych
artefaktów AAR zależności.
Po przekroczeniu limitu całe drzewo danego builda jest kończone, więc nie wolno
uruchamiać drugiej kopii bez sprawdzenia komunikatu pierwszej. Pełne czyszczenie
projektu natywnego wykonuj tylko jawnie z `-CleanNativeProject`, gdy zmieniła się
konfiguracja natywna albo zwykły prebuild zgłosi kontrolowany błąd.

Build Release tworzy albo sprawdza prywatne dane podpisu w
`.tooling\android-signing`. Wykonaj ich bezpieczną kopię poza repozytorium.
Utrata klucza uniemożliwi aktualizację już zainstalowanej aplikacji bez jej
odinstalowania.

Gotowy plik:

```text
apps\mobile\android\app\build\outputs\apk\release\app-release.apk
```

Przed instalacją wykonaj statyczny audyt pakietu:

```powershell
npm run android:verify:offline
```

Audyt sprawdza między innymi podpis, architekturę `arm64-v8a`, bundle
JavaScript, checksum SQLite oraz brak uprawnienia Android `INTERNET`.

## APK utworzone przez panel Admin

W sekcji `Wydania Android`:

1. wybierz opublikowane i zgodne źródła,
2. utwórz nowe wydanie z nowym `VersionCode`,
3. uruchom build,
4. pozostaw `npm run worker:poll` do końca zadania,
5. instaluj dopiero wydanie o statusie gotowym, z zapisanym SHA-256,
6. pobierz APK przez kontrolowany przycisk panelu albo użyj pokazanej względnej
   ścieżki artefaktu.

Panel nie instaluje APK na telefonie. Każdy plik nadal instalujesz ręcznie
przez ADB.

## Podłączenie Google Pixel 10 Pro XL

Na telefonie:

1. `Settings` → `About phone`.
2. Naciśnij siedem razy `Build number`.
3. Wróć do `Settings` → `System` → `Developer options`.
4. Włącz `USB debugging`.
5. Podłącz kabel USB.
6. Odblokuj telefon i zaakceptuj `Allow USB debugging`.

Na komputerze:

```powershell
adb devices -l
```

Telefon musi mieć status `device`, nie `unauthorized`. Do kontrolowanego testu
podłącz dokładnie jedno urządzenie. Gdy podłączonych jest więcej, dodawaj do
komend `adb` parametr `-s SERIAL`.

## Pierwsza instalacja albo aktualizacja APK

Ustaw ścieżkę do wybranego, zweryfikowanego APK:

```powershell
$apkPath = 'apps\mobile\android\app\build\outputs\apk\release\app-release.apk'
```

Pierwsza instalacja:

```powershell
adb install $apkPath
```

Aktualizacja bez kasowania danych:

```powershell
adb install -r $apkPath
```

Nie odinstalowuj aplikacji przed testem aktualizacji. Odinstalowanie usuwa
lokalne dane i nie potwierdza zgodności podpisu ani prawidłowej aktualizacji
in-place.

Aplikacja jest widoczna jako `Sequence Target Analyzer`. Możesz uruchomić ją
ikoną albo:

```powershell
adb shell monkey -p com.gamepredictor.mobile -c android.intent.category.LAUNCHER 1
```

Do odbioru wersji `0.1` używany jest Google Pixel 10 Pro XL. Test offline:

1. uruchom aplikację raz po instalacji,
2. włącz tryb samolotowy,
3. wyłącz Wi-Fi,
4. zamknij i ponownie uruchom aplikację,
5. przejdź przez matching, podpowiedź duplikatu, exact duplicate, Undo/Reset i
   Target.

Gdy wracasz do formalnego testu aktualizacji i dokładnie jeden telefon jest
podłączony, możesz użyć kontrolowanego instalatora:

```powershell
npm run android:device:accept -- -ExpectedModelPattern '^Pixel 10 Pro XL$' -Stage Update -RequireAirplaneMode
```

Skrypt instaluje i uruchamia APK, sprawdza wyższy `VersionCode` oraz zachowanie
`firstInstallTime` i zapisuje raport urządzenia. Ręczne scenariusze znajdują
się w
[M1_DEVICE_ACCEPTANCE.md](../quality/M1_DEVICE_ACCEPTANCE.md).

Po każdej zmianie kodu mobile lub danych SQLite przeznaczonej do testu
samodzielnego trzeba zbudować nowe APK i wykonać `adb install -r`. Zmiany
panelu Admin, API albo Reviewera nie wymagają instalowania APK — wystarczy
restart odpowiedniego procesu lub odświeżenie przeglądarki.

## Pełny reset lokalnej bazy Admina

Reset jest nieodwracalną operacją roboczą. Najpierw zatrzymaj API i workera oraz
wykonaj dump danych, które mogą być jeszcze potrzebne. Następnie uruchom:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/reset_local_admin_database.ps1 -ConfirmReset
```

Skrypt akceptuje wyłącznie bazę `game_predictor` na lokalnym loopbacku. Usuwa
cały schemat `public`, tworzy pusty schemat i wykonuje migracje Alembic od zera.
Nie używa historycznych downgrade'ów, dlatego reset nie zależy od zawartości
starych rekordów. Nie usuwa zdjęć źródłowych, APK, snapshotów SQLite, klucza
podpisu ani innych plików z repozytorium.

## Trwałe usunięcie zarchiwizowanej gry (TASK-0826)

Panel Admin tylko archiwizuje grę. Trwałe usunięcie jednej zarchiwizowanej gry
V2 wykonuje komenda utrzymaniowa; bez `--execute` jedynie czyta bazę:

```powershell
$env:PYTHONPATH = "services/api/src"
.venv\Scripts\python.exe scripts\delete_archived_v2_game.py --game-id <UUID gry>
```

Podgląd pokazuje liczby rekordów, blokady, ścieżki plików gry oraz
`confirmation` i `previewSha256`. Gra nie może być w statusie `draft` ani
`active`, mieć zadań `created`/`processing`, należeć do wydania mobilnego ani
mieć rekordów w tabelach, których mechanizm nie czyści (np. sesje udostępniania
wyszukiwarki). Wykonanie jest nieodwracalne i wymaga obu wartości z podglądu:

```powershell
.venv\Scripts\python.exe scripts\delete_archived_v2_game.py --game-id <UUID gry> `
  --execute --expected-preview-sha256 "<previewSha256>" --confirmation "<confirmation>"
```

Komenda usuwa partycje gry w `game_data_v2` (jedna tabela na transakcję, limit
blokady 2 s), a na końcu symbole, wersje zasad, zadania, lokalizację magazynu i
rekord gry. Kod wyjścia 2 oznacza limit blokady albo czasu: ponów tę samą
komendę, operacja wznawia się od checkpointu (`--expected-preview-sha256` nie
jest wtedy sprawdzany). Komenda nie usuwa plików: katalogi źródłowe i manifesty
wymienione w `filesLeftOnDisk` pozostają na dysku.

## Zatrzymywanie usług

- API, Admin, worker i Reviewer: `Ctrl+C` w ich oknach PowerShell.
- PostgreSQL bez usuwania danych:

```powershell
npm run db:down
```

Nie używaj `db:reset:local` ani nie usuwaj wolumenu Dockera bez świadomej
decyzji i kopii danych.

## Najczęstsze problemy

- `node`, `npm`, `java`, `adb` lub `docker` nie są rozpoznawane — zamknij stare
  okno PowerShell, otwórz nowe i uruchom
  `npm run windows:environment:check`.
- `unauthorized` w `adb devices` — odblokuj telefon i zaakceptuj klucz RSA.
- `more than one device/emulator` — odłącz pozostałe urządzenie albo użyj
  `adb -s SERIAL ...`.
- `INSTALL_FAILED_VERSION_DOWNGRADE` — zbuduj APK z większym `VersionCode`.
- `INSTALL_FAILED_UPDATE_INCOMPATIBLE` — APK ma inny podpis. Nie odinstalowuj
  aplikacji, jeżeli chcesz zachować aktualizację in-place; użyj właściwego,
  zachowanego klucza.
- panel nie widzi danych — sprawdź Docker Desktop, `npm run db:up`, migracje,
  działające API i wynik endpointu health.
- Reviewer nie pokazuje importu — potrzebna jest aktywna gra oraz job
  `image_directory` dla tej gry.
- Reviewer odrzuca kod po restarcie API — utwórz nową sesję w Adminie.
- ogólny job pozostaje `created` — uruchom `npm run worker:poll`;
  job `image_selection` wymaga `npm run worker:image-selection:poll`.
- build Android trwa długo — nie uruchamiaj drugiego builda. Poczekaj na
  zakończenie kontrolowanego procesu Gradle albo sprawdź jego ostatni błąd.

## Udostępnienie wyszukiwarki plansz online

Link daje drugiej osobie tylko do odczytu kopię sekcji „Wyszukaj plansze”
razem z „Przybliżoną wygraną” dla jednej gry (D-471). Wymaga tego samego
produkcyjnego Reviewera i Quick Tunnel co zdalna ręczna selekcja (sekcja
niżej): jednorazowo `npm run reviewer:remote:setup` i `npm run reviewer:build`,
bez `reviewer:dev`. Migracja bazy musi być na `head`
(`npm run db:migrate`; tabela sesji udostępnień pochodzi z
`0130_board_search_share_sessions`).

1. W Adminie otwórz grę, rozwiń „Wyszukaj plansze” i kliknij „Udostępnij
   online”.
2. Podaj etykietę (opcjonalnie), czas dostępu (1/4/8/24 h, domyślnie 8 h) i
   kliknij „Utwórz link”. Pierwsze użycie uruchamia publiczny adres Reviewera
   (do około minuty).
3. Wyślij link i kod osobnymi wiadomościami. Kod jest pokazywany i
   pamiętany tylko w tej przeglądarce Admina.
4. „Dziennik zapytań” przy linku pokazuje, co odbiorca wyszukiwał i liczył;
   „Odtwórz w wyszukiwarce” powtarza zapytanie w Twoim Adminie.
5. Po zakończeniu kliknij „Zatrzymaj” (dwa kliknięcia) i zatrzymaj tunel, gdy
   nic innego nie jest udostępnione.

Najwyżej 5 linków może być aktywnych jednocześnie; 5 błędnych kodów blokuje
link. Odbiorca po wygaśnięciu albo zatrzymaniu widzi ekran zakończenia.
Wyłącznik: `GAME_PREDICTOR_BOARD_SEARCH_SHARE_ENABLED=false` (API i
Reviewer).

## Czasowy link HTTPS do zdalnej ręcznej selekcji

Ten tryb dotyczy wyłącznie purpose-scoped zdalnej ręcznej selekcji zdjęć.
Nie udostępnia ekranu `Korekta cięcia siatki`, który jest wyłącznie
lokalny. Admin, API, PostgreSQL i worker pozostają na `127.0.0.1`. Nie
konfiguruj przekierowania portów routera.

Jednorazowo zainstaluj oficjalny `cloudflared` i zbuduj produkcyjnego Reviewera:

```powershell
npm run reviewer:remote:setup
npm run reviewer:build
```

Uruchom PostgreSQL, migracje, API i Admin. Nie uruchamiaj `reviewer:dev`,
ponieważ serwer developerski nie może zostać wystawiony online. Capability i
link twórz wyłącznie w sekcji zdalnej ręcznej selekcji zdjęć.

Praca lokalna uruchamia lub wykorzystuje gotowego Reviewera na loopback i nie
zajmuje limitu online. Maksymalnie trzy różne importy mogą być jednocześnie
udostępnione online; każdy ma własny kod, sesję i przycisk zakończenia, ale
wszystkie wykorzystują jeden produkcyjny Reviewer oraz jeden Quick Tunnel.
Przycisk online uruchamia brakujące procesy, czeka na gotowość i tworzy scoped
sesję. Nie wykonuje builda w żądaniu. Jeżeli zobaczysz komunikat o trybie
developerskim, zatrzymaj okno z `reviewer:dev` i kliknij ponownie. Zimny start
ma twardy limit 60 sekund; zdrowy warm ingress jest używany ponownie bez nowego
procesu i bez zmiany publicznego originu. Proces uruchomiony przez
`npm run api:dev` automatycznie przeładowuje zmiany API.
Po ręcznym `npm run reviewer:build` kontroler porównuje aktualny `.next/BUILD_ID`
z identyfikatorem serwowanym przez proces na porcie 3001. Starszy produkcyjny
Reviewer zostaje zastąpiony przed ponownym użyciem linku; sam Quick Tunnel może
pozostać aktywny. Proces developerski lub listener, którego nie można bezpiecznie
zidentyfikować jako Node Reviewera, kończy operację jawnym błędem zamiast być
automatycznie zatrzymywany.
Awaryjny odpowiednik CLI:

```powershell
npm run reviewer:remote:start
npm run reviewer:remote:status
```

Kontroler sprawdza teraz połączenie TCP do
`api.trycloudflare.com:443` przed uruchomieniem tunelu. Jeżeli API działa w
procesie z zablokowanym internetem, panel zwraca od razu komunikat o niedostępnym
endpointcie zamiast czekać 30 sekund na nieistniejący URL. W takim przypadku
uruchom ponownie `npm run api:dev` w zwykłym PowerShellu Windows z dostępem do
wychodzącego HTTPS; restart komputera nie jest potrzebny. Firewall może
blokować Admin i API od strony sieci przychodzącej, ale proces API musi móc
nawiązać wychodzące połączenie HTTPS dla jawnie uruchamianego Quick Tunnel.

Nowy losowy hostname Quick Tunnel może przez kilka sekund być ukryty przez
lokalny negatywny cache DNS. Kontroler sprawdza ograniczenie kolejno przez
lokalny resolver, `1.1.1.1`, `8.8.8.8` i Cloudflare DNS-over-HTTPS. Jeżeli
adres jest już widoczny tylko w publicznym DNS, health check używa curl
`--resolve`: połączenie nadal wymaga zgodnego hostname'u, SNI i certyfikatu TLS.
Nie trzeba ręcznie czyścić cache DNS ani ponawiać startu z drugiego terminala.

`start` uruchamia proces w tle i pokazuje losowy adres
`https://...trycloudflare.com`. Nowa sesja automatycznie użyje aktywnego
publicznego originu.

Kontrolery `reviewer:remote:start`, `reviewer:remote:status`,
`reviewer:remote:stop` oraz lokalny start używają tego samego nazwanego mutexu
Windows. Równoległe wywołania są serializowane i mają ograniczony czas
oczekiwania. Stan w `.runtime/` jest publikowany atomowo dopiero po potwierdzeniu
gotowości procesu i zawiera PID, czas startu, executable oraz losowy identyfikator
instancji. Dzięki temu stary plik stanu albo PID ponownie użyty przez inny proces
nie powoduje jego zatrzymania. Nie usuwaj ręcznie pliku stanu podczas aktywnego
startu; `status` zgłosi niepełny lub niezgodny stan jako `stale`.

Każda próba startu zapisuje osobne pliki w
`.runtime/reviewer-lifecycle-logs/`, więc równoległy albo kolejny start nie
próbuje ponownie otworzyć jednego używanego pliku logu. Pliki wynikowe poleceń
API są również unikalne i znajdują się w
`.runtime/reviewer-ingress-controller-results/`. Oba katalogi są danymi
diagnostycznymi runtime i nie zawierają kodu sesji ani bearer tokenu.

Wyślij link i kod dwoma osobnymi kanałami. Odbiorca nie instaluje klienta VPN:
otwiera link w przeglądarce i podaje kod. Kod ma najwyżej pięć prób, a sesja
wygasa najpóźniej po 24 godzinach.

Po zakończeniu użyj `Zakończ pracę` przy właściwym imporcie. Panel unieważnia
tylko sesję tego assignmentu. Pozostałe linki działają nadal, a Quick Tunnel
jest zatrzymywany dopiero po zamknięciu ostatniej aktywnej pracy online. Praca
lokalna może pozostać aktywna, ponieważ nie publikuje portu. Po odświeżeniu
Admin odtwarza assignmenty z PostgreSQL, lecz ze względów bezpieczeństwa nie
pokazuje ponownie jednorazowego kodu. Decyzje plansz i audyt pozostają w
PostgreSQL. Awaryjny globalny stop jest przeznaczony wyłącznie do sytuacji, w
której nie ma już aktywnych prac online:

```powershell
npm run reviewer:remote:stop
npm run reviewer:remote:status
```

Ostatnia komenda powinna zwrócić `stopped`. Ponowny start wygeneruje inny URL,
więc trzeba utworzyć i przekazać nowy link. Stan procesu znajduje się w
ignorowanym katalogu `.runtime/`, a log nie zawiera kodu ani tokenu.

Quick Tunnel jest przeznaczony do czasowych testów/developmentu i nie ma SLA.
Stały adres wymaga później named tunnel i osobnej decyzji. Pełny test odbiorczy
TASK-0115 wykonuje się z urządzenia poza domową siecią: unlock, odczyt tylko
wskazanej gry/importu, jeden zapis, revoke oraz próby wejścia na zabronione
ścieżki Admina.

Lokalny endpoint wyboru bazy i purpose-scoped route sesji zdalnej ręcznej
selekcji zdjęć są domyślnie włączone. Awaryjny rollback bez zmiany bazy,
audytu i istniejących markerów:

```powershell
$env:GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED = 'false'
npm run api:dev
```

Po restarcie API wszystkie te route znikają z OpenAPI. Ponowne ustawienie
`true` przywraca je. Capability utworzone przed restartem procesu API są celowo
nieważne; cookie aktywnej sesji pozostaje ważne do TTL, rotacji lub revoke,
ponieważ binding, hash-only credentials, stan lease i audyt są trwałe w
PostgreSQL.

TASK-0282 dodaje binarny transfer wybranego JPEG-a. Domyślne, trwałe limity
procesu API można zmienić przed jego uruchomieniem:

```powershell
$env:GAME_PREDICTOR_REMOTE_SELECTION_MAX_FILE_BYTES = '33554432'
$env:GAME_PREDICTOR_REMOTE_SELECTION_MAX_SESSION_BYTES = '21474836480'
$env:GAME_PREDICTOR_REMOTE_SELECTION_MAX_ACTIVE_SESSION_TRANSFERS = '4'
$env:GAME_PREDICTOR_REMOTE_SELECTION_MAX_ACTIVE_GLOBAL_TRANSFERS = '8'
$env:GAME_PREDICTOR_REMOTE_SELECTION_UPLOAD_TIMEOUT_SECONDS = '120'
npm run api:dev
```

Zmiana limitu pliku w API powyżej 32 MiB wymaga osobnej zgodnej zmiany limitu
proxy Reviewera; obecna wersja celowo blokuje większe publiczne body wcześniej.
Transfer kończy się na prywatnym stanie `verified`. Brak finalnego `seq_*` jest
oczekiwany do czasu TASK 11.

Od TASK-0279 utworzenie purpose-scoped sesji zdalnej selekcji automatycznie
wykorzystuje ten sam produkcyjny Reviewer i Quick Tunnel. Publiczny link ma
postać `/manual-selection?session=<UUID>` i nie zawiera kodu ani tokenu. Po
restarcie tunelu odśwież detail/listę sesji w Adminie: ten sam identyfikator
sesji otrzyma bieżący origin. Nie uruchamiaj drugiej kopii Reviewera ani tunelu.

Shell TASK 7 obsługuje kod, context, heartbeat i takeover. Nie pokazuje jeszcze
folderu ani zdjęć — workspace i synchronizacja należą do TASK 8. Revoke działa
również wtedy, gdy kontroler tunelu jest niedostępny, i celowo nie zatrzymuje
wspólnego ingressu. Awaryjne wyłączenie całej powierzchni:

```powershell
$env:GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED = 'false'
npm run api:dev
```

Zatrzymaj wcześniej uruchomiony Reviewer i uruchom go ponownie z procesu API,
który dziedziczy tę flagę. Po ponownym uruchomieniu API i Reviewera
`/manual-selection` zwraca 404, proxy
nie przekazuje żądań, a starsze linki zatwierdzania plansz pozostają bez zmian.

## Mumie — stan i wznowienie wgrania (TASK-0843)

Wgrano 225/225 plików do gry „Mumie”, gameId
`fea55cc1-ebf4-4cee-b3ab-a520017ed1be`. Staging jest sfinalizowany; preflight
zwraca `IMAGE_PAGE_GEOMETRY_REVIEW_REQUIRED` dla wszystkich 225 źródeł.
Nie uruchomiono importu plansz. Wybór profilu Mumii obecnie wskazuje model,
ale nie uruchamia sieci w głównym imporcie. Przegląd modelowych siatek jest
w laboratorium `http://127.0.0.1:8105`; V3-D wymaga osobnego polecenia.

Odczyt trwałego stanu bez nowego transferu:

```powershell
$env:PYTHONPATH = 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\worker\src'
& 'C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe' 'C:\Users\tuszy\Documents\game_predicotr\artifacts\grid-v3-deployment-20261004\run_step.py' --timeout 120 --cwd 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3' --name mumie-import-status -- 'C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe' 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\scripts\run_mumie_image_import.py' --step status --source 'C:\Users\tuszy\Documents\game_predictor_traning_set\mumie' --report 'C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-import-20261004\state.json'
```

Ten sam raport i `--step upload` odzyskują istniejący staging i pomijają
wgrane indeksy. `--step advance` sprawdza istniejący geometry job i preflight;
tworzy import tylko po spełnieniu bramek gotowości. Nie zatwierdza siatek.
Nie uruchamiać go z nową ścieżką raportu jako sposobu na obejście review.
Nie wykonywać historycznego `run_v20_layout_import.py` z polityką `verified_v19`.

Pełny odbiór i checksumy: `ai_docs/quality/MUMIE_PRODUCTION_UPLOAD_20261004.md`.
