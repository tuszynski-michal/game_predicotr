---
title: TASK-0194 v10.1 first 200 performance and quality gate
status: todo
release: "0.4"
last_updated: 2026-08-08
---

# TASK-0194 — V10.1 first-200 performance and quality gate

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/tasks/completed/0193-image-selection-deterministic-parallel-verification.md`

## Goal

Powtórzyć izolowany profil indeksów 0–199 i zdecydować, czy można przejść do
ręcznego runu około 5000/32 000.

## Baseline

- 377,530649 s,
- 9 grup,
- 99 pełnych weryfikacji,
- 792 batche i 7128 cropów OCR,
- brak błędów skanu.

## Likely files

- `scripts/profile_image_selection_slice.py`
- `artifacts/image-selection-v10-first-200-timing.json`
- dokumentacja quality/current state

## Proposed solution

- uruchomić ten sam staging, kolejność, limit 200 i cold-cache policy,
- porównać granice, zakresy, checksumy reprezentantów i telemetry,
- obejrzeć każdy zmieniony reprezentant,
- zapisać decyzję `accepted | optimize | rejected`.

## Verification

- pierwszy cel: 113–151 s, czyli 60–70% krócej,
- brak regresji zakresów i jakości reprezentantów,
- raport pokazuje poziomy adaptacyjne oraz anchored/fallback,
- pełny run nie startuje automatycznie.

## Dependencies

- TASK-0188–0193.

## Open questions

Końcowa decyzja `accepted | optimize | rejected` należy do właściciela po
obejrzeniu zmienionych reprezentantów.

## Outcome

Do uzupełnienia po wspólnej ocenie wyniku.
