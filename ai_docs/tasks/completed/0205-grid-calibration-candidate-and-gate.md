---
title: TASK-0205 grid calibration candidate and gate
status: done
release: "0.5"
last_updated: 2026-08-09
---

# TASK-0205 — Grid calibration candidate and gate

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md
- ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md

## Goal

Tworzyć wersjonowanego kandydata kalibracji narożników i porównywać go z
detektorem.

## Verification

Kandydat bez poprawy średniego/p95 błędu lub kompletności cropów nie przechodzi
bramki.

## Dependencies

TASK-0204.

## Outcome

Kandydat profilu stosuje odporne mediany korekt narożników dokładnie w zakresie
`imageSelectionRunId + positionIndex`; brak zgodnego zakresu pozostawia wynik
detektora. Bramka porównuje mean i p95 błędu z baseline oraz poprawność
rzutowanych quadów na source-disjoint validation. Kandydat bez rzeczywistej
poprawy nie może zostać aktywowany.
