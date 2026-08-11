---
title: TASK-0223 image selection v10.4 label lattice
status: done
release: "0.5"
last_updated: 2026-08-11
---

# TASK-0223 — Siatka etykiet 3×3

## Goal

Dopasować siatkę dziewięciu numerów przed OCR i usunąć z domyślnej ścieżki
progresywne poziomy 18/36/72.

## Relevant docs

- `ai_docs/tasks/completed/0221-image-selection-v104-baseline.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`

## Verification

Maksymalnie dziewięć cropów i jedno batchowe wywołanie OCR na zdjęcie;
payouty, symbole i refleksy nie mogą wejść do wybranej siatki.

## Outcome

Dodano `GridFirstVisibleSequenceLabelRangeRecognizer`. Adapter dopasowuje
topologię `3×3`, wykonuje jeden batch maksymalnie dziewięciu cropów na JPEG i
odrzuca niejednoznaczną hipotezę. Testy potwierdzają korektę brakującej pierwszej
cyfry przez pozostałe osiem pól oraz dokładny limit batcha.
