---
title: TASK-0193 deterministic parallel candidate verification
status: done
release: "0.4"
last_updated: 2026-08-08
---

# TASK-0193 — Deterministic parallel candidate verification

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/completed/0192-image-selection-progressive-visible-label-fallback.md`
- `ai_docs/tasks/completed/0176-worker-lane-resource-budgets-and-admin-status.md`

## Goal

Zmniejszyć czas trudnych grup bez zmiany liczby ani wyniku pełnych weryfikacji.

## Problem

Pełne weryfikacje top-k są sekwencyjne. Lokalny predictor jest mutowalny i nie
może być bezpiecznie współdzielony przez kilka wątków.

## Likely files

- `services/worker/src/game_predictor_worker/images/selection/job.py`
- `services/worker/src/game_predictor_worker/images/selection/engine.py`
- `services/worker/src/game_predictor_worker/images/selection/adapters.py`
- supervisor lane i testy workera

## Proposed solution

- porównać 1 i 2 izolowane instancje verifiera/predictora,
- zachować bounded CPU i pamięć lane,
- zbierać wyniki w kolejności shortlisty niezależnie od czasu ukończenia,
- aktywować 2 workery wyłącznie przy identycznym wyniku i realnym zysku.

## Verification

- identyczne decyzje, zakresy, reprezentanty i reason codes dla 1/2 workerów,
- brak współdzielenia predictora Paddle,
- cancel, lease i checkpoint pozostają bounded,
- brak regresji równoległego Importu layoutów.

## Dependencies

- TASK-0192.

## Open questions

Brak pytania produktowego. Aktywacja dwóch verifierów zależy wyłącznie od
pomiaru identyczności, pamięci i czasu.

## Outcome

Dodano `DeterministicParallelCandidateVerifier`, który przyjmuje wyłącznie jedną
lub dwie różne instancje verifiera. Shortlista jest dzielona deterministycznie
na dwie szeregowe partycje. Jedna instancja nigdy nie jest używana równolegle
sama ze sobą, a wyniki wracają w pierwotnej kolejności kandydatów niezależnie od
czasu ukończenia wątków.

Engine wykonuje poziomy adaptacyjne jako bounded batche. Poziomy dowodu zakresu
mają maksymalnie cztery nowe elementy, natomiast po potwierdzeniu zakresu
pozostała ocena reprezentantów jest dzielona między oba verifiery bez OCR.
Fallback do starszego verifiera bez metody batchowej pozostaje sekwencyjny i
zgodny wstecznie.

Produkcyjny lane przy budżecie czterech wątków używa `2 scan workers + 2
verification workers`. Każdy verification worker tworzy własny predictor
Paddle, recognizer kotwic, fallback etykiet oraz detector. Telemetria raportuje
liczbę batchy, elementów i wykorzystanych slotów. Budżet 1–3 pozostawia jeden
verifier. Samodzielne CLI używa poprawnego progresywnego adaptera v5, ale
pozostaje jednowątkowe dla OCR.

Test parity porównuje pełny wynik domenowy jednego i dwóch verifierów, w tym
decyzje, zakres, reprezentanta i reason codes. Test izolacji potwierdza dwie
jednoczesne partycje bez współbieżnego wejścia do tej samej instancji. Fabryka
produkcyjna tworzy dwa różne predictory, a CLI zachowuje łączny budżet czterech
zewnętrznych workerów.

Weryfikacja 2026-08-08:

- Ruff: passed,
- mypy czterech zmienionych modułów: passed,
- selektor, job, adaptery, benchmark harness, CLI i runtime: 134 passed,
- API selekcji/importu, status lane i runtime lane: 31 passed.

Nie wykonano jeszcze rzeczywistego porównania czasu ani peak RSS na dwóch
predictorach. Należy ono do TASK-0194 i może zakończyć się powrotem do jednego
verifiera, jeżeli zysk nie uzasadni pamięci.
