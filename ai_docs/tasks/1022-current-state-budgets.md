# TASK-1022 — Zastosowanie budżetów `CURRENT_STATE.md`

## Status

`todo`

## Goal

`CURRENT_STATE.md` ma najwyżej 30 000 B i mieści się w budżetach sekcji z planu,
treść usunięta z okna jest bez zmian w archiwum, a reguła zamykania taska
utrzymuje nowy format.

## Context

Plan `ai_docs/delivery/STARTUP_READ_DIET_EXECUTION_PLAN_20261016.md`, etap C,
decyzje D2–D4, D6, D7. Klasyfikację punktów i sekcji zatwierdził operator w
raporcie TASK-1021.

## Dependencies / entry conditions

- TASK-1021 z zapisaną decyzją operatora. Rozbieżność między raportem a
  bieżącym oknem (nowe sekcje dopisane po raporcie) klasyfikować tą samą
  regułą i wymienić w `Outcome`; nowe ograniczenia operacyjne bez decyzji
  operatora zostają w pełnej treści.
- Gałąź zsynchronizowana z aktualnym czubkiem gałęzi docelowej tuż przed
  wykonaniem.

## Recommended execution

claude-sonnet-5-5 / high. Duże przeniesienie treści z dowodem i zmiana reguły
zamykania tasków używanej przez wszystkich agentów. Eskalacja do
claude-opus-5-5 / high, jeśli dowód multizbioru nie przechodzi. Audyt:
gpt-6.1-sol / medium.

## Relevant docs

- `AGENTS.md` (sekcje „Obowiązkowa kolejność czytania”, „Po kodowaniu” 3)
- `ai_docs/README.md` (sekcje „Wejście do zadania”, „Reguła aktualizacji”)
- `ai_docs/process/CURRENT_STATE.md`, `ai_docs/archive/CURRENT_STATE_2026Q4.md`
  (tylko początek pliku, `offset`/`limit`)
- `ai_docs/quality/CURRENT_STATE_REVIEW_<data>.md` (raport TASK-1021)
- `ai_docs/delivery/STARTUP_READ_DIET_EXECUTION_PLAN_20261016.md`
- `ai_docs/tasks/completed/0938-process-docs-rolling-window.md` (metoda dowodu)

## Scope

- `CURRENT_STATE.md` według zatwierdzonego raportu:
  - „Obowiązujące ograniczenia”: punkty `zostaje` skrócone do zatwierdzonej
    treści; `archiwum` i pełne wersje skracanych punktów przeniesione bez
    zmian do archiwum; `do task` przeniesione do pliku taska (sekcja
    „Ograniczenia z CURRENT_STATE”) z odnośnikiem;
  - „Plany z niezakończonymi taskami”: tabela (plan, status, pozostałe taski,
    gałąź); podsekcje planów w pełnej treści do archiwum;
  - „Aktywne taski”: każda sekcja ≤ 1 200 B według D7; usunięte bloki
    (np. historia TASK-0290, iteracje TASK-0472) do archiwum bez zmian;
    nagłówek każdej sekcji zachowuje `TASK-NNNN` (kontrola okna);
  - „Ostatnie 10 ukończonych tasków”: 10 wpisów jednowierszowych (D6); pełne
    sekcje `done` do archiwum bez zmian;
  - nagłówek okna: nowa reguła utrzymania; punkt w „Obowiązujących
    ograniczeniach” o nowym formacie dla innych otwartych gałęzi.
- Archiwum: bloki dopisane na początku `ai_docs/archive/CURRENT_STATE_2026Q4.md`
  (lub nowego pliku kwartału, jeśli data wykonania to 2027Q1 lub później;
  wtedy aktualizacja `ai_docs/archive/README.md`).
