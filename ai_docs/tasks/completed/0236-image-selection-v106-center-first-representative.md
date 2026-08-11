---
title: TASK-0236 image-selection v10.6 center-first representative
status: done
release: "0.5"
last_updated: 2026-08-11
---

# TASK-0236 — Reprezentant od środka grupy

## Goal

Ograniczyć koszt i liczbę ręcznych wyborów przez sprawdzanie najpierw pięciu
zdjęć ze środka grupy, a dopiero przy ich nieczytelności po trzech zdjęciach z
obu brzegów. Grupa złożona wyłącznie ze słabych obrazów ma zostać odrzucona bez
OCR, modala i pliku wynikowego.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/process/DECISION_LOG.md`

## Outcome

Domyślny manifest `fast-image-selector-v10.6` ma fingerprint
`bedb6d0fcba5e44faffcad849d5aa40d4ecc0e5277a7b0d5876dc000e33c3050`.
Wszystkie źródła nadal przechodzą tani skan granic, ale pełniejsze sprawdzenie
zaczyna się od pięciu centralnych klatek. Jeżeli żadna nie przechodzi łagodnej,
wersjonowanej bramki czytelności, selektor sprawdza po trzy klatki z obu końców;
ostatnim bezpiecznikiem jest najlepszy czytelny rekord taniego skanu.

Czytelny reprezentant bez zakresu kończy się jako `range_required` z zachowanym
`selected_automatic`. Brak czytelnego zdjęcia kończy się bez OCR jako
`skipped_unreadable`. Historyczny manifest v10.5 i jego fingerprint pozostają
rozwiązywalne. Przeszło 181 skupionych testów API/workera, w tym nowe testy
środka, obu brzegów i całkowicie nieczytelnej grupy, oraz Ruff.
