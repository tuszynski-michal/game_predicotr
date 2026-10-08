# TASK-0939 — Narzędzia oszczędzania tokenów z pomiarem (mapa kodu, Serena, Graphify, hook)

## Status

`todo`

## Goal

Zestaw narzędzi nawigacji po repozytorium i reguł pracy, który mierzalnie
obniża tokeny wejścia typowych zadań bez spadku jakości wyniku; do stałego
użytku wchodzi tylko to, co pomiar potwierdził.

## Context

Operator chce oszczędzać tokeny, ale nie kosztem jakości. Dzisiejsze koszty:
pełne odczyty dużych plików, powtarzane wyszukiwania tego samego miejsca w
kodzie, briefy z całymi dokumentami procesu. Plan: etap T.

## Dependencies / entry conditions

- TASK-0938 niewymagany, ale zalecany wcześniej (największy koszt).
- Fakt: w repo nie ma skilli w `.claude/skills` ani `.codex/skills`; Serena
  i Graphify nie są zainstalowane. Instalacja w izolacji: osobny venv
  (`.tooling/venv-tokens`, ignorowany) i katalog wyników ignorowany.
- Założenie: dane producentów (Graphify „71,5×”, Serena „znacznie”) są
  nieweryfikowane; liczy się pomiar na tym repo.

## Recommended execution

claude-sonnet-5-5 / high. Konfiguracja narzędzi, hook, skrypt mapy kodu i
protokół pomiaru; brak logiki domenowej. Eskalacja do claude-opus-5-5 / high,
jeżeli hook lub MCP destabilizują sesję. Audyt: gpt-6.1-sol / high.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`

## Scope

1. **Mapa kodu** `ai_docs/architecture/CODE_MAP.md` generowana skryptem
   `scripts/generate_code_map.py` (proponowany): obszar funkcjonalny →
   katalogi, kluczowe moduły i symbole, testy, komendy. Skrypt jest
   deterministyczny i uruchamiany po zmianach struktury; `AGENTS.md`
   wskazuje mapę jako pierwsze miejsce szukania.
2. **Serena MCP** (narzędzia symbolowe `find_symbol`,
   `find_referencing_symbols`): konfiguracja projektu dla Pythona i TS,
   indeks wstępny, wpis w ustawieniach projektu z instrukcją włączenia.
3. **Graphify**: instalacja w osobnym venv, graf repo do katalogu
   ignorowanego, eksport Obsidian; ocena użyteczności raportu grafu.
4. **Hook `PreToolUse`** w `.claude/settings.json`: odrzuca `Read` pliku
   > 200 KB bez `offset`/`limit` z komunikatem wskazującym mapę i grep.
5. **Reguły w `AGENTS.md`**: eksploracja subagentem na tańszym modelu z
   wynikiem w formie wniosków; briefy audytu tylko z taskiem, planem i
   diffem; zakaz wklejania całych dokumentów procesu do promptów.
6. **Pomiar**: trzy typowe zadania (lokalizacja miejsca zmiany w Adminie,
   zmiana domeny w API z testem, analiza błędu w workerze) wykonane
   przed/po na tym samym modelu; metryki: tokeny wejścia sesji, liczba
   odczytów plików, czas, ocena jakości wyniku przez audytora (PASS/REVISE).
   Raport `ai_docs/quality/TOKEN_TOOLING_PILOT_<data>.md`.

## Out of scope

- Zmiana stylu komunikacji (caveman) — pozostaje `lite`.
- Zmiany w kodzie produktu.

## Acceptance criteria

- [ ] Mapa kodu generuje się deterministycznie i jest zlinkowana w `AGENTS.md`.
- [ ] Hook blokuje duży odczyt bez zakresu i nie blokuje odczytu z zakresem.
- [ ] Raport pomiaru z liczbami dla każdego narzędzia i decyzją
      „zostaje / wypada”; narzędzie wchodzi do `AGENTS.md` tylko po „zostaje”.
- [ ] Instalacje nie dotykają `.venv` projektu ani `package.json`.

## Expected files

- Nowe: `scripts/generate_code_map.py`, `ai_docs/architecture/CODE_MAP.md`,
  `ai_docs/quality/TOKEN_TOOLING_PILOT_<data>.md`, wpisy w
  `.claude/settings.json` (hook), konfiguracja Serena w projekcie.
- Istniejące: `AGENTS.md`, `.gitignore` (katalogi narzędzi).

## Verification

```powershell
# katalog worktree, timeout 120 s
.\.venv\Scripts\python.exe scripts/generate_code_map.py --check
```

## Risks / open questions

- MCP zwiększa stały koszt kontekstu (definicje narzędzi) — uwzględnić w
  pomiarze; jeśli przewyższa zysk, narzędzie wypada.
- Graphify przetwarza dokumenty przez model (koszt budowy grafu) — kod
  lokalnie; ograniczyć do kodu.

## Outcome

Wypełnia agent po pracy.

### Changed

### Verification results

### Not completed

### Documentation updates

### Recommended next task
