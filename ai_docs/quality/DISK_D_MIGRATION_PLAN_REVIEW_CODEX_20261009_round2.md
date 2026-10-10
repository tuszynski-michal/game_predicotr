---
title: Przegląd planu przeniesienia na dysk D przez Codex (runda 2)
status: active
last_updated: 2026-10-09
---

# Przegląd planu przeniesienia na dysk D — Codex, runda 2

Audytor: Codex CLI 0.162.0, gpt-6.1-sol / high, `codex exec --sandbox read-only`.
Zakres: plan i taski TASK-0952–0957 po poprawkach z rundy 1. Brief: `artifacts/audits/DISK_D_PLAN_REVIEW_PROMPT_ROUND2.md`.

Werdykt: REVISE

## Rozliczenie rundy 1

Numeracja odpowiada kolejności uwag w raporcie rundy 1. `PARTIAL` oznacza wdrożoną część poprawki; `OPEN` oznacza pozostający blocker.

| punkt | status | gdzie/co brakuje |
|---|---|---|
| P0-1 — kopia stanu przełączenia | RESOLVED | Plan, decyzja 2; TASK-0955, kroki 6–7 i procedura awaryjna: niezależna kopia całego VHDX po zamknięciu Dockera/WSL, SHA-256 obu plików, przywrócenie kopii. Obejmuje wszystkie bazy i role. |
| P0-2 — zabezpieczenie pracy wszystkich worktree’ów | OPEN | TASK-0954:56–78,107–108 obejmuje staged, unstaged i nieśledzone, ale wyklucza wszystkie ignorowane pliki. TASK-0953 kopiuje katalogi danych tylko głównego checkoutu. Trwałe, ignorowane wyniki innych worktree’ów mogą zniknąć przy usunięciu C. |
| P1-1 — weryfikacja danych zrzutu | OPEN | TASK-0952:89–90 nadal uznaje kod 0 zrzutu i `pg_restore --list` za dowód kompletności. Dodano kontrolę kodów i pełny spis, ale nie odczyt wszystkich danych archiwum. |
| P1-2 — niedziałający restore przez stdin z `-j` | RESOLVED | TASK-0955:134–145: archiwum jako plik w kontenerze, właściwa sieć, `--exit-on-error`, kod 0, role przed danymi, zachowanie kopii. Doprecyzowanie hasła pozostaje P2. |
| P1-3 — sprzeczny kontrakt robocopy | RESOLVED | TASK-0953:66–76,119–128: jawne tryby `Initial`/`Final`, `INCOMPLETE`, błędy i rozbieżności blokujące `Final`. Kod 16 wymaga uzupełnienia, wskazanego w P2. |
| P1-4 — niewystarczające sumy plików i bajtów | RESOLVED | TASK-0953:59–76: manifesty ścieżka/rozmiar/SHA-256, logi poza zbiorem, jawne wykluczenia, zatwierdzanie nadmiarowych plików przed `/MIR`. |
| P1-5 — stabilna granica przełączenia | OPEN | TASK-0955:64–72 dodaje zatrzymanie producentów i kontrolę po zatrzymaniu workera. Nadal dopuszcza `created` podczas działającego polling workera, więc między kontrolą a `Kill()` może zostać pobrany kolejny job. Brakuje rozstrzygniętej procedury wyjścia z tego przypadku. |
| P1-6 — zależności jobów od C przed usunięciem | RESOLVED | TASK-0957:60–82,123–125: zdekodowany JSON, `cancelled`, kontrola checkpointów, blokady wierszy, ponowna kontrola statusu, warunkowe objęcie `completed`, archiwum blokujące usunięcie C. |
| P1-7 — revoke a dane zdalnej selekcji | RESOLVED | TASK-0956:83–86 i TASK-0957:83–89: inwentaryzacja bindingów, revoke tylko pustych, osobne przeniesienie danych, blokada usunięcia C. Przyjęty fakt pustych `batches` i `host_actions` usuwa wcześniejsze założenie o istniejących partiach wymagających transferu. |
| P1-8 — dostarczenie kodu planu na D | RESOLVED | Plan, decyzja 7; TASK-0954:72–75,99; TASK-0955:30–32: merge, aktualizacja checkoutu, wymagane skrypty i zależność od ukończonego TASK-0954. |
| P1-9 — synchronizacja po dniu pracy z D | RESOLVED | Plan, decyzja 3; TASK-0957:39–40: zakaz synchronizacji C→D po przełączeniu. Nowa bramka manifestu ma jednak osobny problem opisany niżej. |
| P1-10 — pełny odbiór i niezależność od C | OPEN | Dodano wszystkie trzy gry, verifier, restart i odcięcie C. TASK-0956 nadal rozwiązuje część plików przez `source_directory` wskazujące C, a przepisanie tych ścieżek następuje dopiero w TASK-0957, zależnym od zakończenia TASK-0956. Nie określono także pełnego rozliczenia trwałych manifestów zawierających ścieżki. |

**Wymagane domknięcie otwartych uwag:**

