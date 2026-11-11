---
title: Budżet prepare kohorty korekt
status: done
last_updated: 2026-11-12
---

# TASK-1187 — Budżet prepare kohorty korekt

## Status

`done`

## Goal

Przebieg uczenia z korekt Mumie a2 nie kończy się `JOB_EXECUTION_FAILED`
(`OperationalError`) przy tworzeniu kohorty.

## Context

Pierwszy przebieg po TASK-1186 (learning `1bdf4a48`, 2026-11-12 00:22) padł po 77 s na
etapie `learning`, zanim powstała kohorta. Worker wywołuje `prepare` kohorty, który
ponownie liczy pełny chroniony podział (~55 s na danych operatora) pod wspólnym
budżetem 60 s; `CohortDeadline` skraca `statement_timeout` do pozostałego czasu, więc
PostgreSQL anuluje zapytanie (`OperationalError`). TASK-1186 podniósł budżet tylko w
podglądzie.

## Dependencies / entry conditions

- `main` v1.7.609 (`78ebc9bf`), D-603.
- Operator polecił przeprowadzić trening do końca (2026-11-12).

## Recommended execution

claude-opus-5-5 / high — jednowierszowa poprawka budżetu w ślad za D-603.

## Relevant docs

- `AGENTS.md`
- [D-603](../../process/decisions/DECISION_LOG_2026.md#d-603--pozycja-kopii-bez-plansz-i-dłuższy-odczyt-podziału)

## Scope

- `prepare` kohorty z polityką z `CORRECTION_POLICIES` używa `LEARNING_SPLIT_SECONDS`.

## Out of scope

- Budżety stron `capture`/`materialize`, `freeze` i `currentness` (odczyt populacji
  4 importów: 1,8 s).
- Przyspieszenie samego podziału.

## Acceptance criteria

- [x] `prepare` z polityką korekt v2/v4 tworzy budżet 120 s, inna polityka 60 s.
- [x] Testy kohort bez nowych porażek.

## Expected files

- `services/api/src/game_predictor_api/application/grid_training_cohort_commands.py` — `prepare`
- `services/api/tests/test_grid_training_cohort_core.py`

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q services/api/tests/test_grid_training_cohort_core.py services/api/tests/test_grid_correction_cohort_contract.py
```

## Outcome

Commit: v1.7.610 (hash dopisuje kolejny commit).

- `prepare` kohorty korekt ma budżet 120 s; test parametryczny v2/v4/brak polityki PASS.
- `test_grid_training_cohort_core.py`: te same 6 zastanych FAIL co na `main`;
  `test_grid_correction_cohort_contract.py`: 2 zastane FAIL także na kodzie sprzed
  TASK-1186 (570fbe25). Ruff PASS, mypy --strict bez błędów w zmienionym module.
- Odczyt populacji 4 importów Mumie a2: 1,8 s, więc pozostałe kroki mieszczą się w 60 s.
- Audyt krzyżowy niewykonany (poprawka w ślad za D-603, polecenie operatora).
