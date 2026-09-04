---
title: Restore grid review default zoom to 100 percent
status: done
task_id: TASK-0437
last_updated: 2026-09-04
---

# TASK-0437 — Przywrócenie domyślnego zoomu 100% w walidacji siatek

## Goal

Otwierać gotowe siatki w lokalnym Reviewerze domyślnie przy powiększeniu 100%
zamiast 150%.

## Scope

- zmienić początkową wartość zoomu edytora siatki na 100%;
- zachować ręczny wybór 100%, 125%, 150% i 200%;
- zaktualizować test kontraktu UI oraz dokumentację zachowania.

## Out of scope

- zmiana geometrii, hit-testu, canvasu lub API;
- zmiana zoomu ręcznej selekcji i innych workspace'ów;
- utrwalanie zoomu między sesjami.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Definition of Done

- nowo otwarty edytor gotowej siatki pokazuje 100%;
- operator nadal może wybrać pozostałe dostępne powiększenia;
- testy Reviewera, lint, typecheck, format i build są zielone.

## Outcome

- Edytor gotowej siatki inicjalizuje `zoomPercent` wartością 100 zamiast 150.
- Lista ręcznych poziomów 100%, 125%, 150% i 200% pozostała bez zmian.
- Nie zmieniono geometrii, hit-testu, API ani innych workspace'ów obrazowych.
- Weryfikacja:
  - `npm run test --workspace @game-predictor/reviewer` — 173 passed;
  - `npm run lint --workspace @game-predictor/reviewer` — passed;
  - `npm run typecheck --workspace @game-predictor/reviewer` — passed;
  - `npm run reviewer:build` — passed;
  - skoncentrowany Prettier — passed;
  - `git diff --check` — passed.
