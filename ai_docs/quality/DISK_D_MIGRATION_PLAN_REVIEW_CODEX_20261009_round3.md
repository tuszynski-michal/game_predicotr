---
title: Przegląd planu przeniesienia na dysk D przez Codex (runda 3)
status: active
last_updated: 2026-10-09
---

# Przegląd planu przeniesienia na dysk D — Codex, runda 3

Audytor: Codex CLI 0.162.0, gpt-6.1-sol / high, `codex exec --sandbox read-only`.
Zakres: plan i taski TASK-0952–0957 po poprawkach z rundy 2. Brief: `artifacts/audits/DISK_D_PLAN_REVIEW_PROMPT_ROUND3.md`.

Werdykt: REVISE

## Rozliczenie rundy 2

Numeracja P0/P1 odpowiada uwagom z rundy 1. „Nowe P1” i P2 odnoszą się do raportu rundy 2. `PARTIAL` oznacza poprawkę wymagającą domknięcia.

| punkt | status | gdzie/co brakuje |
|---|---|---|
| P0-2 — zabezpieczenie wszystkich worktree’ów | PARTIAL | TASK-0954, Scope i Acceptance criteria obejmują ignorowane dane oraz właściwą kolejność patchy. Jednak Technical notes:124–128 odsyła ignorowane dane głównego checkoutu do TASK-0953, którego lista pomija np. istniejący `.tmp`. Komenda kopii worktree’a:70–71 nie przekazuje zinwentaryzowanego `-Directories`. Trzeba jednoznacznie objąć kopią każdy zachowywany katalog i luźny plik ignorowany. |
| P1-1 — pełny odczyt zrzutu | RESOLVED | TASK-0952:61–64,85–86,120 wymaga pełnego `pg_restore --file=/dev/null` i kodu 0. Odtworzenie próbne pozostaje świadomie wyłączone; podstawą odzyskania jest VHDX. |
| P1-5 — stabilna granica przełączenia | RESOLVED | TASK-0955:69–83,120–123 wymaga opróżnienia kolejki i ponownej kontroli. Opisuje wygaśnięcie dzierżawy oraz późniejsze odzyskanie checkpointu dla przypadku wyścigu. |
| P1-10 — odbiór końcowy bez C | RESOLVED | Plan, decyzja 10; TASK-0956:77–83,93–108; TASK-0957:111–118 rozdzielają B2 od odbioru końcowego, uwzględniają treść manifestów i wymagają odcięcia starej nazwy C. Osobny brak dotyczący trwałego `.runtime` opisano poniżej. |
| Nowe P1-1 — równość raportu po wznowieniu zapisów | PARTIAL | TASK-0955:106–108 przenosi porównanie przed start aplikacji i workera; TASK-0956 stosuje później niezmienniki. Jednak wcześniejsze `npm run db:up` samo wykonuje zapisy — nowe P1-2 poniżej. |
| Nowe P1-2 — bramka manifestu wobec zmiennego stanu | PARTIAL | TASK-0957:105–110 dopuszcza udokumentowane zastąpienia, usunięcia i nowe pliki D. Wyklucza jednak całe `.runtime`, zawierające również trwałe dane. Ponadto używa `-Manifest`, którego nie definiuje kontrakt TASK-0953. |
| P2-1 — robocopy 16 i test verifiera | RESOLVED | TASK-0953:68–73 obsługuje bit 16 i odrzuca wyniki ≥8 w `Final`; :97–101 testuje brakujący plik przez `-VerifyOnly`. |
| P2-2 — hasło, globals i rola startowa | RESOLVED | TASK-0955:151–160 przekazuje `PGPASSWORD`, montuje kopie i rozróżnia oczekiwany błąd istniejącej roli od innych błędów. Przy `ON_ERROR_STOP=0` wymagane jest sprawdzenie komunikatów, nie tylko kodu wyjścia. |
| P2-3 — naprawa rejestracji worktree’ów | PARTIAL | TASK-0957:112–113 dodaje `repair`, ale wskazuje osobny klon D zamiast repozytorium będącego właścicielem rejestracji C — nowe P1-3 poniżej. |
| P2-4 — operator a agent | PARTIAL | TASK-0955:58–61 porządkuje odpowiedzialności, lecz krok 9 nadal przypisuje agentowi `db:up`, uruchamiające kontener, mimo zasady „operator wykonuje wszystko, co […] uruchamia procesy”. |

## Nowe P0

Brak nowych. P0-2 pozostaje niedomknięte: ogólne kryterium zachowania wszystkich ignorowanych danych musi odpowiadać konkretnemu zakresowi kopii.

## Nowe P1

