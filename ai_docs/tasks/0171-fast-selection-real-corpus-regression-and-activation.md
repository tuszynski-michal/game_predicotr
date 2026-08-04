---
title: TASK-0171 fast selection real corpus regression and activation
status: todo
release: "0.4"
last_updated: 2026-08-05
---

# TASK-0171 — Fast selection real-corpus regression and activation

## Status

`todo`

## Goal

Udowodnić na realnym korpusie, że nowa selekcja jest szybka, nie traci różnych
ekranów i może zostać aktywowana dla nowych runów przed końcowym odbiorem
TASK-0157.

## Context

Pełne przebiegi 40 000 zdjęć nie mogą służyć jako metoda strojenia każdej małej
zmiany. Najpierw obowiązują krótkie regresje, a jeden pełny rerun jest końcową
bramką techniczną.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/tasks/0157-image-selection-scale-quality-and-owner-acceptance.md`
- `ai_docs/tasks/completed/0165-image-selection-stage-timing-and-real-corpus-baseline.md`
- `ai_docs/tasks/completed/0166-reduced-jpeg-scan-and-bounded-cpu-budget.md`
- `ai_docs/tasks/completed/0167-appearance-only-sequential-image-grouping.md`
- `ai_docs/tasks/0168-first-usable-range-free-representative-selection.md`
- `ai_docs/tasks/0169-range-agnostic-selection-output-and-import-handoff.md`
- `ai_docs/tasks/0170-versioned-image-scan-cache-and-resume.md`

## Scope

- zbudować niezależny golden kolejnych ekranów i dopuszczalnych granic,
- uruchamiać iteracje najpierw na 500–1000, następnie 3000 zdjęć,
- przygotować dokładnie 40 000 naturalnie uporządkowanych zdjęć i uruchomić
  jeden kontrolowany profil po przejściu krótkich bramek,
- zmierzyć scan throughput, całkowity czas, peak RSS, liczbę grup, false split,
  false merge, output count, cache hits i błędy plików,
- potwierdzić zero wywołań OCR, geometrii plansz i croppera w selekcji,
- porównać liczbę JPEG-ów przekazanych do Importu z liczbą wejść,
- aktywować v9 tylko po wyniku `ready`; inaczej pozostawić status `optimize`.

## Out of scope

- testowanie dokładności OCR, cropów i symboli Importu layoutów,
- pełne 500 000 layoutów,
- profil 100 000 zdjęć w wersji 0.4,
- dalsze strojenie podczas pracującego pełnego joba.

## Acceptance criteria

- [ ] Krótki profil raportuje porównywalny throughput pierwszego przebiegu bez
      cache na komputerze właściciela.
- [ ] Pełny run 40 000 zdjęć zapisuje całkowity czas, throughput i peak RSS bez
      sztywnego progu czasu.
- [ ] Właściciel po otrzymaniu wyniku jawnie wybiera `accepted | optimize`.
- [ ] Golden ma zero fałszywych scaleń różnych kolejnych ekranów.
- [ ] Recall unikalnych kolejnych ekranów wynosi 100%; false split jest jawnie
      raportowany, ale nie może prowadzić do utraty zdjęcia.
- [ ] Każda grupa z dekodowalnym wejściem publikuje jeden reprezentant.
- [ ] OCR, `PageBoardDetector`, homografia, cropy komórek i symbol inference mają
      dokładnie zero wywołań w selektorze.
- [ ] Działający upload nie został zmieniony ani powtórzony przez benchmark.
- [ ] Raport zawiera decyzję `ready | optimize | reject` i porównanie z v8.

## Technical notes

Każdy benchmark ma jawny timeout i cleanup. Pełnego profilu nie wolno uruchomić,
jeśli profil 3000 nie spełnia throughputu albo golden wykazuje false merge.

## Expected files

- `scripts/run_image_selection_benchmark.py`
- `scripts/run_image_selection_benchmark.ps1`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`

## Verification

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_image_selection_benchmark.ps1 -Profile smoke -TimeoutSeconds 300
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_image_selection_benchmark.ps1 -Profile 3000 -TimeoutSeconds 900
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_image_selection_benchmark.ps1 -Profile 30000 -TimeoutSeconds 3600
```

## Risks / open questions

- Końcowa ocena czasu należy do właściciela. Raport nie może sam oznaczyć
  `ready` wyłącznie dlatego, że proces jest szybszy od wersji historycznej.

## Outcome

Do uzupełnienia po realizacji.
