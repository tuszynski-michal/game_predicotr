---
name: merge-to-main
description: Prowadzi scalenie gałęzi roboczej do `main` w D:\game_predicotr z push do origin i bezpiecznym usunięciem worktree (preflight kolizji numerów, zgoda operatora, aktualizacja gałęzi, docs:check, fast-forward, push, odpięcie junction). Użyj, gdy praca na gałęzi jest skończona i trzeba ją scalić, np. "scal do main", "scal gałąź", "wypchnij", "zapushuj main", "merge to main", "merge the branch into main", "ship this branch", "sprzątnij worktree po scaleniu".
---

# Scalanie gałęzi roboczej do `main` (`integration_preflight.py`)

Skill prowadzi scalenie, push i sprzątanie; zawiera procedurę do reguły
wiążącej z `AGENTS.md` („Scalanie do gałęzi integracyjnej”). Pozostałe reguły
są w `AGENTS.md` („Brudny worktree i zakres commita”,
„Kontrola lokalnych usług API i Admin”, „Wersjonowanie commitów”) oraz w
„Obowiązujących ograniczeniach” `ai_docs/process/CURRENT_STATE.md`. Skill ich
nie zastępuje ani nie osłabia; przy sprzeczności obowiązuje `AGENTS.md`.
Skrypt `scripts/integration_preflight.py` tylko czyta stan i raportuje; scalenie,
push i usunięcie worktree wykonujesz Ty, po zgodzie operatora.

Fakty o repozytorium: gałęzią integracyjną jest `main` w `D:\game_predicotr`
(decyzja operatora 2026-10-16). Dawna gałąź `v1.1-vision-lab-hybrid-geometry`
jest w całości zawarta w `main` i usunięta lokalnie; nie scalaj do niej ani nie
zakładaj od niej nowych gałęzi. Nowe prace wykonuj na gałęzi roboczej, aby nie
omijać akceptacji commitem bezpośrednio na `main`.
Ten checkout uruchamia API z `--reload`, więc każda zmiana plików po scaleniu
trafia od razu do działającego procesu. `main` może przesunąć się w trakcie
pracy (równoległa sesja), dlatego stan sprawdzasz tuż przed scaleniem, a nie
tylko na początku.

## Kiedy użyć

Cały zlecony zakres (task, etap albo plan) jest wykonany, ma weryfikację,
dokumentację i osobne commity tasków, a operator chce scalić wynik do `main`.
Nie używaj skilla do pracy w trakcie etapu ani do scalania do innej gałęzi niż
`main` (inną wskaże operator jawnie; wtedy podaj ją w `--base`).

## Bramki zgody (bez osłabiania `AGENTS.md`)

Skill nic nie znosi. Zatrzymaj się i zapytaj operatora, gdy zachodzi którykolwiek
punkt:

1. **Akceptacja wyniku i zgoda na scalenie** są konieczne. Akceptacja planu,
   polecenie rozpoczęcia implementacji, ogólne „kontynuuj” ani milczenie nie są
   zgodą. Przy całym planie albo etapie zadaj jedno końcowe pytanie o cały
   zakres, nie pytaj po każdym tasku. Niezależne blokery i zgody na koszt lub
   operacje na danych zgłaszaj nadal według pozostałych reguł.
2. **Push `main` do origin** obejmuje zgoda na scalenie (decyzja operatora
   2026-10-16); bez tej zgody push nie następuje, nigdy automatycznie. Pytanie o
   zgodę nazywa oba kroki: scalenie i push. Gdy operator w odpowiedzi wprost
   wyłączy push, zakończ na lokalnym scaleniu. Pushuj wyłącznie `main`; gałęzi
   roboczych i pomocniczych nie pushuj. Nigdy `--force`.
3. **Otwarte uwagi audytu P0/P1**, wymagana migracja i zgody na operacje na
   danych lub koszt poza zatwierdzonym zakresem nadal blokują scalenie.
4. **Migracje.** Nie scalaj do `main` kodu wymagającego niewykonanej migracji
   (API z `--reload` w tym checkout nie wystartuje). Migrację bazy wykonuje
   operator za osobną zgodą w kolejności: stop usług, scalenie, `db:migrate`,
   start. Skill jej nie uruchamia.
