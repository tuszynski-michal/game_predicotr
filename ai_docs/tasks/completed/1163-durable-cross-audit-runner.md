---
title: Trwała procedura audytu krzyżowego
status: done
last_updated: 2026-11-08
---

# TASK-1163 — Trwała procedura audytu krzyżowego

## Status

`done`

## Goal

Jeden wersjonowany, ograniczony runner audytu z prawdziwym werdyktem,
diagnostyką niezależnych sesji i ochroną przed duplikatem.

## Context

Sprawdzony runner został w ignorowanym archiwum; istniejący skrypt nie
zachowuje stdout błędu i nie weryfikuje rzeczywistego modelu. Auth CLI
błędnie utożsamiano z logowaniem Desktop.

## Dependencies / entry conditions

Plan FULL_SYMBOL_CROPS_PLAN_20261108 T0 zlecony w całości; koszt8–12h
zaakceptowany. Przekazanie scoped kodu/docs do Anthropic zatwierdzone.
Opus rate limit nie blokuje zależnej implementacji (polecenie operatora),
ale oczekujący audyt nie jest PASS i nie zamyka taska.

## Recommended execution

gpt-6.1-sol/high; audyt Claude Code claude-opus-5-5/high. Brak modelu lub
niejasny stan własnego procesu wymaga jawnej blokady zamiast zastępstwa.

## Relevant docs

- AGENTS.md
- ai_docs/delivery/FULL_SYMBOL_CROPS_PLAN_20261108.md (T0)
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/process/CROSS_AUDIT.md
- ai_docs/quality/AUDIT_REPORT_TEMPLATE.md
- .codex/skills/claude-audit/SKILL.md
- .claude/skills/audit-task/SKILL.md
- .agents/skills/task-close/SKILL.md
- ai_docs/architecture/CODE_MAP.md
- Root artifact: artifacts/full-board-rollout-20261106/worktree-evidence/audits/run_scoped_opus_audit.py (ostatni skuteczny transport; nie źródło wersjonowane)

## Scope

Istniejący audit_task.ps1 pozostaje wejściem i zachowuje brief/Codex.
Nowy proponowany scripts/run_claude_audit.py: stdlib, read-only Claude stream,
receipts/hash/lock, wynik i diagnostyka auth/rate/timeout/model/verdict.
Import raportu z Desktop jawnie rozróżnia źródło dowodu model/effort.
Spójne skille i odsyłacz AGENTS; bez poświadczeń i zmian konfiguracji operatora.

## Out of scope

Geometria, bazy operatora, logowanie/instalowanie CLI, usługi i merge.

## Acceptance criteria

- [x] Terminal wykrywa CLI dynamicznie; bezpieczny read-only scope i brak MCP.
- [x] Auth CLI nie oznacza wylogowania Desktop; brak automatycznej pętli retry.
- [x] Stream aktywność, limit480s, własny PID i zatrzymanie wyłącznie własnego drzewa.
- [x] Idempotencja po utracie odpowiedzi i restart; aktywny duplikat odrzucony.
- [x] Zweryfikowany główny model, jawne effort i transport, SHA pakietu i raportu.
- [x] PASS wymaga kompletnego raportu bez otwartych P0/P1; błąd nie publikuje PASS.
- [x] Test w nowym procesie i innym worktree, bez rzeczywistego płatnego wywołania.
- [ ] Skille i startup wskazują pojedynczą procedurę, audyt Opus i docs/map PASS.

## Technical notes

Modele pomocnicze w modelUsage nie są modelem głównym. Po błędzie zachować
stan i ograniczoną diagnozę bez wypisywania sekretów. Zakończone byte-identical
żądanie odtwarza raport; aktywne nie uruchamia drugiego procesu. Przerwane/
zablokowane wymaga jawnego nowego wywołania, nie wewnętrznej pętli.
Raport Desktop przechodzi ten sam walidator, źródło dowodu jest obserwacją UI.
Założenie techniczne: tożsamość żądania obejmuje bajty briefu, task, model,
effort i rundę; jawny numer transportu pozostaje poza tą tożsamością.
Blokada systemowa obejmuje całe wywołanie, a completion jest zapisane przed
publikacją raportu. Przygotowanie briefu nie zawiera zmiennej daty generacji.
Nie obiecywać, że kod zapobiegnie wygaśnięciu zewnętrznego OAuth.

## Expected files

- Istniejące: scripts/audit_task.ps1 (transport Claude), scripts/tests/test_auditor_cli.ps1.
- Nowe proponowane: scripts/run_claude_audit.py i scripts/tests/test_claude_audit_runner.py.
- Skille audytu i ich kontrolowane kopie, AGENTS.md, dokumentacja taska/planu.

## Test cases

Fake CLI w nowym procesie: PASS/REVISE, niezgodny model, pomocniczy model,
is_error/expired OAuth/rate limit, brak result, sprzeczny verdict, otwarteP1,
timeout i duplikat, replay po restarcie, import Desktop i zmieniony payload.

## Verification

Wymagany cwd: `D:/game_predicotr/worktrees/full-symbol-crops`.
Najpierw `Set-Location 'D:/game_predicotr/worktrees/full-symbol-crops'`.
Root `.venv/Scripts/python.exe -m pytest -q scripts/tests/test_claude_audit_runner.py`
uruchamiać sekwencyjnie z selekcjami sześciu grup zapisanymi w
`ai_docs/quality/TASK-1163_TEST_RESULTS.json` (każda timeout120s).
Nie deklarujemy działania bezpośrednich importów testowych z innego cwd.
PowerShell scripts/tests/test_auditor_cli.ps1 (timeout60s).
docs:check i code-map:check (timeout120s). Realny audyt tylko po scoped briefie,
timeout480s/host600s, jedna runda poprawek zgodnie ze skillem.

