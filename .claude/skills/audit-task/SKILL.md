---
name: audit-task
description: Uruchamia audyt krzyżowy ukończonego taska drugą rodziną modeli (Codex) w trybie tylko do odczytu i zapisuje raport w ai_docs/quality. Użyj po zakończeniu implementacji taska, przed commitem, np. /audit-task 0930.
---

# Audyt krzyżowy taska (Claude Code -> Codex)

Wykonawca (Claude) nie audytuje własnej pracy. Ten skill buduje brief dla
audytora z innej rodziny modeli (Codex) i odbiera jego raport. Zasady procesu
opisuje sekcja „Audyt krzyżowy” w `AGENTS.md`; format raportu definiuje
`ai_docs/quality/AUDIT_REPORT_TEMPLATE.md`.

## Kiedy użyć

Po zakończeniu implementacji i testów taska, przed commitem. Argument: czterocyfrowy
numer taska (`/audit-task 0930`). Nie uruchamiaj skilla w pętli.

## Kroki

1. Upewnij się, że plik taska ma wypełnione `Outcome` (w tym `Verification results`),
   a zmiany taska są w worktree. Zmiany innych tasków w tym samym worktree
   odfiltruj parametrem `-Paths`.
2. Uruchom skrypt z katalogu głównego worktree. Audyt przed commitem (domyślne
   `-Base HEAD`) obejmuje zmiany niezacommitowane i nowe pliki; ogranicz go do
   plików taska parametrem `-Paths`, bo worktree może zawierać zmiany innych
   tasków. Kilka ścieżek podaj po przecinku (`powershell -File` przekazuje je
   jako jeden napis; skrypt dzieli go i przycina):

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/audit_task.ps1 `
     -Task 0930 -Auditor codex -Base HEAD `
     -Paths apps/admin,ai_docs/tasks/0930-symbol-review-zero-shortcut.md `
     -Plan ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md `
     -TimeoutSec 480
   ```

   Narzędzie uruchamiające komendę musi mieć timeout 600 s, a `-TimeoutSec` skryptu
   480 s: po własnym timeoucie skrypt potrzebuje jeszcze ok. 25 s na sprzątanie.
   Alternatywnie uruchom skrypt w tle i monitoruj kod wyjścia. Jeżeli `-Paths` nie
   pasuje do żadnej zmiany, skrypt kończy się kodem 1 (zamiast pustego briefu).

   Inne parametry: `-Base <ref>` dla audytu po commicie (ref sprzed taska, np.
   `-Base HEAD~1` albo `-Base v1.1-vision-lab-hybrid-geometry`),
   `-Model <nazwa>` (np. `gpt-6-astra`; tylko litery, cyfry i `. _ : -`; trafia do
   nazwy raportu), `-Effort low|medium|high` (domyślnie `medium`, szybki audyt;
   `high` tylko gdy tabela planu tego wymaga), `-CodexWindowsSandbox`
   (domyślnie `unelevated`, bo piaskownica `elevated` aplikacji ChatGPT nie
   działa z CLI), `-DryRun` (tylko brief).
3. Odczytaj wynik:
   - Kod 0 i komunikat „Report stored”: otwórz
     `ai_docs/quality/TASK-NNNN_AUDIT_<model>.md` i przeczytaj werdykt.
   - Kod 0 i komunikat „brief-only mode” (brak CLI `codex` w PATH): brief leży w
     `artifacts/audits/TASK-NNNN_BRIEF_codex.md`. Poproś operatora o wklejenie
     go w aplikacji Codex albo użyj niezależnego subagenta Claude (inny model niż wykonawca)
     (zasada zastępcza z `AGENTS.md`). Audytor zastępczy uruchamia skrypt z
     `-Model <rzeczywisty model audytora>` (np. `-Model claude-opus-5-5`), aby
     raport nazywał się `TASK-NNNN_AUDIT_<ten model>.md`, a nie `_codex.md`.
   - Kody wyjścia: 1 błąd walidacji (numer, brak taska, plan, ref, `-Model`,
     niebezpieczny argument dla powłoki `.cmd`, `-Paths` bez zmian) lub błąd
     polecenia git; 2 timeout audytora (wynik częściowy w `artifacts/audits`,
     to nie werdykt); 3 błąd lub niewspierane CLI albo timeout polecenia git;
     4 raport bez wiersza `Werdykt:`. Nie ponawiaj w pętli; zgłoś operatorowi
     przyczynę z komunikatu skryptu.
4. Przeczytaj raport w całości. `Werdykt: REVISE` albo otwarte P0/P1 blokują commit.

## Jedna runda poprawek

- Napraw wszystkie P0/P1, a P2 napraw albo odnotuj w `Outcome` jako zaakceptowane
  ryzyko z uzasadnieniem. Dopisz do `Outcome` odnośnik do raportu.
- Ponowny audyt wykonaj tylko na prośbę operatora albo gdy poprawka zmieniła
  zachowanie objęte P0/P1; uruchom skrypt ponownie (poprzedni raport zostaje
  zachowany w `artifacts/audits/`) i oznacz w raporcie `Runda: 2`.
- Gdy po poprawkach nadal istnieje otwarte P0/P1, zatrzymaj task i zgłoś to
  operatorowi. Nie uruchamiaj kolejnych rund automatycznie.

## Ograniczenia

- Audytor działa tylko do odczytu; nie proś go o edycję plików.
- Brief nie zawiera całego `CURRENT_STATE.md` ani `DECISION_LOG.md`.
- Raport jest dokumentem repozytorium: commituj go razem z taskiem.
