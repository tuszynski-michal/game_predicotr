# TASK-1033 — `README.md` ≤ 5 000 B, `DOC_INDEX.md` i pomiar końcowy

## Status

`todo`

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

Wypełnia agent po pracy.
