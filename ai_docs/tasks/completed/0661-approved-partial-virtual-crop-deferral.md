---
title: Approved partial virtual crop deferral
status: done
last_updated: 2026-09-25
---

# TASK-0661 — virtual crop tylko dla zatwierdzonej planszy częściowej

## Status

`done`

## Goal

Nie pozwolić, aby sama kwalifikacja `pending_partial` pominęła kontrolę 15
renderów bez jawnego disposition `partial`.

## Context

Job `7b90689d-8fe0-49ca-9cde-80f0fd51dd9e` potwierdził pięć plansz z maską,
lecz disposition `automatic`; nie były zatwierdzonymi częściowymi wynikami.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`

## Scope

- Zawężenie wyjątku virtual cropa do `guardResolutionDisposition == partial`.
- Regresja dla niezatwierdzonej maski częściowej.

## Out of scope

- Zmiana progów, usuwanie zdjęć i osłabienie realnych invariantów.

## Acceptance criteria

- [x] Niezatwierdzona częśćowa kwalifikacja z pustym outputem trafia do
  `incomplete_lattice`.
- [x] Istniejące zatwierdzone częściowe plansze zachowują działanie.

## Technical notes

`geometryQualification` opisuje obserwację, a `guardResolutionDisposition`
decyzję. Tylko decyzja `partial` zezwala na mniejszą liczbę renderów.

## Expected files

- `services/worker/src/game_predictor_worker/images/production_workflow.py`
- `services/worker/tests/test_production_image_workflow.py`

## Outcome

### Changed

- Wymagane jest jednocześnie `pending_partial`, poprawna maska i disposition
  `partial`; w przeciwnym razie brak renderów jest trwałym odroczeniem.
- Kontrakt renderera virtual jest w wersji v3, więc nowy reprocess nie
  odzyskuje raportu utworzonego przed tą zmianą semantyki.

### Verification results

- 77/77 testów workflowu i geometry guard przeszło.

### Not completed

- Nie wykonano operacji na zdjęciach ani bazie poza utworzeniem nowych jobów.
