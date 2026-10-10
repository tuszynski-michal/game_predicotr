# Audyt TASK-0955 — Przeniesienie obrazu dysku Dockera z bazą na D

Werdykt: REVISE
Audytor: gpt-6.1-sol, high
Wykonawca: claude-opus-5-5, high
Zakres: HEAD...b776b536e5383510bbfed7ef9a1a26af669feabe oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-10
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano dokumentację wykonania B1, wymagania planu oraz zachowane raporty i logi na D. Log kopii potwierdza identyczne SHA-256 źródła, backupu i docelowego obrazu; porównanie raportów potwierdza zachowanie wykazanych danych głównej bazy. Zamknięcie taska blokują nierozliczona różnica raportów, niespełniona zależność dotycząca checkoutu D oraz braki wymaganej weryfikacji i dokumentacji.

## Znaleziska

### P0

- [P0-1] `ai_docs/tasks/completed/0955-disk-d-database-cutover.md:281` — Task uznano za zakończony mimo braku wymaganej równości raportów wszystkich baz. W `D:\game_predictor_backup\db-state-before-move.txt:20` baza `game_predictor_task0760_e7d125df587d_test` ma 26 531 519 bajtów, a w `D:\game_predictor_backup\db-state-after-move-2.txt:20` — 26 370 575 bajtów. Wyjaśnienie różnicy plikiem `pg_internal.init` nie ustanawia wyjątku od kryterium z linii 138–140 ani bramki planu. Nie jest to dowód utraty danych, ale literalna bramka odbioru nie została spełniona. Należy udokumentować dowód przyczyny różnicy i uzyskać jawne rozliczenie wyjątku przed uznaniem B1 za zamknięty; nie usuwać bazy ani nie odtwarzać danych wyłącznie w celu wyrównania rozmiaru.

### P1

- [P1-1] `ai_docs/tasks/completed/0955-disk-d-database-cutover.md:235` — Wskazany checkout D na `3fb9a0a5` nie zawiera wymaganego skryptu synchronizacji. Odczyt `Test-Path D:\game_predicotr\scripts\sync_data_directories_to_d.ps1` zwrócił `False`; `git ls-files` nie wykazał również `scripts/inventory_worktrees.ps1`. Jednocześnie TASK-0954 pozostaje `in_progress`, choć warunek wejścia z linii 30–32 wymaga jego zakończenia. To pozostawia dalszy workflow zależny od C. Należy dostarczyć uzgodnione skrypty i wpisy npm do checkoutu D oraz zamknąć albo jawnie rozliczyć zależność TASK-0954, bez automatycznego push lub merge.

- [P1-2] `ai_docs/tasks/completed/0955-disk-d-database-cutover.md:238` — Outcome nie zapisuje wymaganych trzech kontroli jobów, końcowego stanu `d9a49da0` ani wyniku kontroli `remote_manual_selection_host_actions`. Ogólne stwierdzenie „queue empty and no live lease” nie pozwala odtworzyć kontroli przed i po zatrzymaniu workera, szczególnie wobec wykrycia dodatkowego `worker:poll`. Należy dołączyć istniejące wyniki z czasami, statusami, dzierżawami i liczbą akcji hosta. Aktualny odczyt nie zastępuje dowodu historycznej granicy przełączenia.

- [P1-3] `ai_docs/tasks/completed/0955-disk-d-database-cutover.md:251` — Raporty przed i po przeniesieniu nie zawierają wymaganej rewizji Alembic ani liczby tabel bazy `game_predictor_v7_pilot`. W obu raportach pilot występuje wyłącznie jako rozmiar bazy i nazwa roli; rewizja oraz liczby tabel dotyczą głównej bazy. Należy uzupełnić porównanie pilota dowodami sprzed i po przełączeniu. Jeśli pomiaru sprzed przełączenia nie zachowano, trzeba jawnie odnotować brak i uzgodnić sposób jego rozliczenia.

- [P1-4] `ai_docs/tasks/completed/0955-disk-d-database-cutover.md:303` — Pominięto wymaganą aktualizację `DATABASE_MAINTENANCE.md`. Runbook nadal wskazuje obraz na C (`ai_docs/guides/DATABASE_MAINTENANCE.md:12`), a sekcja 5.1 uruchamia `npm run db:up` przed weryfikacją (`:522`), co wykonuje provisioning zabroniony przed bramką B1. Należy zapisać faktyczną lokalizację, kopię, czas i procedurę przełączenia oraz poprawną kolejność uruchomienia samego PostgreSQL i porównania raportów. Następnie wykonać i zapisać wynik `npm run docs:check`.

