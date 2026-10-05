---
title: TASK-0863 — diagnostyka trzeciego nagrania Mumii
status: todo
last_updated: 2026-10-06
---

# TASK-0863 — trzeci niezależny katalog

## Status

`todo`

## Goal

Sprawdzić60 nowych zdjęć z odrębnego nagrania i przygotować konkretne wycinki
do istniejącej korekty, jeśli potrzeba nowych etykiet.

## Dependencies / entry conditions

TASK-0862 i0861 z raportem rzeczywistego wyniku. Operator zlecił użycie
C:\Users\tuszy\Documents\mumie i deklaruje osobny film dla każdego nowego katalogu.
Nowym trzecim katalogiem jest24517–50112 cut; stare dwa rozpoznawać po inventory.

## Recommended execution

gpt-6.1-sol, high; własny review i replay, bez delegowania. Source/alias conflict
blokuje partię. Brak human labels blokuje accuracy, nie samą inferencję.

## Relevant docs

- AGENTS.md; ai_docs/README.md; ai_docs/process/CURRENT_STATE.md
- ai_docs/requirements/VISION_LAB.md; ai_docs/architecture/VISION_LAB.md
- ai_docs/delivery/MUMIE_SYMBOL_FEEDBACK_ITERATION_20261005.md
- ai_docs/process/DECISION_LOG.md

## Scope / technical notes

Use existing symbol_batch freeze/inference/report and filename-count cap.
Bounded60 evenly spaced photos. Use qualified V3 if its pair passes all gates;
otherwise retain failed iteration result and diagnose with existing qualified V2.
V2 fresh geometry for this new folder is an explicit variant of the original
same-geometry comparison workflow; keep old default behavior unchanged.
Candidate review stays trainable=false, operator-only, exact PNG-bound.

## Out of scope

New/random training, pseudo-labels, guessed accuracy, automatic activation,
Super labels, database writes and production upload/deployment.

## Acceptance criteria

- [ ] Independent full-folder aliases/protected exclusions before pixels.
- [ ]60 sources, filename-limited geometry, real symbol outputs; no fabricated accuracy.
- [ ] Exact immutable case evidence and usable existing editor when labels needed.
- [ ] Persisted manifest/PIDs, bounded execution and new-process retry/replay.
- [ ] Tests/regressions, scoped lint/types, review, commit/Outcome/CURRENT_STATE.

## Expected files / verification

Existing symbol_batch.py and batch-label preparation if optional adapter required;
tests for compatibility/qualification. Artifact driver/report, current saved
runtime and crop-review root. Finite120s commands, controlled background for
batch inference. No OpenAPI change expected.

## Outcome

Pending.
