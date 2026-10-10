---
title: TASK-0873 — trwały sterownik pasm RGB v2
status: done
last_updated: 2026-10-06
---

# TASK-0873 — trwały sterownik pasm RGB v2

## Status

`done`

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

- [x] Suchy przebieg pasma < 60% w trybie tylko podgląd.
- [x] Wznowienie po przerwaniu opisane i sprawdzone.

## Test cases

- Suchy przebieg; parsowanie skryptu PowerShell.

## Outcome

- `scripts/run_symbol_rgb_bands.ps1`: pasmo × osiem symboli, części ≤ 60 000
  komórek (`--shard` po skrócie id, liczność z `index/summary.json`), faza
  `preview` kończy się bramką (`band-<pasmo>-gate.json`, wpis `GATE`), faza
  `apply` dla każdej części: `manifest` → `apply` → `verify`; części z
  `apply-verify.json` pomijane, część z manifestem wznawiana na nim. Proces
  Pythona z limitem 600 s. Poprawka PowerShell 5.1: `$PSScriptRoot` jest pusty
  w bloku `param`.
- Runbook `ai_docs/guides/SYMBOL_RGB_V2_BAND_RUNBOOK.md`.
- Suchy przebieg 2026-10-05 23:29–23:37 UTC: podgląd pasma < 60% dla ośmiu
  symboli (16 481 komórek, 8 części po jednej na symbol, 1–2 min na część),
  bramka zapisana. Wznowienie sprawdzone ponownym uruchomieniem po zmianie
  reguł zapisu (23:41–23:43 UTC): `scope.json` i cache wycinków użyte
  ponownie, wiersze przeliczone dla nowego klucza.
