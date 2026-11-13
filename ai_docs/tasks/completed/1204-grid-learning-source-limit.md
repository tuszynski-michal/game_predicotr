---
title: TASK-1204 — Limit populacji uczenia siatek 20 000
status: done
last_updated: 2026-11-13
---

# TASK-1204 — Limit populacji uczenia siatek 20 000

## Status

`done`

## Goal

„Ulepsz siatki z korekt” nie blokuje się, gdy importy z korektami mają razem do 20 000
zdjęć, a każda blokada ma przy przycisku zrozumiały polski opis.

## Context

Mumie A2: nowe korekty w `df5c22e1` wciągnęły import do zakresu; razem 7039 źródeł przy
limicie 5000 (`GRID_CORRECTION_POPULATION_LIMIT`, w panelu „Inny powód (…)”). Operator:
„napraw trwale”. Decyzja: D-610.

## Dependencies / entry conditions

- Baza operatora na `0187_grid_gate_cell_cut`.

## Recommended execution

Claude Opus 5.5, reasoning medium; bez dodatkowego review (polecenie operatora).

## Relevant docs

- `AGENTS.md`
- [D-607](../../process/decisions/DECISION_LOG_2026.md#d-607--limity-poleceń-kohort-300-s)
- [D-610](../../process/decisions/DECISION_LOG_2026.md#d-610--limit-populacji-uczenia-siatek-20-000-źródeł)

## Scope

- `CORRECTION_SOURCE_LIMIT = 20 000` w populacji, obu solverach i schematach
  `validationAssignments`; OpenAPI.
- Migracja `0188_grid_learning_source_limit` (sześć predykatów SQL).
- Polskie opisy wszystkich kodów blokad uczenia i ich wyświetlanie przy przycisku.

## Out of scope

- Zmiana semantyki populacji (całe importy, bufory) i budżetów czasu.

## Acceptance criteria

- [x] Populacja 7039 źródeł przechodzi podział w budżecie (pomiar: 125 s / 300 s).
- [x] Migracja zmienia tylko predykaty, zachowuje uprawnienia i jest odwracalna.
- [x] Każdy kod blokady z kodu uczenia ma polski opis (test pokrycia w Adminie).

## Test cases

- `services/api/tests/test_grid_learning_source_limit.py`: limit, solvery, zamiana
  predykatów, przerwanie przy nieoczekiwanej treści, downgrade i jego blokada.
- `services/api/tests/integration/test_grid_learning_source_limit_postgres.py`.
- `apps/admin/test/grid-model-state.test.mjs`: pokrycie opisów kodów.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_learning_source_limit.py
npm run test --workspace @game-predictor/admin
```

## Risks / open questions

- Przy populacjach bliskich 20 000 czas podziału może przekroczyć 300 s.

## Outcome

Commit: v1.7.634 / `ec2146f1bf3895b41896848cbf381b96f324a3db`.

### Changed

- `domain/grid_correction_split.CORRECTION_SOURCE_LIMIT`, solvery, populacja, schematy,
  OpenAPI; `storage/source_recording_source_limit.py`; migracja 0188; głowa schematu.
- Admin: 40 nowych opisów kodów, fallback „Nieopisany powód blokady”, blokady API w
  „Start jest niedostępny: …”.

### Verification results

- Pomiar w wycofanej transakcji na bazie operatora (kod gałęzi, podniesiony limit
  kontekstu): podział 7039 źródeł w 124,8 s; TRAIN 379/517, VALIDATION 19/60, REG 13/21.
- `test_grid_learning_source_limit`, `test_schema_readiness`, `test_migration_baseline`:
  100 passed (6 nowych).
- Testy podziału, kohort i uczenia: 14 porażek identycznych z `main`
  (`test_grid_correction_split_adapter` ×6, `test_grid_correction_cohort_contract` ×2,
  `test_grid_training_cohort_core` ×6); zero nowych.
- PostgreSQL (jednorazowe bazy): migracja 0188 i 0187 — 2 passed.
- Admin: 865/865, interakcje panelu i Geometrii V3 80/80, tsc i eslint PASS.

### Not completed

- Migracja `0188` na bazie operatora i restart usług (operator).

### Documentation updates

- D-610 (wpis i indeks), `CURRENT_STATE.md`.

### Recommended next task

- Po migracji: uruchomienie uczenia Mumie A2 i ocena bramką v5.
