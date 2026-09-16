---
title: Refine structured symbol lattices per board
status: done
last_updated: 2026-09-04
---

# TASK-0446 — Lokalne dopasowanie siatki 5×3

## Status

`done`

## Goal

Dodać izolowany wariant v3 wykorzystujący estimator v19 i fail-closed ochronę
symboli, bez włączania go do produkcyjnego renderowania.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/tasks/completed/0445-separate-board-frame-and-symbol-lattice.md`

## Scope

- wrapper structured v3 dla topologii 3×5;
- jednorazowe użycie estymatora v19 na `analysisQuad`;
- bbox-aware `lattice-content-safety-v1`;
- jawne odroczenie bez fallbacku do ramki.

## Out of scope

- podpięcie do produkcyjnego pipeline'u;
- UI i aktywacja;
- przetwarzanie istniejących importów.

## Acceptance criteria

- [x] bezpieczna siatka zwraca oddzielny `symbolGridQuad`;
- [x] przecięcie chronionego bboxa kończy się `content_boundary_conflict`;
- [x] brak dowodu kończy się odroczeniem bez quada zastępczego;
- [x] topologia inna niż 3×5 jest stabilnie odrzucana;
- [x] historyczna serializacja estymatora v19 pozostaje bez zmian.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_structured_lattice_refinement_v3.py services/worker/tests/test_board_cell_geometry_estimator.py
```

## Outcome

### Changed

- Dodano izolowany refiner v3, jawny wynik content safety i stabilny błąd topologii.
- Estimator zachowuje niewidoczną w serializacji diagnostykę jednego przebiegu detekcji.
- Globalne komponenty przechowują dokładny lewy/górny brzeg bez zmiany payloadu v19.

### Verification results

- `16 passed` dla global lattice, estymatora v19 i refiner v3.
- Ruff: passed.
- Mypy zmienionych modułów: passed.

### Not completed

- Produkcyjne shadow, UI i aktywacja należą do TASK-0447–0448.

### Documentation updates

- Architecture, Decision Log i Current State.

### Recommended next task

- TASK-0447.
