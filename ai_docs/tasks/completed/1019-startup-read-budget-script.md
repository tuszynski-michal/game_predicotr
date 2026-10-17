# TASK-1019 — Skrypt pomiaru i budżetów odczytu startowego

## Status

`done`

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
okaże się niejednoznaczny (np. nagłówki w blokach kodu). Bez audytu Codex (decyzja operatora
2026-10-16); wykonawca robi samokontrolę kryteriów akceptacji i zapisuje ją w
`Outcome`.

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

Wykonawca: claude-opus-5-5 (sesja leada) zamiast przypisanego
claude-sonnet-5-5 / medium; odstępstwo bez wpływu na zakres. Bez audytu Codex
(decyzja operatora 2026-10-16). Commit: v1.7.366 / `d117430487f8b4fd401ecb94d7796bcfc209c0ec`.

### Changed

- Nowy `scripts/check_startup_read_budget.py`: raport (`--report`) plików
  obowiązkowego odczytu, sumy, sekcji `##`/`###` `CURRENT_STATE.md` (nagłówki w
  blokach kodu pominięte) i liczby wierszy indeksu decyzji; tabela `BUDGETS`
  z D3 planu, każdy budżet z flagą `enforced` (wszystkie `False`); `check()`
  zwraca problemy tylko dla włączonych budżetów, z podpowiedzią.
- `package.json`: skrypt dopisany na końcu `docs:check`.
- Nowy `services/worker/tests/test_check_startup_read_budget_script.py`
  (6 testów: repozytorium przechodzi, raport bez wymuszeń, negatywny budżet
  sekcji aktywnego taska z podpowiedzią, negatywny budżet wierszy indeksu,
  nagłówek w bloku kodu, punkty z kontynuacją).

### Verification results

- pytest (nowe testy + `test_check_decision_links_script.py`): 10 passed.
- `ruff check`, `ruff format --check`, `mypy --strict` (skrypt i test): PASS.
- `npm run docs:check`: PASS, `check_startup_read_budget: OK (startup read 213899 bytes, 0/9 budgets enforced)`.
- Raport bazowy (2026-10-16, po commitach v1.7.364–365): `AGENTS.md` 26 120 B,
  `README.md` 16 557 B, `CURRENT_STATE.md` 93 594 B, `DECISION_LOG.md`
  77 628 B, suma 213 899 B; `CLAUDE.md` 8 392 B. Sekcje `CURRENT_STATE.md`:
  ograniczenia 20 389 B, plany 8 288 B, otwarte decyzje 1 013 B, aktywne
  taski 50 038 B (52 sekcje, 10 ponad 1 200 B; największa TASK-0290
  13 740 B), ukończone 12 737 B (10 sekcji, wszystkie ponad 400 B). Indeks
  decyzji: 187 wierszy. Przekroczone (tylko raport) wszystkie 9 budżetów.
- Samokontrola kryteriów akceptacji: wszystkie pięć spełnione.

### Not completed

- Brak.

### Documentation updates

- `CURRENT_STATE.md` (sekcja `done`), ten plik.

### Recommended next task

- TASK-1020.