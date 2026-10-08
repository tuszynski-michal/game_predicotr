# TASK-0929 — Skill audytu krzyżowego i sekcja „Audyt krzyżowy” w AGENTS.md

## Status

`done`

## Goal

Po zakończeniu zadania jedno polecenie (`/audit-task NNNN` w Claude Code,
lustrzany skill w Codex) buduje brief z pliku taska, planu i diffu, uruchamia
audyt drugą rodziną modeli w trybie tylko do odczytu i zapisuje raport do
`ai_docs/quality/`; `AGENTS.md` opisuje ten proces jako obowiązujący.

## Context

Operator chce, aby zmiany Claude audytował Codex, a zmiany Codex audytował
Claude. Dziś audyt odbywa się ręcznie w drugiej aplikacji. Biblioteka
`claudex-loop` została odrzucona (nieutrzymywana, błędy na Windows, własny
proces sprzeczny z `AGENTS.md`). Plan:
`ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`, etap P.

## Dependencies / entry conditions

- Fakt: `codex` i `claude` nie są na PATH (2026-10-08). Operator instaluje
  `npm i -g @openai/codex @anthropic-ai/claude-code` i loguje oba CLI; agent
  nie wpisuje poświadczeń. Bez tego skrypt działa w trybie „tylko brief”
  (zapisuje brief do pliku, operator wkleja go w drugiej aplikacji).
- Założenie: `codex exec --sandbox read-only -o <plik>` i
  `claude -p --permission-mode plan` są dostępne w zainstalowanych wersjach;
  sprawdzić `--help` przed użyciem i odnotować wersje w Outcome.

## Recommended execution

