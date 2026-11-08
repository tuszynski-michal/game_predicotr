---
name: claude-audit
description: Uruchamia niezależny audyt taska przez Claude, tylko do odczytu, z trwałym receipt i walidacją raportu przed commitem.
---

# Audyt krzyżowy taska (Codex → Claude)

Stosuj po implementacji i testach, gdy tabela zaakceptowanego planu wymaga
niezależnego review. Argument: numer taska, np. 1163. Wykonawca nie audytuje
własnej pracy. Reguły nadrzędne: `AGENTS.md`, sekcja „Audyt krzyżowy”.

Jedynym opisem transportu, stanu sesji, retry i importu Desktop jest
[ai_docs/process/CROSS_AUDIT.md](../../../ai_docs/process/CROSS_AUDIT.md).
Przeczytaj go przed uruchomieniem. Raport ma używać całego szablonu
`ai_docs/quality/AUDIT_REPORT_TEMPLATE.md`; zawiera jawne liczniki otwartych
P0/P1, task, rundę i SHA pakietu. Receipt jest częścią dowodu audytu.

1. Uzupełnij `Outcome` taska i weryfikację. Ustal zakres `-Paths` bez cudzych
   zmian. Sprawdź model/effort w tabeli planu oraz zgodę na przekazanie pakietu.
2. Z katalogu worktree przygotuj brief przez `scripts/audit_task.ps1 -DryRun`.
   `Resolve-AuditorCli` wykrywa także instalacje poza PATH; brak PATH nie jest
   diagnozą braku instalacji. DryRun nie uruchamia audytora ani auth.
3. Po sprawdzeniu briefu uruchom jedną próbę bez `-DryRun`, np.:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/audit_task.ps1 `
     -Task 1163 -Auditor claude -Model claude-opus-5-5 -Effort high -Base HEAD `
     -Paths scripts/run_claude_audit.py,scripts/audit_task.ps1,scripts/tests `
     -Plan ai_docs/delivery/FULL_SYMBOL_CROPS_PLAN_20261108.md `
     -Python D:/game_predicotr/.venv/Scripts/python.exe -TimeoutSec 1800
   ```

   Zastąp scope przykładu rzeczywistymi plikami taska. Host może mieć limit
   1860 s. Runner ma limit1800s/idle60s (decyzja operatora 2026-11-08),
   Read/Glob/Grep bez MCP i prompt na stdin.
   Nie zmieniaj ustawień konta, `setting-sources`, auth ani poświadczeń.
4. Odczytaj raport i sąsiedni `.receipt.json`; dopasuj SHA do pakietu.
   `REVISE` lub otwarte P0/P1 blokują commit. Brak raportu, timeout, OAuth
   i rate-limit nie są PASS. Nie ponawiaj automatycznie. Stan CLI i Desktop
   jest niezależny; działającą sesję Desktop można wykorzystać wyłącznie
   z jawnym importem i zaobserwowanymi metadanymi według wspólnej procedury.
5. Napraw P0/P1 w jednej rundzie, P2 napraw lub odnotuj z ryzykiem w Outcome.
   Focused review po zmienionym zachowaniu lub na prośbę operatora używa
   `-ReviewRound 2`; jawna nowa próba nieukończonego transportu używa
   `-TransportAttempt 2` i nie udaje nowej rundy review. Otwarte P0/P1 po
   jednej rundzie poprawek zatrzymują task. Nie twórz pętli audytów.
6. Zachowaj raport i metadane w commicie taska. Zamknięcie i zapis hasha
   prowadzi skill `task-close`. Sam kod0 nie dowodzi PASS; odczytaj werdykt.

Brak dostępnego wymaganego audytora wymaga jawnego odnotowania; dopuszczalny
zamiennik musi być zgodny z planem i regułami `AGENTS.md`. Nie zastępuj
niezależnego raportu opinią wykonawcy ani deklaracją wybranego modelu.
