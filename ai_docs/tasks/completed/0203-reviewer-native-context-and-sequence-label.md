---
title: TASK-0203 Reviewer native context and sequence label
status: done
release: "0.5"
last_updated: 2026-08-09
---

# TASK-0203 — Reviewer native context and sequence label

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md
- ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md

## Goal

Zastąpić prawy podgląd 500×300 natywnym fragmentem źródła obejmującym planszę
i jej numer.

## Verification

Nowe dane używają quada etykiety OCR, historyczne bezpiecznego fallbacku, a
numer jest widoczny bez modalu.

## Dependencies

TASK-0198.

## Outcome

Pipeline utrwala `sequenceLabelQuad`, a Reviewer wyznacza viewport obejmujący
planszę i numer na oryginalnym źródle. Dane historyczne używają ograniczonego
fallbacku. Prawy podgląd nie bazuje już na sztucznie zmniejszonym obrazie
500×300, dzięki czemu numer i szczegóły źródła są widoczne bez modalu siatki.
