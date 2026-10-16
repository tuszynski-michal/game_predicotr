# TASK-1023 — `CLAUDE.md` bez duplikatu `AGENTS.md` i końcowy pomiar

## Status

`todo`

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
Audyt: gpt-6.1-sol / medium.

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

Wypełnia agent po pracy.
