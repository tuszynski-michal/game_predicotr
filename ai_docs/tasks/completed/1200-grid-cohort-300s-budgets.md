---
title: TASK-1200 — Limity poleceń kohort 300 s
status: done
last_updated: 2026-11-13
---

# TASK-1200 — Limity poleceń kohort 300 s

## Status

`done`

## Goal

Zamrożenie kohorty uczenia Mumie A2 (4847 źródeł) mieści się w budżecie:
polecenia kohort, podział korekt i pojedyncze zapytanie mają po 300 s.

## Context

Uczenie `170f610d` (kohorta `0630f2cc`) dwa razy padło przy zamrażaniu z
`GRID_COHORT_TIMEOUT` („metadata closure exceeded its bounded lock budget”),
również bez równoległych jobów. Pomiar w wycofanej transakcji: walidacja 2,7 s,
członkowie 19,7 s, blokady 5,2 s, `register_cohort_use` 37,8 s (≈ 65 s przy
budżecie 60 s; jedno zapytanie > 30 s). Operator (2026-11-13): „ustaw takie
limity na 300 sek, bo często się to sypie przez wąskie limity”.

## Dependencies / entry conditions

TASK-1199 (v1.7.625, `7203e1db`) na tej samej gałęzi. Bez migracji i bez zmiany
kontraktu API.

## Recommended execution

Claude Opus 5.5, reasoning standard — zmiana trzech stałych i testów; operator
zlecił bezpośrednio. Bez audytu krzyżowego (brak planu z kolumną
`Dodatkowy review`).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- [D-607](../../process/decisions/DECISION_LOG_2026.md#d-607--limity-poleceń-kohort-300-s)
- [D-603](../../process/decisions/DECISION_LOG_2026.md#d-603--pozycja-kopii-bez-plansz-i-dłuższy-odczyt-podziału)

## Scope

- `services/api/src/game_predictor_api/domain/grid_training_cohorts.py`:
  `COMMAND_SECONDS = 300`, `LEARNING_SPLIT_SECONDS = 300`, nowy
  `STATEMENT_SECONDS = 300`.
- `services/api/src/game_predictor_api/storage/grid_training_cohort_repository.py`:
  `CohortDeadline.check` i `apply_statement_timeout` ograniczają
  `statement_timeout` przez `STATEMENT_SECONDS` zamiast stałej 30 000 ms.
- Testy budżetów w `services/api/tests/test_grid_training_cohort_core.py`.

## Out of scope

- Inne limity 30 s (pomiary jakości siatek, retencja zasobów kohort).
- Zastane porażki `test_grid_training_cohort_core.py` (14, identyczne na `main`).

## Acceptance criteria

- [x] Domyślny budżet `CohortDeadline` i budżet podziału wynoszą 300 s, a
  `statement_timeout` jednego zapytania do 300 000 ms.
- [x] Przygotowanie kohorty korekt i zwykłej używa nazwanych budżetów (300 s).
- [x] Brak nowych porażek względem `main` w testach kohort i uczenia.

## Technical notes

Semantyka bez zmian: po wyczerpaniu budżetu `GRID_COHORT_TIMEOUT` (503), bez
zawężania populacji; `ROLLBACK` po przerwanym savepoincie nie wykonuje `SET`.

## Expected files

- `services/api/src/game_predictor_api/domain/grid_training_cohorts.py`
- `services/api/src/game_predictor_api/storage/grid_training_cohort_repository.py`
- `services/api/tests/test_grid_training_cohort_core.py`
- `ai_docs/process/DECISION_LOG.md`, `decisions/DECISION_LOG_2026.md`,
  `decisions/DECISION_INDEX_ARCHIVE.md`, `ai_docs/architecture/VISION_LAB.md`

## Test cases

- Zegar 299 s: domyślny i podziałowy budżet przechodzą; 301 s: oba rzucają
  `GRID_COHORT_TIMEOUT` z „300 second budget”.
- Pierwsze zapytanie dostaje `statement_timeout=300000`, przy 2 s do końca 2000.
- `prepare` dla polityk v2/v4 i bez polityki dostaje 300 s.

## Verification

```powershell
# z worktree, runner usuwa finder edytowalnej instalacji i wstawia ścieżki worktree
.\.venv\Scripts\python.exe <runner> -q services/api/tests/test_grid_training_cohort*.py services/api/tests/test_grid_correction*.py services/api/tests/test_grid_learning*.py
```

## Outcome

Commit: v1.7.626 (hash dopisuje kolejny commit).

- Wynik: trzy budżety po 300 s (D-607).
- Weryfikacja: 363 testy kohort/uczenia (API i worker): 349 PASS, 14 FAIL
  identycznych jak na `main` (zastane, poza zakresem; 0 nowych porażek); ruff
  check/format PASS; mypy `--strict` zmienionych modułów PASS.
- Ryzyko: blokady gry przy zamrażaniu do 300 s. Worker `general` musi zostać
  zrestartowany, by wczytać nowe limity (API przeładowuje się samo z `main`).
