---
title: TASK-0416 Unblock local virtual source geometry save
status: done
last_updated: 2026-09-03
---

# TASK-0416 — Odblokowanie zapisu lokalnej geometrii źródłowej v0.10

## Problem

Lokalny Reviewer poprawnie pozwala wyznaczyć cztery narożniki dla wszystkich
dziewięciu plansz jednego zdjęcia, lecz akcja `Zapisz i zatwierdź 9 plansz`
kończy się ogólnym błędem. Diagnoza bieżącej gry `777` wykazała, że source
geometry ma kompletną, checksum-bound proweniencję, ale globalny stan rollout
backfillu gry jest `not_started`. Repozytorium blokuje przez to niezależną,
lokalną korektę bieżącego źródła przed właściwą walidacją jego własnych danych.

## Scope

- Usunąć globalną bramkę `backfill_status == ready` z odczytu pojedynczego
  aktualnego kontekstu `virtual_source`.
- Zachować lokalne fail-closed kontrole źródła, rewizji, topologii, render specu
  i kompletności komórek przed zapisem.
- Dodać regresję, że kompletne bieżące źródło można przygotować do ręcznej
  korekty, gdy niezależny, game-wide backfill jeszcze nie wystartował.
- Uaktualnić opis zachowania lokalnego Reviewera.

## Out of scope

- Bez uruchamiania backfillu, importów, jobów i mutacji danych użytkownika.
- Bez zmiany zdalnego Reviewera, OpenAPI, migracji ani globalnej semantyki
  rolloutów.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/process/CURRENT_STATE.md`

## Acceptance criteria

- [ ] `Zapisz i zatwierdź 9 plansz` nie jest blokowane wyłącznie dlatego, że
  globalny backfill innego źródła nie wystartował.
- [ ] Niekompletna lub niespójna proweniencja konkretnej planszy nadal kończy
  się stabilnym błędem.
- [ ] Test odtwarza globalny stan `not_started` przy kompletnym źródle.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_virtual_grid_geometry_repository.py services/api/tests/test_virtual_grid_geometry.py -q
.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py services/api/tests/test_virtual_grid_geometry_repository.py
.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py
npm run test --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
```

## Outcome

### Changed

- `virtual_geometry_context` nie uzależnia już lokalnej korekty jednego
  kompletnego `virtual_source` od game-wide stanu backfillu. Globalny backfill
  pozostaje narzędziem migracyjnym, a bieżące źródło nadal przechodzi pełne
  kontrole proweniencji, topologii, revision/crop render specu oraz kompletności
  15 komórek przed wspólnym zapisem.
- Dodano regresję dla stanów `not_started`, `rebuilding` oraz `failed` i
  zachowano osobny test, że niepełna projekcja komórek nadal jest blokowana.
- Rzeczywista, niezmieniająca danych walidacja źródła `10–18` gry `777`
  przygotowała dziewięć slotów `(0..8)` oraz po 15 wirtualnych cropów na
  planszę. Wcześniej dokładnie ten odczyt kończył się
  `IMAGE_GEOMETRY_ROLLOUT_NOT_READY`.

### Verification results

- `pytest services/api/tests/test_virtual_grid_geometry_repository.py services/api/tests/test_virtual_grid_geometry.py services/api/tests/test_image_grid_review_api.py -q` — 16 passed.
- `ruff check` dla zmienionego repozytorium i regresji — passed.
- `npm run python:typecheck` — passed.
- `npm run test --workspace @game-predictor/reviewer` — 172 passed.
- `npm run lint --workspace @game-predictor/reviewer` — passed.
- `npm run typecheck --workspace @game-predictor/reviewer` — passed.

### Not completed

- Nie uruchamiano backfillu, importu, joba ani żadnej mutacji danych gry.

### Recommended next step

- Po restarcie lokalnego API ponownie otworzyć to źródło w lokalnym Reviewerze
  i kliknąć `Zapisz i zatwierdź 9 plansz`; w razie nowego błędu backend zwróci
  już wyłącznie source-scoped walidację zamiast blokady globalnego backfillu.
