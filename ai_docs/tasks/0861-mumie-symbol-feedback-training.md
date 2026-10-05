---
title: TASK-0861 — ograniczony trening symboli po korektach Mumii
status: blocked
last_updated: 2026-10-06
---

# TASK-0861 — iteracja symboli feedback

## Status

`blocked`

## Goal

Wykonać jedną nową parę RGB/gray na kwalifikowanym feedbacku i ocenić
all-class validation,18 hard-case regression oraz9 diagnostic_test.

## Dependencies / entry conditions

TASK-0860 done, qualified immutable manifest i odpowiedź dotycząca nagrania.
Polecenie operatora obejmuje kontynuację; nie potrzeba rutynowego potwierdzenia.
Manifest przeszedł kwalifikację, lecz obecnie blokuje go brak folderu źródłowego
481537–500000 cut. Operator otrzymał pytanie o nową lokalizację dokładnych zdjęć.

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
- [x] Sampler/RNG zachowują dokładne resume; istniejące warianty bez zmian.
- [ ]Unique264 development,84 validation i jawna lista18 feedback sample_ids.
- [ ]ONNX parity, all-class/reference conflict oraz diagnostic_test9 po wyborze epoki.
- [x] Raport ujawnia exposure i rzeczywisty brak wyników po utracie źródeł.
- [ ]Oryginalne SHA bez zmian; testy/lint/types, audit, commit i Outcome.

## Expected files

Istniejące symbol_models.py, symbol_runs.py, symbol_training.py i ich testy;
opcjonalna ocena/batch generacji3 po kwalifikacji, plan/raport/CURRENT_STATE.

## Verification

Focused pytest/lint/mypy120s, nowe procesy admission/status/verify i
rzeczywiste CPU Torch/ORT parity wszystkich84 PNG; GPU jako kontrolowany background.

## Outcome

Implementation checkpoint: `v1.7.207`; this task is not complete.
Generation 3, feedback-weight4 sampling and frozen diagnostic evaluation are
ready. Forty-three focused tests passed, including exact resumes for generations
1/2/3. Ruff and scoped mypy passed with explicit Torch/ONNX typing boundaries.

The real RGB run 8da05da671d645dd9688c217ef094ce9 failed before checkpoint 0
or any optimizer step because the complete 481537–500000 cut folder disappeared.
The directory without cut contains different bytes for all 2,052 images and
cannot substitute. The exact 18 PNGs and decisions remain preserved. No relabeling
is needed. Gray training, real ONNX parity, evaluation and conditional inference
have not run. PID 41612 exited; no duplicate worker was launched.

Evidence: ai_docs/quality/MUMIE_SYMBOL_FEEDBACK_TRAINING_20261006.md.
The actual source location/restoration is the required human-input gate.
After exact-input verify, resume the same RGB run, then run gray and evaluate.
No DB, activation, merge/push or deployment. Separate code review has no open
P0–P2; the plan and Definition of Done are not yet satisfied.
