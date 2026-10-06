---
title: TASK-0863 — diagnostyka trzeciego nagrania Mumii
status: done
last_updated: 2026-10-06
---

# TASK-0863 — trzeci niezależny katalog

## Status

`done`

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

Confirmed entry: V3 RGB/gray/fusion each83/84 with no class regression;
18/18 training-feedback and9/9 limited diagnostic. Use this qualified pair.
No blocking question remains. For V3 review, reuse the original D-498 approval
provenance after checking its dictionary against the composite cohort. The
new packet pins that provenance, the immutable cohort/batch and exact case
sources; it need not rehash every unrelated feedback source on each UI read.
Full cohort/evaluation validation remains required before packet preparation.
Existing consumers and all exact-source/render/store-history gates are preserved.

## Out of scope

New/random training, pseudo-labels, guessed accuracy, automatic activation,
Super labels, database writes and production upload/deployment.

## Acceptance criteria

- [x]  Independent full-folder aliases/protected exclusions before pixels.
- [x] 60 sources, filename-limited geometry, real symbol outputs; no fabricated accuracy.
- [x]  Exact immutable case evidence and usable existing editor when labels needed.
- [x]  Persisted manifest/PIDs, bounded execution and new-process retry/replay.
- [x]  Tests/regressions, scoped lint/types, review, commit/Outcome/CURRENT_STATE.

## Expected files / verification

Existing symbol_batch.py and batch-label preparation if optional adapter required;
tests for compatibility/qualification. Artifact driver/report, current saved
runtime and crop-review root. Finite120s commands, controlled background for
batch inference. No OpenAPI change expected.

Planned code files: vision_lab/symbol_batch_inputs.py, symbol_batch.py,
symbol_batch_labels.py and focused batch/qualification tests. Documentation:
VISION_LAB requirements/architecture, D-504, accepted iteration plan, report,
this task and CURRENT_STATE. Runtime/driver/evidence stay in separate artifacts.

## Outcome

Documentation follow-up: `v1.7.211`. The initially documented Program Files
PowerShell7 path is absent; restart/status instructions now use the actual
bundled absolute executable. New-process Status confirms both owned lab
processes and ready ports. This corrects operator instructions only; no model,
source, decision, API or runtime setting changed.

Completed: `v1.7.210` / `92b3bd8a316fa80f4428d045d29fabf773e8c4a2`. Source2844, byte duplicate/overlap0; qualified V3
on60 evenly spaced photos. Real540/540 expected/detected/selected boards,
8100/8100 crops/predictions,0 unavailable/count anomalies. Model uncertainty
424 and disagreement37; unlabelled accuracy remains null.
Prepared24 exact RGB96 cases from15 photos,10-class coverage, revision0 and
no new human decisions. Existing editor/shortcuts works without grid changes;
backend/proxy preview 0.110s/0.109s, HTTP200. Saved runtime and
new-process controlled lab restart use the exact new reference `82f925f2a6f14ac549658cd230f65f41aef07e411b7ae21e86cea0c76892d27a`.
Driver completed25/25/10 and exited. Fresh process performs0 repeated photos,
retains270 identical artifact hashes, all original input/store/model
pins and idempotent exact preparation.42 focused+36 regression tests PASS;
Ruff/format/scoped mypy PASS. Separate review: no P0–P2. All acceptance criteria
and applicable DoD met; no API/HTTP/UI schema change or production deployment.
Full audit: ai_docs/quality/MUMIE_THIRD_RECORDING_20261006.md.
Human boundary: operator classifies24 pending crops at
http://127.0.0.1:3102/symbols/batch. No more routine continuation permission,
folder upload or30-per-class assignment required. No DB/migration/deletion,
new/random training, activation, merge/push or Super labels.
