---
name: claude-audit
description: Uruchamia audyt krzyżowy ukończonego taska drugą rodziną modeli (Claude) w trybie tylko do odczytu i zapisuje raport w ai_docs/quality. Użyj po zakończeniu implementacji taska w Codex, przed commitem, np. claude-audit 0930.
---

# Audyt krzyżowy taska (Codex -> Claude)

Wykonawca (Codex) nie audytuje własnej pracy. Ten skill buduje brief dla
audytora z innej rodziny modeli (Claude) i odbiera jego raport. Regułę wiążącą
zawiera sekcja „Audyt krzyżowy” w `AGENTS.md`; skill opisuje szczegóły i jej
nie osłabia. Format raportu definiuje `ai_docs/quality/AUDIT_REPORT_TEMPLATE.md`.
Parametry Codex CLI (kierunek odwrotny) opisuje
`.claude/skills/audit-task/SKILL.md`. Skill jest lustrem
`.claude/skills/audit-task/SKILL.md` i używa tego samego skryptu z
`-Auditor claude`.

## Kiedy użyć

Po zakończeniu implementacji i testów taska w Codex, przed commitem, gdy
kolumna `Dodatkowy review` planu wymaga audytu. Argument: czterocyfrowy
numer taska (np. 0930). Nie uruchamiaj skilla w pętli.

## Zasady (z `AGENTS.md`, „Audyt krzyżowy”)

- Audyt jest wymagany tylko po tasku, który wskazuje go w kolumnie
  `Dodatkowy review` zaakceptowanego planu, przed commitem. Operator może z
  niego zrezygnować dla planu lub taska (np. 2026-10-16); rezygnację zapisz w
  `Outcome`.
- Zmiany taska audytuje model z innej rodziny niż wykonawca: pracę Claude
  audytuje Codex, a pracę Codex audytuje Claude. Wykonawca nie audytuje własnej
  pracy.
- Audytor zastępczy: dopóki oba CLI (`codex`, `claude`) nie są zainstalowane i
  zalogowane przez operatora, audytorem jest niezależny subagent Claude z innym
  modelem niż wykonawca, w świeżym kontekście i wyłącznie do odczytu. Zastępstwo
  odnotuj jawnie w `Outcome`; musi być zgodne z kolumną `Dodatkowy review`
  planu. Brak dostępnego modelu zatrzymuje task zgodnie z
  `ai_docs/process/PLAN_STANDARD.md`.
- Brief buduje `scripts/audit_task.ps1`: plik taska, fragment planu,
  `git diff <base>...HEAD` wraz ze zmianami niezacommitowanymi (domyślnie
  `-Base HEAD`, czyli audyt przed commitem; `-Paths` ogranicza diff do plików
  taska) i linie weryfikacji z `Outcome`. Brief leży w `artifacts/audits/`
  (katalog ignorowany przez git). Gdy CLI audytora jest dostępne, skrypt
  uruchamia je tylko do odczytu z limitem czasu; bez CLI kończy się na briefie,
  a audyt wykonuje się ręcznie lub zastępczym subagentem.
- Audytor nie zmienia plików. Przegląd jest statyczny: ocenia zgodność z
  zakresem, kryteriami akceptacji, planem i regułami `AGENTS.md`, nie rozszerza
  zakresu.
- Domyślny audyt jest szybki (decyzja operatora 2026-10-09): `gpt-6-astra` (audytor Codex) na
  poziomie `medium` (`high` tylko dla tasków zmieniających schemat bazy,
  migracje, wypłaty albo dane dowodowe), brief ograniczony `-Paths` do plików
  taska, raport skupiony na P0 i P1, najwyżej pięć najważniejszych uwag P2.
  Audytor zastępczy Claude stosuje ten sam zakres i poziom `medium`, chyba że
  tabela planu wymaga `high`. Brak odpowiedzi audytora w limicie czasu nie
  zatrzymuje taska, tylko jest odnotowany w `Outcome`.
- Limit czasu: wyjątek od domyślnych 120 s z `AGENTS.md`. Narzędzie
  uruchamiające audyt może mieć timeout do 600 s, a własny `-TimeoutSec`
  skryptu musi być niższy (zalecane 480 s, bo po jego upływie skrypt potrzebuje
  jeszcze około 25 s na sprzątanie). Alternatywnie uruchom skrypt jako
  kontrolowany proces w tle i monitoruj go.
