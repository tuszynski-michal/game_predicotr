# TASK-1030 — Skill `task-close` ze skryptem zamykania taska

## Status

`todo`

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

Wypełnia agent po pracy.
