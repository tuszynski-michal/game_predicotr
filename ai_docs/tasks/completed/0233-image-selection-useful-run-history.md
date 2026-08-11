---
title: TASK-0233 useful image-selection run history
status: done
release: "0.5"
last_updated: 2026-08-11
---

# TASK-0233 — Użyteczna historia runów selekcji

## Goal

Nie pokazywać anulowanych, nieudanych i niepełnych terminalnych runów w
dropdownie roboczym `Selekcji zdjęć`, zachowując pełny run oczekujący na review.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/completed/0232-image-selection-manual-output-durability.md`

## Outcome

Admin pokazuje runy `created`, `processing`, `completed` oraz
`waiting_for_review` tylko przy pełnym postępie. Ta sama reguła obejmuje listę,
odtwarzanie localStorage i przejście aktywnego runu do stanu terminalnego.
Przeszło 190 testów Admina i typecheck.
