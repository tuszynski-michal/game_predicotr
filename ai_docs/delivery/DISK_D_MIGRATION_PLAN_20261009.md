---
title: Przeniesienie aplikacji i bazy na dysk D
status: accepted
last_updated: 2026-10-10
---

# Przeniesienie aplikacji i bazy na dysk D

## Stan i zakres zlecenia

Operator chce uruchamiać aplikację z `D:\game_predicotr` dokładnie tak, jak
dziś z `C:\Users\tuszy\Documents\game_predicotr`, a potem przestać używać
katalogu na C. Baza danych ma również trafić na D, bo rośnie, a C ma
26,6 GB wolnego. Przeniesienie ma być podzielone na małe, wznawialne kroki,
między którymi można zrestartować komputer. Wynik końcowy: wyszukiwarka plansz
pokazuje zdjęcia, weryfikacja symboli pokazuje wszystkie kropy ze statusami,
czyli 100% danych jest dostępne z D.

Operator wykonał już na D: `git clone`, `npm install`, `.venv` z `pip install
-e ".[dev]"`. Nie uruchamiał `db:up` z D. Plan jest propozycją. Każdy etap
startuje dopiero na jawne polecenie operatora; operacje na danych operatora,
zatrzymywanie usług i zmiany w Docker Desktop pozostają przy operatorze lub
wymagają jego osobnej zgody (`AGENTS.md`, „Kontrola lokalnych usług API i
Admin”, „Operacje destrukcyjne”).

## Fakty ustalone w inwestygacji (2026-10-09, odczyt bez zmian)

Repozytoria:

- C: gałąź `v1.1-vision-lab-hybrid-geometry`, `c504fe70` (v1.7.296),
  27 niecommitowanych zmian (25 plików `ai_docs/tasks/**`, `package-lock.json`,
  nieśledzony `v7-output/`). Gałęzie tylko na C (brak na `origin`):
  `feat/grid-engine-v3`, `feat/mumie-super-game-plan`,
  `feat/super-game-series-count`, `task-0860`. Worktree'y: `worktrees/`
  (geometry-correction-revert, grid-engine-v3, mumie-super-game,
  super-game-series-count, disk-migration), `.claude/worktrees/agent-…`
  (`task-0860`) oraz jeden w katalogu tymczasowym sesji (detached `db99654f`).
  Stan plików w tych worktree'ach nie był sprawdzany.
- D: ten sam commit `c504fe70`, czysty, `origin` ten sam. `.venv`
  (Python 3.12.10) importuje `game_predictor_api`, `game_predictor_worker`,
  `alembic`, `psycopg`; `node_modules` ma 717 pakietów.

Baza:

- Kontener `game-predictor-postgres-1` (`postgres:18.4-alpine3.24`), projekt
  compose `game-predictor` (nazwa zapisana w `infra/docker/compose.yaml`),
  wolumen `game-predictor_game_predictor_postgres_data`, sieć
  `game-predictor_default`. Hash konfiguracji compose z C i z D jest
  identyczny (`545e46b4…`), więc `docker compose up` z D podłącza się do
  istniejącego kontenera bez odtwarzania.
- Dane leżą w `C:\Users\tuszy\AppData\Local\Docker\wsl\disk\docker_data.vhdx`
  (137,6 GB). Docker Desktop nie ma ustawionego własnego `DataFolder`
  (domyślna lokalizacja). Backend WSL2, limit pamięci 8 GB w `.wslconfig`.
- `game_predictor`: 85 GB, Alembic `0153_merge_compact_super_games`
  (head kodu). Obok: `game_predictor_v7_pilot` (188 MB),
  `mumie_0884_restore_20261006_155101_test` (44 GB) i 14 baz testowych po
  16–43 MB; role globalne `game_predictor`, `game_predictor_app`,
  `game_predictor_v7_pilot_app` i 10 ról `game_predictor_app_test_*`.
  Trzy gry: 777 (`bfc4f949…`, active), „777 aktu 2” (`f0ea7306…`, draft),
  Mumie (`fea55cc1…`, active).
- Joby: 1 `processing` (import `d9a49da0`, 3171/5784, etap
  `image_pipeline:sequence_ocr`, dzierżawa `laptop-16148`), 1 `created`
  (`super_game_series_derive`), 49 `waiting_for_review`. Tabele
  `remote_manual_selection_host_actions` i `remote_manual_selection_batches`
  są puste (brak oczekujących akcji hosta).
- Ścieżki w bazie: wszystkie kolumny `*_path` w `game_data_v2` są względne
  (np. `originals/c2/…jpg` względem `source_directory` joba,
  `data/symbol-references/…png` względem `artifact_root`). Ścieżki
  bezwzględne do C występują tylko w `public.jobs.input_payload`
  (`source_directory`, 173 jobów importu: 1 processing, 49 waiting_for_review,
  110 completed, 8 failed, 5 cancelled; `requeue_job` dopuszcza ponowienie
  `waiting_for_review`, `failed` i `cancelled`) i w
  `public.remote_manual_selection_sessions.host_base_path` (13 sesji:
  4 active, 9 revoked).

Pliki i konfiguracja:

