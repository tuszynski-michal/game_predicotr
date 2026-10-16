# TASK-1033 — `README.md` ≤ 5 000 B, `DOC_INDEX.md` i pomiar końcowy

## Status

`done`

## Goal

`ai_docs/README.md` jest krótkim wejściem (≤ 5 000 B), katalog dokumentów
leży w `ai_docs/DOC_INDEX.md` otwieranym na żądanie, a obowiązkowy odczyt
startowy mieści się w 45 000 B z wymuszonymi budżetami.

## Context

Plan `delivery/STARTUP_READ_STAGE2_EXECUTION_PLAN_20261016.md`, etap B,
decyzje E4–E5. `README.md` ma ok. 17 300 B, z czego sekcja „Aktywna
dokumentacja” ok. 13 000 B to lista planów i dokumentów, potrzebna tylko przy
szukaniu dokumentu.

## Dependencies / entry conditions

- TASK-1032 ukończony (ostatni pomiar sumy uwzględnia nowy `AGENTS.md`).

## Recommended execution

claude-sonnet-5-5 / medium. Bez dodatkowego review; samokontrola kryteriów w
`Outcome`.

## Relevant docs

- `ai_docs/README.md`, `AGENTS.md` („Obowiązkowa kolejność czytania”)
- `ai_docs/delivery/STARTUP_READ_STAGE2_EXECUTION_PLAN_20261016.md`
- `scripts/check_startup_read_budget.py`

## Scope

- Nowy `ai_docs/DOC_INDEX.md` (proponowany): sekcje „Aktywna dokumentacja”
  (Projekt, Wymagania, Architektura, Dostarczanie, Proces i jakość,
  Bezpieczeństwo, Instrukcje operatorskie, Materiały warunkowe) i
  „Historia” przeniesione bez zmian treści; linki względne poprawione
  (plik leży w tym samym katalogu, więc ścieżki zostają).
- `ai_docs/README.md`: cel, wejście do zadania (z linkiem do
  `DOC_INDEX.md` i `CODE_MAP.md`), zasada pojedynczego źródła prawdy,
  statusy, reguła aktualizacji; nowe plany dopisuje się do `DOC_INDEX.md`.
- `AGENTS.md`, `CLAUDE.md`, skille: odwołania do katalogu w README
  przepiąć na `DOC_INDEX.md`, gdzie dotyczą listy dokumentów.
- `scripts/check_startup_read_budget.py`: budżet `README.md` 5 000 B,
  suma 45 000 B; oba wymuszone; testy negatywne.
- Pomiar końcowy planu (`--report` przed/po) i dopisek „Wynik” w planie;
  status planu `implemented`.

## Out of scope

- Zmiana treści opisów dokumentów; porządkowanie starych planów milestone.

## Acceptance criteria

- [ ] `README.md` ≤ 5 000 B, suma obowiązkowego odczytu ≤ 45 000 B; budżety wymuszone.
- [ ] Każdy link z dawnej sekcji „Aktywna dokumentacja” jest w `DOC_INDEX.md` i rozwiązuje się (sprawdzenie skryptem lub `rg` + `Test-Path`).
- [ ] `npm run docs:check` PASS; tabela przed/po w `Outcome` i w planie.

## Expected files

- Nowe (proponowane): `ai_docs/DOC_INDEX.md`.
- Istniejące: `ai_docs/README.md`, `AGENTS.md`, `CLAUDE.md` (odwołania),
  `scripts/check_startup_read_budget.py`, test budżetu, plan etapu 2,
  `ai_docs/process/CURRENT_STATE.md`.

## Verification

```powershell
# katalog worktree z dowiązaniem .venv, timeout 120 s
.\.venv\Scripts\python.exe scripts/check_startup_read_budget.py --report
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_check_startup_read_budget_script.py -q -p no:cacheprovider --basetemp D:/ptw
npm run docs:check
```

## Risks / open questions

- Zewnętrzne odwołania do kotwic README (np. z archiwów) mogą stracić cel;
  przed zmianą `rg "README.md#"` w `ai_docs/`.

## Outcome

Commit: v1.7.382 (hash dopisuje kolejny commit).

Wykonawca: claude-sonnet-5-5 (medium), bez dodatkowego review (samokontrola).

### Changed

- Nowy `ai_docs/DOC_INDEX.md`: sekcje „Aktywna dokumentacja” (wszystkie
  podsekcje) i „Historia” przeniesione z `README.md`, wpisy bez zmian poza
  trzema: baner wydania Selektora Windows 1.0.0 dopisany pod wpisem selektora
  w „Dostarczanie” (poprawiona literówka „wpisy0.1.x”), wpis planu etapu 2
  zmieniony z `accepted` na wykonany oraz wstęp (katalog na żądanie, nowe
  plany dopisuje się tutaj).
- `ai_docs/README.md` skrócony do cel, wejście do zadania (linki do
  `DOC_INDEX.md` i `CODE_MAP.md`), zasada źródła prawdy, statusy, reguła
  aktualizacji (nowe plany i dokumenty do `DOC_INDEX.md`); baner wydania
  przeniesiony do indeksu.
- `scripts/check_startup_read_budget.py`: budżet `ai_docs/README.md` 5 000 B
  (wymuszony, z podpowiedzią) i suma 45 000 B (z 90 000, wymuszona); testy
  negatywne w `test_check_startup_read_budget_script.py` (README powyżej
  5 000 B i miara LF, suma powyżej 45 000 B, suma 45 000 B przechodzi).
- Plan etapu 2: status `implemented`, tabela „Wynik” przed/po.
- Odwołania: `AGENTS.md`, `CLAUDE.md`, skille, `TOKEN_TOOLING.md` wskazują
  `README.md` wyłącznie jako wejście odczytu startowego, nie jako katalog,
  więc bez zmian (`AGENTS.md` ma zapas tylko 58 B do budżetu). `rg
  "README.md#"` poza archiwami i ukończonymi taskami: brak kotwic.

### Verification

| Pomiar | Przed | Po | Budżet |
|---|---:|---:|---:|
| `ai_docs/README.md` | 17 931 B | 4 092 B | 5 000 B |
| `AGENTS.md` | 13 942 B | 13 942 B | 14 000 B |
| `CLAUDE.md` (poza sumą) | 5 974 B | 5 974 B | 6 000 B |
| suma obowiązkowego odczytu | 52 252 B | 38 413 B | 45 000 B |

Wartości „przed” to stan po TASK-1032; pomiar wyjściowy planu (~65 000 B) jest
w tabeli „Wynik” planu etapu 2.

- Linki: 110 linków dawnej sekcji „Aktywna dokumentacja” (109 unikalnych)
  jest w `DOC_INDEX.md`, wszystkie 112 linków indeksu rozwiązuje się do
  istniejących plików.
- `check_startup_read_budget.py`: OK, 11/11 budżetów wymuszonych.
- pytest `test_check_startup_read_budget_script.py`: 17 passed.
- `ruff check`, `ruff format --check`, `mypy --strict` skryptu budżetu: PASS.
- `npx prettier --check` README, DOC_INDEX, AGENTS, plan: PASS.
- `npm run docs:check` (decision links, okno stanu, budżety, lustra skilli): PASS; `git diff --check`: PASS.

### Not completed

- Brak. `CURRENT_STATE.md` i przeniesienie taska do `completed/` zostają dla
  zamykającego.

### Recommended next task

- Etap 3 (skille domenowe: diagnostyka pipeline siatek, migracje) po pomiarze
  etapu 2, według planu; osobno uporządkować stare plany milestone w
  `DOC_INDEX.md`.
