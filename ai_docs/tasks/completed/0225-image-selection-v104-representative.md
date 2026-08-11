---
title: TASK-0225 image selection v10.4 representative
status: done
release: "0.5"
last_updated: 2026-08-11
---

# TASK-0225 — Reprezentant całej grupy

## Goal

Ocenić każde zdjęcie tanim scoringiem, nie stosować early exit i wybrać
najlepszy czytelny reprezentant bez wymagania jego własnej pełnej geometrii.

## Relevant docs

- `ai_docs/tasks/completed/0222-image-selection-v104-group-boundaries.md`
- `ai_docs/tasks/completed/0224-image-selection-v104-hybrid-ranges.md`

## Verification

Najlepszy czytelny kandydat całej grupy jest wybierany deterministycznie, a
miękkie problemy geometrii wpływają na ranking zamiast wymuszać manual review.

## Outcome

Każdy JPEG grupy otrzymuje tanią ocenę, a dowód zakresu jest bounded do dwóch
najlepszych kandydatów. Ranking reprezentanta obejmuje całą grupę i nie ma early
exit. Miękka geometria wpływa na ranking; blur, okluzja, brak planszy, konflikt
zakresu i błąd techniczny pozostają twardą blokadą.