5. **Usługi.** Nie uruchamiaj, nie zatrzymuj ani nie restartuj API, Admin,
   Reviewer i workerów; nie wdrażaj i nie aktywuj modeli. Jeżeli scalenie
   wymaga restartu lub przebudowania (np. `npm install`, build), podaj operatorowi
   komendę i zostaw wykonanie jemu.
6. **Cudze niezacommitowane zmiany** w którymkolwiek worktree nie są Twoje:
   nie nadpisuj ich, nie usuwaj, nie dołączaj do commita. Kolidującą pracę
   zabezpiecz i odtwórz bez utraty danych; gdy nie możesz tego potwierdzić,
   zatrzymaj scalenie i zgłoś konkretny blocker.
7. **Operacje destrukcyjne na danych** (GC, cleanup danych, `db:reset:local`,
   usuwanie legacy) nie należą do tego skilla. Usuwasz tylko worktree i gałąź
   właśnie scalonej pracy, i tylko po zgodzie z kroku 2, która je nazywa.

Jeżeli operator w bieżącej turze wprost polecił scalenie (i push) konkretnego,
znanego mu wyniku, to polecenie jest zgodą z kroku 2: nie pytaj ponownie, ale
preflight, raport i pozostałe bramki obowiązują bez zmian.

## Kroki

Każda komenda ma jawny timeout (≤ 120 s). Katalog roboczy: główny katalog
worktree gałęzi (`.venv` i `node_modules` w worktree są dowiązaniami do
`D:\game_predicotr`).

1. **Preflight** (tylko odczyt, bez fetch):

   ```powershell
   .\.venv\Scripts\python.exe scripts/integration_preflight.py
   .\.venv\Scripts\python.exe scripts/integration_preflight.py --json
   ```

   Pierwszy argument pozycyjny wskazuje inną gałąź niż bieżąca, `--base` inną
   gałąź integracyjną. Raport: liczba commitów przed/za `main`, czy fast-forward
   jest możliwy, stan `main` względem `origin/main` (ref lokalny, może być
   nieaktualny, bo nie robisz fetch), czy worktree gałęzi i checkout `main` są
   brudne, kolizje numerów TASK, `D-NNN`, `vX.Y.N` i migracji z `main` oraz z
   innymi niescalonymi gałęziami lokalnymi, migracje dodane przez gałąź. Kod
   wyjścia to 0 także przy kolizjach; ostrzeżenia czytasz z treści. Kod 1 to
   błąd git: napraw przyczynę, nie ignoruj.

2. **Pokaż wynik i zapytaj o zgodę** (pomiń pytanie tylko w sytuacji z ostatniego
   akapitu sekcji „Bramki zgody”). Podaj: nazwę gałęzi, zakres commitów
   (`git log --oneline main..<gałąź>`), wyniki testów i audytów, ostrzeżenia
   preflightu (kolizje, migracje, brudne worktree, `main` przed `origin/main`),
   a w pytaniu nazwij scalenie fast-forward do `main`, push `main` do origin oraz
   usunięcie worktree i gałęzi. Kolizje i migrację zgłoś przed pytaniem, nie po
   zgodzie. Oczekującego scalenia nie przedstawiaj jako wykonanego.

3. **Aktualizacja gałęzi.** Jeżeli `main` ma commity, których gałąź nie ma
   (preflight: „behind” większe od 0), albo jeśli `main` przesunął się od
   ostatniego preflightu, scal `main` do gałęzi w jej worktree:

   ```powershell
   git merge main
   ```

   Użyj `-m "vX.Y.N - merge main into <gałąź>"`, gdzie `vX.Y.N` to wersja
   następna po ostatnim wersjonowanym commicie gałęzi (`git log`). Brak
   tożsamości git w `D:\game_predicotr`: jeśli commit odmawia pracy, dodaj
   `git -c user.name=... -c user.email=...` z autorem istniejących commitów,
   nie zmieniaj konfiguracji.

