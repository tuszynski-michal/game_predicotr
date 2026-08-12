---
title: TASK-0199 curated import source and batch storage
status: done
release: "0.5"
last_updated: 2026-08-09
---

# TASK-0199 — Curated import source and batch storage

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md
- ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md

## Goal

Dodać trwały model źródła z manifestu Selekcji Zdjęć oraz atomowo
rezerwowanych partii następnych N wpisów.

## Verification

Migracja i testy uniemożliwiają nakładające się zakresy oraz utratę kursora po
restarcie.

## Dependencies

TASK-0198.

## Outcome

Migracja `0038_curated_image_import_batches` dodała checksum-bound źródło
manifestu i niezmienne partie. Repozytorium rezerwuje kolejne zakresy pod
blokadą wiersza, utrwala monotoniczny kursor oraz nie pozwala nakładać partii.
Reset danych gry usuwa również te rekordy, więc stan nie przecieka do nowego
importu.
