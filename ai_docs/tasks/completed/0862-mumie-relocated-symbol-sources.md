---
title: TASK-0862 — trwała lokalizacja źródeł symboli Mumii
status: done
last_updated: 2026-10-06
---

# TASK-0862 — lokalizacja przeniesionych źródeł

## Status

`done`

## Goal

Odblokować ten sam qualified manifest/run po przeniesieniu pełnego nagrania,
zachowując wszystkie SHA, decyzje, podział i bramki bezpieczeństwa danych.

## Context / entry conditions

Operator wskazał C:\Users\tuszy\Documents\mumie jako aktualny parent zdjęć.
Znajdują się tam dwa wcześniejsze cut foldery oraz trzeci24517–50112 cut.
Deklaruje osobny film dla każdego nowego katalogu. Technical aliases mają
pierwszeństwo nad deklaracją. Brak zgody na DB/aktywację/wdrożenie.

## Recommended execution

gpt-6.1-sol, high. Własny odrębny review i regression gates, bez delegowania.
Zmiana raster/source bytes albo podziału blokuje lokalizację i resume.

## Relevant docs

- AGENTS.md; ai_docs/README.md; ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md; ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/requirements/VISION_LAB.md; ai_docs/architecture/VISION_LAB.md
- ai_docs/process/DECISION_LOG.md (D-502, D-503)
- ai_docs/delivery/MUMIE_SYMBOL_FEEDBACK_ITERATION_20261005.md
- ai_docs/tasks/0861-mumie-symbol-feedback-training.md

## Scope

Create-only manifest-bound source-location sidecar, full inventory proof,
optional adapter reads and output protection, CLI binding/verify, tests.
Dokładne rozwiązanie w planie. Nie zmieniać settings istniejącego runu.

## Out of scope

Remap metadanych/etykiet/PNG, zmiana logicznych ścieżek manifestu, nowy trening,
filesystem move/copy/delete zdjęć, symlinki, zmiana API/UI, DB i wdrożenie.

## Acceptance criteria

- [x] Full-folder names/SHA match before feedback pixels; current exact quad rendering.
- [x] Same manifest_id, decisions, class/split/counts and checkpoint binding.
- [x] Optional persisted sidecar; wrong identity/relative root/drift/overlap rejected.
- [x] New-process verify/retry; default adapter behavior preserved.
- [x] Original files unchanged; tests/lint/types, separate review, commit/Outcome.

## Expected files

Existing symbol_feedback.py (compose, adapter, CLI), symbol_runs.py (output guards),
test_vision_lab_symbol_feedback.py; plan, decisions, requirements/architecture,
quality report and CURRENT_STATE. No HTTP change.

## Verification

Focused pytest and old adapter/run regressions, Ruff/mypy with explicit Torch
boundary, real2052-file match and fresh-process verify. Finite120s runner.

## Outcome

Create-only sidecar relocates all2,052 exact sources to the operator-supplied
C:\Users\tuszy\Documents\mumie\481537- 500000 cut. All names/SHA match;
all18 rasters re-render exactly. Manifest0cff2a15…1e3de4, labels, 264/84/9,
graph and run settings remain unchanged. No image move/copy/delete or symlink.

29 qualification/location tests and28 adapter/training regressions passed.
Ruff format/lint and scoped mypy passed. Real bind, fresh-process verify and
identical retry passed, with default behavior and metadata protected.
Separate review found no unresolved P0–P2. Evidence:
ai_docs/quality/MUMIE_SOURCE_RELOCATION_20261006.md.

Commit: `v1.7.208`. Continue0861, resuming the same failed RGB run, then0863.
