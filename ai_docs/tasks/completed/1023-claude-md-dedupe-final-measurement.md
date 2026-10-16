# TASK-1023 — `CLAUDE.md` bez duplikatu `AGENTS.md` i końcowy pomiar

## Status

`done`

## Goal

`CLAUDE.md` ma najwyżej 6 000 B i zawiera tylko treść specyficzną dla Claude
Code plus odesłanie do `AGENTS.md`; budżet sumy obowiązkowego odczytu
(90 000 B) jest włączony, a końcowy pomiar zamyka plan.

## Context

Plan `ai_docs/delivery/STARTUP_READ_DIET_EXECUTION_PLAN_20261016.md`, etap C,
decyzje D2, D3, D8. Claude Code ładuje `CLAUDE.md` (8 392 B) automatycznie w
każdej sesji, a sekcja „Mandatory process rules” streszcza reguły, które
agent i tak czyta w `AGENTS.md`. Streszczenia rozjeżdżają się z czasem
(np. opis odczytu `CURRENT_STATE.md` i `DECISION_LOG.md` sprzed TASK-0938).

## Dependencies / entry conditions

- TASK-1022 ukończony.

## Recommended execution

claude-sonnet-5-5 / medium. Krótka zmiana instrukcji i włączenie budżetów;
ryzyko w pominięciu reguły potrzebnej Claude przed odczytem `AGENTS.md`.
Bez audytu Codex (decyzja operatora
2026-10-16); wykonawca robi samokontrolę kryteriów akceptacji i zapisuje ją w
`Outcome`.

## Relevant docs

- `CLAUDE.md`, `AGENTS.md`
- `ai_docs/delivery/STARTUP_READ_DIET_EXECUTION_PLAN_20261016.md`

## Scope

- `CLAUDE.md`:
  - „Mandatory process rules” zastąpione krótkim akapitem: `AGENTS.md` jest
    wiążący i czytany przed każdym zadaniem; tylko reguły potrzebne zanim
    agent go przeczyta (język polski, `caveman lite` przez skill, odczyt
    przed zadaniem) oraz wskazanie skilla `audit-task`;
  - „Environment”, „Commands”, „Architecture”, „Domain invariants”:
    zachowane; skrócone tylko tam, gdzie powtarzają `AGENTS.md` dosłownie;
  - bez importu `@AGENTS.md` (decyzja planu: import ładowałby 26 KB także do
    krótkich pytań bez zadania).
- `scripts/check_startup_read_budget.py`: włączone budżety `CLAUDE.md` 6 000 B
  i sumy czterech plików 90 000 B.
- Końcowy pomiar: `--report` przed i po całego planu (wartości z `Outcome`
  TASK-1019) w `Outcome` tego taska i w sekcji „Stan obecny” planu jako
  dopisek „Wynik”.
- Ocena ryzyka z TASK-1020 (przeoczone decyzje): czy w trakcie TASK-1021–1023
  agent potrzebował decyzji spoza 30 wierszy i czy ją znalazł; wynik w
  `Outcome`.
- Zamknięcie planu: status planu, sekcja planu w `CURRENT_STATE.md`,
  `ai_docs/README.md` (pozycja planu w „Dostarczanie”).

## Out of scope

- Zmiana treści `AGENTS.md` poza tym, co wymagały TASK-1020 i TASK-1022.
- Odchudzanie `AGENTS.md` i `README.md` (osobny plan po tym pomiarze).

## Acceptance criteria

- [ ] `CLAUDE.md` ≤ 6 000 B; każda reguła z usuniętej sekcji ma odpowiednik w `AGENTS.md` (lista porównania w `Outcome`).
- [ ] Suma obowiązkowego odczytu ≤ 90 000 B; budżet włączony; `npm run docs:check` PASS.
- [ ] Test negatywny budżetu sumy PASS.
- [ ] Tabela przed/po w `Outcome` i dopisek „Wynik” w planie.

## Technical notes

- `scripts/check_decision_links.py` skanuje `CLAUDE.md`; po zmianie
  uruchomić `docs:check`.
- Opcjonalnie operator porównuje `/context` świeżej sesji Claude Code przed i
  po; wynik trafia do `Outcome`, jeśli zostanie podany.

## Expected files

- Istniejące: `CLAUDE.md`, `scripts/check_startup_read_budget.py`, test
  skryptu, plan, `ai_docs/process/CURRENT_STATE.md`, `ai_docs/README.md`.

