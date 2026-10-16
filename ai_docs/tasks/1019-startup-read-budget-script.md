# TASK-1019 — Skrypt pomiaru i budżetów odczytu startowego

## Status

`todo`

## Goal

`scripts/check_startup_read_budget.py` raportuje rozmiar obowiązkowego odczytu
startowego (plik po pliku i sekcja po sekcji `CURRENT_STATE.md`) i pilnuje
budżetów oznaczonych jako włączone; skrypt jest częścią `npm run docs:check`.

## Context

Plan `ai_docs/delivery/STARTUP_READ_DIET_EXECUTION_PLAN_20261016.md`, etap A,
decyzje D1–D3. Obowiązkowy odczyt ma 211 359 B; jedyny limit to 100 000 B na
plik w dwóch skryptach kontroli. Bez pomiaru nie da się wykazać efektu
kolejnych tasków ani zapobiec ponownemu rozrostowi.

## Dependencies / entry conditions

- Brak zależności od innych tasków planu.
- Fakt: `docs:check` w `package.json` uruchamia
  `scripts/check_decision_links.py` i `scripts/check_current_state_window.py`.
- Przed commitem potwierdzić wolny numer TASK i wersję względem czubka gałęzi
  integracyjnej.

## Recommended execution

claude-sonnet-5-5 / medium. Mały skrypt i testy według wzorca istniejących
skryptów kontroli. Eskalacja do claude-opus-5-5 / high, jeśli podział sekcji
okaże się niejednoznaczny (np. nagłówki w blokach kodu). Audyt:
gpt-6.1-sol / medium przez `scripts/audit_task.ps1`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/STARTUP_READ_DIET_EXECUTION_PLAN_20261016.md` (sekcje
  „Stan obecny”, „Kluczowe decyzje planu” D1–D3)
- `scripts/check_current_state_window.py`, `scripts/check_decision_links.py`

## Scope

- Nowy `scripts/check_startup_read_budget.py`:
  - lista obowiązkowego odczytu jako stała: `AGENTS.md`,
    `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`,
    `ai_docs/process/DECISION_LOG.md`; osobno `CLAUDE.md`;
  - raport: bajty każdego pliku, suma czterech plików, bajty każdej sekcji
    `##` i każdej podsekcji `###` w `CURRENT_STATE.md` (nagłówki w blokach
    kodu pomijane), liczba wierszy indeksu `| [D-` w `DECISION_LOG.md`;
  - tabela budżetów z planu (D3) jako stałe, każdy z flagą `enforced`;
    w tym tasku wszystkie flagi `False`;
  - exit 1 tylko przy przekroczeniu budżetu z `enforced=True`; komunikat
    podaje budżet, wartość i wskazówkę (np. „przenieś najstarsze wiersze do
    `decisions/DECISION_INDEX_ARCHIVE.md`”);
  - opcja `--report` wypisuje pełną tabelę także przy sukcesie; domyślnie
    jedna linia `OK (...)` jak w pozostałych skryptach.
- `package.json`: dopisanie skryptu do `docs:check`.
- Testy w `services/worker/tests/` (obok `test_check_decision_links_script.py`).

## Out of scope

- Zmiana treści `CURRENT_STATE.md`, `DECISION_LOG.md`, `AGENTS.md`, `CLAUDE.md`.
- Usuwanie limitów 100 000 B z istniejących skryptów (TASK-1020, TASK-1022).
- Liczenie tokenów przez API.

## Acceptance criteria

- [ ] `npm run docs:check` PASS na bieżących dokumentach (budżety wyłączone).
- [ ] `--report` wypisuje wszystkie pliki, sumę, sekcje `CURRENT_STATE.md` i liczbę wierszy indeksu.
- [ ] Test negatywny: budżet z `enforced=True` i za mały plik testowy daje exit 1 z czytelnym komunikatem.
- [ ] Test: nagłówek `##` w bloku kodu nie tworzy sekcji.
- [ ] Raport bazowy (wynik `--report`) zapisany w `Outcome`.

## Technical notes

- Ścieżki względem korzenia repo (`Path(__file__).resolve().parents[1]`), jak
  w istniejących skryptach; możliwość podania innego korzenia w testach
  (parametr funkcji, nie zmienna globalna).
- Bajty liczone z `read_bytes()`, bez normalizacji końców linii.
- Sekcja = od nagłówka do następnego nagłówka tego samego lub wyższego
  poziomu.

## Expected files

- Nowe (proponowane): `scripts/check_startup_read_budget.py`,
  `services/worker/tests/test_check_startup_read_budget_script.py`.
- Istniejące: `package.json` (`docs:check`).

## Verification

```powershell
# katalog worktree, timeout 120 s
.\.venv\Scripts\python.exe scripts/check_startup_read_budget.py --report
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_check_startup_read_budget_script.py -q
.\.venv\Scripts\python.exe -m ruff check scripts/check_startup_read_budget.py
.\.venv\Scripts\python.exe -m mypy --strict scripts/check_startup_read_budget.py
npm run docs:check
```

## Risks / open questions

- Worktree nie ma `.venv`; przed weryfikacją utworzyć ignorowane dowiązanie
  `New-Item -ItemType Junction -Path .venv -Target D:\game_predicotr\.venv`
  (komendy `npm run docs:check` używają ścieżki względnej `.venv`).

## Outcome

Wypełnia agent po pracy.