claude-sonnet-5-5 / high. Skrypt PowerShell, dwa pliki skilli i edycja
dokumentu; brak logiki domenowej. Eskalacja do claude-opus-5-5 / high, jeżeli
uruchamianie CLI wymaga obsługi kodowania lub procesów trudnej do
przetestowania. Audyt: gpt-6.1-sol / high; do czasu CLI zamiennik claude-opus-5-5 / high.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`

## Scope

- Nowy skill `.claude/skills/audit-task/SKILL.md` (proponowany) wywołujący
  `scripts/audit_task.ps1` (proponowany) z parametrami `-Task NNNN`,
  `-Auditor codex|claude`, `-Base <ref>`.
- Skrypt: składa brief (plik taska, sekcja planu, `git diff <base>...HEAD`
  plus zmiany niezacommitowane, lista uruchomionych testów z Outcome),
  uruchamia audytora w trybie tylko do odczytu z limitem czasu, zapisuje
  raport `ai_docs/quality/TASK-NNNN_AUDIT_<model>.md` w ustalonym formacie
  (werdykt PASS/REVISE, znaleziska P0–P2 z plikiem i linią, testy
  proponowane). Bez pętli: jedna runda audytu, jedna runda poprawek,
  ponowny audyt na żądanie.
- Lustrzany skill `.codex/skills/claude-audit/SKILL.md` (proponowany)
  używający tego samego skryptu z `-Auditor claude`.
- `AGENTS.md`: sekcja „Audyt krzyżowy” (kto audytuje, format raportu, co
  blokuje commit, gdzie leży raport) oraz zamiana „Joker” na „Wild” w
  dokumentach procesu, gdzie występuje.
- Kodowanie: wymuszone UTF-8 dla wejścia/wyjścia procesów (polskie znaki).

## Out of scope

- Instalacja CLI i logowanie (operator).
- Automatyczne uruchamianie audytu hookiem `Stop`.
- Pętle wielorundowe.

## Acceptance criteria

- [x] `scripts/audit_task.ps1 -Task 0930 -Auditor codex` tworzy brief i raport
      albo, bez CLI, sam brief z czytelnym komunikatem.
- [x] Ten sam skrypt z `-Auditor claude` działa lustrzanie.
- [x] Raport ma wymagany format i trafia do `ai_docs/quality/`.
- [x] `AGENTS.md` zawiera sekcję „Audyt krzyżowy” spójną z PLAN_STANDARD.md.
- [x] Skrypt ma limit czasu i kończy się kodem ≠ 0 przy błędzie CLI.

## Technical notes

- Audytor pracuje tylko do odczytu; żadnych edycji repo przez audytora.
- Brief nie zawiera całego `CURRENT_STATE.md` ani `DECISION_LOG.md`; tylko
  wskazane sekcje (oszczędność tokenów).
- Raport jest zapisywany normalną prozą (reguła dokumentów w `AGENTS.md`).

## Expected files

- Nowe: `.claude/skills/audit-task/SKILL.md`, `.codex/skills/claude-audit/SKILL.md`,
  `scripts/audit_task.ps1`, `ai_docs/quality/AUDIT_REPORT_TEMPLATE.md`.
- Istniejące: `AGENTS.md`.

## Test cases

- Task istniejący, brak CLI → brief zapisany, kod wyjścia 0, komunikat.
- CLI dostępne, audytor zwraca raport → plik raportu, kod 0.
- CLI przekracza limit czasu → kod ≠ 0, częściowy wynik oznaczony.
- Nazwa taska nieistniejąca → błąd walidacji.

## Verification

```powershell
# katalog worktree, timeout 120 s
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/audit_task.ps1 -Task 0930 -Auditor codex -DryRun
```

## Risks / open questions

- Dokładne flagi CLI zależą od zainstalowanych wersji; sprawdzić i zapisać.
- Audyt Claude z aplikacji desktop (bez CLI) pozostaje ręczny.

## Outcome

Wypełnione przez wykonawcę (claude-sonnet-5-5 / high). Status taska i commit
nadaje lead po audycie.

### Changed

- Nowy `scripts/audit_task.ps1` (Windows PowerShell 5.1, plik wyłącznie ASCII,
  CRLF zgodnie z `.gitattributes`). Parametry: `-Task NNNN` (także `TASK-NNNN`),
  `-Auditor codex|claude`, `-Base` (po poprawkach domyślnie `HEAD`, patrz niżej),
  `-Plan`, `-Model`, `-Paths` (pathspec ograniczający diff, dodany ponad
  zakres, bo worktree zawiera zmiany równoległych tasków), `-DryRun`,
  `-TimeoutSec` (domyślnie 480 po audycie, żeby sprzątanie zmieściło się w limicie narzędzia 600 s), `-MaxSectionKB` (domyślnie 300). Brief zawiera
  instrukcję dla audytora, szablon raportu, plik taska, fragmenty planu
  wspominające task wraz z wierszem tabeli modeli, linie `Verification results`
  z `Outcome`, `git diff <base>...HEAD`, `git diff HEAD` oraz treść nowych,
  nieśledzonych plików (nowe pliki taska nie są widoczne w `git diff`). Brief
  trafia do `artifacts/audits/TASK-NNNN_BRIEF_<auditor>.md` (`artifacts/` jest
  ignorowany przez git, sprawdzone `git check-ignore`).
- Każde wywołanie procesu (git, `--version`, `--help`, audytor) idzie przez
  jedną funkcję z limitem czasu; po przekroczeniu limitu drzewo procesów jest
  kończone przez `taskkill /T /F`. UTF-8 jest wymuszony dla konsoli, strumieni
  procesów i plików; prompt do CLI to krótka instrukcja ASCII wskazująca plik
  briefu, więc nie ma kodowania stdin ani limitów długości linii poleceń.
- Raport: surowy wynik audytora trafia do `artifacts/audits/TASK-NNNN_RAW_<model>.md`,
  a do `ai_docs/quality/TASK-NNNN_AUDIT_<model>.md` kopiowany jest dopiero po
  stwierdzeniu wiersza `Werdykt: PASS|REVISE`. Poprzedni raport o tej samej
  nazwie jest zachowywany w `artifacts/audits/`. Timeout zapisuje wynik
  częściowy jako `*.partial.md` z nagłówkiem „PARTIAL RESULT” poza `ai_docs/`.
- Kody wyjścia (stan po rundzie poprawek): 0 brief zapisany lub raport
  zapisany, 1 błąd walidacji (numer, brak taska, brak planu, brak refa
  bazowego, zły `-Model`, metaznak w argumencie dla shima `.cmd`, `-Paths` bez
  dopasowań) albo błąd gita, 2 timeout audytora, 3 błąd lub niewspierane CLI
  (sprawdzenie `--help`) albo timeout gita, 4 raport bez wiersza werdyktu,
  5 nieoczekiwany błąd.
- Polecenia audytora (z dokumentacji CLI, patrz „Not completed”): Codex
  `exec --sandbox read-only --output-last-message <plik> <prompt>`, Claude
  `-p --permission-mode plan <prompt>`; opcjonalnie `--model`.
- Nowy `ai_docs/quality/AUDIT_REPORT_TEMPLATE.md`: format raportu (werdykt,
  audytor, wykonawca, zakres, runda, oświadczenie o przeglądzie statycznym,
  znaleziska P0–P2 z `ścieżka:linia`, pokrycie kryteriów, listy zamknięte i
  otwarte, proponowane testy, ograniczenia) oraz definicje P0/P1/P2 i zasady
  werdyktu.
- Nowe skille `.claude/skills/audit-task/SKILL.md` (`-Auditor codex`) i
  `.codex/skills/claude-audit/SKILL.md` (`-Auditor claude`): jak uruchomić
  skrypt, jak odczytać wynik i kody wyjścia, jedna runda audytu, jedna runda
  poprawek, ponowny audyt tylko na żądanie, bez pętli.
- `AGENTS.md`: nowa sekcja „Audyt krzyżowy” przed „Hierarchia źródeł prawdy”
  (plik zachował zakończenia CRLF).
- Zamiana „Joker” na „Wild”: po korekcie leada historyczne wpisy
  `CURRENT_STATE.md` i `DECISION_LOG.md` pozostają bez zmian (początkowa
  zamiana tam została cofnięta, `git diff` tych plików jest pusty od mojej
  strony). `AGENTS.md`, `AI_DRIVEN_DEVELOPMENT.md`, `DEFINITION_OF_DONE.md`,
  `PLAN_STANDARD.md` i `TASK_TEMPLATE.md` nie zawierają słowa „Joker”
  (grep bez dopasowań), więc nie było czego zamieniać.

### Audyt i runda poprawek

Audyt niezależnego subagenta Claude zwrócił REVISE (2 × P1, 5 × P2). Zastosowano
jedną rundę poprawek:

- P1 `-Paths`: przy `powershell -File` lista po przecinku dociera jako jeden
  napis i dawała puste diffy z kodem 0. Skrypt dzieli każdy element na
  przecinkach i przycina go; gdy podano `-Paths`, a sekcja zacommitowana,
  niezacommitowana i lista plików nieśledzonych są puste, kończy się kodem 1
  z komunikatem. Oba skille mają przykład z kilkoma ścieżkami.
- P1 wstrzykiwanie przez `-Model`/ścieżki w shimach npm: `-Model` musi pasować
  do `^[A-Za-z0-9._:-]{1,64}$` (kod 1 w przeciwnym razie); gdy CLI jest plikiem
  `.cmd`/`.bat`, każdy argument trafiający do CLI (w tym ścieżka repozytorium i
  pliku wyjściowego) jest odrzucany z kodem 1, jeżeli zawiera `"`, `%`, `&`,
  `|`, `<`, `>` lub `^`. Dla `.exe` zostało dotychczasowe cytowanie.
