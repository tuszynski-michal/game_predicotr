# TASK-0729 — Odbiór weryfikacji per komórka (D-462)

## Status

todo

## Goal

Potwierdzić na żywych danych gry `777`, po zatwierdzonym `apply` TASK-0728,
że scenariusze 1–9 planu D-462 działają end-to-end.

## Context

Ostatnie zadanie etapu C planu
`ai_docs/delivery/CELL_LEVEL_VERIFICATION_EXECUTION_PLAN.md`.

## Dependencies / entry conditions

TASK-0728 done oraz `apply` wykonany po osobnej zgodzie operatora. Bez apply
zadanie jest `blocked`.

## Recommended execution

claude-opus-5-5, high — odbiór całości na żywych danych bez zapisu. Audyt:
claude-opus-5-5, high (subagent, poziom warunkowy).

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` D-462
- `ai_docs/delivery/CELL_LEVEL_VERIFICATION_EXECUTION_PLAN.md`

## Scope

- Odczyt po apply: zero akceptacji innych pikseli, dokumenty wyszukiwania
  zgodne z projekcją, ponowny preview TASK-0728 pusty.
- Przegląd scenariuszy 1–9 (testy automatyczne + odczyt żywych danych).
- Aktualizacja `CURRENT_STATE.md` i zamknięcie planu.

## Out of scope

- Nowe zmiany kodu poza poprawkami znalezionych błędów (osobne taski).

## Acceptance criteria

- [ ] Ponowny preview TASK-0728 na grze `777` nie ma żadnej pozycji.
- [ ] Każdy scenariusz 1–9 ma dowód (test albo odczyt) w `Outcome`.

## Verification

```powershell
.\.venv\Scripts\python.exe scripts/migrate_cell_level_verification.py preview --game-id bfc4f949-5c14-4850-b02a-db99610bcfa5 --output artifacts/cell-level-migration/acceptance-777.json
```

## Risks / open questions

- Aktywność operatora między apply a odbiorem może dodać nowe pozycje
  preview; odbiór je wyjaśnia, zamiast je ukrywać.

## Outcome

Wypełnia agent po pracy.
