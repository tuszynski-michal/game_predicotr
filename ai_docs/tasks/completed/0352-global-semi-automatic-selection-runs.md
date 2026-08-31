---
title: TASK-0352 Global semi-automatic selection runs
status: done
last_updated: 2026-08-31
---

# TASK-0352 — Globalny run, staging i API

## Status

`done`

## Goal

Utrwalić niezależny od gry run półautomatycznej selekcji, jego oczekiwane
zakresy, globalny staging oraz bezpieczne kontrakty HTTP przed implementacją
algorytmu grupowania.

## Relevant docs

- `AGENTS.md`
- `.tmp/TASK-0350-0357-semi-automatic-selection-plan.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- migracja `0087_semi_automatic_image_selection`,
- globalne runy i zakresy bez `gameId`,
- purpose stagingu `semi_automatic_selection`,
- `JobType.SEMI_AUTOMATIC_IMAGE_SELECTION` w istniejącym selection lane,
- capabilities, start/status/ranges/diagnostics/source asset, pause/resume/cancel
  i output acknowledgement,
- idempotencja, trwałość po restarcie oraz scope uploadu/runu.

## Out of scope

- OCR i proof (TASK-0351),
- grupowanie, wybór środka, checkpoint JSONL i handler workera (TASK-0353),
- lokalny writer i UI (TASK-0354–0356).

## Acceptance criteria

- [x] Run i job mają `gameId = null`.
- [x] Ten sam staging i kontrakt zwracają ten sam run.
- [x] Obcy purpose, zmieniony manifest albo źródło innego runu są blokowane.
- [x] Po odtworzeniu serwisu run, zakresy i sterowanie nadal działają.
- [x] Nowy job należy do istniejącego lane selekcji, lecz bez handlera nie jest
      podejmowany przed TASK-0353.
- [x] Migracja jest addytywna i ma bezpieczny downgrade tabel.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_semi_automatic_image_selections.py -q
.venv\Scripts\python.exe -m pytest services/api/tests/test_semi_automatic_selection_migration.py -q
.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api services/api/tests/test_semi_automatic_image_selections.py
.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api/domain/semi_automatic_image_selections.py services/api/src/game_predictor_api/application/semi_automatic_image_selections.py
```

## Outcome

- Dodano migrację `0087`, trwałe modele runu/zakresów i globalny purpose
  browser stagingu.
- Dodano idempotentny application service i lokalne endpointy lifecycle,
  diagnostyki, assetów oraz output acknowledgement.
- Nowy typ joba korzysta wyłącznie z istniejącego slotu selekcji; general lane
  go nie podejmuje, a handler pozostaje poza zakresem do TASK-0353.
- Staging jest przypinany w tej samej transakcji SQL co job i run. Manifest i
  każdy asset są ponownie sprawdzane przez SHA-256.
- Feature flag API pozostaje domyślnie wyłączona.
