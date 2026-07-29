---
title: Classifier and review vertical slice acceptance
status: done
last_updated: 2026-07-29
---

# TASK-0067 — Classifier and review vertical slice acceptance

## Status

`done`

## Goal

Zebrać deterministyczny, wersjonowany dowód pełnego pionu M6 od
zaakceptowanej geometrii v16 i cropów przez lokalną inferencję ONNX do decyzji
manual review oraz opisać bezpieczny retraining i rollback modelu.

## Context

M6.1 dostarczyło zaakceptowany korpus v16, 416 jawnie oznaczonych cropów i
source-aware split. M6.2 dostarczyło bootstrapowy model ONNX, kalibrację oraz
politykę `manual-review-only`. M6.3 dostarczyło trwały batch review, pełny
workspace decyzji i niezmienne wersje feedbacku. Ostatnia bramka M6 ma połączyć
te dowody bez uruchamiania masowego importu i bez przedstawiania słabego modelu
bootstrapowego jako gotowego do auto-accept.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0062-onnx-export-local-inference-parity.md`
- `ai_docs/tasks/completed/0063-confidence-calibration-active-learning-selection.md`
- `ai_docs/tasks/completed/0064-review-storage-admin-api.md`
- `ai_docs/tasks/completed/0065-manual-review-admin-ui.md`
- `ai_docs/tasks/completed/0066-review-corrections-labeled-feedback-export.md`

## Scope

- jeden bounded runner pionu: zaakceptowany raport geometrii v16 → inventory i
  cropy → checksum-bound ONNX → skalibrowane predykcje → jawne decyzje review,
- metryki automatyczne globalne i per symbol na oznaczonym golden corpus,
- metryki po review, czas inferencji, udział manual review i kompletne
  provenance wejść,
- deterministyczny raport JSON i schema z kontrolą odtworzenia byte-for-byte,
- testy błędów checksum, wersji, geometrii, cropów, modelu i niepełnych decyzji,
- instrukcja batchowego retrainingu, promocji i rollbacku bez mutacji
  opublikowanego modelu.

## Out of scope

- ponowny trening albo zmiana architektury modelu,
- włączenie auto-accept lub auto-reject,
- masowe, wielogodzinne przetwarzanie zdjęć,
- zmiana geometrii v16, UI manual review albo schematu PostgreSQL,
- publikacja modelu lub snapshotu do aplikacji mobilnej.

## Acceptance criteria

- [x] runner weryfikuje zaakceptowaną geometrię, inventory, cropy, model ONNX,
  kalibrację i decyzje review przed policzeniem wyniku,
- [x] wszystkie oznaczone próbki golden corpus otrzymują `modelVersion`,
  confidence i deterministyczny wynik ONNX,
- [x] raport zawiera accuracy/macro recall i metryki per symbol przed review,
  wynik po review, czas inferencji i udział manual review,
- [x] polityka `manual-review-only` pozostaje wymuszona, a niespełnione progi
  są raportowane jako powód retrainingu zamiast ukrywane,
- [x] zmiana dowolnego checksumowanego wejścia lub brak decyzji kończy przebieg
  fail-closed stabilnym kodem,
- [x] drugi przebieg `--check --require-pass` odtwarza ten sam raport,
- [x] dokumentacja opisuje retraining, promocję i rollback modelu,
- [x] właściwe testy, lint i typecheck zmienionych części przechodzą.

## Technical notes

- Goldenem odbioru jest zaakceptowane v16 powiązane z 416 decyzjami
  `reviewed-cell-labels-v1`; nie należy traktować 5389 pending cropów jako
  danych ground truth.
- Wynik „po review” oznacza jawne zastosowanie zapisanej etykiety człowieka do
  dokładnego `cropSampleId`, a nie automatyczne uczenie online.
- Model bootstrapowy pozostaje `manual-review-only`; dlatego udział review może
  wynosić 100% i nadal być poprawnym, jawnym wynikiem bramki technicznej.
- Wszystkie długie komendy muszą mieć ograniczony timeout i bounded wejście.

## Expected files

- `services/worker/src/game_predictor_worker/images/symbol_vertical_slice.py`
- `services/worker/tests/test_symbol_vertical_slice.py`
- `scripts/accept_m6_classifier_vertical_slice.py`
- `ai_docs/quality/m6-classifier-review-vertical-slice.schema.json`
- `ai_docs/quality/m6-classifier-review-vertical-slice-report.json`
- `ai_docs/quality/M6_MODEL_RETRAINING_ROLLBACK.md`
- dokumentacja procesu, architektury i bieżącego stanu

## Verification

```powershell
python scripts/accept_m6_classifier_vertical_slice.py
python scripts/accept_m6_classifier_vertical_slice.py --check --require-pass
python -m pytest services/worker/tests/test_symbol_vertical_slice.py
python -m ruff check services/worker/src/game_predictor_worker/images/symbol_vertical_slice.py services/worker/tests/test_symbol_vertical_slice.py scripts/accept_m6_classifier_vertical_slice.py
python -m mypy services/worker/src/game_predictor_worker/images/symbol_vertical_slice.py scripts/accept_m6_classifier_vertical_slice.py
```

## Risks / open questions

- Bootstrapowe metryki modelu są poniżej celu jakościowego; TASK-0067 ma to
  raportować i skierować do kolejnego batchowego retrainingu, nie obniżać progi.
- Dowód integracji z PostgreSQL pozostaje w testach TASK-0064–0066; runner
  odbioru nie może tworzyć drugiego, konkurencyjnego magazynu decyzji.

## Outcome

Completed 2026-07-29.

### Changed

- Dodano bounded orkiestrator `classifier-review-vertical-slice-v1`, który
  ponownie buduje zaakceptowany inventory v16, weryfikuje kompletny łańcuch
  dataset/split/ONNX/kalibracja/active-learning i uruchamia lokalną inferencję.
- Raport obejmuje 387 plansz, 5805 cropów, 416 oznaczonych inferencji,
  metryki globalne/split/per symbol, 24 whole-board resolution replay oraz
  zamrożoną obserwację czasu.
- Dodano schema raportu, testy czystej logiki i dokument batchowego
  retrainingu, promocji oraz rollbacku.
- Zaktualizowano architekturę, strategię testów, plan M6, Decision Log i
  `CURRENT_STATE.md`.

### Verification results

- `accept_m6_classifier_vertical_slice.py --check --require-pass` przeszedł
  dwukrotnie z raportem SHA-256
  `552a54e55b93ad05e6016a2807987066dd781251ab61583096686f452d1533a1`.
- 30 focused testów classifier/ONNX/confidence/review przeszło. Pierwszy
  przebieg bez `--basetemp` miał 13 błędów setup z powodu ACL systemowego
  `%TEMP%`; powtórka w `.pytest-tmp/task-0067-final-20260729` przeszła.
- Ruff przeszedł dla trzech zmienionych plików Python.
- Strict mypy z `--follow-imports=skip` przeszedł dla dwóch nowych modułów.
  Szeroki graf importów osiągnął wcześniej jawny limit 60 sekund.
- Schema i raport przechodzą parsowanie JSON; raport ma dokładnie 416
  predykcji.

### Not completed

- Nie uruchomiono retrainingu ani nie włączono auto-accept/auto-reject.
- Nie uruchomiono masowego importu. Model ma decyzję
  `retraining_required_before_auto_accept`.
- Cztery historyczne częściowe plansze (56 próbek) nie są udawane jako
  whole-board feedback; replay obejmuje 24 kompletne plansze.

### Documentation updates

- Dodano D-077 oraz
  `ai_docs/quality/M6_MODEL_RETRAINING_ROLLBACK.md`.
- M6.4 i G6 mają status `passed_with_retraining_required`.

### Recommended next task

- Po poleceniu właściciela rozpocząć `TASK-0068 — Versioned image pipeline
  contract`, pierwszy zakres M7.1.
