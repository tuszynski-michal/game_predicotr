# TASK-1040 — Hooki Claude Code i subagent `repo-explorer`

## Status

`done`

## Goal

Claude Code w repozytorium blokuje edycję chronionych ścieżek, pyta o zgodę przed
poleceniami destrukcyjnymi i formatuje edytowany plik, a szeroką eksplorację kodu
można zlecić tanim subagentem `repo-explorer`; wszystko jest opisane, przetestowane i
wpisane w `.claude/settings.json`.

## Context

Operator wybrał 2026-10-16 z analizy `claude-code-setup` trzy automatyzacje: hook
formatujący edytowany plik, hooki blokujące `.env`, `.tooling/`, starą kopię C i
polecenia destrukcyjne oraz subagenta `repo-explorer`. Istnieje już hook odczytu
(`scripts/hooks/block_large_read.py`, TASK-0939), którego styl (stdlib, fail-open,
`python -I`) nowe hooki powtarzają.

## Dependencies / entry conditions

- `main` na v1.7.385, worktree `claude-automations` z dowiązaniami `.venv` i
  `node_modules`.
- Fakt: Codex nie czyta `.claude/settings.json`; reguły wiążące zostają w `AGENTS.md`.

## Recommended execution

claude-sonnet-5-5 / medium (przypisanie operatora dla tego taska). Bez dodatkowego
review: operator go nie zlecił.

## Relevant docs

- `AGENTS.md`, `CLAUDE.md`
- `ai_docs/guides/TOKEN_TOOLING.md`, `ai_docs/DOC_INDEX.md`
- `ai_docs/process/TASK_TEMPLATE.md`, `.claude/skills/task-close/SKILL.md`

## Scope

- `scripts/hooks/guard_paths.py` (`PreToolUse` `Edit|Write|NotebookEdit`): exit 2 z
  komunikatem po polsku dla `.env`/`.env.*` (poza `.env.example`), `.tooling/`, starej
  kopii `C:\Users\tuszy\Documents\game_predicotr` i `package-lock.json`.
- `scripts/hooks/guard_commands.py` (`PreToolUse` `Bash|PowerShell`): `ask` dla
  `db:reset`, wymuszonego `git push`, `git reset --hard`, `git clean -f`,
  `git worktree remove --force`, `git branch -D`, SQL `DROP`/`TRUNCATE`,
  rekurencyjnego usuwania korzenia repozytorium, `D:\game_predicotr`, `.venv` i
  `node_modules` oraz poleceń zapisujących w starej kopii C.
- `scripts/hooks/format_edited_file.py` (`PostToolUse` `Edit|Write`): `ruff format` lub
  `prettier --write` tylko dla edytowanego pliku w zakresie `format:check`.
- `.claude/settings.json`, `.claude/agents/repo-explorer.md`, zdanie w `AGENTS.md`
  („Oszczędzanie kontekstu”), testy, `ai_docs/guides/CLAUDE_CODE_AUTOMATIONS.md`,
  wpisy w `DOC_INDEX.md` i `TOKEN_TOOLING.md`.

## Out of scope

- Hooki dla Codex; zmiana reguł wiążących `AGENTS.md`; hook odczytu (bez zmian).
- Wykrywanie usunięcia katalogu worktree z junctionami (opisana luka).

## Acceptance criteria

- [x] Trzy hooki działają zgodnie z protokołem Claude Code, są fail-open na
  błędnym wejściu i mają testy pozytywne oraz negatywne (fałszywe alarmy).
- [x] `.claude/settings.json` jest poprawnym JSON i zachowuje hook odczytu.
- [x] Subagent `repo-explorer` ma front matter `haiku` i narzędzia tylko do odczytu.
- [x] `AGENTS.md` ≤ 14 000 B (LF) i nazywa subagenta.
- [x] Dokumentacja opisuje działanie, wyłączanie i notkę o Codex.
- [x] Test dymny na żywo i kontrole z sekcji Verification przechodzą.

## Technical notes

- `guard_commands.py` dzieli polecenie na segmenty poza cudzysłowami i analizuje
  tokeny git (pomija opcje `-C`, `-c`, `--git-dir`), więc `git -C <stara kopia>
  status` przechodzi, a `git -C <stara kopia> commit` pyta. Hook nigdy nie
  odmawia, tylko pyta (`ask`); fałszywy alarm kosztuje jedno kliknięcie.
- Rekurencyjne usuwanie przez junction w `worktrees\*` pyta celowo: w Windows
  PowerShell 5.1 kasuje zawartość celu. Bezpieczne `cmd /c rmdir` bez `/s` przechodzi.
