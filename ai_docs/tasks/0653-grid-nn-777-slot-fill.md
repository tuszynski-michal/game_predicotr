---
title: TASK-0653 — Sieć siatek v3: dorysowanie slotów 777 w narzędziu reweryfikacji
status: blocked
---

# TASK-0653 — Użycie sieci w reweryfikacji 777

## Status

`blocked` — propozycję uzupełniania slotów historycznego 777 siecią wycofano. Obowiązuje `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (D-447); TASK-0645–0647 nie otrzymują takiej integracji. D-446 dotyczy „Przybliżonej wygranej”. Numer koliduje z ukończoną serią o tej nazwie; identyfikuj plik pełną ścieżką.

## Goal

Historyczna, niewykonywana propozycja zastąpienia kroku „dorysowania” w hybrydzie 777. D-446 nie jest jej decyzją.

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
- Wycofana propozycja dopuszczenia modelu w narzędziu reweryfikacji 777; brak zgody na ten zakres.
- Dry-run pozostałych slotów bez siatki, przegląd, zapis przez ścieżkę Reviewera.

## Out of scope

- Produkcyjny engine geometrii, inne gry.

## Acceptance criteria

- [ ] Dry-run z siecią: więcej pewnych slotów niż hybryda, 0 fałszywie zielonych w przeglądzie użytkownika.
- [ ] Zapis tylko zaakceptowanych zdjęć; licznik „Brakujące plansze” spada zgodnie z raportem.
- [ ] Ten plik pozostaje historyczny i zablokowany; nie uruchamiać wykonania.

## Outcome

Wypełnia agent po pracy.
