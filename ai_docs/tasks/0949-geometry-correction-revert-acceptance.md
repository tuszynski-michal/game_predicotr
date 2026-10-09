# TASK-0949 — D-538, dokumentacja i odbiór cofania korekt

## Status

`todo`

## Goal

Decyzja D-538 i dokumenty opisują cofanie korekt, operator wykonuje migrację `0153` po scaleniu za zgodą, a odbiór potwierdza cofnięcie slotu 69004 wykonane przez operatora w Reviewerze.

## Context

Plan `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`, etap R3.

## Dependencies / entry conditions

- TASK-0945–0948 ukończone; zgoda operatora na scalenie i push.

## Recommended execution

`claude-sonnet-5-5`, reasoning `low`: dokumentacja i odczytowy odbiór. Eskalacja: rozbieżność stanu bazy z oczekiwanym → zatrzymaj i zgłoś. Review: Codex `gpt-6-astra`, `medium`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- D-538 (pełny wpis w `DECISION_LOG_2026.md`, indeks, okno pięciu wpisów): cofanie ostatniej korekty, status `reverted`, fizyczne usuwanie w przypadku B z audytem, reguła `assignment_source`, zmiana D-462 w zakresie „bez usuwania historii” dla wierszy utworzonych przez cofany zapis.
- `DATA_MODEL.md` (tabela audytu, status, kolumna zdarzeń), `API_CONTRACT.md` (trzy trasy), wymagania Reviewera, `README.md` (link do planu), status planu.
- Instrukcja operatora: stop API/worker/Admin/Reviewer → scalenie → `npm run db:migrate` → start → cofnięcie w Reviewerze.
- Odczytowy pomiar N1: ile korekt importu `092ff7a4-…` jest `revertable` i jakie są powody blokad.
- Odbiór po cofnięciu 69004 przez operatora (odczyt): slot `pending`, brak planszy `378a273f-…`, sąsiedzi 69006–69012 na rewizji źródła 0, rewizja 1 `reverted`, wiersz audytu.

## Out of scope

- Wykonywanie cofnięcia lub migracji przez agenta.

## Acceptance criteria

- [ ] `npm run docs:check` zielone; D-538 w indeksie i oknie.
- [ ] Odbiór 69004 opisany w `Outcome` z wynikami zapytań odczytowych.

## Verification

```powershell
npm run docs:check
# odczyt stanu bazy operatora: psql SELECT, bez zapisów
```

## Risks / open questions

- Operator może najpierw ponownie poprawić 69004; wtedy cofnięcie dotyczy nowszego zapisu albo jest blokowane — odnotuj w `Outcome`.

## Outcome

Wypełnia agent po pracy.
