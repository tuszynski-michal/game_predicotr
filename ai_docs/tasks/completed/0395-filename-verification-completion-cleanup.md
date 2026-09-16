---
title: TASK-0395 — Domknięcie i cleanup weryfikacji nazw zakresów
status: done
last_updated: 2026-09-02
---

# TASK-0395 — Domknięcie i cleanup weryfikacji nazw zakresów

## Goal

Po automatycznym wyniku bez pozycji do kontroli albo po ostatniej ręcznej
decyzji run `filename_verification` ma przejść do `done`, zachowując tylko
lekkie podsumowanie i bezpiecznie usuwając własny staging oraz dane OCR.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- trwałe stany `cleanup_pending` i `cleanup_blocked` oraz migracja 0092;
- automatyczne zaplanowanie cleanupu po wyniku bez ręcznego review i po
  ostatniej ręcznej decyzji;
- idempotentne, fenced usunięcie zasobów należących wyłącznie do jednego runu:
  browser stagingu, artefaktów OCR, rekordów zakresów i decyzji;
- lekka historia runu z podsumowaniem liczników i statusem zakończenia;
- Admin informujący o trwającym albo zablokowanym cleanupie.

## Out of scope

- usuwanie folderów `seq_*` lub źródeł operatora;
- usuwanie cropów, modeli, danych gry, innych importów albo shared stagingu;
- zmiana OCR, proofów i selekcji reprezentantów.

## Acceptance criteria

- [ ] Workflow nazw nie wywołuje `apply_selection` i nie tworzy `seq_*`.
- [ ] Automatycznie zgodny run kończy cleanupem bez ręcznej akcji.
- [ ] Ostatnia decyzja ręczna jednorazowo uruchamia cleanup.
- [ ] Cleanup usuwa tylko zasoby runu, daje się wznowić po awarii i blokuje się
      z konkretną diagnostyką przy obcej albo aktywnej referencji.
- [ ] Bieżący failed run można wznowić bez drugiego OCR; cleanup wykona się
      dopiero po jego pełnym review.

## Technical notes

Usunięcie jest wykonywane przez ten sam job i lease. Katalogi są najpierw
przenoszone do managed trash na tym samym woluminie; obca referencja nigdy nie
jest usuwana. W historii pozostają metadata runu oraz liczniki, ale nie
obserwacje OCR, raport ani indeksy pojedynczych decyzji.

## Expected files

- `services/api/alembic/versions/0092_filename_verification_cleanup.py`
- `services/api/src/game_predictor_api/domain/semi_automatic_image_selections.py`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/api/src/game_predictor_api/storage/semi_automatic_image_selection_repository.py`
- `services/worker/src/game_predictor_worker/semi_automatic_selection/job.py`
- `apps/admin/src/features/manual-image-selection/manual-selection-range-verification-workspace.tsx`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_semi_automatic_image_selections.py services/worker/tests/test_semi_automatic_selection_job.py -q
.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api services/worker/src/game_predictor_worker/semi_automatic_selection
.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api services/worker/src/game_predictor_worker/semi_automatic_selection
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run openapi:check
npm run admin:build
```

## Outcome

Wdrożono migrację `0092`, trwałe stany `cleanup_pending` i
`cleanup_blocked` oraz fenced, wznawialny cleanup wykonywany przez ten sam job.
Run weryfikacji nazw nie może zamknąć się na decyzjach dla automatycznie
zgodnych plików. Po automatycznym sukcesie albo ostatniej wymaganej decyzji
usuwa wyłącznie własne dane OCR, staging i rekordy robocze, pozostawiając
kompaktową historię. Konflikt referencji pozostawia dane nietknięte oraz daje
Adminowi akcję `Wznów czyszczenie`, bez drugiego OCR i bez ponownego review.

Kontrole: 35 skoncentrowanych testów API/workera, Ruff, mypy, 366 testów
Admina, lint, typecheck, `openapi:check` i produkcyjny build Admina przeszły.