- [P1-5] `ai_docs/tasks/completed/0955-disk-d-database-cutover.md:280` — Udokumentowany baseline A′ i wynik to `0154_geometry_correction_revert`, lecz kryterium taska nadal wymaga `0153` (`:138`), a plan odbioru również wskazuje `0153`, 272 tabele i 13 sesji. Raport odniesienia zawiera już `0154`, 280 tabel i 14 sesji. Ponadto `CURRENT_STATE.md:83` nadal opisuje B1 jako oczekujący na sygnał. Należy uzgodnić kryteria i stan procesu z udokumentowanym baseline A′. Nie wykonywać downgrade’u w celu dopasowania do starego tekstu.

### P2

- [P2-1] `ai_docs/tasks/completed/0955-disk-d-database-cutover.md:256` — Outcome skraca SHA-256 i pomija wymagany czas kopii oraz odsyłacz do logu. Dowody istnieją: `D:\game_predictor_backup\b1-vhdx-copy.log:2` podaje 63 s dla backupu, `:4` — 233 s dla kopii docelowej, a linie 6–8 zawierają pełne, identyczne hashe. Należy przenieść te dane lub ich jednoznaczne odwołanie do Outcome.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Trzy kontrole jobów, dzierżawy, puste akcje hosta i brak procesów C | niezweryfikowane | Outcome `ai_docs/tasks/completed/0955-disk-d-database-cutover.md:238` nie zawiera pełnego zapisu kontroli; P1-2 |
| Final i równe manifesty | spełnione | Pierwszy przebieg wykazuje wyłącznie dwa nadmiarowe pliki `.runtime`; drugi ma `missing=0 different=0 extra=0` i `RESULT: OK` w `D:\game_predictor_backup\sync-logs\20261010-175735-Final\SUMMARY.txt:6` |
| Równe SHA-256 źródła i backupu oraz rozmiar | spełnione | `D:\game_predictor_backup\b1-vhdx-copy.log:6`–`:8`: identyczne hashe i 158 440 882 176 bajtów |
| Czas kopii zapisany w Outcome | niespełnione | Dane są w logu, lecz nie w Outcome; P2-1 |
| Wolumen i uruchomienie PostgreSQL | niezweryfikowane | Zadeklarowane w `ai_docs/tasks/completed/0955-disk-d-database-cutover.md:273` i `:278`; brak niezależnego zachowanego wyniku tych poleceń |
| `db:current = 0153` | niespełnione | Raporty zawierają `0154`; wymaganie wymaga aktualizacji względem baseline A′, P1-5 |
| Równość raportów wszystkich baz | niespełnione | Różnica 160 944 bajtów w jednej bazie; P0-1 |
| Pełny wymagany raport pilota V7 | niespełnione | Brak rewizji i liczby tabel pilota; P1-3 |
| Obraz i trwałe ustawienie Docker Desktop na D | spełnione | Plik docelowy istnieje; `C:\Users\tuszy\AppData\Roaming\Docker\settings-store.json:3` wskazuje `D:\docker\DockerDesktopWSL` |
| Zapis stanu na granicy etapu oraz ścieżek odzyskania | niezweryfikowane | Ścieżki i kopie zapisano; historyczny stan zatrzymania usług pozostaje niepełnie udokumentowany |

## Listy zamknięte i otwarte

Zamknięte: Brak. Runda 1.

Otwarte: P0-1, P1-1, P1-2, P1-3, P1-4, P1-5, P2-1.

## Proponowane testy

- Dla zachowanych raportów: `Compare-Object (Get-Content D:\game_predictor_backup\db-state-before-move.txt) (Get-Content D:\game_predictor_backup\db-state-after-move-2.txt)`; rozliczyć dokładnie wskazaną różnicę.
- Dla checkoutu D: `git -C D:\game_predicotr ls-files -- scripts/sync_data_directories_to_d.ps1 scripts/inventory_worktrees.ps1`; potwierdzić także wymagane wpisy npm.
- Dla raportu pilota: uzupełnić wymagane pomiary z istniejących dowodów. Nie przedstawiać późniejszego pomiaru jako pomiaru sprzed przełączenia.
- Po poprawieniu dokumentacji: `npm run docs:check`; zapisać wynik w Outcome.

## Zakres przeglądu i ograniczenia

Przeczytano brief, task, właściwe fragmenty planu, dokumentację procesu i runbooki. Sprawdzono read-only historię i diff Git, checkout D, raporty baz, podsumowania synchronizacji, log kopii, metadane obrazów oraz zapis ustawienia Docker Desktop.

Nie uruchamiano testów, usług, kontenerów ani poleceń SQL. Nie przeliczano ponownie hashów obrazów; oceniono zachowany log. Nie potwierdzono stanu baz i procesów na żywo ani zachowania po restarcie Windows, które należy do dalszego odbioru. Upoważnienie do obsługi usług i Docker Desktop oceniono na podstawie cytatu operatora w Outcome; nie uznano samego wykonania tych czynności przez agenta za naruszenie.