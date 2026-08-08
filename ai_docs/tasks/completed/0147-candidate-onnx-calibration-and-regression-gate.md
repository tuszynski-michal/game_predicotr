---
title: TASK-0147 candidate ONNX calibration and regression gate
status: done
last_updated: 2026-08-08
---

# TASK-0147 — Candidate ONNX, calibration and regression gate

## Status

`done`

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
- `ai_docs/tasks/completed/0146-durable-symbol-model-training-job.md`

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

- [x] ONNX, checkpoint, katalog klas, kalibracja i raport mają zweryfikowane
      SHA-256 oraz wspólny manifest.
- [x] Parity test przechodzi w jawnej tolerancji na reprezentatywnej próbce.
- [x] Kandydat i aktywny model są mierzone na identycznym, nieużywanym w
      treningu zestawie.
- [x] Bramka pokazuje regresję per symbol, nawet jeśli metryka globalna rośnie.
- [x] Model niespełniający progu nie może uzyskać `candidate_ready`.
- [x] Przejście bramki nie zmienia aktywnego modelu.
- [x] Smoke test ONNX Runtime CPU przechodzi w środowisku workera.

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
- Założenie implementacyjne: bramka jest dalszą częścią tego samego trwałego
  joba `symbol_training`. Status `trained` jest checkpointem po treningu, a
  dopiero `candidate_ready` albo kontrolowane `rejected` kończy przetwarzanie
  bez zmiany aktywnego modelu.
- TASK-0148 jest właścicielem encji aktywacji. Do czasu jej implementacji brak
  aktywnego modelu jest jawnie raportowany jako `baseline_unavailable`; nie
  wolno udawać porównania ani blokować pierwszego kandydata wyłącznie dlatego,
  że nie istnieje jeszcze baza odniesienia.

## Outcome

Dodano migrację `0036_symbol_model_candidate_gate`, trwałe statusy bramki,
content-addressed ONNX, katalog klas, kalibrację, raport i wspólny manifest.
Ten sam job po treningu wykonuje cztery checkpointowane etapy i kończy jako
`candidate_ready` albo `rejected`; błąd techniczny pozostaje `failed`. Bramka
mierzy validation/test/regression, parity PyTorch–ONNX, smoke CPU i regresję per
symbol. Brak aktywnego modelu jest jawny jako `baseline_unavailable`, a podanie
bazy wymusza identyczne próbki. Admin pokazuje ostatnią iterację, podstawowe
metryki, raport i przyczyny odrzucenia. Aktywacja nie jest wykonywana.

Weryfikacja: Ruff; 47 skupionych testów API/migracji/OpenAPI/workera; 174 testy
Admina; 35 testów klienta po dodaniu odczytu iteracji; typecheck Admina; szybka
izolowana kontrola mypy modułów workera. Pełny mypy PyTorch przekroczył limit
60 sekund bez wyniku, dlatego nie pozostawiono procesu bez timeoutu.
