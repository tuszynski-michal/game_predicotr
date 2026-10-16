# TASK-1030 — Skill `task-close` ze skryptem zamykania taska

## Status

`done`

## Goal

Zamknięcie taska (plik do `completed/`, pełna sekcja `done` do archiwum,
wiersz w oknie, usunięcie wskaźnika, zapis hasha po commicie) wykonuje
przetestowany `scripts/close_task.py`, wywoływany przez skill `task-close`
w Claude Code i w Codex.

## Context

Plan `delivery/STARTUP_READ_STAGE2_EXECUTION_PLAN_20261016.md`, etap A,
decyzje E1–E2. Format okna opisuje nagłówek `CURRENT_STATE.md` i `AGENTS.md`,
„Po kodowaniu” 3. 2026-10-16 ręczne zamykanie dało commit z czerwonym
`docs:check` i edycję złych plików przy kolizji numerów (TASK-1022, TASK-1024).

## Dependencies / entry conditions

- Brak zależności w planie. Przed commitem potwierdzić wolny numer i wersję
  względem `main` i otwartych gałęzi.
- Fakt: `scripts/check_current_state_window.py` akceptuje wiersz `done` bez
  hasha (hash dopisuje kolejny commit).

## Recommended execution

claude-sonnet-5-5 / high; eskalacja do claude-opus-5-5 / high, jeśli Codex nie
wykrywa skilli repozytorium w żadnym katalogu. Bez dodatkowego review;
samokontrola kryteriów w `Outcome`.

## Relevant docs

- `AGENTS.md` („Po kodowaniu”, „Wersjonowanie commitów”, „Brudny worktree”)
- `ai_docs/process/CURRENT_STATE.md` (nagłówek z regułą utrzymania)
- `ai_docs/delivery/STARTUP_READ_STAGE2_EXECUTION_PLAN_20261016.md`
- `.claude/skills/audit-task/SKILL.md` (wzorzec skilla w repo)

## Scope

- Nowy `scripts/close_task.py` (proponowany), tryby:
  - `close TASK-NNNN --title … --version vX.Y.N --done-file <plik z pełną sekcją>`:
    znajduje plik taska po **pełnej ścieżce** z `ai_docs/tasks/NNNN-*.md`
    (błąd, gdy pasuje więcej niż jeden plik albo żaden), ustawia status
    `done` w sekcji `## Status` i w front matter, `git mv` do `completed/`,
    usuwa wskaźnik `### TASK-NNNN` z okna, dopisuje pełną sekcję `done` na
    początku archiwum kwartału, dodaje wiersz `done` na początku listy i
    usuwa wiersze ponad 10;
  - `record-hash TASK-NNNN --commit <hash>`: dopisuje krótki hash w wierszu
    okna, pełny w sekcji archiwum i w `Outcome` pliku taska;
  - `--dry-run`: wypisuje planowane zmiany bez zapisu.
  Skrypt nie commituje. Kończy się błędem, gdy po zmianie
  `check_current_state_window.py` lub budżety nie przechodzą (zapisy
  wycofane).
- Skill `.claude/skills/task-close/SKILL.md`: kiedy użyć (zamykanie
  każdego taska), kroki (Outcome → `close_task.py` → `docs:check` →
  `git diff --cached --check` → commit `vX.Y.N - …` → `record-hash` w
  kolejnym commicie), uwagi (kolizje numerów, polskie cudzysłowy w
  PowerShell, nie commitować cudzych hunków).
- Katalog skilli Codex: test na zainstalowanym Codex CLI, czy wykrywa skill
  w `.agents/skills/` i/lub `.codex/skills/` (np. `codex` z promptem
  wymieniającym dostępne skille, w trybie tylko do odczytu, z limitem
  czasu). Kopia `task-close` trafia do wykrytego katalogu; wynik testu w
  `Outcome`. Jeżeli wykrywany jest tylko `.agents/skills/`, przenieś też
  `claude-audit` i zaktualizuj odwołania.
- Nowy `scripts/check_skill_mirrors.py` w `docs:check`: pary lustrzane
  (lista w skrypcie) muszą być identyczne bajtowo.

## Out of scope

- Zmiana `AGENTS.md` (TASK-1032); skill uzupełnia, nie zastępuje reguł.

## Acceptance criteria

