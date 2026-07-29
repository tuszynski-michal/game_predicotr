---
title: Productionize selected spatial symbol model
status: done
last_updated: 2026-07-29
---

# TASK-0105 — Productionize selected spatial symbol model

## Status

`done`

## Goal

Przenieść wybrany w TASK-0104 checkpoint `spatial-symbol-cnn-v1` do
wersjonowanego, checksum-bound wydania produkcyjnego z ONNX, kalibracją
confidence i dynamicznym vertical slice na aktualnym korpusie.

## Context

TASK-0104 wybrał wariant `spatial` wyłącznie na validation i dopiero potem
otworzył zamrożony test. Checkpoint osiągnął `0.97666667` validation accuracy
oraz `0.96166134` test accuracy, ale nie jest jeszcze używany przez kontrakt
produkcyjny. M6.5 potrzebuje stabilnych sugestii symboli i najwyżej czterech
alternatyw bez naruszania decyzji człowieka.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/MILESTONE_06_5_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0104-bounded-symbol-model-architecture-benchmark.md`
- `ai_docs/quality/m6-symbol-model-validation-selection-report.json`
- `ai_docs/quality/m6-symbol-model-selected-test-report.json`

## Scope

- dodać wersjonowany loader checkpointu `spatial-symbol-cnn-v1`,
- wyeksportować ONNX i sprawdzić parytet PyTorch/ONNX,
- dopasować temperaturę i próg wyłącznie na zamrożonym validation,
- zmierzyć test dopiero po zamrożeniu temperatury i polityki,
- zwracać stabilnie uporządkowane, najwyżej cztery alternatywy symbolu,
- wykonać dynamiczny vertical slice na aktualnym checksum-bound korpusie,
- związać checkpoint, ONNX, kolejność klas, kalibrację i raporty jednym
  manifestem wydania,
- jawnie oddzielić `symbolAutoAcceptEnabled` od globalnego
  `massImportAllowed`.

## Out of scope

- ponowny trening lub zmiana datasetu i splitu,
- wykorzystanie testu do strojenia temperatury albo progu,
- automatyczna akceptacja OCR numerów,
- zmiana decyzji człowieka albo opublikowanego stagingu,
- UI stanowiska review; powstaje w TASK-0107.

## Acceptance criteria

- [x] loader odrzuca niewłaściwą architekturę, klasy, provenance i checksumy,
- [x] checkpoint oraz ONNX są deterministyczne i checksum-bound,
- [x] parytet ma zero top-one mismatch i mieści się w tolerancji numerycznej,
- [x] temperatura i próg wynikają wyłącznie z validation,
- [x] test jest wyłącznie końcowym pomiarem zamrożonej polityki,
- [x] predykcje zawierają najwyżej cztery stabilnie uporządkowane alternatywy,
- [x] vertical slice wyprowadza liczności z aktualnego datasetu i splitu,
- [x] jeden manifest wiąże model, ONNX, klasy, kalibrację i raporty,
- [x] decyzja nie obchodzi `manual_review_only` OCR.

## Expected files

- `services/worker/src/game_predictor_worker/images/symbol_model_release.py`
- `services/worker/src/game_predictor_worker/images/symbol_onnx.py`
- `scripts/release_m6_spatial_symbol_model.py`
- `services/worker/tests/test_symbol_model_release.py`
- `ai_docs/quality/m6-spatial-symbol-model-*.json`
- `artifacts/m6-spatial-symbol-model-release-v1/`
- dokumentacja procesu

## Assumptions and decisions

- Wybrany checkpoint jest kopiowany bajt w bajt; zadanie nie uruchamia treningu.
- `symbolAutoAcceptEnabled` wynika z bieżącej validation confidence policy.
- Globalne `massImportAllowed` pozostaje `false`, gdy OCR numerów ma status
  `manual_review_only`, nawet jeśli symbol confidence gate przejdzie.
- W pełni ręcznie zweryfikowany, ciągły zakres nadal może być publikowany
  ścieżką nadzorowaną zgodnie z D-086.
- Każda komenda potencjalnie ciężka ma jawny timeout nie większy niż 120 sekund.

## Outcome

- Dodano fail-closed loader wybranego spatial checkpointu, kontrakt wydania,
  walidację manifestu i stabilne top-4 sugestie.
- Istniejący eksporter ONNX przyjmuje teraz dowolny `nn.Module` i jawną wersję
  modelu bez zmiany domyślnego kontraktu bootstrapu.
- Checkpoint został skopiowany bez retrainingu. ONNX ma zero top-one mismatch
  na wszystkich trzech splitach, a maksymalny błąd to `0.000002861`.
- Kalibracja validation wybrała temperaturę `1.1515684402` i próg
  `0.88850097`. Test zmierzony po zamrożeniu polityki osiąga przy progu
  precision `0.97674419` oraz coverage `0.82428115`.
- Dynamiczny vertical slice objął 1316 próbek, 84 kompletne oraz 4 częściowe
  plansze. Ogólna accuracy wynosi `0.97492401`.
- `symbolAutoAcceptEnabled = true`; globalne `massImportAllowed = false`
  pozostaje z powodu `SEQUENCE_OCR_MANUAL_REVIEW_ONLY`. D-086 nadal pozwala na
  publikację w pełni ręcznie zweryfikowanego ciągłego zakresu.
- Manifest wydania ma SHA-256
  `9f0dd6f7f67105c9c3b479e9b30cb5f9d58d341e6c5b041564be14963a3db8d0`
  i został odtworzony przez `--check`.
- Weryfikacja:
  - `ruff check` — passed,
  - `ruff format --check` — passed po formatowaniu,
  - `mypy` dla zmienionych modułów — passed,
  - 30 testów modelu, ONNX, confidence, vertical slice i benchmarku — passed,
  - generacja wydania oraz ponowne `--check` — passed w około 26 sekund każde.
- Nie wykonano retrainingu, zmiany OCR, UI ani integracji z operacyjnym API;
  kolejnym zadaniem jest TASK-0106.