- Reguły:
  - `AGENTS.md` „Po kodowaniu” 3: przy zamknięciu pełna sekcja `done` idzie
    na początek najnowszego archiwum, do okna trafia wiersz D6 (najstarszy
    ponad 10 usunięty z okna, jego pełna sekcja już jest w archiwum); sekcja
    aktywna ≤ 1 200 B; `npm run docs:check`;
  - `AGENTS.md` „Obowiązkowa kolejność czytania” pkt 2: opis okna;
  - `ai_docs/README.md`: te same zmiany;
  - wzmianki w `ai_docs/process/AI_DRIVEN_DEVELOPMENT.md`,
    `ai_docs/process/DEFINITION_OF_DONE.md` i skillach audytu
    (`.claude/skills/audit-task/SKILL.md`, `.codex/skills/claude-audit/SKILL.md`),
    jeśli opisują stary format.
- Skrypty:
  - `scripts/check_current_state_window.py`: limit `done` liczony z wierszy
    D6 w sekcji „Ostatnie 10 ukończonych tasków” (≤ 10, format sprawdzany),
    usunięty limit 100 000 B; kontrola sekcji aktywnych tasków bez zmian;
  - `scripts/check_startup_read_budget.py`: włączone budżety
    `CURRENT_STATE.md` z D3 (wartości po ewentualnej zmianie zatwierdzonej w
    TASK-1021);
  - testy: pozytywny dla nowego formatu, negatywne dla 11 wierszy `done`,
    sekcji aktywnej > 1 200 B i pliku > 30 000 B.

## Out of scope

- Zmiana sensu ograniczeń, statusów tasków i planów poza zatwierdzonym raportem.
- Naprawa rozbieżności statusów wykrytych w TASK-1021.

## Acceptance criteria

- [ ] `CURRENT_STATE.md` ≤ 30 000 B; wszystkie budżety sekcji D3 spełnione.
- [ ] Dowód multizbioru bloków: (okno przed) = (bloki okna po, które istniały przed) + (bloki dopisane do archiwum i plików tasków); nowe bloki okna (skróty, wiersze D6, tabela planów) wymienione z liczbą.
- [ ] Każdy plik aktywnego taska ma sekcję w oknie; `npm run docs:check` PASS z włączonymi budżetami.
- [ ] Reguła zamykania w `AGENTS.md` i `README.md` opisuje nowy format; brak sprzecznych wzmianek w dokumentach procesu i skillach audytu.
- [ ] Raport `--report` przed i po w `Outcome`.

## Technical notes

- Skrót punktu ograniczenia zachowuje: co jest zabronione lub wymagane, kogo
  dotyczy, źródło (link do archiwum lub taska).
- Przykład wpisu D6:
  `- **TASK-1007** — Trwałe wykrywanie Claude Code CLI — v1.7.361 / baf67dbd — tasks/completed/1007-claude-cli-discovery.md`.
- Wiersze D6 dla dziesięciu obecnych sekcji `done` budować z ich treści
  (wersja i hash commita implementacji lub zamknięcia).

## Expected files

- Istniejące: `ai_docs/process/CURRENT_STATE.md`,
  `ai_docs/archive/CURRENT_STATE_2026Q4.md`, `AGENTS.md`, `ai_docs/README.md`,
  `scripts/check_current_state_window.py`, `scripts/check_startup_read_budget.py`,
  testy skryptów w `services/worker/tests/`, wybrane pliki aktywnych tasków,
  wzmianki w dokumentach procesu i skillach audytu.

## Verification

```powershell
# katalog worktree (z dowiązaniem .venv), timeout 120 s
.\.venv\Scripts\python.exe scripts/check_startup_read_budget.py --report
.\.venv\Scripts\python.exe -m pytest services/worker/tests -k "check_current_state or startup_read" -q
.\.venv\Scripts\python.exe -m ruff check scripts/check_current_state_window.py scripts/check_startup_read_budget.py
.\.venv\Scripts\python.exe -m mypy --strict scripts/check_current_state_window.py scripts/check_startup_read_budget.py
npx prettier --check AGENTS.md
npm run docs:check
```

## Risks / open questions

- Równoległe gałęzie dopisują sekcje w starym formacie; po scaleniu wymagają
  przepisania hunków (punkt w ograniczeniach).
- Pliki tasków rosną o przeniesione ograniczenia; to akceptowane, bo czyta
  się je tylko przy pracy nad tym taskiem.

## Outcome

Wypełnia agent po pracy.