- [ ] Testy `close_task.py`: zamknięcie z przesunięciem 11. wiersza, zapis hasha, kolizja dwóch plików o tym samym numerze (błąd), brak pliku (błąd), `--dry-run` bez zapisu, wycofanie przy czerwonej kontroli okna.
- [ ] Skill `task-close` w Claude Code i kopia wykryta przez Codex CLI (dowód w `Outcome`).
- [ ] `check_skill_mirrors.py` w `docs:check`, test negatywny różnicy kopii.
- [ ] `npm run docs:check`, ruff, `mypy --strict` PASS.

## Expected files

- Nowe (proponowane): `scripts/close_task.py`, `scripts/check_skill_mirrors.py`,
  `.claude/skills/task-close/SKILL.md`, kopia w katalogu Codex, testy w
  `services/worker/tests/`.
- Istniejące: `package.json` (`docs:check`).

## Verification

```powershell
# katalog worktree z dowiązaniem .venv, timeout 120 s
.\.venv\Scripts\python.exe -m pytest services/worker/tests -k "close_task or skill_mirrors" -q -p no:cacheprovider --basetemp D:/ptw
.\.venv\Scripts\python.exe -m mypy --strict scripts/close_task.py scripts/check_skill_mirrors.py
npm run docs:check
```

## Risks / open questions

- Wersja Codex CLI może nie ładować skilli z repozytorium; wtedy wynik
  testu i obejście (instrukcja w `AGENTS.md`) w `Outcome`.

## Outcome

Commit: v1.7.378 / `54e011333aafc4aaf5ae6b8e63a5a36e1546f184`.

Wykonawca: claude-sonnet-5-5 (podagent leada). Bez dodatkowego review
(zgodnie z planem); samokontrola kryteriów poniżej. Status `todo` zostaje do
uruchomienia `close_task.py close` przez leada.

### Changed

- `scripts/close_task.py` (nowy): podkomendy `close` i `record-hash`, globalne
  `--dry-run` (przed podkomendą) i `--root` (do testów). Niczego nie commituje;
  `git mv` tylko dla pliku taska (dla niezaśledzonego pliku zwykłe
  przeniesienie). Reguły dopasowania:
  - plik taska: jedyne `ai_docs/tasks/NNNN-*.md` (tylko katalog aktywny; 0 lub
    więcej niż 1 plik to błąd z listą plików);
  - status: pierwsza niepusta linia `## Status` musi mieć postać `` `token` ``,
    token → `` `done` `` (następny nagłówek nietknięty, także bez pustej linii);
    front matter: `status:` → `done`, `last_updated:` → `--date` (domyślnie
    dziś) tylko gdy klucz istnieje;
  - archiwum: najnowszy `CURRENT_STATE_<rok>Q<n>.md` (inne pliki
    `CURRENT_STATE_*` ignorowane); sekcja z `--done-file` trafia pod pierwszą
    linię `# `; nagłówek pliku musi być `### TASK-NNNN … (done)` i tekst musi
    wspominać `vX.Y.N`;
  - okno: wiersz na początku „Ostatnie 10 ukończonych tasków”, elementy ponad 10
    usuwane; wskaźnik `###`/`####` `TASK-NNNN` w „Aktywne taski” (dokładnie
    jeden) usuwany razem z treścią do następnego nagłówka tego samego lub
    wyższego poziomu; stan kończy się jednym znakiem nowej linii;
  - `record-hash`: dokładnie jeden wiersz okna `TASK-NNNN … vX.Y.N — tasks/…`
    bez hasha (opcjonalne `--version` zawęża) → `vX.Y.N / `<8 znaków>``; w
    najnowszym archiwum pierwsza (od góry) sekcja `### …TASK-NNNN` z wzmianką
    `vX.Y.N` bez hasha → `vX.Y.N / `<pełny hash>``; w pliku taska z
    `completed/` jedyna linia `Commit: vX.Y.N (hash dopisuje kolejny commit).`
    → `Commit: vX.Y.N / `<pełny hash>`.` (plik z tym hashem już zapisanym
    zostaje); commit musi istnieć w repozytorium (`git cat-file`).
  - kontrole: po zapisie w procesie `check_current_state_window` (z podmienionym
    `ROOT`/`STATE`/`TASKS`) i `check_startup_read_budget.check(root)`; przy
    błędzie wycofanie zapisów i `git mv`. `--dry-run` liczy zmianę w pamięci i
    uruchamia obie kontrole na tymczasowej kopii (bez zapisu w repozytorium).
  - końce linii (LF/CRLF) pliku są zachowane, kodowanie UTF-8 bez zmiany BOM.