1. **Odbiór B2 przeczy opróżnieniu kolejki w B1.**
   [TASK-0955:69](ai_docs/tasks/0955-disk-d-database-cutover.md:69) przewiduje zakończenie `super_game_series_derive` na C. Plan, „Odbiór całego przepływu”, punkt 6, oraz TASK-0956:103 wymagają zakończenia tego joba na D. Prawidłowa podstawowa ścieżka B1 nie spełni takiego odbioru.
   **Poprawka:** zaakceptować zakończenie na C albo udokumentowane anulowanie i wznowienie na D. Nie wymagać ponownego wykonania zakończonego joba.

2. **Przed porównaniem raportów wykonywany jest provisioning bazy.**
   [TASK-0955:104](ai_docs/tasks/0955-disk-d-database-cutover.md:104) wywołuje `npm run db:up`. [package.json:50](package.json:50) dołącza do tej komendy provisioning. `provision_application_role` wykonuje `ALTER ROLE` z nowym verifierem SCRAM oraz operacje uprawnień. Porównanie następuje więc po zapisach, które mogą również zmienić rozmiary katalogów systemowych.
   **Poprawka:** operator uruchamia wyłącznie PostgreSQL przez `docker compose … up -d --wait postgres`; agent wykonuje odczyty i porównanie. Provisioning przenieść za tę bramkę.

3. **`git worktree repair` działa w niewłaściwym repozytorium.**
   [TASK-0957:111](ai_docs/tasks/0957-disk-d-cleanup-and-job-paths.md:111) wskazuje wykonanie naprawy na D. Odczyt potwierdził, że D ma własne `.git` i tylko jeden worktree; rejestracje C należą do `C:\Users\tuszy\Documents\game_predicotr\.git`. Naprawa w niezależnym klonie D nie naprawi tych połączeń. [Dokumentacja Git](https://git-scm.com/docs/git-worktree).
   **Poprawka:** po zmianie nazwy naprawić rejestracje z głównego repozytorium `_old`, podając nowe ścieżki przeniesionych worktree’ów. Worktree’y potrzebne na D odtworzyć w klonie D. Usuwanie wykonać przez właściwe repozytorium.

4. **Wykluczenie całego `.runtime` pomija trwałe dane i manifesty.**
   [TASK-0957:105](ai_docs/tasks/0957-disk-d-cleanup-and-job-paths.md:105) uznaje całe `.runtime` za odtwarzalne. Tymczasem LOCAL_OPERATION_GUIDE:36–37 wskazuje trwałe sesje i profile V7, a [V7LabelGeometryCalibrationService:118](services/api/src/game_predictor_api/application/v7_label_geometry_calibration.py:118) przechowuje tam profile i sesje. Katalog `.runtime/v7-label-geometry` istnieje na C. Verifier ograniczony do manifestów wskazanych kolumnami bazy nie obejmie automatycznie tych danych.
   **Poprawka:** wyłączyć z bramki tylko zinwentaryzowane PID-y, stan procesów i uzgodnione logi. Trwałe sesje, profile i lokalne manifesty objąć kontrolą zachowania oraz rozliczeniem operacyjnych ścieżek C.

## P2

- TASK-0953, Scope: dodać kontrakt `-Manifest` używanego przez TASK-0957. Określić porównanie z zapisanym B1, bez odczytu C i bez odrzucania nowych plików D.
- TASK-0953:140 przekazuje listę przez `powershell.exe -File`. Dla parametru tablicowego użyć bezpośredniego wywołania skryptu z PowerShell albo jawnie zdefiniowanego parsowania tekstu. [Dokumentacja Microsoft](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_powershell_exe?view=powershell-5.1).
- Ujednolicić skróty w mapie dowodów i CURRENT_STATE: nadal występują wcześniejsze opisy kontroli zrzutu, sum plików oraz porównania z etapem A.

## Potwierdzone

- Pełny odczyt archiwum przez `pg_restore --file=/dev/null` bez `-d` i `-j` jest zgodny z proponowaną kontrolą. [Dokumentacja PostgreSQL](https://www.postgresql.org/docs/18/app-pgrestore.html).
- Niezależna kopia VHDX po zatrzymaniu Docker Desktop i WSL zabezpiecza wszystkie zachowywane bazy i role.
- Zachowano zakaz synchronizacji C→D po przełączeniu oraz osobne zgody na operacje destrukcyjne.
- Przyjęto fakty briefu: puste `batches` i `host_actions`, sieć `game-predictor_default`, wewnętrzny NVMe/NTFS i 1857 GB wolnego miejsca.
- Przegląd statyczny, bez zmian w plikach. Nie uruchamiałem usług, kopii, operacji bazodanowych ani testów odtworzenia.