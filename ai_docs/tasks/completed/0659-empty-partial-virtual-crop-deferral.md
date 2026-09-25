---
title: Empty partial virtual-crop deferral
status: in_progress
last_updated: 2026-09-25
---

# TASK-0659 — odroczenie pustej częściowej planszy virtual

## Status

`in_progress`

## Goal

Nie dopuścić, aby plansza oznaczona `pending_partial` bez indeksów niedostępnych komórek blokowała reprocess jako naruszenie topologii.

## Context

Po TASK-0658 live reprocess `51b256c4-1ff5-4a94-a764-d54ee15390da` nadal
odtworzył pięć pustych wyników virtual cropa. Diagnostyka pokazała, że ich
kwalifikacja `pending_partial` nie zawierała maski brakujących komórek.

## Dependencies / entry conditions

- TASK-0658 jest dostarczony w commicie `6bbe6943`.
- Polityka `image-geometry-systemic-guard-v2-manual-review` rozróżnia jakość
  od realnego naruszenia integralności.

## Recommended execution

`gpt-6-sol`, reasoning `high`: zmiana jest lokalna, ale wpływa na trwały
workflow importu i wymaga regresji. Eskalacja do niezależnego review jest
wymagana wyłącznie, gdy test ujawni zmianę kontraktu częściowych plansz.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`

## Scope

- Walidacja, że częściowa kwalifikacja ma niepustą, uporządkowaną maskę
  indeksów z topologii 3 × 5.
- Pusty albo błędny wynik virtual renderów dla takiej planszy trafia do
  istniejącego `incomplete_lattice` / ręcznej korekty.
- Regresja jednostkowa.

## Out of scope

- Usuwanie zdjęć, zmiana schematu, zmiana progu 98% lub osłabianie prawdziwych
  invariantów checksumy, kolejności i topologii.

## Acceptance criteria

- [ ] `pending_partial` bez maski nie publikuje pustego cropa.
- [ ] Poprawne częściowe maski, w tym wszystkie 15 komórek, zachowują działanie.
- [ ] Testy workflowu geometrii przechodzą.

## Technical notes

Źródłem prawdy dla częściowego stanu jest `geometryQualification` wraz z
`unavailableCellIndices`. `pending_partial` z pustą maską nie opisuje
częściowego wyniku i nie może omijać kontroli kompletności renderów.

## Expected files

- Istniejące: `services/worker/src/game_predictor_worker/images/production_workflow.py` — `ProductionImageStageAdapterSuite._virtual_board_payload`.
- Istniejące: `services/worker/tests/test_production_image_workflow.py`.

## Test cases

- Pusta kwalifikacja częściowa i zero renderów → jeden `incomplete_lattice`.
- Poprawna częściowa maska pozostaje obsługiwana.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_production_image_workflow.py services/worker/tests/test_grid_profile_end_to_end_gate.py services/worker/tests/test_large_import_geometry_guard.py
```

## Risks / open questions

- Reprocess musi dostać nowy fingerprint po restarcie workera, aby nie odczytać
  starego immutable raportu.

## Outcome

### Changed

- `pending_partial` musi mieć niepustą, poprawną maskę niedostępnych indeksów,
  aby pominąć kontrolę pełnego zestawu renderów.
- Pusta kwalifikacja częściowa jest trwałym `incomplete_lattice` zamiast
  fałszywego naruszenia topologii.

### Verification results

- 77 testów workflowu, bramki i systemic geometry guard przeszło.
- Ruff check oraz format check przeszły.

### Not completed

- Nie usunięto żadnego zdjęcia ani nie zmieniono schematu bazy.

### Documentation updates

- Zaktualizowano `CURRENT_STATE.md`.

### Recommended next task

- Po restarcie workera uruchomić nowy reprocess z kontynuacją ręcznej geometrii.