## Verification

```powershell
# katalog worktree (z dowiązaniem .venv), timeout 120 s
.\.venv\Scripts\python.exe scripts/check_startup_read_budget.py --report
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_check_startup_read_budget_script.py -q
npx prettier --check CLAUDE.md
npm run docs:check
```

## Risks / open questions

- Sesja Claude Code, która nie przeczyta `AGENTS.md`, straci reguły
  streszczone dziś w `CLAUDE.md`; akapit odesłania musi być pierwszą treścią
  pliku.

## Outcome

Wykonawca: claude-opus-5-5 (sesja leada) zamiast przypisanego
claude-sonnet-5-5 / medium. Bez audytu Codex (decyzja operatora 2026-10-16).
Commit: v1.7.372 (hash dopisuje kolejny commit).

### Changed

- `CLAUDE.md` 8 392 → 5 974 B: sekcja „Mandatory process rules” zastąpiona
  odesłaniem do `AGENTS.md` jako pierwszą treścią oraz trzema regułami
  potrzebnymi przed jego odczytem (polski i `caveman lite`; zakaz benchmarków,
  operacji destrukcyjnych i restartów bez prośby; skill `audit-task`);
  „Domain invariants” zastąpione jednym zdaniem z odesłaniem.
  „Environment”, „Commands” i „Architecture” bez zmian. Bez importu
  `@AGENTS.md`.
- `scripts/check_startup_read_budget.py`: wymuszone budżety `CLAUDE.md`
  6 000 B i sumy 90 000 B (wszystkie 9 budżetów wymuszone), z podpowiedziami.
- Nowy test `test_enforced_startup_total_and_claude_budgets_fail`.
- Plan: status `implemented`, dopisek „Wynik”; `README.md` i
  `CURRENT_STATE.md` (wiersz planu usunięty z tabeli planów).

### Verification results

- Porównanie usuniętych reguł z `AGENTS.md`: kolejność czytania
  („Obowiązkowa kolejność czytania”), PLAN_STANDARD i tabela modeli („Zasady
  nadrzędne”), język i `caveman lite` („Zasady nadrzędne”), reguła etapów
  („Zasady nadrzędne”, „Po kodowaniu” 8), hierarchia źródeł („Hierarchia
  źródeł prawdy”), wersjonowanie i `git diff --cached --check`
  („Wersjonowanie commitów”), zamykanie taska („Po kodowaniu”), timeouty i
  benchmarki („Limity czasu…”, „Testy, benchmarki i regresje”), operacje
  destrukcyjne („Trwałe workflowy i operacje danych”), trwałość napraw
  („Trwałość rozwiązań”), niezmienniki domenowe („Zasady nadrzędne”). Każda
  ma odpowiednik; przykładowe nazwy benchmarków zostały w `CLAUDE.md`.
- Pomiar końcowy (`--report`): `AGENTS.md` 26 821 B, `README.md` 17 267 B,
  `CURRENT_STATE.md` 23 052 B, `DECISION_LOG.md` 10 755 B, suma 77 895 B
  (przed planem 211 359 B, −63 %); `CLAUDE.md` 5 974 B; 9/9 budżetów
  wymuszonych, żaden nie jest przekroczony.
- pytest (3 pliki testów skryptów): 22 passed; `ruff check`,
  `ruff format --check`, `mypy --strict`, `prettier --check CLAUDE.md`,
  `npm run docs:check`: PASS.
- Ryzyko przeoczonych decyzji (TASK-1020): w TASK-1021 potrzebna była decyzja
  spoza 30 wierszy (D-467 o migracji `0125`); subagent znalazł ją `rg` w
  pliku wpisów. Brak przypadku przeoczenia.
- Samokontrola kryteriów akceptacji: wszystkie cztery spełnione. `CLAUDE.md`
  ma tylko 26 B zapasu do budżetu.

### Not completed

- Opcjonalne porównanie `/context` świeżej sesji przed i po: niewykonane
  (wymaga operatora).

### Documentation updates

- Jak w „Changed”; bez wpisu `DECISION_LOG.md` (D8 planu).

### Recommended next task

- Scalenie `feat/startup-read-diet` do `main` za zgodą operatora; potem
  przepisanie hunków `CURRENT_STATE.md` w otwartych gałęziach na nowy format.
