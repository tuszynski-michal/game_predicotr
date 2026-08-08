---
title: TASK-0191 adaptive multi-frame range consensus
status: done
release: "0.4"
last_updated: 2026-08-08
---

# TASK-0191 — Adaptive multi-frame range consensus

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/completed/0190-image-selection-anchored-ocr-from-full-resolution-geometry.md`

## Goal

Zakończyć zbieranie dowodów numeru po pewnym konsensusie, zachowując pełne
top-12 jako fallback dla trudnych grup.

## Problem

V10 weryfikuje sekwencyjnie całą shortlistę nawet wtedy, gdy pierwsze poprawne
klatki zgodnie wskazują ten sam zakres.

## Likely files

- `services/worker/src/game_predictor_worker/images/selection/engine.py`
- `services/worker/src/game_predictor_worker/images/selection/manifest.py`
- `services/worker/tests/test_fast_image_selector.py`

## Proposed solution

- wersjonować poziomy `2 -> 4 -> 8 -> 12` w manifeście,
- kończyć wyłącznie OCR po dwóch niezależnych zgodnych odczytach wysokiej
  pewności,
- konflikt lub brak wyniku rozszerza kolejny poziom,
- ranking reprezentanta nadal obejmuje całą grupę.

## Verification

- dobra grupa kończy zakres po dwóch kandydatach,
- konflikt rozszerza aż do top-12,
- wynik jest niezależny od kolejności ukończenia pracy,
- liczba weryfikacji i powód stopu trafiają do telemetry.

## Dependencies

- TASK-0190.

## Open questions

Brak pytań blokujących. Poziomy adaptacyjne są częścią fingerprintu selektora.

## Outcome

Manifest v10.1 zawiera fingerprintowaną `AdaptiveRangeConsensusPolicy` z
poziomami `2 -> 4 -> 8 -> 12` i wymaganiem dwóch niezależnych, zgodnych odczytów
o confidence co najmniej równym progowi manifestu. Poprzedni fingerprint v10.1
z samą polityką geometrii oraz pierwszy fingerprint v10.1 pozostają
rozwiązywalne.

Selektor kończy OCR po potwierdzeniu konsensusu, ale wszystkie pozostałe
elementy top-12 nadal przechodzą pełną ocenę reprezentanta. Brak lub niska
pewność rozszerza następny poziom. Wykrycie dwóch różnych zakresów utrzymuje OCR
aż do końca shortlisty. Wyniki późniejszych ocen reprezentanta są jawnie
pozbawiane dowodu zakresu, także dla starszego adaptera bez dedykowanej metody.

`FullCandidateVerifier` udostępnia `assess_representative()` bez OCR oraz
telemetrię: `rangeEvidenceVerifications`, `rangeConsensusEvidenceCount`,
`rangeConsensusCandidateCount` i osobne liczniki dla `confirmed`,
`conflict_exhausted` oraz `no_consensus_exhausted`.

Weryfikacja 2026-08-08:

- zgodne pierwsze dwie klatki kończą OCR po dwóch dowodach,
- dwa braki rozszerzają poziom do czterech i kończą po dwóch późniejszych
  zgodnych odczytach,
- konflikt rozszerza OCR do całego top-12,
- ranking nadal wybiera poprawnego reprezentanta spośród wszystkich 12 klatek,
- dwa deterministyczne uruchomienia konfliktu zwracają identyczny wynik,
- Ruff: passed,
- mypy trzech zmienionych modułów: passed,
- pełny zestaw selektora, adapterów, joba i benchmarku: 114 passed,
- testy API selekcji i importu: 28 passed,
- `git diff --check`: passed z istniejącymi ostrzeżeniami LF/CRLF.

Nie uruchamiano profilu 200 ani runu 5000/32 000.
