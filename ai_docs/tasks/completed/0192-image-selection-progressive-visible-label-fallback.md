---
title: TASK-0192 progressive visible label fallback
status: done
release: "0.4"
last_updated: 2026-08-08
---

# TASK-0192 — Progressive visible-label fallback

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/completed/0191-image-selection-adaptive-multi-frame-range-consensus.md`

## Goal

Ograniczyć typowy koszt fallbacku OCR bez zmiany jego maksymalnej czułości.

## Problem

Każdy fallback od razu przetwarza do 72 cropów w ośmiu batchach, mimo że dobry
układ może zostać rozstrzygnięty na znacznie mniejszej puli.

## Likely files

- `services/worker/src/game_predictor_worker/images/selection/adapters.py`
- `services/worker/src/game_predictor_worker/images/sequence_ocr.py`
- `services/worker/tests/test_image_selection_adapters.py`
- testy OCR parity

## Proposed solution

- deterministycznie rankować kandydatów etykiet,
- analizować poziomy `18 -> 36 -> 72`,
- zaakceptować wcześniejszy wynik tylko po istniejącej pełnej bramce lattice,
- trudny przypadek kończy identycznym maksymalnym zbiorem 72.

## Verification

- łatwe przypadki kończą na 18 lub 36,
- trudne przypadki uruchamiają 72 i zachowują wynik v10,
- crop wielocyfrowy zachowuje margines,
- telemetry raportuje poziom i liczbę cropów.

## Dependencies

- TASK-0191.

## Open questions

Brak pytań blokujących. Pełny poziom 72 pozostaje obowiązkowym fallbackiem.

## Outcome

Nowe runy v10.1 używają fingerprintowanej
`ProgressiveVisibleLabelFallbackPolicy` z poziomami `18 -> 36 -> 72` oraz
adaptera `visible-sequence-label-range-v5`. Historyczny manifest v10.1 z pełnym
fallbackiem v4 pozostaje rozwiązywalny i zachowuje poprzednie zachowanie.

Kandydaci etykiet są deterministycznie porządkowani według fill ratio, pola i
położenia. Każdy poziom wykonuje OCR wyłącznie dla nowych cropów, a dotychczasowe
wyniki są ponownie używane. Wcześniejsze zakończenie jest możliwe tylko po
przejściu istniejącej bramki lattice: co najmniej sześć inlierów, obecna pierwsza
i ostatnia pozycja oraz pokrycie trzech rzędów i kolumn. Brak pełnego wyniku
rozszerza próbę aż do identycznego maksymalnego zbioru 72 kandydatów.

Telemetria zapisuje liczbę prób poziomów, cropów, poziom rozstrzygnięcia oraz
wyczerpanie pełnego fallbacku. Testy potwierdzają zakończenie na 18, 36 i 72,
parity wyniku poziomu 72 ze starszym adapterem oraz zachowanie poziomego i
pionowego marginesu cropa wielocyfrowego.

Weryfikacja 2026-08-08:

- Ruff: passed,
- mypy trzech zmienionych modułów: passed,
- pełny zestaw selektora, adapterów, joba i benchmarkowego harnessu: 119 passed,
- testy API selekcji i importu: 28 passed.

Nie uruchamiano profilu 200 ani runu 5000/32 000.
