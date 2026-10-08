# TASK-0929 — Skill audytu krzyżowego i sekcja „Audyt krzyżowy” w AGENTS.md

## Status

`todo`

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

- [ ] `scripts/audit_task.ps1 -Task 0930 -Auditor codex` tworzy brief i raport
      albo, bez CLI, sam brief z czytelnym komunikatem.
- [ ] Ten sam skrypt z `-Auditor claude` działa lustrzanie.
- [ ] Raport ma wymagany format i trafia do `ai_docs/quality/`.
- [ ] `AGENTS.md` zawiera sekcję „Audyt krzyżowy” spójną z PLAN_STANDARD.md.
- [ ] Skrypt ma limit czasu i kończy się kodem ≠ 0 przy błędzie CLI.

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

Wypełnia agent po pracy.

### Changed

### Verification results

### Not completed

### Documentation updates

### Recommended next task
