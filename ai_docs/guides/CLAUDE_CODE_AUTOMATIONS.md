---
title: Automatyzacje Claude Code (hooki i subagent)
status: active
last_updated: 2026-10-16
---

# Automatyzacje Claude Code (TASK-1040)

Projektowe hooki i subagent Claude Code. Wszystkie są skryptami stdlib uruchamianymi
jako `.venv\Scripts\python.exe -I scripts/hooks/<nazwa>.py`, wpisanymi w
`.claude/settings.json`, i działają w sesjach Claude Code uruchomionych w katalogu
projektu (w worktree potrzebne są dowiązania `.venv` i `node_modules`; bez nich hook
nie startuje i narzędzie przechodzi bez kontroli). Hooki chronią przed pomyłką agenta,
nie są barierą bezpieczeństwa: ktoś, kto chce je obejść, obejdzie je poleceniem
złożonym inaczej, więc reguły wiążące zostają w `AGENTS.md`.

| Hook | Zdarzenie / matcher | Skutek |
|---|---|---|
| `block_large_read.py` | `PreToolUse` `Read` | blokada odczytu pliku > 200 KB bez `offset`/`limit` (`TOKEN_TOOLING.md`) |
| `guard_paths.py` | `PreToolUse` `Edit\|Write\|NotebookEdit` | blokada (exit 2) edycji chronionych ścieżek |
| `guard_commands.py` | `PreToolUse` `Bash\|PowerShell` | pytanie o zgodę (`ask`) przy poleceniach destrukcyjnych |
| `format_edited_file.py` | `PostToolUse` `Edit\|Write` | formatowanie tylko edytowanego pliku |

## `guard_paths.py`: blokada edycji

Komunikat po polsku trafia do modelu. Blokowane są:

