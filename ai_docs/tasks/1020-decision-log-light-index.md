# TASK-1020 — `DECISION_LOG.md` jako lekki indeks

## Status

`todo`

## Goal

`DECISION_LOG.md` ma najwyżej 12 000 B i 30 wierszy indeksu, bez pełnych kopii
wpisów; starsze wiersze są w `decisions/DECISION_INDEX_ARCHIVE.md`, a reguły
mówią, jak znaleźć decyzję wyszukiwaniem.

## Context

Plan `ai_docs/delivery/STARTUP_READ_DIET_EXECUTION_PLAN_20261016.md`, etap A,
decyzje D2–D5. Plik ma 77 628 B: indeks 58 556 B (187 wierszy) i pięć pełnych
kopii (ok. 17 KB) identycznych z wpisami w `decisions/DECISION_LOG_2026.md`.
Agent rzadko potrzebuje 187 jednozdaniowych wierszy; potrzebuje decyzji
dotyczących jego taska.

## Dependencies / entry conditions

- TASK-1019 ukończony (skrypt budżetów w `docs:check`).
- Gałąź zsynchronizowana z aktualnym czubkiem gałęzi docelowej tuż przed
  wykonaniem; inne tory dopisują wiersze (np. D-548..D-555 na
  `codex/v3-grid-fine-tuning`). Przenieść wszystkie wiersze obecne w chwili
  wykonania.
- Fakt: `scripts/check_decision_links.py` porównuje zbiór wierszy wszystkich
  plików `DECISION_LOG.md` + `decisions/DECISION_INDEX_*.md` ze zbiorem
  nagłówków wpisów i sprawdza linki `DECISION_LOG*.md#d-…` w `ai_docs/`,
  `AGENTS.md`, `CLAUDE.md`.

## Recommended execution

claude-sonnet-5-5 / medium. Mechaniczne przeniesienie z dowodem i zmiana reguł
w kilku dokumentach. Eskalacja do claude-opus-5-5 / high przy kolizji numerów
D z innym torem. Audyt: gpt-6.1-sol / medium.

## Relevant docs

- `AGENTS.md` (sekcje „Obowiązkowa kolejność czytania”, „Przed kodowaniem” 5,
  „Hierarchia źródeł prawdy”)