- `scripts/check_skill_mirrors.py` (nowy) i dopisek w `docs:check`
  (`package.json`): pary lustrzane (na razie `task-close`) muszą być identyczne
  bajtowo; brak pliku lub różnica to kod 1 z komunikatem.
- `.claude/skills/task-close/SKILL.md` (nowy, kanoniczny) i jego kopia
  `.agents/skills/task-close/SKILL.md` (Codex).
- Testy: `services/worker/tests/test_close_task_script.py` (22),
  `services/worker/tests/test_check_skill_mirrors_script.py` (6).

### Verification results

- `pytest` (`-p no:cacheprovider --basetemp D:/pw30`): nowe 28 testów, razem z
  istniejącymi `test_check_current_state_window_script.py`,
  `test_check_startup_read_budget_script.py` i
  `test_check_decision_links_script.py` 50 passed. Pokrycie kryteriów:
  zamknięcie z przesunięciem 11. wiersza
  (`test_close_moves_task_and_updates_window_archive_and_status`), zapis hasha
  (`test_record_hash_updates_window_archive_and_outcome`, prawdziwy commit w
  tymczasowym repozytorium), kolizja dwóch plików (`test_collision_of_two_task_files_is_an_error`),
  brak pliku (`test_missing_task_file_is_an_error`), `--dry-run` bez zapisu
  (`test_dry_run_prints_plan_and_writes_nothing`, migawka bajtów i
  `git status`), wycofanie przy czerwonej kontroli (budżet:
  `test_red_budget_check_rolls_back_every_write_and_the_move`, okno:
  `test_red_window_check_rolls_back`), test negatywny kopii
  (`test_differing_copy_fails_with_clear_message`).
- `ruff check` i `ruff format --check` (4 pliki), `mypy --strict` (4 pliki):
  PASS.
- `npm run docs:check`: PASS (decision links 545, okno 4 aktywne / 10 done,
  budżety 9/9, `check_skill_mirrors` 1 para). `git diff --check`: czysto.
- `close_task.py --dry-run close TASK-1030 --title … --version v1.7.378
  --done-file …` na prawdziwym repozytorium: kod 0, plan: przeniesienie pliku do
  `completed/`, 4 linie w archiwum Q4, nowy wiersz okna, usunięcie wiersza
  TASK-0992 i wskaźnika TASK-1030, „checks: window and budgets would pass”;
  `git status` bez zmian.

### Codex CLI probe

- Zainstalowany `codex-cli 0.162.0`, uruchomienie jak w `scripts/audit_task.ps1`
  (`node.exe` + `codex.js`, piaskownica `unelevated`, tylko do odczytu) z
  katalogu worktree, `timeout 280`, bez poświadczeń w poleceniu:
  `node.exe <npm>/node_modules/@openai/codex/bin/codex.js exec --sandbox read-only
  -c 'windows.sandbox="unelevated"' -c 'model_reasoning_effort="low"' "<prompt:
  wypisz nazwy skilli dostępnych w tej sesji dla repozytorium, bez zmian plików>"`.
- Wynik: lista zawierała `task-close` (kopia tylko w `.agents/skills/`) oraz
  `claude-audit` (istniejący w `.codex/skills/`), a także skille systemowe i
  użytkownika; odpowiedź wskazała jako źródła repozytoryjne
  `<worktree>\.codex\skills` i `<worktree>\.agents\skills`. Codex 0.162.0
  wykrywa więc oba katalogi. Zgodnie z regułą „oba działają → `.agents/skills/`”
  kopia `task-close` leży tylko w `.agents/skills/task-close/SKILL.md`;
  `claude-audit` zostaje w `.codex/skills/` (przenosiny niepotrzebne).
  Ograniczenie dowodu: lista pochodzi z odpowiedzi modelu, jedno uruchomienie;
  `task-close` nie był sprawdzany w `.codex/skills/` (nie było potrzeby).

### Not completed

- Brak commita i zamknięcia taska (robi lead: `close`, potem `record-hash` po
  commicie). Nie zmieniono `AGENTS.md` (TASK-1032). Odwołania do ścieżek
  skilli Codex w dokumentacji nie wymagały zmiany.
- `close_task.py` nie aktualizuje „Obowiązujące ograniczenia” ani „Plany” w
  oknie (zostaje ręcznie, krok 3 skilla).

### Recommended next task

TASK-1031 — `scripts/integration_preflight.py` i skill `merge-to-main`; ten sam
wzorzec skill + skrypt + testy; kopię skilla dopisać do `MIRRORED_PAIRS` w
`scripts/check_skill_mirrors.py` i umieścić w `.agents/skills/`.