- P2 timeout: skille zalecają timeout narzędzia 600 s i `-TimeoutSec 480`
  (skrypt potrzebuje ok. 25 s po własnym timeoucie na sprzątanie) albo
  uruchomienie w tle; `AGENTS.md` ma jawny wyjątek od limitu 120 s dla audytu.
- P2 sprzeczność w `AGENTS.md`: punkt 8 „Po kodowaniu” mówi teraz o otwartych
  uwagach P0/P1 po jednej rundzie poprawek, a uwagi P2 odnotowane w `Outcome`
  nie zatrzymują (spójnie z sekcją „Audyt krzyżowy”).
- P2 tryb „tylko brief”: skille każą audytorowi zastępczemu uruchomić skrypt z
  `-Model <rzeczywisty model audytora>`, aby raport miał właściwą nazwę.
- P2 domyślny `-Base`: zmieniono na `HEAD` (audyt przed commitem); `-Base <ref>`
  służy do audytu po commicie. Przykłady w skillach używają
  `-Base HEAD -Paths ...`; `AGENTS.md` wspomina nowy domyślny `-Base`.
- P2 kody wyjścia: nagłówek skryptu i oba skille dokumentują, że kod 3 obejmuje
  też timeout polecenia git, a błędy poleceń git dają kod 1.

