---
title: TASK-0861 — ograniczony trening symboli po korektach Mumii
status: done
last_updated: 2026-10-06
---

# TASK-0861 — iteracja symboli feedback

## Status

`done`

## Goal

Wykonać jedną nową parę RGB/gray na kwalifikowanym feedbacku i ocenić
all-class validation,18 hard-case regression oraz9 diagnostic_test.

## Dependencies / entry conditions

TASK-0860 done, qualified immutable manifest i odpowiedź dotycząca nagrania.
Polecenie operatora obejmuje kontynuację; nie potrzeba rutynowego potwierdzenia.
TASK-0862 odtworzył exact dostęp przez persisted source location pod nowym
parent C:\Users\tuszy\Documents\mumie. Manifest/SHA/podział i settings runu
pozostają takie same. Wznowić istniejący RGB run zamiast tworzyć kolejny.

## Recommended execution

gpt-6.1-sol, high; własny odrębny review oraz test resume, bez delegowania.
Po niespełnieniu83/84/per-class gate zachować wyniki i zakończyć bez kolejnej próby.

## Relevant docs

- AGENTS.md; ai_docs/README.md; ai_docs/process/CURRENT_STATE.md
- ai_docs/requirements/VISION_LAB.md; ai_docs/architecture/VISION_LAB.md
- ai_docs/delivery/MUMIE_SYMBOL_FEEDBACK_ITERATION_20261005.md
- ai_docs/tasks/completed/0860-mumie-symbol-feedback-qualification.md

## Scope

Generacja3, sampler feedbackweight4, dokładne RNG/resume i unikalne metryki;
dwa bounded from-scratch runy20epochs/1800s/10000steps, parity/ocena.
Po ocenie kontynuować TASK-0863: operator wskazał nowe trzecie nagranie
zamiast kolejnych źródeł pierwszego. Osobny task obejmuje diagnostyczny
odczyt60 zdjęć i konkretne przypadki do korekty, bez deklaracji accuracy.

## Out of scope

Trening bez kwalifikacji, wybór na diagnostic_test, DB/aktywacja/wdrożenie,
losowe kolejne próby, zmiana starych modeli/partii i pełna geometria.

## Acceptance criteria

- [x] Jedna para generacji3, qualified input i trwałe admission/budżety/checkpointy.
- [x] Sampler/RNG zachowują dokładne resume; istniejące warianty bez zmian.
- [x] Unique264 development,84 validation i jawna lista18 feedback sample_ids.
- [x] ONNX parity, all-class/reference conflict oraz diagnostic_test9 po wyborze epoki.
- [x] Raport ujawnia exposure i rzeczywisty brak wyników po utracie źródeł.
- [x] Oryginalne SHA bez zmian; testy/lint/types, audit, commit i Outcome.

## Expected files

Istniejące symbol_models.py, symbol_runs.py, symbol_training.py i ich testy;
opcjonalna ocena/batch generacji3 po kwalifikacji, plan/raport/CURRENT_STATE.

## Verification

Focused pytest/lint/mypy120s, nowe procesy admission/status/verify i
rzeczywiste CPU Torch/ORT parity wszystkich84 PNG; GPU jako kontrolowany background.

## Outcome

Completed: `v1.7.209`; original implementation checkpoint
`v1.7.207` / `7647ccb6afe13f181513bbfab5b881c036d8f4e4` retained in history.
One RGB/gray pair succeeded,20epochs/200steps each, best epochs
11/11. RGB resumed its existing ID
after exact source restoration; no new RGB or random rerun.
Validation RGB/gray/fusion: 83/83/83 out of84; unchanged per-class
V1 gate rgb=True, gray=True, fusion=True. Pair qualified=True.
Feedback regression 18/18/18 out of18 training targets;
diagnostic 9/9/9 out of9, post-selection/two classes only.
Neither result is independent population accuracy. Actual CPU Torch/ORT parity
passes all84 per branch, max errors 2.86102295e-06/
3.81469727e-06.
Unique264 development and318 weighted draws are recorded;84 validation and9
diagnostic are excluded from sampling. Both workers exited; durable checkpoints,
budgets/history and artifact hashes remain. Evaluation in two fresh processes
reproduces `evaluation-e3d948f8852fa5287dbfee15501b4c8c8c7626ac932df495f8d3fe813792e2f9.json`. Original data/SHA/labels/models are preserved.
Prior43 focused training/feedback tests, Ruff and scoped mypy PASS; source
relocation added29+28 passing regressions. Final separate review has no P0–P2.
All acceptance criteria and Definition of Done met. Full audit:
ai_docs/quality/MUMIE_SYMBOL_FEEDBACK_TRAINING_20261006.md.
No DB/activation/merge/push/deployment. Continue authorized TASK-0863 on the
new independent third recording; no routine operator confirmation is needed.
