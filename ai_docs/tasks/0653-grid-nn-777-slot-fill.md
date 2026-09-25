---
title: TASK-0653 — Sieć siatek v3: dorysowanie slotów 777 w narzędziu reweryfikacji
status: todo
---

# TASK-0653 — Użycie sieci w reweryfikacji 777

## Status

`todo`

## Goal

Sieć zastępuje krok „dorysowania” w hybrydzie 777; nowy dry-run pozostałych slotów, przegląd użytkownika i zapis za zgodą, z decyzją D-446.

## Dependencies / entry conditions

- TASK-0652 `done` z akceptacją użytkownika; ścieżka zapisu z planu 777 (TASK-0646) gotowa.

## Recommended execution

`claude-opus-5-5`, reasoning `high`; review przed zapisem: `claude-opus-5-5`, reasoning `high`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GRID_ENGINE_V3_NEURAL_EXECUTION_PLAN.md`
- `ai_docs/delivery/GAME_777_GRID_REVERIFICATION_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-262)

## Scope

- `scripts/reverify_777_grids.py`: tryb `--fill-engine nn` (ONNX, CPU) z tymi samymi kontrolami geometrycznymi; decyzje i podgląd jak w dry-runie.
- D-446: dopuszczenie modelu wyłącznie w narzędziu reweryfikacji 777, z przeglądem użytkownika przed zapisem; bez produkcyjnego importu i rolloutu.
- Dry-run pozostałych slotów bez siatki, przegląd, zapis przez ścieżkę Reviewera.

## Out of scope

- Produkcyjny engine geometrii, inne gry.

## Acceptance criteria

- [ ] Dry-run z siecią: więcej pewnych slotów niż hybryda, 0 fałszywie zielonych w przeglądzie użytkownika.
- [ ] Zapis tylko zaakceptowanych zdjęć; licznik „Brakujące plansze” spada zgodnie z raportem.
- [ ] D-446 i CURRENT_STATE zaktualizowane.

## Outcome

Wypełnia agent po pracy.