- Dodatkowe polecenia git traktowane jako zapis w starej kopii poza listą z
  zadania: `add`, `restore`, `clean`, `pull`, `cherry-pick`, `revert`.
- `ruff format` dostaje `--force-exclude`, żeby respektować wykluczenia z konfiguracji.

## Expected files

- Nowe: `scripts/hooks/guard_paths.py`, `guard_commands.py`, `format_edited_file.py`,
  `.claude/agents/repo-explorer.md`, `ai_docs/guides/CLAUDE_CODE_AUTOMATIONS.md`,
  trzy testy w `services/api/tests/`.
- Zmienione: `.claude/settings.json`, `AGENTS.md`, `ai_docs/DOC_INDEX.md`,
  `ai_docs/guides/TOKEN_TOOLING.md`, `ai_docs/process/CURRENT_STATE.md`.

## Test cases

- `Edit` `.env` → exit 2; `Edit` `.env.example` → 0; `Write` w starej kopii C → 2.
- `git push --force origin main` → `ask`; `git push origin main` → brak wyjścia.
- `git -C <stara kopia> commit` → `ask`; `git -C <stara kopia> status` → brak wyjścia.
- Formatowanie pliku `.py` w `scripts/`; brak formatera lub błąd → exit 0 bez zmian.

## Verification

```powershell
# katalog worktree, timeout 120 s na polecenie
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp D:/pta1 services/api/tests/test_guard_paths_hook.py services/api/tests/test_guard_commands_hook.py services/api/tests/test_format_edited_file_hook.py services/api/tests/test_block_large_read_hook.py -q
.\.venv\Scripts\python.exe -m ruff check scripts/hooks services/api/tests
.\.venv\Scripts\python.exe -m mypy --strict scripts/hooks/guard_paths.py scripts/hooks/guard_commands.py scripts/hooks/format_edited_file.py
npx prettier --check AGENTS.md .claude/agents/repo-explorer.md
npm run docs:check
git diff --check
```

## Risks / open questions

- Hooki działają tylko w sesjach Claude Code z dowiązaniami `.venv`; bez nich wpis w
  `settings.json` nie uruchomi skryptu (narzędzie przechodzi bez kontroli).
- Fałszywe alarmy `ask` (tekst `DROP TABLE` w komunikacie commita).

## Outcome

Commit: v1.7.386 / `ce72b7e7f9aae165257c887bdc0484f5e27126b0`.

Wykonawca: claude-sonnet-5-5. Bez dodatkowego review (operator go nie zlecił).

### Changed

- Hooki `guard_paths.py`, `guard_commands.py`, `format_edited_file.py` i wpisy w
  `.claude/settings.json` (timeouty 10 s, 10 s, 30 s); subagent
  `.claude/agents/repo-explorer.md`; zdanie w `AGENTS.md` (13 941 B LF).

### Verification results

- `pytest` (trzy nowe testy hooków + `test_block_large_read_hook.py`): 166 passed
  (nowe: guard_paths 24, guard_commands 100, format_edited_file 34, w tym test BOM i
  polskich liter w stdin).
- `ruff check`, `ruff format --check`, `mypy --strict` na trzech skryptach,
  `prettier --check AGENTS.md .claude/agents/repo-explorer.md`, `npm run docs:check`
  (11/11 budżetów, `AGENTS.md` 13 941 B), `git diff --check`, `json.tool` na
  `settings.json`: PASS.
- Test dymny na żywo: `.env` → exit 2, `.env.example` → 0, zapis w starej kopii C →
  2, `git push --force` → `ask`, `git push origin main` → brak wyjścia, `git -C <C>
  commit` → `ask`, `git -C <C> status` → brak wyjścia, formatowanie pliku `.py` w
  `scripts/` (ruff) i `.json` w katalogu głównym (prettier) → plik sformatowany.
- Odstępstwo: skrypty czytają stdin jako bajty UTF-8 (z tolerancją BOM), bo
  PowerShell 5.1 dopisuje BOM i dekodowanie według strony kodowej psuje polskie znaki.

### Not completed

- Niewykryte: rekurencyjne usunięcie katalogu worktree z junctionami (opis w
  `CLAUDE_CODE_AUTOMATIONS.md`).

### Documentation updates

- `ai_docs/guides/CLAUDE_CODE_AUTOMATIONS.md`, `ai_docs/DOC_INDEX.md`,
  `ai_docs/guides/TOKEN_TOOLING.md`, `ai_docs/process/CURRENT_STATE.md`.

### Recommended next task

- Po akceptacji: zamknięcie skryptem `close_task.py` i scalenie do `main`.
