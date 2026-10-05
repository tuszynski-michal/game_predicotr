---
title: TASK-0861 — trwały sterownik pasm RGB v2
status: todo
last_updated: 2026-10-05
---

# TASK-0861 — trwały sterownik pasm RGB v2

## Status

`todo`

## Goal

Skrypt w repo wykonuje pasmo dla ośmiu symboli po kolei: podgląd → zatrzymanie na bramce operatora → po zgodzie zapis i weryfikacja; wznawialny po części, z logiem i raportem pasma.

## Context

Etap A planu `ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md`
(zaakceptowany przez operatora 2026-10-05). Metoda i ograniczenia:
`ai_docs/guides/SYMBOL_RGB_FEEDBACK_HANDOFF_20261005.md`.

## Dependencies / entry conditions

- Plan zaakceptowany; poprzednie taski etapu A wykonane w kolejności planu.

## Recommended execution

`claude-sonnet-5-5`, reasoning `medium` (zgodnie z tabelą planu; audyt wstrzymany
przez operatora 2026-10-01).

## Relevant docs

- `ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md`
- `ai_docs/guides/SYMBOL_RGB_FEEDBACK_HANDOFF_20261005.md`
- `ai_docs/process/DECISION_LOG.md` (D-466)

## Scope

- `scripts/run_symbol_rgb_bands.ps1` (proponowany) i runbook w `ai_docs/guides/`.

## Out of scope

- Zapis w bazie operatora (etap B), trening i zmiana checkpointu CNN,
  zatwierdzanie komórek, geometria.

## Acceptance criteria

- [ ] Suchy przebieg pasma < 60% w trybie tylko podgląd.
- [ ] Wznowienie po przerwaniu opisane i sprawdzone.

## Test cases

- Suchy przebieg; parsowanie skryptu PowerShell.

## Outcome

Brak.
