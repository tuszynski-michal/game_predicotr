---
name: audit-task
description: Uruchamia niezależny audyt taska przez Codex, tylko do odczytu, i zapisuje raport przed commitem.
---

# Audyt krzyżowy taska (Claude Code → Codex)

Stosuj po implementacji i testach, gdy tabela zaakceptowanego planu wymaga
niezależnego review. Argument: numer taska, np. 1163. Wykonawca nie audytuje
własnej pracy. Reguły nadrzędne: `AGENTS.md`, sekcja „Audyt krzyżowy”.
Format raportu: `ai_docs/quality/AUDIT_REPORT_TEMPLATE.md`.

Wspólny opis przygotowania pakietu, zasad werdyktu i metadanych jest w
[ai_docs/process/CROSS_AUDIT.md](../../../ai_docs/process/CROSS_AUDIT.md).
Jego część Claude/receipts/import Desktop dotyczy odwrotnego kierunku,
opisanego w `.codex/skills/claude-audit/SKILL.md`. Ścieżka Codex w
`scripts/audit_task.ps1` zachowuje dotychczasowy transport; nie deklaruj dla
niej nowej walidacji receipt ani sprawdzania `system.init`.

1. Uzupełnij `Outcome` i weryfikację taska. Sprawdź model/effort w planie oraz
   niezależną rodzinę modelu audytora. Ogranicz `-Paths` do zmian taska.
2. Uruchom z katalogu worktree (scope i plan są przykładami do dostosowania):

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/audit_task.ps1 `
     -Task 1163 -Auditor codex -Model gpt-6-astra -Effort medium -Base HEAD `
     -Paths scripts/run_claude_audit.py,scripts/audit_task.ps1,scripts/tests `
     -Plan ai_docs/delivery/FULL_SYMBOL_CROPS_PLAN_20261108.md -TimeoutSec 480
   ```

   `-DryRun` tylko przygotowuje brief. `-Base` domyślnie HEAD obejmuje zmiany
   niezacommitowane i nowe pliki; po commicie wskaż ref sprzed taska. Pusta
   lista zmian dla podanego `-Paths` jest błędem, nie pustym audytem.
3. Host ma limit do600s, audyt do480s. Codex CLI pracuje z `exec --sandbox
   read-only --output-last-message`, przez `node.exe` i `codex.js`, gdy shim
   `.cmd` nie przenosi cudzysłowów. Domyślne nadpisanie Windows sandbox to
   `unelevated`; `-CodexWindowsSandbox none` pozostawia konfigurację operatora.
   Domyślny effort to medium; plan może wymagać high. Nie wpisuj poświadczeń.
4. Przeczytaj cały raport `ai_docs/quality/TASK-NNNN_AUDIT_<model>.md`.
   Sprawdź zgodność werdyktu, jawnych liczników, taska i zakresu. Kod0 może
   oznaczać również sam brief przy braku Codex CLI; nie oznacza wtedy audytu.
   Błąd, timeout i brak raportu nie są PASS. Zastępstwo wymaga rzeczywiście
   niezależnego modelu zgodnego z planem i jawnego wpisu w Outcome.
5. P0/P1 blokują commit. Napraw je w jednej rundzie; P2 napraw lub odnotuj
   ryzyko w Outcome. Focused review uruchom wyłącznie na prośbę operatora lub
   po zmianie zachowania objętego P0/P1. Nie uruchamiaj pętli; po jednej
   rundzie poprawek z nadal otwartymi P0/P1 zatrzymaj task.
6. Raport zachowaj w commicie. Skill `task-close` prowadzi zamknięcie i hash.

Kody dotychczasowej ścieżki Codex: 1 walidacja/git; 2 timeout; 3 CLI lub timeout
polecenia git; 4 brak werdyktu; 5 błąd wewnętrzny. Sprawdzenie wersji CLI
potwierdza jedynie jego start. Nie proś audytora o uruchamianie usług ani testów
zapisujących dane; przegląd jest statyczny i tylko do odczytu.
