---
title: TASK-0652 — Sieć siatek v3: ocena shadow i kalibracja pewności
status: blocked
---

# TASK-0652 — Ocena shadow na zbiorze złotym

## Status

`blocked` — plan zastąpiony przez `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (D-447); ocena to TASK-0674/TASK-0678. Numer koliduje z ukończoną serią „Przybliżona wygrana”; identyfikuj plik pełną ścieżką.

## Goal

Liczbowe porównanie sieci z hybrydą na zbiorze złotym i ustalenie reguły pewności z zerem fałszywie zielonych siatek.

## Dependencies / entry conditions

- TASK-0651 `done`.

## Recommended execution

`claude-opus-5-5`, reasoning `high`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GRID_ENGINE_V3_NEURAL_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-261)

## Scope

- Raport: błąd punktów, poprawność board-level, pokrycie pewnych slotów i fałszywie zielone — sieć vs hybryda, per kategoria trudności (strzałka, prawa kolumna, ręka, rozmazanie, zakrzywienie).
- Reguła pewności: szerokość piku heatmap + zgodność z modelem ekranu z pozostałych plansz + test połówek + kształt.
- Podgląd HTML (pełna siatka, cienka linia) do oceny wizualnej użytkownika.

## Out of scope

- Zapis do bazy.

## Acceptance criteria

- [ ] 0 fałszywie zielonych na zbiorze złotym; poprawność board-level ≥ 98% (D-261).
- [ ] Pokrycie pewnych slotów ≥ 1,5 × hybryda na kategoriach trudnych.
- [ ] Akceptacja wizualna użytkownika.

## Outcome

Wypełnia agent po pracy.
