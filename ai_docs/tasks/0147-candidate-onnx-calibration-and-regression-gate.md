---
title: TASK-0147 candidate ONNX calibration and regression gate
status: todo
last_updated: 2026-08-01
---

# TASK-0147 — Candidate ONNX, calibration and regression gate

## Status

`todo`

## Goal

Zamienić checkpoint treningowy w odtwarzalnego kandydata ONNX, skalibrować
confidence i porównać go z aktywnym modelem na rozłącznym zestawie kontrolnym.

## Context

Wysokie accuracy treningowe nie wystarcza do wdrożenia. Model musi działać w
runtime produkcyjnym i nie może ukrywać regresji pojedynczego symbolu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/delivery/MILESTONE_06_6_EXECUTION_PLAN.md`
- `ai_docs/tasks/0146-durable-symbol-model-training-job.md`

## Scope

- eksportować niezmienny model ONNX,
- wykonywać parity test checkpoint–ONNX,
- kalibrować confidence na validation,
- mierzyć aktywny model i kandydata na tym samym test/regression set,
- raportować accuracy, macro recall, metryki per symbol, confusion matrix,
  próg oraz wydajność CPU,
- wersjonować konfigurację bramki i dopuszczalne regresje,
- ustawiać `candidate_ready`, `rejected` albo `failed` bez automatycznej aktywacji.

## Out of scope

- zmiana aktywnego wskaźnika modelu,
- ponowna inferencja danych,
- ręczne poprawianie próbek z poziomu raportu.

## Acceptance criteria

- [ ] ONNX, checkpoint, katalog klas, kalibracja i raport mają zweryfikowane
      SHA-256 oraz wspólny manifest.
- [ ] Parity test przechodzi w jawnej tolerancji na reprezentatywnej próbce.
- [ ] Kandydat i aktywny model są mierzone na identycznym, nieużywanym w
      treningu zestawie.
- [ ] Bramka pokazuje regresję per symbol, nawet jeśli metryka globalna rośnie.
- [ ] Model niespełniający progu nie może uzyskać `candidate_ready`.
- [ ] Przejście bramki nie zmienia aktywnego modelu.
- [ ] Smoke test ONNX Runtime CPU przechodzi w środowisku workera.

## Technical notes

Progi nie powinny być zaszyte tylko w UI. Wersja konfiguracji bramki i jej
checksum są częścią manifestu iteracji.

## Expected files

- `services/worker/src/game_predictor_worker/symbols/`
- `services/worker/tests/`
- `services/api/src/game_predictor_api/application/`
- `services/api/tests/`
- `apps/admin/src/features/model-quality/`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
python -m pytest services/worker/tests -q
python -m pytest services/api/tests -q
npm.cmd test --workspace @game-predictor/admin
```

## Risks / open questions

- Przy małym zestawie testowym raport powinien pokazać przedziały i liczności,
  aby pojedynczy wynik nie był fałszywą gwarancją jakości.

## Outcome

Do uzupełnienia po realizacji.