## Risks / open questions

2026-11-08: zablokowany Windows zatrzymał przekazanie focusedR2 przez UI.
Operator wybrał dalsze audyty wyłącznie terminalowo, sam wykonał auth login
--claudeai; nowy proces potwierdził loggedIn:true/authMethod:claude.ai.
Nie kopiowano tokenów ani nie sterowano logowaniem. FocusedR2 wykonano
terminalowo: PASS, otwarteP0=0/P1=0; model potwierdzony przez system.init.

OAuth może nadal wygasać. Desktop fallback wymaga faktycznego działającego
modelu, nie przyjmuje deklaracji wykonawcy jako niezależnego audytu.

## Outcome

Commit: v1.7.572 / `32db23e3e3e0ad8a349702a7c5b309ad9c3432ab`.

### Changed

- Dodano `scripts/run_claude_audit.py`: stdlib, prompt stdin, read-only
  Read/Glob/Grep bez MCP, total480s/idle60s według zdarzeń streamu.
- Dodano blokadę systemową, atomowe receipts i SHA pakietu/żądania/raportu,
  historię jawnych prób, replay po restarcie i utracie publikacji.
- Windows job kill-on-close obejmuje tylko własnego audytora i potomków;
  ponowne użycie PID rozpoznaje czas utworzenia procesu.
- Walidacja wymaga głównego system.init.model, poprawnego exit/result/is_error,
  pełnego raportu, zgodnej rundy/SHA i liczników/list otwartych P0/P1.
- Desktop import używa tego samego walidatora i jawnie zapisuje obserwację
  UI; CLI effort pozostaje żądany, bez udawanego dowodu backendowego.
- audit_task.ps1 zachowuje builder i Codex, deleguje Claude do wspólnego
  runnera, generuje deterministyczny brief i obsługuje jawny import/retry.
- Jedyna runda poprawek R1: zgodny jednowierszowy kontrakt Zamknięte w
  szablonie/prompcie, blokada zamykania w rundzie1 i nakładania list, jawne
  identyfikatory P0/P1, diagnoza auth tylko z błędu, kod1 dla złych argumentów
  oraz preflight importu z UTF8-BOM bez zużywania próby przy literówce.
- Procedura/skille/AGENTS wskazują jednego właściciela; szablon zawiera
  jawne liczniki i SHA. Testy nie wywołują płatnego API ani operatorgit.

### Verification results

- FakeCLI scenariusze w izolowanym git worktree i nowych procesach:
  przed R1:21przypadków; po ostatnich bajtach poprawek R1:34/34PASS w6grupach
  sekwencyjnych, w tym cały pierwotny zakres21 i13regresji audytu.
  SHA5plików kodu/szablonu i wyniki: artifacts/audits/TASK-1163_R2_VERIFICATION.json.
- PowerShell test_auditor_cli.ps1: PASS, 13 asercji wykrywania i regresji Codex.
- Ruff check/format: PASS; mypy obu nowych plików: PASS.
- Dwa DryRun: identyczny SHA briefu, prawidłowy wiersz modeli T0, bez CLI.
- Dwukrotna pełna paczka przekroczyła120s bez końcowego wyniku; zachowano
  pełne pokrycie21przypadków w grupach. Po obu timeoutach brak własnych
  osieroconych audytorów potwierdzony przez PID i czas utworzenia.
- docs:check oraz code-map generate/check: PASS.
- Szczegóły i końcowe docs/map: `ai_docs/quality/TASK-1163_VERIFICATION.md`.
- Rzeczywisty Opus5.5/high: R1DesktopREVISE zachowany z receipt, focusedR2
  przez zalogowane CLI PASS, brak otwartychP0/P1. Raport i główny model:
  `ai_docs/quality/TASK-1163_AUDIT_claude-opus-5-5.md` oraz .receipt.json.
  SHA pakietuR2 bef9a747b56c9cbb0deb3002600f52f2c1ee201a24ce1e024e957f4962fb3520.

### Not completed

- ResidualP2-1 przyjęty przez wykonawcę: wewnętrznie sprzeczny raportR2
  z numerowanym zamkniętym i dodatkowym nienumerowanym znaleziskiem może
  przejść automat. Obowiązkowy pełny odczyt raportu przed commitem pozostaje
  dodatkową kontrolą; sam kod0 ani liczniki nie oznaczają zgody na commit.
- P2-6 ograniczony dokumentacyjnie: komendy testów wymagają jawnego cwd
  worktree. Nie poprawiano importu ani nie deklarowano jego niezależności
  od cwd; testy procesowe i izolowany worktree mają rzeczywiste wyniki.
- Wskazówki wrappera o imporcie Desktop nie upoważniają do jego użycia;
  zgodnie z nowym poleceniem operatora wymaga osobnego jawnego wyboru.
- Bez migracji operatora, usług, treningu, aktywacji, merge i push.

### Documentation updates

- Nowy właściciel `ai_docs/process/CROSS_AUDIT.md`; krótkie odsyłacze w AGENTS
  i skillach obu kierunków audytu, z zachowaniem odrębnej ścieżki Codex.
- Szablon raportu zawiera SHA pakietu i liczniki otwartych P0/P1.
- Plan/rejestr/DOC_INDEX utrzymuje koordynator; mapa kodu regenerowana.

### Recommended next task

TASK-1164 / T1.
