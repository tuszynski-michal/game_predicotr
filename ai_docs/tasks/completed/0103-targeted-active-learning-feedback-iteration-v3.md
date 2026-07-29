---
title: Targeted active-learning feedback and retraining iteration v3
status: done
last_updated: 2026-07-29
---

# TASK-0103 — Targeted active-learning feedback and retraining iteration v3

## Status

`done`

## Goal

Zebrać kolejny checksum-bound batch 30 pełnych plansz z selection v2, zwiększyć
rzeczywiste wsparcie słabych klas `grapes` i `seven`, a następnie zbudować
niezmienną iterację dataset/model/ONNX/calibration v3 i ponownie ocenić
`massImportAllowed`.

## Context

TASK-0102 zwiększył źródło etykiet z 416 do 866 próbek i utworzył iterację v2.
Pion techniczny przeszedł, lecz `bootstrapTargetMet = false`, ponieważ
`grapes` ma 84, a `seven` 64 zaakceptowane próbki. Selection v2 zawiera 30
pełnych pending plansz z 30 różnych źródeł i nie nakłada się na przejrzane
próbki. Predykcje wskazują w batchu 48 komórek `grapes` i 73 komórki `seven`;
to jest priorytet do weryfikacji przez człowieka, a nie automatyczna etykieta.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/quality/m6-symbol-active-learning-selection-v2.json`
- `ai_docs/quality/m6-active-learning-iteration-v2-manifest.json`

## Scope

### A. Review batch v2

- zweryfikować canonical JSON, inventory checksum i brak overlapu,
- pokazać dokładnie 30 plansz w kolejności `selectionRank`,
- zachować 866 istniejących decyzji bez zmiany przy uruchomieniu,
- jawnie zaakceptować albo poprawić wszystkie 450 komórek,
- raportować rzeczywisty support per symbol po zamknięciu batcha.

### B. Retraining v3

- wyeksportować osobny dataset i source-aware split v3,
- trenować z jawnym seedem i limitem czasu pojedynczej komendy,
- utworzyć osobne artefakty PyTorch i ONNX v3,
- zweryfikować parity, kalibrację i kolejny wybór active-learning,
- wykonać dynamiczny vertical slice i checksum-bound manifest iteracji v3,
- ustawić `massImportAllowed` wyłącznie z aktualnego quality gate.

## Out of scope

- automatyczne przypisanie etykiet na podstawie predykcji,
- nadpisanie artefaktów bootstrapu albo iteracji v2,
- rozpoczęcie TASK-0076 przy `massImportAllowed = false`,
- zmiana architektury kolejki albo dodanie Redis/Celery.

## Acceptance criteria

- [x] selection v2 ma 30 pełnych plansz, 30 źródeł i zero reviewed overlap,
- [x] samo uruchomienie zachowuje 866 decyzji byte-for-byte,
- [x] manual gate kończy się 30 rozwiązanymi planszami i 450 decyzjami,
- [x] support per symbol jest liczony z jawnych etykiet, nie z predykcji,
- [x] powstają osobne dataset/split/model/ONNX/calibration/selection/report v3,
- [x] bootstrap i iteracja v2 nadal przechodzą reprodukcję,
- [x] manifest v3 wiąże checksumy wszystkich wejść i wyników,
- [x] `massImportAllowed` wynika wyłącznie z nowego quality gate.

## Expected files

- `artifacts/m6-symbol-review-v16/reviewed-labels.json`
- nowe artefakty iteracji v3 w osobnych rootach
- nowe raporty `ai_docs/quality/*-v3*.json`
- dokumentacja procesu i testów

## Risks / open questions

- Predykowane 48 `grapes` i 73 `seven` nie są ground truth; po review rzeczywiste
  wsparcie może nadal nie osiągnąć celu.
- Osiągnięcie 100 próbek per klasa nie gwarantuje jeszcze wymaganej precision
  na source-disjoint validation.

## Outcome

- selection v2 o SHA-256
  `fda4b76648d7b141ff63ae957bea4cfbc7781ecdd9eb1e9e5e853b3a0be55e62`
  miało 30 pełnych plansz z 30 źródeł, 450 pending komórek i zero overlapu,
- samo uruchomienie zachowało 866 decyzji byte-for-byte; właściciel następnie
  jawnie zaakceptował 30/30 plansz i 450 komórek,
- źródło ma 1316 etykiet o SHA-256
  `08102dcf502498e24e3c28afd895ecaa2358aabb7ffb7929fd1a9e87c8c58e5d`;
  każda klasa przekracza target 100, minimum to `seven = 108`,
- dataset v3 ma 1316 próbek z 40 zdjęć i `bootstrapTargetMet = true`,
- trening 24 epok wybrał epoch 22; source-disjoint test osiągnął
  `0.79233227` accuracy i `0.80828644` macro recall,
- ONNX ma SHA-256
  `2d841dd7be3675d9176990288f3d6a22c3f1a875d71dd69ae1cb3f97950708aa`,
  zero top-one mismatch i maksymalny błąd prawdopodobieństwa `7.153e-7`,
- calibration i selection v3 odtworzyły się bajtowo; dynamiczny vertical slice
  1316 próbek przeszedł z `0.7606383` accuracy i `0.78106706` macro recall,
- bootstrap oraz iteracja v2 nadal przechodzą własne checksum-bound vertical
  slice bez mutacji,
- manifest `m6-active-learning-iteration-v3` ma SHA-256
  `de44d94a29e271a73992d0c2490498db561ba4e27847c0942cbba6b3d48181ef`,
- validation nie ma żadnego threshold candidate spełniającego wymagania
  precision; reason codes to `MODEL_NOT_PRODUCTION_CANDIDATE` i
  `VALIDATION_THRESHOLD_GATE_NOT_MET`. Auto-accept oraz `massImportAllowed`
  pozostają `false`,
- kolejny krok to bounded benchmark lepszego modelu/augmentacji na zamrożonym
  source-aware split, nie automatyczne zbieranie trzeciego batcha.
