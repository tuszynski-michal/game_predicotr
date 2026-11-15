---
title: TASK-1209 — Akceptacja V3 dla wiązań z brakującymi slotami
status: todo
last_updated: 2026-11-15
---

# TASK-1209 — Akceptacja V3 dla wiązań z brakującymi slotami

## Status

`todo`

## Goal

Zdjęcie z wiązaniem z brakami (D-614) dostaje akceptację V3 dla przypisanych pozycji,
a brakujące pozycje zostają planszami do ręcznej geometrii, bez blokowania akceptacji.

## Context

Akceptacja decyduje o rozpoznaniu symboli (Mumie A2: rewizje `accepted` 170 424/170 424
plansz z komórkami, `needs_review` 94/733). Dziś wymaga kompletu pozycji, braku
`missingPositionIndexes` i braku odroczonej geometrii. Operator: „Pełny automat”.

## Dependencies / entry conditions

- TASK-1208 na tej samej gałęzi.

## Recommended execution

Claude Opus 5.5, reasoning high. Dodatkowy review: Codex (domyślny model CLI `codex`,
warunkowo), reasoning high, skill `audit-task` — zlecony przez operatora.

## Relevant docs

- `AGENTS.md`
- [D-614](../process/decisions/DECISION_LOG_2026.md#d-614--przypisanie-plansz-po-pozycji-strony-3--3-przy-niepełnym-wykryciu)
- [plan](../delivery/PARTIAL_SLOT_BINDING_PLAN_20261115.md)

## Scope

- `qualify_v3_engine_acceptance` i budowa `positions`/`deferred` w repozytoriach
  `v3_engine_acceptance_repository`, `virtual_grid_geometry_repository`,
  `grid_engine_acceptance_repository`: oczekiwane pozycje = zakres minus
  `missingPositionIndexes`; odroczona geometria brakującego slotu nie blokuje.

## Out of scope

- Zmiana bramki cięcia (TASK-1208) i reguły wiązania.

## Acceptance criteria

- [ ] Wiązanie z brakami: przypisane pozycje akceptowane, rewizja `accepted`,
      brakująca pozycja `pending` w ręcznej kolejce geometrii.
- [ ] Odroczona pozycja przypisana nadal blokuje (`V3_ACCEPTANCE_DEFERRED`).
- [ ] Pełne wiązania bez zmian (dotychczasowe testy akceptacji).

## Verification

Testy jednostkowe akceptacji + integracyjne PostgreSQL z
`$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'` (bazy `*_test`).

## Outcome

(do uzupełnienia)
