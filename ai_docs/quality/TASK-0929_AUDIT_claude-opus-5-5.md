---
title: TASK-0929 — audyt niezależny (claude-opus-5-5 / high)
status: accepted
last_updated: 2026-10-08
---

# TASK-0929 — audyt: skill audytu krzyżowego i sekcja „Audyt krzyżowy”

Audytor: niezależny subagent claude-opus-5-5 / high, świeży kontekst, tylko
odczyt, atrapy CLI wyłącznie w scratchpadzie (zamiennik audytu Codex do czasu
dostępności CLI, D-535). Zakres: `scripts/audit_task.ps1`, oba `SKILL.md`,
`ai_docs/quality/AUDIT_REPORT_TEMPLATE.md`, `AGENTS.md`, plik taska.

## Runda 1 — werdykt REVISE

1. [P1] `-Paths` z kilkoma wartościami przez `powershell -File` trafiał jako
   jeden napis i dawał pusty brief z kodem 0. Naprawione: podział po
   przecinkach, kod 1 przy braku dopasowań.
2. [P1] Wstrzyknięcie poleceń przez `-Model` i ścieżki przy shimach `.cmd`
   (cmd.exe nie honoruje `\"`). Naprawione: walidacja `-Model` wzorcem,
   odrzucenie metaznaków `"%&|<>^` w argumentach dla `.cmd`/`.bat`.
3. [P2] Timeout skilla niewykonalny w limicie narzędzia 600 s i bez wyjątku
   w `AGENTS.md`. Naprawione: `-TimeoutSec 480`, jawny wyjątek w sekcji.
4. [P2] Sprzeczność punktu 8 „Po kodowaniu” (dwa cykle) z nową sekcją
   (jedna runda). Naprawione: punkt 8 ujednolicony.
5. [P2] Raport audytora zastępczego pod nazwą `_codex.md`. Naprawione:
   skille każą podać `-Model <faktyczny model>`.
6. [P2] Domyślny `-Base` dawał diff całej gałęzi (194 KB). Naprawione:
   domyślnie `HEAD`, przykłady z `-Base HEAD -Paths ...`.
7. [P2] Kod 3 obejmuje też timeout gita; błąd gita daje 1 — niedopisane.
   Naprawione w nagłówku skryptu i skillach.

## Runda 2 — werdykt PASS

Wszystkie siedem uwag zamknięte i potwierdzone testami (atrapy `codex.cmd`,
repozytorium ze ścieżką z `&`, `-Paths` wielokrotne przez `-File`, timeout
bez osieroconych procesów). Trzy uwagi P2 naprawione przez leada przed
commitem: domyślny `-TimeoutSec` 480 zamiast 600; nieaktualne opisy w
Outcome (kody wyjścia, DryRun nie zapisuje raportu, `-Model 'bad"x'` zależne
od sposobu wywołania); linia 89 znaków w `AGENTS.md`.

## Sprawdzone bez uwag

- PowerShell 5.1: brak `&&`, ternary, `??`; ASCII, CRLF; każdy proces z
  limitem czasu i `taskkill /T`; UTF-8 dla konsoli, procesów i plików.
- Brief w ignorowanym `artifacts/audits/`; surowy wynik poza `ai_docs/` do
  czasu wiersza werdyktu; brak path traversal (nazwa raportu oczyszczona).
- Brief nie zawiera całych `CURRENT_STATE.md`/`DECISION_LOG.md`.
- Skille z poprawnym frontmatterem, zgodne ze skryptem; skill Codex jest
  lustrem skilla Claude. Sekcja „Audyt krzyżowy” zgodna z PLAN_STANDARD.md
  i regułą wykonywania etapu.
- Wpisy historyczne `CURRENT_STATE.md`/`DECISION_LOG.md` nietknięte.

## Testy uruchomione przez audytora (runda 2)

- `-Task 0929 -Auditor claude -DryRun -Base HEAD -Paths AGENTS.md,scripts/audit_task.ps1,ai_docs/quality`
  przez `powershell -File`: kod 0, brief 56 KB, diff ograniczony do ścieżek.
- `-Paths does/not/exist`: kod 1. `-Model 'a&b'`: kod 1. Repozytorium ze
  ścieżką z `&` i shim `.cmd`: kod 1, shim niewywołany. Atrapa śpiąca przy
  `-TimeoutSec 10`: kod 2, plik `.partial.md`, brak procesów.
- `scripts/check_powershell_syntax.ps1`: 45 skryptów poprawnych.

Nie testowano prawdziwych CLI `codex` i `claude` (brak na PATH).
Przegląd statyczny, bez zmian plików przez audytora.
