# TASK-0938 — Okno kroczące `CURRENT_STATE.md` i indeks `DECISION_LOG.md`

## Status

`todo`

## Goal

Obowiązkowe dokumenty startowe mieszczą się w limicie czytelnym dla agenta:
`CURRENT_STATE.md` zawiera tylko zadania `in_progress` i ostatnie 10 `done`,
`DECISION_LOG.md` jest indeksem decyzji z pełnymi wpisami w plikach rocznych;
żadna treść nie ginie.

## Context

`CURRENT_STATE.md` ma 11 774 linie (853 KB), `DECISION_LOG.md` 11 300 linii
(791 KB). Pełny odczyt na start każdej sesji jest niewykonalny i kosztowny.
Plan: etap T.

## Dependencies / entry conditions

- Decyzja operatora D-1 planu (teraz czy później).
- Fakt: `AGENTS.md` i `ai_docs/README.md` nakazują czytać oba pliki; wiele
  dokumentów linkuje do `DECISION_LOG.md#d-xxx`.

## Recommended execution

claude-sonnet-5-5 / medium. Przeniesienie treści bez zmian merytorycznych,
kontrola linków. Eskalacja niepotrzebna. Audyt: gpt-6.1-sol / medium.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- `CURRENT_STATE.md`: zostają sekcje zadań `in_progress` i ostatnich 10
  `done` plus krótkie wskaźniki; reszta przeniesiona bez edycji do
  `ai_docs/archive/CURRENT_STATE_2026Q3.md` (i kolejnych).
- `DECISION_LOG.md`: na górze indeks (numer, tytuł, status, data, jedno
  zdanie, link do pełnego wpisu); pełne wpisy w
  `ai_docs/process/decisions/DECISION_LOG_2026.md` (lub podział kwartalny),
  kotwice `#d-xxx` zachowane; skrypt `scripts/check_decision_links.py`
  (proponowany) sprawdza linki w `ai_docs/`.
- `AGENTS.md` i `README.md`: obowiązkowy odczyt = indeks; pełny wpis na
  żądanie, gdy zadanie go wskazuje.

## Out of scope

- Zmiana treści decyzji lub stanów; skracanie wpisów.

## Acceptance criteria

- [ ] Oba pliki < 100 KB; archiwa zawierają przeniesioną treść bez zmian
      (diff treści = przeniesienie).
- [ ] Wszystkie linki `DECISION_LOG.md#d-` w `ai_docs/` rozwiązują się.
- [ ] `AGENTS.md`/`README.md` opisują nowy obowiązkowy odczyt.

## Verification

```powershell
# katalog worktree, timeout 120 s
.\.venv\Scripts\python.exe scripts/check_decision_links.py
```

## Risks / open questions

- Równoległe sesje edytują oba pliki; wykonać w oknie bez innych aktywnych
  zadań i zmergować jako pierwsze.

## Outcome

Wypełnia agent po pracy.

### Changed

### Verification results

### Not completed

### Documentation updates

### Recommended next task