- Raport leży w `ai_docs/quality/TASK-NNNN_AUDIT_<model>.md`, jest pisany
  normalną prozą po polsku w formacie `ai_docs/quality/AUDIT_REPORT_TEMPLATE.md`:
  werdykt `PASS` albo `REVISE`, znaleziska P0–P2 z `plik:linia`, listy
  zamkniętych i otwartych uwag, proponowane testy oraz oświadczenie „przegląd
  statyczny, bez zmian w plikach”. Raport wchodzi do commita taska.
- Po commicie taska lead dopisuje wersję i pełny hash commita do
  `CURRENT_STATE.md` i `Outcome` (skill `task-close`, `record-hash`); audytor
  sprawdza obecność tego zapisu.
- Poświadczeń CLI nie wpisuje agent: instalację i logowanie wykonuje operator.
- Dostęp do Claude Code CLI (trwałe ustalenie 2026-10-14): operator używa
  lokalnego Claude Code CLI. Brak `claude` w `PATH` nie oznacza braku instalacji
  ani problemu z siecią lub logowaniem. `scripts/audit_task.ps1` wykrywa także
  `.local/bin/claude.exe` i instalacje `Claude/claude-code/<wersja>/<build>` w
  profilu użytkownika, w tym fizyczny katalog pakietu Windows
  `AppData/Local/Packages/Claude_*/LocalCache/Roaming/Claude/claude-code`.
  Korzystaj z tego wykrywania przed zgłoszeniem niedostępności audytora. Ścieżka
  `AppData/Roaming` raportowana przez działający proces może być wirtualna; nie
  utrwalaj numeru wersji, builda ani PID. Sprawdzenie `--version` z limitem
  czasu potwierdza uruchomienie CLI, ale nie logowanie ani wykonanie audytu. Nie
  proponuj ponownej instalacji wyłącznie na podstawie `Get-Command`.

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
     -Task 0930 -Auditor claude -Base HEAD `
     -Paths apps/admin,ai_docs/tasks/0930-symbol-review-zero-shortcut.md `
     -Plan ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md `
     -TimeoutSec 480
   ```

   Narzędzie uruchamiające komendę musi mieć timeout 600 s, a `-TimeoutSec` skryptu
   480 s: po własnym timeoucie skrypt potrzebuje jeszcze ok. 25 s na sprzątanie.
   Alternatywnie uruchom skrypt w tle i monitoruj kod wyjścia. Jeżeli `-Paths` nie
   pasuje do żadnej zmiany, skrypt kończy się kodem 1 (zamiast pustego briefu).

   Inne parametry: `-Base <ref>` dla audytu po commicie (ref sprzed taska, np.
   `-Base HEAD~1` albo `-Base main`),
   `-Model <nazwa>` (np. `claude-opus-5-5`; tylko litery, cyfry i `. _ : -`; trafia do
   nazwy raportu), `-DryRun` (tylko brief).

3. Odczytaj wynik:
   - Kod 0 i komunikat „Report stored”: otwórz
     `ai_docs/quality/TASK-NNNN_AUDIT_<model>.md` i przeczytaj werdykt.
   - Skrypt szuka CLI najpierw w PATH, następnie w natywnej instalacji użytkownika
     i fizycznym katalogu pakietu Windows `Claude_*/LocalCache/Roaming/Claude/claude-code`.
     Nie utrwalaj wersji ani builda; brak wyniku `Get-Command claude` nie oznacza
     braku instalacji. `--version` potwierdza start CLI, nie stan logowania.
   - Kod 0 i komunikat „brief-only mode” (CLI niewykryte w obsługiwanych lokalizacjach): brief leży w
     `artifacts/audits/TASK-NNNN_BRIEF_claude.md`. Poproś operatora o wklejenie
     go w aplikacji Claude albo użyj niezależnego audytora Claude (inny model niż wykonawca)
     (zasada zastępcza z `AGENTS.md`). Audytor zastępczy uruchamia skrypt z
     `-Model <rzeczywisty model audytora>` (np. `-Model claude-opus-5-5`), aby
     raport nazywał się `TASK-NNNN_AUDIT_<ten model>.md`, a nie `_claude.md`.
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