- `.env` i `.env.*` z wyjątkiem `.env.example` (sekrety);
- wszystko pod `.tooling\` (izolowany JDK/SDK i klucze podpisu wydań);
- wszystko pod starą kopią `C:\Users\tuszy\Documents\game_predicotr`;
- `package-lock.json` (zmienia go wyłącznie npm).

Ścieżki są porównywane bez rozróżniania wielkości liter, ze znormalizowanymi
separatorami; ścieżki względne rozwiązuje `cwd` z wywołania. Błędne wejście nie blokuje.

## `guard_commands.py`: pytanie przed poleceniem destrukcyjnym

Hook nigdy nie odmawia: zwraca `permissionDecision: "ask"` z powodem po polsku, a
operator decyduje w oknie zgody. Polecenie jest dzielone na segmenty (`;`, `&&`, `||`,
`|`, nowa linia, poza cudzysłowami); ciągi z `cmd /c`, `powershell -Command` i
`bash -c` są analizowane rekurencyjnie. Pytanie wywołują:

- `db:reset` w poleceniu;
- `git push` z `--force`, `-f` (także w skupieniu, np. `-fu`), `--force-with-lease`
  lub refspecem `+gałąź`; `git reset --hard`; `git clean` z `-f`;
  `git worktree remove` z `--force`/`-f`; `git branch -D` (małe `-d` przechodzi);
- SQL `DROP DATABASE|TABLE|SCHEMA` i `TRUNCATE` (bez względu na wielkość liter, także
  w cudzysłowie, więc komunikat commita z takim tekstem też zapyta);
- **rekurencyjne usuwanie** (`rm -r/-rf/-R/--recursive`, `Remove-Item -Recurse`,
  `rmdir`/`rd /s`), gdy cel to katalog główny repozytorium albo `D:\game_predicotr`
  (także `\*` i `.` rozwiązane względem `cwd`) albo ścieżka z komponentem `.venv` lub
  `node_modules`. Dotyczy to także dowiązań (junction) w `worktrees\<nazwa>\`: w
  Windows PowerShell 5.1 rekurencyjne usunięcie przez junction kasuje zawartość celu.
  Bezpieczne odlinkowanie `cmd /c rmdir <ścieżka>` (bez `/s`) przechodzi bez pytania, tak
  jak usuwanie innych katalogów (`.next`, scratch, `worktrees\x` przez `git worktree
  remove` bez `--force`);
- polecenia zapisujące w starej kopii C: komenda git typu zapis (`commit`, `push`,
  `merge`, `reset`, `checkout`, `switch`, `rebase`, `stash`, `mv`, `rm` oraz `add`,
  `restore`, `clean`, `pull`, `cherry-pick`, `revert`) albo cmdlet/polecenie zapisujące
  (`Set-Content`, `Out-File`, `Add-Content`, `Remove-Item`, `Move-Item`, `Copy-Item` i
  aliasy), gdy ścieżka starej kopii jest w segmencie (`git -C`, argument) albo
  wcześniej w poleceniu jest `cd`/`Set-Location` do niej; przekierowanie `>` do niej też.
  `Copy-Item` pyta tylko wtedy, gdy stara kopia jest celem, nie źródłem. Polecenia
  tylko do odczytu (`git status|log|show|diff`, `Get-Content`, `cat`) przechodzą.

Znane fałszywe alarmy (zawsze tylko pytanie, nigdy odmowa): tekst `DROP TABLE` albo
`git push -f` w cudzysłowie komunikatu commita, `git push` z argumentem zaczynającym się
od `+`, `git clean -fn` (próba na sucho z `-f`), `truncate <słowo>` w cudzysłowie.
Znana luka: rekurencyjne usunięcie katalogu worktree (`worktrees\<nazwa>`) zawierającego
junctiony nie jest wykrywane; używaj `git worktree remove` albo najpierw `cmd /c rmdir`
na obu junctionach.

## `format_edited_file.py`: formatowanie po edycji

Po `Edit`/`Write` formatuje wyłącznie edytowany plik, i tylko wewnątrz katalogu projektu
(`CLAUDE_PROJECT_DIR`):

- `.py` pod `services/api`, `services/worker`, `services/test_support`, `scripts` →
  `ruff format --force-exclude <plik>` z `.venv`;
- pliki w zakresie `format:check` z `package.json` (`*.{css,js,json,md,mjs,ts,tsx,yaml,yml}`
  w katalogu głównym oraz pod `apps/`, `infra/`, `packages/`) →
  `node_modules\.bin\prettier.cmd --write <plik>` (zgodnie z `.prettierignore`).

Reszta (np. `ai_docs/**/*.md`) zostaje nietknięta. Limit 20 s na formater; brak
formatera, błąd albo przekroczenie czasu kończą się cicho kodem 0 (fail-open). Hook nic
nie wypisuje. Edytor widzi zmieniony plik przy następnym odczycie, więc po `Edit`
agent ponawia odczyt zamiast zakładać stary tekst.

## Wyłączanie

- Jedno zdarzenie albo hook: usuń wpis z `.claude/settings.json` (zmiana na gałęzi) albo,
  tylko dla siebie, nadpisz w `.claude/settings.local.json` (nieśledzony).
- Wszystkie hooki użytkownika: `"disableAllHooks": true` w `.claude/settings.local.json`.
- Hook odczytu ma własne zmienne środowiskowe (`TOKEN_TOOLING.md`); pozostałe nie.
- Test ręczny (kod 2 = blokada; dla `guard_commands.py` JSON z `ask` na stdout):

```powershell
# katalog repozytorium, timeout 20 s
'{"tool_name":"Edit","tool_input":{"file_path":"D:\\game_predicotr\\.env"}}' | .\.venv\Scripts\python.exe -I scripts/hooks/guard_paths.py; $LASTEXITCODE
'{"tool_name":"PowerShell","tool_input":{"command":"git push --force origin main"}}' | .\.venv\Scripts\python.exe -I scripts/hooks/guard_commands.py
```

Testy: `services/api/tests/test_guard_paths_hook.py`, `test_guard_commands_hook.py`,
`test_format_edited_file_hook.py`.

## Subagent `repo-explorer`

`.claude/agents/repo-explorer.md`: model `haiku`, narzędzia `Read`, `Grep`, `Glob`
(bez edycji i bez powłoki). Do szerokiej, odczytowej eksploracji („gdzie leży kod”, „jak
przebiega przepływ”): startuje od `CODE_MAP.md`, szuka w `CODE_MAP_SYMBOLS.md`, czyta
fragmenty z `offset`/`limit`, pomija katalogi robocze i zwraca listę
`ścieżka:linia — symbol — opis` oraz otwarte pytania (ok. 300 słów). Wywołanie: Claude
Code deleguje sam po opisie albo poleceniem „użyj subagenta repo-explorer”. Wnioski haiku
traktuj jak wskazówki lokalizacji: przed zmianą kodu sprawdź wskazany fragment.

## Codex

Codex nie czyta hooków z `.claude/settings.json` ani agentów z `.claude/agents/`. Te
same reguły (chronione ścieżki, polecenia destrukcyjne, zakaz zmian w starej kopii C)
obowiązują go przez `AGENTS.md`; hooki są dodatkowym zabezpieczeniem tylko po stronie
Claude Code.