4. **Konflikty.** Rozwiąż je bez gubienia cudzej pracy. Dla dokumentów procesu
   obowiązują bieżące formaty:
   - `CURRENT_STATE.md`: okno kroczące; wskaźnik aktywnego taska ≤ 1 200 B, 10
     jednowierszowych wpisów `done` (≤ 400 B), pełne sekcje `done` na początku
     najnowszego archiwum `ai_docs/archive/CURRENT_STATE_*.md` bez zmian
     tekstu; ograniczenia i plany po obu stronach scal ręcznie.
   - `DECISION_LOG.md`: indeks 30 najnowszych wierszy; wiersze ponad 30
     przenieś bez zmiany treści na początek
     `ai_docs/process/decisions/DECISION_INDEX_ARCHIVE.md`, poprawiając tylko
     ścieżkę linku na `DECISION_LOG_2026.md#…`; pełny wpis jest na początku
     `decisions/DECISION_LOG_2026.md`.
   - Numery: kolizja `vX.Y.N` jest znana i akceptowana (bez przepisywania
     historii), odnotuj ją w raporcie. Kolizja TASK, `D-NNN` albo migracji:
     jeżeli numer jest jeszcze tylko na gałęzi roboczej, przenumeruj własny wpis
     (plik, nagłówki, odwołania, wiersze `CURRENT_STATE.md`) w nowym commicie na
     gałęzi; przy migracji (identyfikatory rewizji Alembic) i przy wielu
     taskach zapytaj operatora. Nie zgaduj, który wpis jest „starszy”.
   - Konflikt w kodzie, który zmienia sens pracy, wymaga powrotu do operatora.

5. **Kontrola dokumentów** po synchronizacji i konfliktach:

   ```powershell
   npm run docs:check
   git diff --check
   ```

   Gdy synchronizacja przyniosła kod z `main`, który dotyka zmienianego
   obszaru, uruchom też testy zmienionych części (jak przed zgodą).