- `ai_docs/README.md` (sekcje „Wejście do zadania”, „Reguła aktualizacji”)
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/delivery/STARTUP_READ_DIET_EXECUTION_PLAN_20261016.md`
- `ai_docs/tasks/completed/0938-process-docs-rolling-window.md` (metoda dowodu)

## Scope

- `DECISION_LOG.md`:
  - nagłówek z regułami skrócony do: czym jest plik, gdzie są pełne wpisy i
    starszy indeks, jak szukać (`rg`), jak dopisać nową decyzję;
  - indeks: 30 najnowszych wierszy; starsze wiersze przeniesione bez zmian na
    początek tabeli w `decisions/DECISION_INDEX_ARCHIVE.md` (kolejność malejąca
    zachowana);
  - usunięte pięć pełnych kopii najnowszych wpisów (sekcja „Najnowsze wpisy
    (pełne kopie)”).
- Reguły (D5):
  - `AGENTS.md` „Obowiązkowa kolejność czytania” pkt 3: nagłówek i 30
    najnowszych wierszy; starsze decyzje wyszukiwaniem
    `rg -n "<słowo|D-NNN>" ai_docs/process/DECISION_LOG.md ai_docs/process/decisions/DECISION_INDEX_ARCHIVE.md`;
    pełny wpis przez kotwicę na żądanie;
  - `AGENTS.md` „Przed kodowaniem” pkt 5: nowa decyzja = pełny wpis w pliku
    rocznym + wiersz na początku indeksu; najstarszy wiersz ponad 30 przenieś
    do archiwum indeksu (zamiast podmiany pełnych kopii);
  - `ai_docs/README.md` „Wejście do zadania” i „Reguła aktualizacji”: ten sam
    opis;
  - `ai_docs/process/TASK_TEMPLATE.md` `Relevant docs`: przykładowa pozycja
    „decyzje D-NNN istotne dla taska (link z kotwicą do
    `decisions/DECISION_LOG_2026.md`)”;
  - sprawdzić i zaktualizować wzmianki o „pięciu najnowszych wpisach” w
    `ai_docs/process/AI_DRIVEN_DEVELOPMENT.md`,
    `ai_docs/process/DEFINITION_OF_DONE.md`, `ai_docs/process/CURRENT_STATE.md`
    (sekcja „Otwarte decyzje i pytania”), `.claude/skills/audit-task/SKILL.md`,
    `.codex/skills/claude-audit/SKILL.md` (`rg -n "pięć|pełne kopie|five" …`).
- Skrypty:
  - `scripts/check_startup_read_budget.py`: włączyć budżety
    `DECISION_LOG.md` 12 000 B i ≤ 30 wierszy indeksu;
  - `scripts/check_decision_links.py`: usunąć limit 100 000 B i kontrolę
    pełnych kopii (pkt 3 i 4 docstringu), zaktualizować docstring; reszta
    kontroli bez zmian;
  - testy obu skryptów zaktualizowane (w tym negatywny: 31 wierszy → FAIL).

## Out of scope

- Zmiana treści wpisów, wierszy indeksu, statusów decyzji i kotwic.
- `CURRENT_STATE.md` poza zdaniem o indeksie w „Otwartych decyzjach i pytaniach”.

## Acceptance criteria

- [ ] `DECISION_LOG.md` ≤ 12 000 B, dokładnie 30 wierszy indeksu (lub mniej, jeśli decyzji jest mniej), brak pełnych kopii.
- [ ] Dowód: multizbiór wierszy indeksu (`DECISION_LOG.md` + archiwum) przed = po; usunięte kopie identyczne z wpisami pliku rocznego (z dokładnością do końcowego znaku nowej linii).
- [ ] `npm run docs:check` PASS z włączonymi budżetami `DECISION_LOG.md`.
- [ ] Test negatywny budżetu wierszy i rozmiaru PASS.
- [ ] Brak wzmianek o pięciu pełnych kopiach w dokumentach procesu i skillach audytu.
- [ ] Raport `--report` przed i po w `Outcome`.

## Technical notes

- Dowód wykonać skryptem poza repo (scratchpad), jak w TASK-0938; w `Outcome`
  podać liczby wierszy i wynik porównania.
- Przeniesione wiersze w archiwum indeksu trafiają nad dotychczasowy pierwszy
  wiersz tabeli, z zachowaniem nagłówka tabeli archiwum.
- Nie zmieniać kotwic; linki `DECISION_LOG.md#d-…` w dokumentach (jeśli są)
  muszą nadal przechodzić `check_decision_links.py`.

## Expected files

- Istniejące: `ai_docs/process/DECISION_LOG.md`,
  `ai_docs/process/decisions/DECISION_INDEX_ARCHIVE.md`, `AGENTS.md`,
  `ai_docs/README.md`, `ai_docs/process/TASK_TEMPLATE.md`,
  `scripts/check_decision_links.py`, `scripts/check_startup_read_budget.py`,
  `services/worker/tests/test_check_decision_links_script.py`,
  `services/worker/tests/test_check_startup_read_budget_script.py`; wybrane
  wzmianki w dokumentach procesu i skillach audytu.

## Verification

```powershell
# katalog worktree (z dowiązaniem .venv), timeout 120 s
.\.venv\Scripts\python.exe scripts/check_startup_read_budget.py --report
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_check_decision_links_script.py services/worker/tests/test_check_startup_read_budget_script.py -q
.\.venv\Scripts\python.exe -m ruff check scripts/check_decision_links.py scripts/check_startup_read_budget.py
.\.venv\Scripts\python.exe -m mypy --strict scripts/check_decision_links.py scripts/check_startup_read_budget.py
npx prettier --check AGENTS.md ai_docs/process/DECISION_LOG.md
npm run docs:check
```

## Risks / open questions

- Agent może przeoczyć starszą decyzję, której nie wyszukał. Ograniczenie:
  `Relevant docs` taska i „Obowiązujące ograniczenia”; ryzyko odnotować w
  `Outcome` i ocenić w TASK-1023.
- Konflikt scalenia z torem, który w międzyczasie dopisze wiersz w starym
  układzie; po scaleniu przenieść nadmiarowe wiersze do archiwum.

## Outcome

Wypełnia agent po pracy.