- **P0-2:** zinwentaryzować ignorowane dane każdego worktree’a. Każdy zbiór oznaczyć jako zachowany albo świadomie odtwarzalny. Zabezpieczyć zachowywane pliki i zweryfikować ich integralność na D. Próba odtworzenia zmian musi stosować patch staged, a następnie unstaged na odtworzonym indeksie; oba patche nie muszą niezależnie pasować do HEAD.
- **P1-1:** wymagać odczytu całej zawartości archiwum, np. wygenerowania pełnego SQL przez `pg_restore --file=/dev/null` wewnątrz kontenera, z kontrolą kodu zakończenia. Odtworzenie próbne może pozostać poza zakresem, ponieważ podstawą odzyskania jest VHDX. `--list` czyta spis, nie wszystkie dane. [Dokumentacja PostgreSQL](https://www.postgresql.org/docs/18/app-pgrestore.html).
- **P1-5:** opróżnić uzgodnione kolejki przed zatrzymaniem albo jawnie opisać zatrzymanie z dopuszczonym odzyskaniem checkpointu. Dla joba pobranego między kontrolą a zatrzymaniem określić odzyskanie, ponowną kontrolę i warunek kontynuacji B1.
- **P1-10:** rozdzielić odbiór B2 z tymczasowo zachowanymi zależnościami C od końcowego odbioru wyłącznie z D. Końcowy verifier musi odrzucać operacyjne rozwiązania do starego katalogu i obejmować zachowywane ścieżki w trwałych manifestach.

## Nowe P0

Brak nowych. P0-2 z rundy 1 pozostaje otwarte.

## Nowe P1

1. **Raport B1 ma pozostać identyczny po wznowieniu zapisów.**
   [Plan:238–252](ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md:238) i [TASK-0956:80–96](ai_docs/tasks/0956-disk-d-application-startup.md:80) wymagają równości rozmiarów baz i rozkładu statusów po uruchomieniu workera oraz zakończeniu `super_game_series_derive`. Te operacje mogą zmienić raport prawidłowo. Tworzenie nowych sesji także zmienia liczniki.
   **Poprawka:** równość z B1 sprawdzić przed startem producentów i workerów. Późniejszy odbiór oprzeć na niezmiennikach i jawnie oczekiwanych zmianach.

2. **Bramka usunięcia C wymaga zachowania plików, które wcześniejszy task usuwa lub zmienia.**
   [TASK-0957:98–107](ai_docs/tasks/0957-disk-d-cleanup-and-job-paths.md:98) wymaga identycznego SHA-256 każdego pliku manifestu B1. Tymczasem [TASK-0956:65–66](ai_docs/tasks/0956-disk-d-application-startup.md:65) usuwa skopiowane pliki stanu `.runtime`; nowe procesy zapisują własny stan i logi. Bramka nie przejdzie po prawidłowym wykonaniu B2.
   **Poprawka:** oddzielić zachowywane pliki niezmienne od stanu odtwarzanego i plików zmiennych. Dla każdego odstępstwa zapisać dowód zachowania, zastąpienia albo świadomego usunięcia. Nie przywracać starych plików do aktywnego D.

## P2

- TASK-0953:66–70: jawnie obsłużyć fatalny kod robocopy 16; `Final` powinien odrzucać wszystkie kody ≥8. Test brakującego pliku wykonać na samym verifierze, ponieważ pełny przebieg synchronizacji najpierw go dokopiuje.
- TASK-0955:137–141: przekazać `PGPASSWORD` do kontenera przez `-e`. Opisać również dostęp kontenera do pliku globals oraz obsługę istniejącej roli startowej przy kontroli błędów `psql`.
- TASK-0957:104–109: po zmianie nazwy głównego repozytorium przewidzieć `git worktree repair`; istniejące rejestracje i pliki `.git` nadal wskazują stare ścieżki.
- TASK-0955:58 i kroki 6–7 niespójnie przypisują działania operatorowi/agentowi. Ujednolicić odpowiedzialności.

## Potwierdzone

- Kopia VHDX po zamknięciu Docker Desktop i WSL zabezpiecza stan przełączenia wszystkich baz i ról.
- Compose wskazuje projekt `game-predictor` oraz nazwany wolumen. Przyjęta sieć to `game-predictor_default`.
- `requeue_job` dopuszcza `cancelled`; odzyskanie wygasłego joba zachowuje checkpoint.
- `ApiSettings` czyta środowisko procesu; skrypt środowiska zapisuje konfigurację użytkownika trwale.
- Przyjęto fakty z briefu: puste `batches` i `host_actions`, D jako wewnętrzny NVMe/NTFS z 1857 GB wolnego miejsca.
- Tabela modeli obejmuje sześć tasków i odpowiada ich `Recommended execution`; instrukcja audytu zawiera model, reasoning, plan i ograniczenie ścieżek.
- Przegląd statyczny, bez zmian w plikach. Nie uruchamiałem usług, kopii, operacji bazodanowych ani testów odtworzenia.