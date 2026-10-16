---
name: task-close
description: Zamyka ukończony task według formatu okna CURRENT_STATE.md skryptem scripts/close_task.py (plik do completed/, pełna sekcja done do archiwum, wiersz w oknie, usunięcie wskaźnika, zapis hasha po commicie). Użyj, gdy task jest gotowy do commita i trzeba go zamknąć, np. "zamknij task", "zamknij TASK-1030", "close task", "mark task done", "zapisz hash commita taska".
---

# Zamykanie taska (`close_task.py`)

Zamknięcie taska jest powtarzalne, więc robi je skrypt `scripts/close_task.py`,
a nie ręczna edycja. Ręczne zamykanie dawało commity z czerwonym `docs:check`
i edycję złych plików przy kolizji numerów TASK. Skill uzupełnia reguły z
`AGENTS.md` („Po kodowaniu”, „Wersjonowanie commitów”, „Brudny worktree i zakres
commita”); ich nie zastępuje. Format okna opisuje nagłówek
`ai_docs/process/CURRENT_STATE.md`.

## Kiedy użyć

Przy zamykaniu każdego taska: implementacja i testy są gotowe, sekcja `Outcome`
wypełniona, a task ma wejść do commita. Drugi tryb (`record-hash`) uruchamiasz w
commicie następującym po zamykającym.

## Kroki

1. Ustal numer wersji `vX.Y.N` commita zamykającego z historii bieżącego
   brancha (`git log`, zasada z `AGENTS.md`). Pierwszy wiersz sekcji `Outcome`
   taska musi brzmieć dokładnie `Commit: vX.Y.N (hash dopisuje kolejny commit).`;
   tę linię `record-hash` zamieni potem na wersję z hashem.
2. Przygotuj plik z pełną sekcją `done` (poza repozytorium, np. w katalogu
   tymczasowym sesji), w formacie archiwum: nagłówek
   `### TASK-NNNN — Tytuł (done)`, pusta linia i punkty (plik taska, commit
   `**vX.Y.N**`, wynik). Nagłówek musi zawierać numer taska i kończyć się
   `(done)`, a tekst musi wspominać `vX.Y.N`. Tekst trafia do archiwum bez zmian.
3. Zaktualizuj ręcznie to, czego skrypt nie dotyka: „Obowiązujące ograniczenia”
   i „Plany” w `CURRENT_STATE.md` (jeżeli task je zmienia) oraz dokumentację
   zmienionego zachowania.
4. Sprawdź plan bez zapisu (ze skryptu z katalogu głównego worktree; flaga
   `--dry-run` stoi przed podkomendą):

   ```powershell
   .\.venv\Scripts\python.exe scripts/close_task.py --dry-run close TASK-NNNN `
     --title "Tytuł taska" --version vX.Y.N --done-file <plik-sekcji.md>
   ```

   Dry-run wypisuje zmiany i sprawdza je kontrolą okna oraz budżetami na kopii
   tymczasowej. Błąd oznacza, że nic nie zostanie zapisane.

5. Uruchom to samo bez `--dry-run`. Skrypt: znajduje plik taska po jedynym
   dopasowaniu `ai_docs/tasks/NNNN-*.md` (błąd przy 0 lub więcej niż 1 pliku),
   ustawia status `done` (sekcja `## Status` i front matter), robi `git mv` do
   `ai_docs/tasks/completed/`, dopisuje sekcję na początku najnowszego archiwum
   kwartału, dodaje wiersz na początku „Ostatnie 10 ukończonych tasków”, usuwa
   wiersze ponad 10 i wskaźnik taska z „Aktywne taski”. Potem sam uruchamia
   `check_current_state_window.py` oraz `check_startup_read_budget.py`; gdy któraś
   kontrola nie przechodzi, wycofuje wszystkie zapisy i `git mv` (kod wyjścia 1).
   Skrypt niczego nie commituje.
6. Uruchom `npm run docs:check`.
7. Dodaj do indeksu wyłącznie pliki i hunki tego taska, potem
   `git diff --cached --check` oraz przegląd `git diff --cached --stat`.
   Commit: `vX.Y.N - krótki opis` (z linią atrybucji wymaganą przez sesję).
8. W następnym commicie (zwykle kolejnego taska albo osobnym, jeżeli to
   koniec pracy) zapisz hash:

   ```powershell
   .\.venv\Scripts\python.exe scripts/close_task.py record-hash TASK-NNNN `
     --commit <pełny-40-znakowy-hash>
   ```

   Skrypt dopisuje 8-znakowy hash w wierszu okna, pełny hash w sekcji archiwum i
   w `Outcome` pliku w `completed/`, i przechodzi te same kontrole. Przy kilku
   wierszach okna dla tego numeru bez hasha dodaj `--version vX.Y.N`.

## Uwagi

- Kolizje numerów TASK: skrypt szuka pliku tylko w `ai_docs/tasks/` (aktywne) i
  przerywa przy dwóch plikach o tym samym numerze; rozwiąż kolizję (przenumeruj
  jeden task) przed zamknięciem. Nie zgaduj pliku.
- Wiersz `done` bez hasha jest poprawny dla `check_current_state_window.py`;
  hash dopisuje dopiero `record-hash`. Zamknięcie ma przejść `docs:check` bez
  hasha.
- Polskie cudzysłowy („ ”) w napisach PowerShell w podwójnym cudzysłowie psują
  parser. Tytuł z cudzysłowami albo `$` podaj w apostrofach lub zapisz plik
  sekcji narzędziem do edycji plików, a nie literałem w PowerShell.
- Nie commituj cudzych hunków: w worktree mogą być zmiany innych tasków lub
  użytkownika. `CURRENT_STATE.md` często zawiera zmiany kilku tasków, więc
  dodawaj do indeksu tylko własne hunki: interaktywne `git add -p` nie działa
  w sesji agenta, więc zapisz swój fragment `git diff -- <plik>` do pliku
  łatki, usuń z niej cudze hunki i dodaj ją przez `git apply --cached`.
- Wiersz okna ma ≤ 400 B, a wskaźniki ≤ 1 200 B (budżety w
  `check_startup_read_budget.py`); krótki tytuł oszczędza budżet.
- Wszystkie pliki są zapisywane jako UTF-8 bez BOM z zachowaniem końców linii
  pliku; nie dopisuj sekcji do archiwum ręcznie.
- Kopia tego skilla dla Codex musi być identyczna bajtowo; edytuj
  `.claude/skills/task-close/SKILL.md` i skopiuj plik, a
  `scripts/check_skill_mirrors.py` (część `npm run docs:check`) wykryje rozjazd.