- Korzenie danych są względne wobec katalogu uruchomienia API i workera
  (`ApiSettings.from_environment`, `services/api/src/game_predictor_api/config.py`):
  `GAME_PREDICTOR_ARTIFACT_ROOT` = `artifacts`, `GAME_PREDICTOR_IMPORT_ROOT`
  = `imports`, `GAME_PREDICTOR_REVIEW_SOURCE_ROOT` = `examples/imgs`,
  `GAME_PREDICTOR_REVIEW_CROP_ROOT` = `artifacts/m5-reviewed-…`,
  `GAME_PREDICTOR_V7_LABEL_GEOMETRY_RUNTIME_ROOT` = `.runtime`. Obrazy
  operacyjne są rozwiązywane pod `artifact_root/data`
  (`image_job_repository.py`, `root_name="data"`). Konfiguracja czyta
  wyłącznie `os.environ`; nie ma loadera `.env` i nie ma pliku `.env` na C
  ani na D; w HKCU nie ma zmiennych `GAME_PREDICTOR_*ROOT`.
- Katalogi ignorowane przez git, obecne tylko na C: `artifacts/` 47,0 GB
  (282 746 plików), `imports/` 28,8 GB (114 836 plików), `.tooling/` 1,1 GB
  (node, JDK, Android SDK, klucze podpisu), `.runtime/` 0,2 GB (stan
  lane'ów `worker-lanes.json`, tunelu `remote-reviewer.json`, logi),
  `work/` 0,2 GB, `v7-output/`, `examples/imgs/` (1 plik).
- Zmienne użytkownika (HKCU) wskazują C: `GAME_PREDICTOR_NODE_HOME`,
  `GAME_PREDICTOR_GRADLE_USER_HOME`, `JAVA_HOME`, `ANDROID_HOME`,
  `ANDROID_SDK_ROOT` oraz wpisy `.tooling\…` w `Path`. Ustawia je
  `scripts/configure_windows_user_environment.ps1` na podstawie katalogu
  repozytorium (`npm run windows:environment:setup`); skrypt dodaje nowe
  wpisy `Path` przed istniejącymi i nie usuwa starych; `GRADLE_USER_HOME`
  zostaje `C:\gpg`, jeśli ten katalog istnieje.
- Procesy na C: worker `general` (PID 16148), API 8000 z `--reload`, Admin
  3000 (`admin:dev`), Reviewer 3001 produkcyjny (`reviewer:start`), Quick
  Tunnel `cloudflared` (`arizona-everything-disturbed-corps.trycloudflare.com`).
  `scripts/manage_worker_lanes.ps1 -Action Stop` kończy proces workera
  przez `Kill()`, bez czekania na koniec joba. Przewodnik: restart API
  unieważnia sesje udostępnienia wyszukiwarki (capability procesu);
  trwałe sesje zdalnej selekcji pozostają w bazie.
- Dyski: C NTFS 447 GB (26,6 GB wolne), D NTFS 1 863 GB (1 857 GB wolne),
  wewnętrzny NVMe (Lexar NQ790 2 TB). Windows 11 Home (bez Hyper-V,
  `diskpart` do kompaktowania).
- Istniejący runbook: `ai_docs/guides/DATABASE_MAINTENANCE.md`, sekcje 3
  (kompaktowanie vhdx), 4 (kopia `pg_dump -Fc -Z 1`, ok. 22 GB, ok. 25 min)
  i 5 (migracja na inny dysk: dysk Dockera, artefakty, repozytorium).

## Decyzje planu

1. **Baza przenosi się przez zmianę lokalizacji obrazu dysku Docker Desktop**
   (Settings → Resources → Advanced → Disk image location), nie przez
   `pg_dump`/`pg_restore` ani bind mount. Docker kopiuje cały `docker_data.vhdx`
   i przełącza lokalizację; wolumen, kontener i wszystkie bazy przenoszą się
   bez zmiany zawartości. Bind mount katalogu NTFS do kontenera odrzucony
   (wydajność i `fsync` przez WSL).
2. **Dwa zabezpieczenia przed przeniesieniem.** (a) Etap A: `pg_dump -Fc`
   bazy `game_predictor` plus `pg_dumpall --globals-only` (role) na D;
   kopia logiczna, bez odtworzenia próbnego, chyba że operator zdecyduje
   inaczej (ok. 85 GB i godziny na D). (b) Etap B1, po zatrzymaniu zapisów
   i całkowitym zamknięciu Docker Desktop (`wsl --shutdown`): niezależna
   kopia pliku `docker_data.vhdx` na D (`robocopy /Z`, wznawialna) z
   weryfikacją SHA-256 źródła i kopii. Kopia vhdx jest podstawą odzyskania:
   obejmuje wszystkie bazy i role w stanie z chwili przełączenia. Zrzut
   z A jest dodatkowy (odzyskanie logiczne, odchudzenie).
3. **Wszystkie zachowywane wpisy ignorowane przez git kopiuje `robocopy`
   przyrostowo** z jednego skryptu (proponowany
   `scripts/sync_data_directories_to_d.ps1`): tryb `-Inventory`
   klasyfikuje wpisy ignorowane w danym checkoucie jako odtwarzalne
   (`node_modules`, `.venv*`, `.next`, cache, `packages/*/dist`,
   tymczasowe katalogi testów w `.runtime`) albo zachowywane (katalogi
   danych, `.runtime` z profilami i sesjami V7, `.tmp`, ustawienia
   lokalne, luźne pliki), a kopia obejmuje wszystkie zachowywane; dwa
   tryby kopii:
   `Initial` (przy działających usługach, błędy plików w użyciu dozwolone,
   wynik oznaczony jako niekompletny) i `Final` (po zatrzymaniu usług,
   każdy błąd, rozbieżność lub nieudana weryfikacja blokuje przełączenie).
   Weryfikacja trybu `Final` to porównanie manifestów (ścieżka względna,
   rozmiar, SHA-256) źródła i celu, nie liczb plików; `-VerifyOnly
   -Manifest` porównuje później cel z zapisanym manifestem B1 bez odczytu
   C i bez odrzucania nowych plików D. Logi poza kopiowanym zbiorem
   (`D:\game_predictor_backup\sync-logs\`). Po przełączeniu
   synchronizacja C→D do aktywnych katalogów jest zabroniona; w `.runtime`
   na D usuwa się tylko zinwentaryzowane pliki stanu procesów.
4. **Granica przełączenia (B1) jest stabilna:** najpierw zatrzymanie
   producentów zapisów (tunel, Reviewer, Admin, API), potem opróżnienie
   kolejki lane `general` (brak `processing` i brak `created`; job
   `super_game_series_derive` kończy się na C albo operator go anuluje i
   wznawia na D), potem `workers:stop`, potem ponowna kontrola jobów,
   dzierżaw i `remote_manual_selection_host_actions`; wyścig (job pobrany
   między kontrolą a `Kill()`) ma jawną procedurę: czekanie na wygaśnięcie
   dzierżawy, odzyskanie przez worker na D z checkpointem
   (`recover_expired_job`), rozliczenie jak joby ponawialne. Raport
   odniesienia dla wszystkich zachowywanych baz powstaje po tych
   kontrolach, a jego równość z raportem po przeniesieniu jest sprawdzana
   przed startem jakiegokolwiek producenta lub workera na D; późniejsze
   odbiory używają niezmienników i wyjaśnionych różnic. Po przeniesieniu
   operator uruchamia sam PostgreSQL (`compose up -d --wait postgres`);
   provisioning ról (`npm run db:up`, zapisy `ALTER ROLE`) następuje
   dopiero po bramce równości, w B2. Dopiero po raporcie odniesienia:
   `compose stop postgres`, kopia vhdx i przeniesienie. Źródło i wyniki
   joba `d9a49da0` leżą na C, więc B1 czeka na jego stan końcowy; job
   `super_game_series_derive` kończy się na C (ścieżka podstawowa) albo
   jest anulowany i wznowiony na D, i w obu przypadkach odbiór B2 uznaje
   jego stan końcowy bez ponownego uruchamiania.
5. **Brak zmian w kodzie aplikacji i w schemacie bazy.** Nowe są tylko
   skrypty operacyjne (synchronizacja, inwentaryzacja worktree'ów,
   weryfikacja odwołań do plików, podgląd przepisania ścieżek) i
   dokumentacja.
6. **Zabezpieczenie repozytorium (A3) obejmuje każdy worktree na C**
   (także detached HEAD): zmiany staged, unstaged i nieśledzone, bundle
   wszystkich referencji (`git bundle create … --all`), patche `--binary`
   zapisane przez `git diff --output` (bez przekierowań PowerShell), kopie
   plików nieśledzonych, inwentarz plików ignorowanych każdego worktree'a
   sklasyfikowanych jako odtwarzalne (`node_modules`, `.next`, `.venv`,
   cache) albo zachowywane (kopia na D z manifestem SHA-256), weryfikacja
   odtwarzalności na D (`git bundle verify`, patch staged przez `apply
   --index`, potem unstaged na odtworzonym indeksie). Usunięcie C
   (etap C) wymaga powtórnej inwentaryzacji i braku nowych zmian po A3.
7. **Dostarczenie planu i skryptów na D:** gałąź `feat/disk-d-migration-plan`
   jest wypychana po akceptacji i scalana do gałęzi integracyjnej za zgodą
   operatora (merge obejmuje push); B1 wymaga, aby checkout na D był na
   commicie zawierającym skrypt synchronizacji i wpis npm.
8. **Ścieżki bezwzględne do C w `jobs.input_payload` i bindingi zdalnej
   selekcji są rozliczane przed usunięciem C (etap C).** Dopóki katalog
   `imports/` na C istnieje, wznowienie starych jobów działa. Usunięcie
   C jest zablokowane do czasu, gdy: ponawialne joby (`waiting_for_review`,
   `failed`, `cancelled`, `created`) nie wskazują C, historyczne
   (`completed`) mają udokumentowany brak użycia `source_directory` przez
   obsługiwany przepływ, a 13 bindingów zdalnej selekcji ma zinwentaryzowane
   dane i brak oczekujących akcji. Wybór „archiwum `imports/` zostaje na C”
   wyklucza usunięcie tego archiwum.
9. **Zmienne użytkownika przepisuje istniejący skrypt** uruchomiony z D
   (`npm run windows:environment:setup`), po skopiowaniu `.tooling`.
   Stare wpisy `Path` z C usuwa się po odbiorze, jawnie (B2).
10. **Odbiór „100% danych” ma dowody, nie próbkę, i dwa poziomy:** skrypt
    tylko do odczytu (proponowany `scripts/verify_artifact_references.py`)
    rozwiązuje wszystkie kolumny `*_relative_path` z `game_data_v2` i
    `public` pod właściwymi korzeniami, czyta treść manifestów i raportuje
    brakujące pliki oraz rozwiązania „zależne od C”. Odbiór B2 dopuszcza
    zależności od C (tymczasowe, liczone) i powtarza się po restarcie
    Windows. Odbiór końcowy (etap C) po kontrolowanym odcięciu C (zmiana
    nazwy katalogu na `game_predicotr_old`, `git worktree repair`) wymaga
    `--forbid-prefix` = 0 rozwiązań do starego katalogu, także w treści
    manifestów, przed usunięciem.
11. **Stary katalog C, stary vhdx i bazy testowe usuwa się dopiero w
    etapie C**, po odbiorze z D i osobnej zgodzie na każdą operację.

## Etapy i kolejność

| Etap | Taski | Przestój | Można przerwać i wznowić |
|---|---|---|---|
| A (przygotowanie, aplikacja działa) | TASK-0952, TASK-0953, TASK-0954 | brak | tak, każdy task osobno |
| B1 (baza na D) | TASK-0955 | API, Admin, Reviewer, worker, baza | nie w trakcie kopii vhdx i przenoszenia; między krokami tak |
| B2 (aplikacja z D) | TASK-0956 | do pierwszego startu z D | tak |
| C (sprzątanie, osobne zgody) | TASK-0957 | brak | tak |

Kolejność: A1, A2, A3 mogą iść równolegle względem siebie. B1 wymaga:
TASK-0952, TASK-0953 (co najmniej jeden przebieg `Initial`) i TASK-0954
`done`, checkoutu D na commicie ze skryptami, joba `d9a49da0` w stanie
końcowym. B2 bezpośrednio po B1 albo po restarcie komputera (stan trwały:
Docker Desktop wskazuje D, usługi zatrzymane). C dopiero po pozytywnym
odbiorze B2, po restarcie Windows i po co najmniej jednym pełnym dniu
pracy z D.

Stan trwały i wznowienie na granicach etapów:

- po A: kopie i manifesty na D, gałęzie na `origin`, `Outcome` tasków;
  wznowienie = powtórzenie przebiegu `Initial` (idempotentny);
- po B1: Docker Desktop wskazuje D, usługi zatrzymane, raport odniesienia
  w `D:\game_predictor_backup\`; wznowienie = B2 od kroku 1;
- po B2: usługi z D; wznowienie = odbiór z sekcji niżej;
- w C: każda operacja ma własny podgląd i zgodę; przerwanie między nimi
  nie zostawia stanu pośredniego.

Miejsce na D (przed każdym krokiem skrypt liczy wolne miejsce): zrzut
ok. 25 GB + role, kopia vhdx 138 GB, katalogi danych 77 GB, przeniesiony
vhdx 138 GB, zapas na odtworzenie awaryjne 100 GB: razem ok. 480 GB przy
1 857 GB wolnego. Warunek zatrzymania planu: wolne miejsce poniżej
potrzebnego dla następnego kroku, błąd weryfikacji kopii (SHA-256 lub
`pg_restore --list` z kodem ≠ 0), błąd trybu `Final`.

## Mapa wymagań → task → dowód

| Wymaganie | Task | Dowód odbioru |
|---|---|---|
| Baza na D, bez utraty danych | 0955 | raport odniesienia (wszystkie bazy, rozmiary, `0153`, liczby tabel i jobów) równy raportowi po przeniesieniu; ustawienie Docker Desktop i plik vhdx na D |
| Zabezpieczenie przed awarią przeniesienia | 0952, 0955 | zrzut z kodem 0, pełny `pg_restore --list` i pełny odczyt `pg_restore --file=/dev/null` z kodem 0; kopia vhdx z równym SHA-256 |
| Wszystkie pliki plansz, cropów, modeli i dane `.runtime` na D | 0953, 0956 | inwentarz wpisów ignorowanych bez wpisów „nowych” nierozliczonych; manifest `Final` równy; `verify_artifact_references.py` = 0 brakujących |
| Praca i gałęzie z C zachowane | 0954, 0957 | bundle zweryfikowany na D, odtworzenie patchy (staged `--index`, potem unstaged) równe inwentarzowi, zachowywane dane ignorowane worktree'ów z równym manifestem, ponowna inwentaryzacja przed usunięciem |
| Start z D jak z C | 0956 | `windows:environment:check`, health API, `workers:status`, nowy tunel, odbiór funkcji, brak procesów z C, odbiór po restarcie Windows |
| Brak zależności od C | 0957 | joby ponawialne bez ścieżek C (zdekodowany JSON), bindingi zdalnej selekcji rozliczone, odbiór po zmianie nazwy katalogu C |
| Kroki wznawialne, restart możliwy | wszystkie | sekcja „Stan trwały i wznowienie” |

## Odbiór całego przepływu

Po B2, z D, przy usługach uruchomionych wyłącznie z D, powtórzony po
restarcie Windows:

1. `npm run db:current` pokazuje `0153_merge_compact_super_games`.
2. Równość raportu odniesienia z B1 (lista baz z rozmiarami, liczba tabel
   `game_data_v2` = 272 i `public` = 59, `count(*)` z `public.jobs`
   i rozkład statusów, 13 sesji zdalnej selekcji) z raportem po
   przeniesieniu została potwierdzona w B1 przed startem usług; w B2
   obowiązują niezmienniki (rewizja, liczba tabel, liczba jobów ≥ B1,
   rozmiary ±2%) z wyjaśnieniem każdej różnicy (zakończony job derive,
   nowe sesje).
3. `verify_artifact_references.py`: 0 brakujących plików dla wszystkich
   trzech gier; liczba „zależnych od C” zapisana (B2) i równa 0 z
   `--forbid-prefix` w odbiorze końcowym (etap C).
4. Admin: „Wyszukaj plansze” dla 777, „777 aktu 2” i Mumii pokazuje
   zdjęcie planszy i crop komórki; „Weryfikacja symboli” pokazuje kropy ze
   statusami.
5. Reviewer produkcyjny z D odpowiada na 3001; nowy Quick Tunnel ma nowy
   adres; nowa sesja udostępnienia wyszukiwarki działa z telefonu;
   istniejąca aktywna sesja zdalnej selekcji otwiera się (odbiór
   istniejącego bindingu, nie tylko nowego).
6. Worker z D: `npm run workers:status` widzi lane `general`; job
   `super_game_series_derive` jest w stanie końcowym (zakończony na C w
   B1 albo wznowiony i zakończony na D według `Outcome` TASK-0955); nowe
   joby utworzone z D są wykonywane przez worker z D.
7. Żaden proces z `Get-CimInstance Win32_Process` nie ma w linii poleceń
   `C:\Users\tuszy\Documents\game_predicotr`; `Path` użytkownika bez
   wpisów C po czyszczeniu w B2.

## Ryzyka

- **Przerwanie kopiowania vhdx przez Docker Desktop.** W trakcie nie
  restartować komputera i nie usypiać. Zabezpieczenie: kopia vhdx z
  równym SHA-256 (B1) i zrzut (A). Procedura awaryjna w TASK-0955:
  przywrócenie starej lokalizacji, a gdy plik na C jest uszkodzony,
  podstawienie kopii vhdx z D; odtworzenie ze zrzutu dopiero jako trzecia
  ścieżka (`pg_restore` z pliku zamontowanego do kontenera, bez stdin,
  `--exit-on-error`, role najpierw).
- **Pamięć WSL.** Limit 8 GB zostaje; kopiowanie vhdx wykonuje host.
- **`robocopy` i pliki w użyciu.** W trybie `Initial` błędy plików w użyciu
  są raportowane, wynik oznaczony jako niekompletny; w trybie `Final`
  każdy błąd blokuje.
- **Sesje udostępnienia i tunel.** Adres tunelu zmienia się; kody sesji
  udostępnienia po restarcie API są nieważne. Operator wysyła nowy link i
  kod. Trwałe sesje zdalnej selekcji pozostają w bazie z `host_base_path`
  na C: inwentaryzacja w B2, rozliczenie w C.
- **Joby z `source_directory` na C.** Ponawialne joby czytają z C do
  decyzji w C; usunięcie `imports/` z C przed rozliczeniem jest zablokowane.
- **Niezapisana praca na C.** Utrata, jeśli C zostanie usunięty przed A3
  lub po zmianach dokonanych po A3 (ponowna inwentaryzacja w C).
- **Numeracja.** TASK-0952–0957 wolne na wszystkich gałęziach lokalnych i
  `origin` (sprawdzone 2026-10-09; zajęte do 0951). Decyzja planu dostanie
  numer D-540 przy akceptacji.

## Zakres wyłączony

- Zmiany kodu aplikacji, API, migracje Alembic, `compose.yaml`.
- Odtworzenie próbne zrzutu do osobnej bazy (osobna decyzja operatora,
  godziny i ok. 85 GB).
- Przeniesienie bindingów zdalnej selekcji z zachowaniem tożsamości
  (jeśli inwentaryzacja w B2 pokaże potrzebę, powstaje osobny task).
- Usunięcie baz testowych, kompaktowanie vhdx, usunięcie C (tylko C, z
  osobnymi zgodami).
- Przeniesienie `worktrees/` z C jako katalogów (gałęzie w bundle i na
  `origin`; worktree'y odtwarza się na D w razie potrzeby).
- Aplikacja mobilna i build APK poza sprawdzeniem `windows:environment:check`.

## Przegląd Codex

Runda 1 (2026-10-09, gpt-6.1-sol, high, tylko odczyt): `Werdykt: REVISE`,
2 P0, 10 P1, 4 P2; raport
`ai_docs/quality/DISK_D_MIGRATION_PLAN_REVIEW_CODEX_20261009_round1.md`.
Runda 2 (ta sama konfiguracja): `Werdykt: REVISE`; rozliczenie rundy 1:
8 RESOLVED, 4 OPEN (P0-2 ignorowane dane worktree'ów, P1-1 pełny odczyt
zrzutu, P1-5 wyścig przy zatrzymaniu workera, P1-10 odbiór końcowy bez C),
2 nowe P1 (równość raportu B1 po wznowieniu zapisów; bramka manifestu
wobec zmiennego `.runtime`), 4 P2; raport
`ai_docs/quality/DISK_D_MIGRATION_PLAN_REVIEW_CODEX_20261009_round2.md`.
Wszystkie otwarte i nowe P0/P1 oraz P2 naniesione (decyzje 4, 6, 10;
taski 0952–0957).

Runda 3: `Werdykt: REVISE`; P1-1, P1-5, P1-10, P2-1, P2-2 RESOLVED; PARTIAL:
P0-2 (zakres kopii wpisów ignorowanych), nowe P1-1/P1-2 z rundy 2,
P2-3, P2-4; 4 nowe P1 (odbiór joba derive sprzeczny z B1; provisioning
`db:up` przed porównaniem raportów; `git worktree repair` w niewłaściwym
repozytorium; `.runtime` zawiera trwałe dane V7); 3 P2. Raport
`ai_docs/quality/DISK_D_MIGRATION_PLAN_REVIEW_CODEX_20261009_round3.md`.
Naniesione w tej wersji: inwentarz `-Inventory` i klasyfikacja wpisów
ignorowanych (decyzja 3, TASK-0953/0954), sam PostgreSQL przed bramką i
provisioning w B2 (decyzja 4, TASK-0955/0956), stan końcowy joba derive
(decyzja 4, odbiór pkt 6), naprawa worktree'ów z repozytorium
`game_predicotr_old` (TASK-0957), `.runtime` w bramce z wyłączeniem tylko
plików stanu procesów i logów (TASK-0956/0957), kontrakt `-Manifest`,
parsowanie list przy `powershell -File`, kontrola komunikatów `psql`.
Runda 4: `Werdykt: REVISE`; wszystkie punkty rundy 3 RESOLVED poza jednym
PARTIAL (skrót w `CURRENT_STATE.md`); 2 nowe P1 (domyślny inwentarz
obejmował `worktrees/`; procedura awaryjna tworzyła rolę aplikacyjną przed
odtworzeniem globals), 2 P2. Raport
`ai_docs/quality/DISK_D_MIGRATION_PLAN_REVIEW_CODEX_20261009_round4.md`.
Naniesione: oba korzenie worktree'ów zawsze wyłączone z kopii
(TASK-0953), sam PostgreSQL i provisioning po odtworzeniu w procedurze
awaryjnej (TASK-0955), pełna ścieżka `git -C` (TASK-0957), skrót w
`CURRENT_STATE.md`.

Runda 5: `Werdykt: PASS`; wszystkie punkty rundy 4 RESOLVED, brak nowych
P0/P1/P2. Raport
`ai_docs/quality/DISK_D_MIGRATION_PLAN_REVIEW_CODEX_20261009_round5.md`.
PASS dotyczy planu, nie wykonania migracji.

## Akceptacja i wykonanie

2026-10-10 operator zaakceptował plan poleceniem „przenieś tą aplikację,
jak skończą się wszystkie procesy job” (D-540). Elementy możliwe wcześniej
(etap A) startują od razu; monitoring kolejki jobów co 30 min od 5:00.
B1 startuje po opróżnieniu kolejki `general` i zakończeniu pracy dwóch
równoległych sesji Claude Code („Interfejs korekcji siatek plansz”,
„Cofnięcie zatwierdzenia siatki”), których commity muszą trafić na
`origin`. Zatrzymanie usług i zmiana lokalizacji obrazu dysku w Docker
Desktop pozostają czynnościami operatora. Wykonawca: sesja Claude Code na
`claude-opus-5-5` (zmiana modelu przez operatora); odstępstwa od tabeli
modeli odnotowuje `Outcome` każdego taska.

## Aktualizacja 2026-10-10 po etapie A

### Stan

- Etap A wykonany: TASK-0952 `done` (v1.7.302), TASK-0953 `done`
  (v1.7.303), TASK-0954 `in_progress` (v1.7.304; zabezpieczenie gotowe,
  push i merge czekają na operatora). Pełny `-VerifyOnly` 102 wpisów
  (06:12–07:40): SHA-256 C i D równe. Kolejka jobów była pusta od 01:14,
  ale o ok. 09:00 pojawiły się nowe joby importu (181 jobów z
  `source_directory`, wcześniej 173), a równoległe sesje nadal wdrażają
  zmiany.
- **Decyzja operatora (2026-10-10):** B1 nie startuje, dopóki operator nie
  da znać, że skończyły się wszystkie joby i zmiany. Po tym sygnale dane
  na D trzeba najpierw odświeżyć (etap A′ poniżej), dopiero potem B1.
  Monitoring cyklicznym zadaniem został wyłączony; sygnał daje operator.

### Etap A′ — odświeżenie po sygnale operatora (bez przestoju)

Kolejność, wszystko wznawialne:

1. Kontrola: `public.jobs` bez `created`/`processing`; obie równoległe sesje
   bezczynne; `git log` gałęzi integracyjnej i `origin`.
2. Nowy zrzut bazy (powtórzenie TASK-0952 do nowych plików; stare zostają do
   etapu C): zrzut z etapu A jest nieaktualny po nowych importach.
3. `sync_data_directories_to_d.ps1 -Mode Initial` (dokopiowanie nowych
   plików). Inwentarz pokaże nowe wpisy jako `new` do przeglądu.
4. `inventory_worktrees.ps1 -OutputRoot D:\game_predictor_backup\repo-<data>
   -CreateRefs`, bundle `--all`, `-VerifyClone D:\game_predicotr`, pobranie
   `refs/remotes/c/*` na D.
5. Decyzje operatora (niżej) i ich wykonanie (push, merge, `git pull` na D).
6. Dopiero teraz B1 (TASK-0955) z kopią `Final`, raportem odniesienia i
   kopią vhdx.

Nowe wpisy przeglądu z ostatniego przebiegu `Initial` (puste katalogi
tymczasowe): `.codex-tmp`, `.pytest-task0900`, `.test-artifacts`.

### Worktree'y: tylko wybrane wracają na D

Wszystkie worktree'y są zabezpieczone w `D:\game_predictor_backup\repo-…`
(patche, pliki nieśledzone, dane ignorowane, bundle), więc na D odtwarza się
tylko te, które operator wskaże. Pozostałe zostają wyłącznie w kopii (nic
nie ginie) i są usuwane z C dopiero w etapie C.

| Worktree (ścieżka na C) | Gałąź | Ostatni commit | Zmiany | `origin` | W integracyjnej | Propozycja |
|---|---|---|---|---|---|---|
| główny checkout | `v1.1-vision-lab-hybrid-geometry` | 2026-10-09 v1.7.299 | 25 zmienionych (3 tylko EOL), 5 nieśledzonych (`v7-output/`) | +3 commity | tak | staje się `D:\game_predicotr` |
| `…\scratchpad\wt0858` (katalog tymczasowy sesji) | detached `db99654f` | 2026-10-05 v1.7.198 | 3 nieśledzone | brak | tak | usunąć |
| `.claude\worktrees\agent-ad9ceefe41647c77c` | `task-0860` | 2026-10-05 v1.7.197 | 10 treściowych + 15 tylko EOL | brak | tak | nie odtwarzać (patch zostaje) |
| `worktrees\disk-migration` | `feat/disk-d-migration-plan` | 2026-10-10 v1.7.304 | 0 | brak | nie | potrzebny do końca migracji, potem merge i usunięcie |
| `worktrees\geometry-correction-revert` | `feat/geometry-correction-revert` | 2026-10-09 v1.7.295 | 52 | aktualna | nie | do decyzji operatora |
| `worktrees\grid-engine-v3` | `feat/grid-engine-v3` | 2026-10-06 v1.7.225 | 36 | brak | tak | nie odtwarzać (patch zostaje) |
| `worktrees\mumie-super-game` | `feat/mumie-super-game-plan` | 2026-10-09 v1.7.290 | 0 | brak | tak | usunąć |
| `worktrees\reviewer-geometry-gaps` | `feat/reviewer-geometry-gaps` | 2026-10-10 v1.7.304 | 9 | brak | nie | odtworzyć (aktywna sesja) |
| `worktrees\super-game-series-count` | `feat/super-game-series-count` | 2026-10-09 v1.7.297 | 0 | brak | nie | gałąź zachować (push), worktree niepotrzebny |

Odtworzenie wybranego worktree'a na D (TASK-0956): `git -C D:\game_predicotr
worktree add <ścieżka> <gałąź z refs/remotes/c/…>` (gałąź lokalna tworzona z
`c/<gałąź>`), `git apply --index staged.patch`, `git apply unstaged.patch`,
kopia `untracked\` i `ignored\` z backupu, `npm install` i `.venv` tylko jeśli
worktree ich potrzebuje. Zgodność sprawdza ten sam mechanizm co
`-VerifyClone` (status i skrót treści).

### Uruchamianie aplikacji z D tymi samymi komendami

Ustalone 2026-10-10 (odczyt):

- `.venv` na D ma pakiety w trybie edytowalnym wskazujące D
  (`D:\game_predicotr\services\api\src\…`, `…\worker\src\…`).
- `npm run db:up` z D używa tego samego projektu compose (`name:
  game-predictor`, identyczny hash), więc podłącza się do istniejącego
  kontenera i wolumenu; po B1 wolumen leży w obrazie dysku na D.
- Konfiguracja API i workera nie ma pliku `.env` ani zmiennych
  `GAME_PREDICTOR_*ROOT`; korzenie danych są względne wobec katalogu
  uruchomienia, więc z D wskazują dane na D.
- W kodzie nie ma ścieżek do C poza dwoma miejscami, które nie wpływają na
  uruchamianie: tekst testu `apps/admin/test/v7-selection-form.test.mjs`
  (przykładowa ścieżka) i domyślny `-LabRoot` w
  `scripts/vision_lab_assisted_annotation.ps1`
  (`C:\Users\tuszy\Documents\game_predictor_vision_data`).
- Wymagania przed pierwszym startem z D (TASK-0956): `npm run
  windows:environment:setup` (zmienne `.tooling`), wyczyszczenie stanu
  procesów w `.runtime`, `npm run reviewer:build` (produkcyjny Reviewer).

Odbiór TASK-0956 obejmuje uruchomienie z `D:\game_predicotr` każdej
komendy z dziennej procedury: `npm run db:up`, `npm run db:migrate` (bez
zmian, `0153`), `npm run db:current`, `npm run api:dev` (health 200),
`npm run admin:dev`, `npm run reviewer:dev` lub `reviewer:build` +
`reviewer:start`, `npm run workers:start` i `npm run workers:status`,
`npm run worker:poll`, `npm run reviewer:remote:start`,
`npm run windows:environment:check`, oraz po restarcie Windows ponownie
`db:up`, `api:dev`, `workers:start`.

### Poza repozytorium (do decyzji operatora)

- Katalogi w `C:\Users\tuszy\Documents` poza repozytorium:
  `game_predictor_vision_data` (12,4 GB, 22 815 plików; domyślny katalog
  Vision Lab), `mumie` (2,1 GB, 7 595 plików), `new_traning_set` (250 MB,
  994 pliki), `game_predictor_traning_set` (113 MB, 474 pliki); razem
  ok. 14,9 GB.
  Baza nie odwołuje się do nich (0 jobów). Jeśli mają trafić na D, kopiuje
  je ten sam skrypt (`-Source <katalog> -Destination D:\<katalog>`), a
  domyślny `-LabRoot` skryptu Vision Lab wymaga osobnej małej zmiany.
- Pamięć Claude Code jest przypisana do ścieżki projektu
  (`~\.claude\projects\C--Users-tuszy-Documents-game-predicotr\`); sesje
  otwarte w `D:\game_predicotr` zaczną z pustą pamięcią, dopóki operator nie
  skopiuje jej do katalogu projektu D.

### Kolizje numeracji z równoległą sesją

Gałąź `feat/reviewer-geometry-gaps` używa również v1.7.300–304 oraz
rezerwuje D-540 (TASK-0961–0965). Przy merge do gałęzi integracyjnej
gałąź scalana jako druga przenumerowuje swoje wersje i decyzję w commicie
merge (zasada z poprzednich kolizji).

### Decyzje operatora potrzebne w A′

1. Push na `origin` 17 gałęzi lokalnych i gałęzi integracyjnej (+3) czy
   pozostanie przy bundle na D.
2. Merge `feat/disk-d-migration-plan` do gałęzi integracyjnej (merge =
   push).
3. Lista worktree'ów do odtworzenia na D (tabela wyżej).
4. Czy przenosić katalogi spoza repozytorium.

## Przypisanie modeli do zadań

Dostępność potwierdzona w tym środowisku 2026-10-09: Claude —
`claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`
(low/medium/high/xhigh/max); Codex CLI 0.162.0 — `gpt-6.1-sol` (konfiguracja
użytkownika, `high`), `gpt-6-astra` (bywa „at capacity”). Wykonawcą tasków
jest sesja Claude Code (operator przy komputerze dla B1/B2). Audyt krzyżowy
Codex po każdym tasku:
`scripts/audit_task.ps1 -Task NNNN -Auditor codex -Model gpt-6.1-sol
-Effort <z tabeli> -Plan ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md
-Paths <pliki taska> -TimeoutSec 480`. Długie kopie (A1, A2, B1) biegną
jako procesy w tle z jawnym limitem czasu w skrypcie i zgodą operatora na
czas trwania przed startem.

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0952 | claude-sonnet-5-5 | medium | Kopia `pg_dump` i `pg_dumpall --globals-only` według runbooka, kontrola kodów wyjścia, raport stanu; bez logiki domenowej. | Wymagany: gpt-6.1-sol, medium |
| TASK-0953 | claude-sonnet-5-5 | high | Skrypt PowerShell `robocopy` z dwoma trybami, manifestami SHA-256 i kontraktem błędów; bez logiki domenowej. | Wymagany: gpt-6.1-sol, high |
| TASK-0954 | claude-opus-5-5 | medium | Inwentaryzacja wszystkich worktree'ów, bundle, patche binarne, weryfikacja odtwarzalności; ryzyko utraty pracy operatora. | Wymagany: gpt-6.1-sol, medium |
| TASK-0955 | claude-opus-5-5 | high | Granica przełączenia, kopia vhdx, przeniesienie, raport odniesienia i procedura awaryjna; ryzyko utraty danych. | Wymagany: gpt-6.1-sol, high |
| TASK-0956 | claude-opus-5-5 | high | Pierwszy start z D, zmienne środowiskowe, skrypt weryfikacji odwołań do plików, odbiór po restarcie, przewodniki. | Wymagany: gpt-6.1-sol, high |
| TASK-0957 | claude-opus-5-5 | high | Operacje destrukcyjne z podglądem i osobnymi zgodami; rozliczenie ścieżek jobów i bindingów przed usunięciem C. | Wymagany: gpt-6.1-sol, high |
