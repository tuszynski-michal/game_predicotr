---
title: TASK-0190 anchored OCR from full-resolution geometry
status: done
release: "0.4"
last_updated: 2026-08-08
---

# TASK-0190 — Anchored OCR from full-resolution geometry

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/completed/0189-image-selection-separate-representative-and-range-evidence.md`

## Goal

Użyć jednego batcha trzech kotwic, gdy pełna detekcja wiarygodnie znajduje
plansze, zamiast zawsze uruchamiać fallback 72 cropów.

## Problem

Appearance scan v10 zwraca `board_count=None`, a verifier wymaga wcześniejszego
count do uznania geometrii za kompletną. W profilu 200 wszystkie 99 kandydatów
przeszły przez kosztowny fallback.

## Likely files

- `services/worker/src/game_predictor_worker/images/selection/adapters.py`
- `services/worker/src/game_predictor_worker/images/selection/telemetry.py`
- `services/worker/tests/test_image_selection_adapters.py`

## Proposed solution

- dopuścić stabilny count 1–9 z pełnej detekcji jako lokalny dowód geometrii,
- najpierw OCR pierwszej, środkowej i ostatniej etykiety w jednym batchu,
- fallback uruchamiać tylko po niepowodzeniu kotwic,
- dodać osobne liczniki ścieżek anchored/fallback.

## Verification

- zgodny zakres kotwic pomija fallback,
- brak lub konflikt kotwic uruchamia fallback bez utraty jakości,
- przypadek wielocyfrowy zachowuje pierwszą cyfrę,
- terminalna grupa 1–8 plansz pozostaje obsługiwana.

## Dependencies

- TASK-0189.

## Open questions

Brak pytań blokujących. Próg stabilnej geometrii pozostaje wersjonowanym
parametrem, nie ukrytą stałą adaptera.

## Outcome

Manifest v10.1 zawiera wersjonowaną `FullGeometryPolicy`: stabilna detekcja
`1–9` plansz z confidence co najmniej `0.64` może lokalnie ustalić
`board_count`, nawet gdy appearance scan zwrócił `None`. Polityka jest częścią
fingerprintu. Poprzedni fingerprint v10.1 pozostaje rozwiązywalny bez tej
polityki, a historyczny v10 nie zmienia zachowania.

`FullCandidateVerifier` najpierw uruchamia istniejący
`AnchoredSequenceRangeRecognizer`, który przekazuje pierwszą, środkową i
ostatnią etykietę w jednym batchu. Fallback uruchamia się dopiero po braku lub
konflikcie wyniku kotwic. Lokalny `board_count` pozostaje częścią oceny
reprezentanta i obsługuje również terminalne grupy mniejsze niż dziewięć.

Telemetria udostępnia osobne liczniki prób, sukcesów i błędów:
`anchoredOcrAttempts`, `anchoredOcrSuccesses`, `anchoredOcrFailures`,
`fallbackOcrAttempts`, `fallbackOcrSuccesses` i `fallbackOcrFailures`.

Weryfikacja 2026-08-08:

- szybka ścieżka pomija fallback przy zgodnych kotwicach,
- konflikt kotwic uruchamia fallback,
- terminalna grupa pięciu plansz zachowuje zakres i `board_count=5`,
- zakres `7300–7308` zachowuje pierwszą cyfrę,
- poprzedni fingerprint v10.1 pozostaje rozwiązywalny,
- Ruff: passed,
- mypy pięciu modułów selekcji: passed,
- pełny zestaw selektora, adapterów, joba i benchmarku: 111 passed,
- testy API selekcji i importu: 28 passed,
- `git diff --check`: passed z istniejącymi ostrzeżeniami LF/CRLF.

Nie uruchamiano profilu 200 ani runu 5000/32 000.