6. **Hashe commitów tasków.** Dla tasków zamkniętych na tej gałęzi, których
   wiersz w „Ostatnie 10 ukończonych tasków” nie ma hasha, zapisz hash przed
   scaleniem (fast-forward zachowuje hashe):

   ```powershell
   rg -n "^- \*\*TASK-\d{4}\*\* — .* — v\d+\.\d+\.\d+ — tasks/completed/" ai_docs/process/CURRENT_STATE.md
   git log main..HEAD --format="%H %s"
   .\.venv\Scripts\python.exe scripts/close_task.py record-hash TASK-NNNN `
     --commit <pełny-40-znakowy-hash> --version vX.Y.N
   ```

   Hash bierz z commitu zamykającego taska (wiersz zaczynający się od jego
   `vX.Y.N`). Potem `npm run docs:check`, `git diff --cached --check` i jeden
   commit `vX.Y.N - record task hashes` z numerem następnym po ostatnim na
   gałęzi (zasady z `task-close`). Dodaj do indeksu wyłącznie te pliki.

7. **Ponowny preflight tuż przed scaleniem.** Uruchom krok 1 jeszcze raz.
   Wymagane: fast-forward możliwy (behind = 0), worktree gałęzi czysty, checkout
   `D:\game_predicotr` na `main` i bez zmian śledzonych, brak nowych kolizji,
   brak migracji wymagającej wykonania. Gdy `main` znów się przesunął, wróć do
   kroku 3. Zapamiętaj czubek `main` sprzed scalenia:

   ```powershell
   git -C D:\game_predicotr rev-parse main
   ```

8. **Scalenie fast-forward** w checkout integracyjnym (nie w worktree gałęzi;
   `main` jest wyewidencjonowany w `D:\game_predicotr`):

   ```powershell
   git -C D:\game_predicotr branch --show-current
   git -C D:\game_predicotr merge --ff-only <gałąź>
   ```

   Błąd `--ff-only` oznacza, że `main` się przesunął: wróć do kroku 3, nie
   zastępuj go zwykłym merge ani `reset`. Nie nadpisuj nieśledzonych plików
   operatora w `D:\game_predicotr` (np. `worktrees/`).

9. **Push** (zgoda na scalenie z kroku 2 go obejmuje, chyba że operator wprost
   go wyłączył):

   ```powershell
   git -C D:\game_predicotr push origin main
   ```

   Odrzucenie push (origin się przesunął) zgłoś operatorowi; bez `--force`, bez
   fetch i automatycznego rebase. Potem potwierdź:
   `git -C D:\game_predicotr rev-parse main origin/main`.

10. **Sprzątanie worktree** (dopiero po udanym scaleniu, z checkoutu
    `D:\game_predicotr`, nigdy z wnętrza usuwanego worktree). Dowiązania
    `.venv` i `node_modules` wskazują na główny checkout, więc najpierw je
    odepnij, bez `/s` i bez `--force`:

    ```powershell
    $wt = '<ścieżka worktree>'
    $dirs = @(Get-ChildItem -LiteralPath $wt -Force -Directory) +
      @(Get-ChildItem -Path "$wt\apps\*", "$wt\packages\*", "$wt\services\*" -Force -Directory -ErrorAction SilentlyContinue)
    $dirs | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint } |
      ForEach-Object { "$($_.FullName) -> $($_.Target)" }
    cmd /c rmdir "$wt\.venv"
    cmd /c rmdir "$wt\node_modules"
    Test-Path D:\game_predicotr\.venv\Scripts\python.exe
    Test-Path D:\game_predicotr\node_modules
    ```

    Odepnij też każde inne dowiązanie z wyliczenia (`cmd /c rmdir <ścieżka>`).
    Oba `Test-Path` muszą zwrócić `True`; jeśli nie, zatrzymaj się i zgłoś,
    nie wykonuj kolejnych kroków. Dopiero potem:

    ```powershell
    git -C D:\game_predicotr worktree remove <ścieżka worktree>
    git -C D:\game_predicotr branch -d <gałąź>
    ```

    `git worktree remove` bez `--force` odmawia przy niezacommitowanych lub
    nieśledzonych plikach: zgłoś je operatorowi zamiast wymuszać. `branch -d`
    (nie `-D`) odmawia, gdy gałąź nie jest w całości w `main`; to sygnał błędu
    scalenia, nie przeszkoda do ominięcia. Wpisów `remotes/` i gałęzi innych
    sesji nie usuwaj.

11. **Raport końcowy.** Najpierw potwierdź, że `main` zawiera commity tasków
    (`git -C D:\game_predicotr merge-base --is-ancestor <hash> main`, kod 0).
    Podaj: nazwę scalonej gałęzi, zakres wypchniętych
    commitów (`git log --oneline <czubek main sprzed>..main`) z pełnym hashem
    czubka `main` i `origin/main`, wynik `docs:check`, kolizje numerów
    zaakceptowane lub rozwiązane, stan worktree po scaleniu
    (`git -C D:\game_predicotr status --short`), stan sprzątania oraz rzeczy do
    zrobienia przez operatora (restart usług, `npm install`, build, migracja).
    Rozróżnij wynik scalony od oczekującego i zapisz hashe w `Outcome` oraz
    `CURRENT_STATE.md` (krok 6 robi to przed scaleniem).

## Uwagi

- Preflight liczy kolizje dla numerów, które gałąź dodała względem wspólnego
  przodka z `main`. Ten sam plik (ta sama nazwa), ten sam nagłówek `D-NNN` i ten
  sam commit po obu stronach to jeden element, nie kolizja. Sekcja
  „Informational” raportu pokazuje kolizje innych gałęzi z `main`; nie dotyczą
  scalanej pracy, ale przydają się do przewidzenia kolejnego scalenia.
- Raport używa lokalnego `origin/main`. Skrypt nie robi fetch; jeżeli
  potrzebna jest świeżość, poproś operatora o fetch lub wykonaj go tylko za jego
  wyraźnym poleceniem.
- Polskie cudzysłowy („ ”) w napisach PowerShell w podwójnym cudzysłowie psują
  parser; komunikaty commitów z takimi znakami przekazuj z pliku (opcja `-F` komendy `git commit`) albo w
  apostrofach.
- Kopia tego skilla dla Codex musi być identyczna bajtowo; edytuj
  `.claude/skills/merge-to-main/SKILL.md` i skopiuj plik do
  `.agents/skills/merge-to-main/SKILL.md`, a `scripts/check_skill_mirrors.py`
  (część `npm run docs:check`) wykryje rozjazd.
