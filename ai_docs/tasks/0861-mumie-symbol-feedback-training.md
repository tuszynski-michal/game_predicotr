---
title: TASK-0861 — ograniczony trening symboli po korektach Mumii
status: todo
last_updated: 2026-10-05
---

# TASK-0861 — iteracja symboli feedback

## Status

`todo`

## Goal

Wykonać jedną nową parę RGB/gray na kwalifikowanym feedbacku i ocenić
all-class validation,18 hard-case regression oraz9 diagnostic_test.

## Dependencies / entry conditions

TASK-0860 done, qualified immutable manifest i odpowiedź dotycząca nagrania.
Polecenie operatora obejmuje kontynuację; nie potrzeba rutynowego potwierdzenia.

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
Po kwalifikacji mały diagnostyczny odczyt nowych źródeł pierwszego nagrania
i konkretne przypadki do istniejącej korekty, bez deklaracji accuracy.

## Out of scope

Trening bez kwalifikacji, wybór na diagnostic_test, DB/aktywacja/wdrożenie,
losowe kolejne próby, zmiana starych modeli/partii i pełna geometria.

## Acceptance criteria

- [ ]Jedna para generacji3, qualified input i trwałe admission/budżety/checkpointy.
- [ ]Sampler/RNG zachowują dokładne resume; istniejące warianty bez zmian.
- [ ]Unique264 development,84 validation i jawna lista18 feedback sample_ids.
- [ ]ONNX parity, all-class/reference conflict oraz diagnostic_test9 po wyborze epoki.
- [ ]Raport ujawnia training/validation/test exposure i per-class regresje.
- [ ]Oryginalne SHA bez zmian; testy/lint/types, audit, commit i Outcome.

## Expected files

Istniejące symbol_models.py, symbol_runs.py, symbol_training.py i ich testy;
opcjonalna ocena/batch generacji3 po kwalifikacji, plan/raport/CURRENT_STATE.

## Verification

Focused pytest/lint/mypy120s, nowe procesy admission/status/verify i
rzeczywiste CPU Torch/ORT parity wszystkich84 PNG; GPU jako kontrolowany background.

## Outcome

Do uzupełnienia po wykonaniu. Następna interakcja: etykiety nowych konkretnych
pomyłek, dopiero jeśli kwalifikowany eksperyment osiągnie tę granicę.