### Verification results

Katalog uruchomienia: worktree `mumie-super-game`; każda komenda z timeoutem
110 s.

- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/audit_task.ps1 -Task 0930 -Auditor codex -DryRun`:
  kod 0, brief `artifacts/audits/TASK-0930_BRIEF_codex.md` zapisany, komunikat
  „CLI 'codex' not found on PATH: brief-only mode”.
- To samo z `-Auditor claude`: kod 0, brief `TASK-0930_BRIEF_claude.md`,
  komunikat „CLI 'claude' not found on PATH: brief-only mode”.
- `-Task 9999`: kod 1, „task 9999 not found in ai_docs/tasks or
  ai_docs/tasks/completed.”; `-Task abc`: kod 1, „invalid task”; `-Base nope`:
  kod 1, „base ref 'nope' does not exist”.
- `scripts/check_powershell_syntax.ps1`: „PowerShell syntax is valid for 45
  script(s).”; skrypt nie zawiera znaków spoza ASCII.
- Ścieżki z CLI sprawdzone na atrapie `codex.cmd`/`claude.cmd` (PATH
  ograniczony do katalogu w scratchpadzie, atrapa to skrypt PowerShell
  obsługujący `--version`, `--help` i tryby ok/fail/slow/noverdict):
  tryb ok z Codex i Claude (`-Model claude-opus-5-5`) zapisał raport
  `ai_docs/quality/TASK-0930_AUDIT_<model>.md` z polskimi znakami bez
  uszkodzeń i wypisał „Verdict: REVISE”, kod 0; brak wiersza werdyktu: kod 4,
  nic nie trafiło do `ai_docs/quality`; atrapa kończąca się kodem 7: kod 3 z
  ogonem stderr; atrapa śpiąca 60 s przy `-TimeoutSec 15`: kod 2, wynik
  częściowy w `TASK-0930_RAW_codex.partial.md`, brak osieroconych procesów;
  atrapa bez wymaganych flag w `--help`: kod 3. Raporty i briefe z tych prób
  usunięto. To nie jest test z prawdziwymi CLI.
- Po rundzie poprawek (komendy przez `powershell -NoProfile -ExecutionPolicy Bypass -File`, timeout 110 s):
  `-Task 0930 -Auditor codex -DryRun -Base HEAD -Paths apps/admin,ai_docs/tasks/completed/0930-symbol-review-zero-shortcut.md`
  kończy się kodem 1 („-Paths ... matches no changes (HEAD...HEAD, git diff
  HEAD, untracked)”), bo TASK-0930 jest już zacommitowany (b230857b) i przy
  `-Base HEAD` nie ma żadnych zmian; to oczekiwane zachowanie nowej
  walidacji. Ta sama lista z `-Base HEAD~1` daje niepustą sekcję
  „Committed changes (HEAD~1...HEAD)” (5 plików, +166/-17), kod 0, brief 23 KB,
  nagłówek „Diff limited to pathspecs: apps/admin, ai_docs/tasks/completed/...”.
  `-Task 0929 -Auditor claude -DryRun -Base HEAD -Paths AGENTS.md,scripts/audit_task.ps1,ai_docs/quality`
  daje niepustą sekcję niezacommitowaną (AGENTS.md) i kod 0.
  `-Paths does/not/exist`: kod 1 z tym samym komunikatem. `-Model 'bad"x'`: kod 1
  przy wywołaniu bezpośrednim (`& .\scriptsudit_task.ps1`) albo `-File` z
  `bad\"x`; przy `powershell -File` z PowerShell 5.1 cudzysłów nie dociera do
  skryptu i wartość `badx` przechodzi walidację (kod 0). Atrapa `codex.cmd` z
  `-Model gpt-6.1-sol -DryRun`: kod 0; DryRun nic nie zapisuje, tylko wypisuje
  docelową nazwę raportu `TASK-0930_AUDIT_gpt-6.1-sol.md`. Strażnik
  metaznaków `.cmd` sprawdzony przez audytora na repozytorium ze ścieżką
  zawierającą `&`: kod 1, shim niewywołany. `scripts/check_powershell_syntax.ps1`: „PowerShell syntax is valid for
  45 script(s).”; plik nadal bez znaków spoza ASCII.
