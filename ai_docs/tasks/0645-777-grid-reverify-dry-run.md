---
title: TASK-0645 — Gra 777: reguła decyzji i pełny dry-run reweryfikacji siatek
status: todo
---

# TASK-0645 — Reguła decyzji i dry-run (read-only)

## Status

`todo`

## Goal

Dla każdej planszy „Do walidacji” i każdego slotu „Do poprawy” gry 777 wyznaczyć decyzję (pewny / niepewny / pominięty + powód) bez żadnego zapisu i zaraportować liczności.

## Dependencies / entry conditions

- TASK-0644 `done`, D-445 zaakceptowany (progi).

## Recommended execution

`claude-sonnet-5`, reasoning `high` — zgodnie z tabelą planu. Eskalacja do `claude-opus-5-5` high, gdy reguła rodzeństwa wymaga interpretacji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GAME_777_GRID_REVERIFICATION_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-445)

## Scope

- Czysta funkcja decyzji (plansza, slot, zdjęcie z regułą rodzeństwa) z progami z D-445.
- Podkomenda `plan`: iteracja po zdjęciach kursorem, partie 200, checkpoint JSONL, wznowienie; transakcja `READ ONLY`.
- Raport: liczności per populacja × decyzja × powód; szacowany czas `execute`.

## Out of scope

- Zapis do bazy.

## Acceptance criteria

- [ ] Plansze zatwierdzone, z rewizją > 0 lub z `grid_issue` → `skipped` (nigdy nie przetwarzane).
- [ ] Zdjęcie ze slotem odroczonym → `resolvable` tylko przy pewności wszystkich slotów odroczonych i każdego niezatwierdzonego rodzeństwa.
- [ ] Przerwany `plan` wznawia się bez podwójnego liczenia.
- [ ] Testy tabeli decyzji przechodzą; pełny dry-run zakończony, raport w Outcome.

## Test cases

- Plansza: weryfikator `needs_review` → niepewna; `estimated`, odchylenie > τ → niepewna; ≤ τ i p95 ≤ r → pewna.
- Zdjęcie: 1 slot pewny + 1 niepewny → `unresolved`; wszystkie sloty pewne, rodzeństwo pewne/zatwierdzone → `resolvable`; jedno rodzeństwo niepewne → `unresolved`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest <test file> -q   # timeout 120 s
# pełny dry-run jako kontrolowany proces w tle z checkpointem
npm run python:lint; npm run python:typecheck
```

## Outcome

Wypełnia agent po pracy.
