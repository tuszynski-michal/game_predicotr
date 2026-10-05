---
title: TASK-0871 — kontrakt zapisu symbol-rgb-v2 w writerze
status: todo
last_updated: 2026-10-05
---

# TASK-0871 — kontrakt zapisu symbol-rgb-v2 w writerze

## Status

`todo`

## Goal

Writer zapisuje rewizję `symbol-rgb-v2` (pewna 0,99, do przeglądu 0,50, wpis `rgbV2` z pochodzeniem); zapis, weryfikacja i cofnięcie działają dla nowej wersji; side-effect na komórce spoza celów kończy planszę jako stale zamiast zatrzymywać przebieg.

## Context

Etap A planu `ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md`
(zaakceptowany przez operatora 2026-10-05). Metoda i ograniczenia:
`ai_docs/guides/SYMBOL_RGB_FEEDBACK_HANDOFF_20261005.md`.

## Dependencies / entry conditions

- Plan zaakceptowany; poprzednie taski etapu A wykonane w kolejności planu.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (zgodnie z tabelą planu; audyt wstrzymany
przez operatora 2026-10-01).

## Relevant docs

- `ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md`
- `ai_docs/guides/SYMBOL_RGB_FEEDBACK_HANDOFF_20261005.md`
- `ai_docs/process/DECISION_LOG.md` (D-466)

## Scope

- `reference_library_writer.py`: polityka zapisu jako parametr (wersja, aktor, pewność, wpis), dotychczasowe zachowanie biblioteki bez zmian.
- Zapis/weryfikacja/cofnięcie manifestów RGB v2.
- Wpis D-520 w `DECISION_LOG.md`.

## Out of scope

- Zapis w bazie operatora (etap B), trening i zmiana checkpointu CNN,
  zatwierdzanie komórek, geometria.

## Acceptance criteria

- [ ] Testy writera: pewna, do przeglądu, cel na komórce starej biblioteki, side-effect jako stale.
- [ ] Test PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`) zapisu i cofnięcia jednej planszy.
- [ ] Stare testy biblioteki bez zmian zielone.

## Test cases

- `services/worker/tests/test_symbol_reference_library_writer.py` + test integracyjny PG.

## Outcome

Brak.