- Nie uruchamiano `npm run python:lint`: zmiana nie zawiera Pythona (krótkie
  jednorazowe skrypty edycji plików uruchomiono poza repozytorium).

### Not completed

- Kryteria „raport i brief z prawdziwego CLI” oraz „CLI przekracza limit czasu”
  nie były weryfikowane na prawdziwych `codex` i `claude`: żadne nie jest na
  PATH (2026-10-08), więc flagi CLI nie zostały sprawdzone przez `--help` ani
  wersje zapisane. Skrypt przy realnym CLI sam sprawdza obecność flag
  `--sandbox`/`--output-last-message` (Codex `exec --help`) i `--permission-mode`/
  `--print` (Claude `--help`) i kończy się kodem 3, gdy ich brakuje. Po
  instalacji CLI należy uruchomić skrypt bez `-DryRun`, odnotować wersje
  (skrypt wypisuje je w wierszu „Auditor CLI”) i potwierdzić, że Claude w
  trybie `plan` poprawnie czyta plik briefu w katalogu repozytorium.
- Audyt krzyżowy tego taska nie był wykonywany przez wykonawcę; wykonuje go lead.

### Documentation updates

- `AGENTS.md`: sekcja „Audyt krzyżowy”. Nowy dokument
  `ai_docs/quality/AUDIT_REPORT_TEMPLATE.md`. Brak zmian w
  `CURRENT_STATE.md` i `DECISION_LOG.md` (zob. wyżej); status taska tam
  aktualizuje lead po audycie i commicie.
- `AGENTS.md` ma dodatkowo wyjątek timeoutu dla audytu i zmieniony punkt 8 „Po kodowaniu”.
- Do rozważenia przez leada: `ai_docs/README.md` mógłby linkować do szablonu
  raportu; poza oczekiwanymi plikami taska, więc nie zmieniano.

### Audyt końcowy

Ponowny audyt niezależny (claude-opus-5-5 / high, tylko odczyt): PASS, trzy
uwagi P2 naprawione przez leada przed commitem: domyślny `-TimeoutSec` 480,
korekta opisów w tym Outcome (kody wyjścia, DryRun nie zapisuje raportu,
zachowanie `-Model 'bad"x'` zależne od sposobu wywołania), przełamanie długiej
linii w `AGENTS.md`. Raport: `ai_docs/quality/TASK-0929_AUDIT_claude-opus-5-5.md`.
Lead dodał też link do szablonu raportu w `ai_docs/README.md`.

### Recommended next task

TASK-0930 (etap S-0) jest już wykonywany równolegle; po commicie TASK-0929
audyt każdego kolejnego taska można uruchamiać skryptem (z `-Paths`, gdy
worktree zawiera zmiany innych tasków).
