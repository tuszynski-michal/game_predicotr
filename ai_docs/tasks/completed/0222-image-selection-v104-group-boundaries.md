---
title: TASK-0222 image selection v10.4 group boundaries
status: done
release: "0.5"
last_updated: 2026-08-11
---

# TASK-0222 — Granice grup v10.4

## Goal

Skupiać descriptor na siatce layoutów i potwierdzać zmianę względem starej
grupy, aby perspektywa nie dzieliła jednego ekranu i nie dołączała pierwszej
klatki następnego ekranu do poprzedniej galerii.

## Relevant docs

- `ai_docs/tasks/completed/0221-image-selection-v104-baseline.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`

## Verification

Deterministyczne testy bufora granicznego, wznowienia z checkpointu i
ciągłości `orderIndex`.

## Outcome

Manifest v10.4 używa centralnego ROI siatki. Bufor graniczny potwierdza kolejne
klatki względem stabilnego obrazu starej grupy, więc różna perspektywa nowych
klatek nie dołącza pierwszego obrazu następnego ekranu do poprzedniej galerii.
Testy zachowują deterministyczny `orderIndex`.
