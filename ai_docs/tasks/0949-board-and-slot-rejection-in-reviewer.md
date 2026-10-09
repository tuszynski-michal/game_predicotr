# TASK-0949 — Odrzucanie przyciętej planszy i slotu odroczonego w Reviewerze

## Status

`todo`

## Goal

Operator odrzuca w Reviewerze przyciętą planszę albo slot odroczony z powodem; odrzucony element nie jest cięty na symbole, znika z kolejki korekty, a zdjęcie czeka na zamiennik (bramka D-484 bez zmian).

## Context

Plan `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`, sekcja „Odrzucanie przyciętych plansz i zdjęcie zastępcze”, decyzje 1–4, wymagania W7–W8.

## Dependencies / entry conditions

- TASK-0945 (migracja `0153` ze statusem `rejected` slotu), TASK-0947 (lista „Ostatnie korekty” w API), TASK-0948 (sekcja w Reviewerze).

## Recommended execution

`claude-sonnet-5-5`, reasoning `high`: pion API + UI według istniejących wzorców rozstrzygnięcia, z wpływem na bramkę i kolejkę. Eskalacja: potrzeba zmiany reguły bramki → zatrzymaj (W8 zakazuje). Review: Codex `gpt-6-astra`, `medium`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md` — D-484, D-485

## Scope

- Slot odroczony: serwis i trasa (proponowana) `POST /api/v1/admin/games/{gameId}/image-imports/{importJobId}/board-cell-geometry-pending/{pendingId}/rejection` (`rejectPendingBoardCellGeometry`), body `{idempotencyKey, reason, note?, expectedGeometryRevision}`; tylko z `pending`; blokady jak przy rozstrzygnięciu slotu; przeliczenie bramki zdjęcia; usunięcie z widoku `correction` i liczników (`storage/image_grid_review_repository.py` `_pending_statement`, `grid_review_counts`).
- Plansza istniejąca: przycisk w Reviewerze wywołujący istniejące `POST /admin/image-review-items/{id}/resolution` z `action = rejected` i powodem (`api/image_reviews.py:613`); odmowa 409 `BOARD_REJECT_CANONICAL` dla kanonicznego właściciela.
- Cofnięcie odrzucenia: wpisy w `listGeometryCorrections` (rodzaj `rejection`) i akcja „Cofnij” przez `revertGeometryCorrection` (slot → `pending`; pozycja → nowe zdarzenie rozstrzygnięcia przywracające `pending`), dopóki sekwencji nie przejął zamiennik (kod `GEOMETRY_REVERT_REPLACED`).
- UI: w „Korekta cięcia siatki” przycisk „Odrzuć planszę” z wyborem powodu („Plansza przycięta”, „Rozmyta”, „Inny” z opisem) i potwierdzeniem; ten sam przycisk na ekranie operacyjnym pozycji.
- OpenAPI, klient, wrapper, allowlisty (`security/local_admin.py`, `reviewer-proxy-policy.ts`), testy żądań.

## Out of scope

- Przejęcie sekwencji przez nowe zdjęcie (TASK-0950), zmiana bramki kompletności, odrzucanie w Adminie.

## Acceptance criteria

- [ ] Test PG: odrzucony slot ma status `rejected` z powodem, znika z kolejki i liczników, zdjęcie pozostaje `geometry_incomplete`, pozostałe plansze bez komórek (W8).
- [ ] Test PG: odrzucona plansza poza weryfikacją symboli i wyszukiwarką; kanoniczny właściciel → 409.
- [ ] Cofnięcie odrzucenia przywraca slot/pozycję do `pending`; po przejęciu przez zamiennik → 409 `GEOMETRY_REVERT_REPLACED`.
- [ ] Testy UI: wybór powodu, potwierdzenie, jedno żądanie, odświeżenie kolejki i listy.

## Technical notes

- Kolejność blokad jak przy rozstrzygnięciu slotu (sekwencje → zdjęcie → slot).
- Odrzucenie nie tworzy planszy ani komórek; nie zmienia rewizji geometrii źródła.

## Expected files

- Zmieniane: `api/board_cell_geometry_pending.py`, `application/board_cell_geometry_pending.py`, `storage/board_cell_geometry_pending_repository.py`, `storage/image_grid_review_repository.py`, serwis cofania z TASK-0945, Reviewer `board-geometry-correction-workspace.tsx`, `geometry-correction-history.tsx`, ekran operacyjny, klient API.
- Nowe (proponowane): `services/api/tests/integration/test_pending_slot_rejection_postgres.py`, test UI.

## Test cases

- Slot `pending` → odrzucenie → kolejka bez slotu; ponowne odrzucenie z tym samym kluczem → ten sam wynik; inny klucz → 409.
- Slot `resolved` → odrzucenie → 409 (najpierw cofnięcie korekty).
- Plansza `pending_partial` → odrzucenie → `rejected`, komórki poza weryfikacją.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_pending_slot_rejection_postgres.py services/api/tests/integration/test_image_geometry_completeness_gate.py -q
npm run openapi:check
npm run test --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run python:lint
npm run python:typecheck
```

## Risks / open questions

- Odrzucona plansza z komórkami już zweryfikowanymi: weryfikacje zostają w historii, ale wypadają z wyszukiwarki — komunikat potwierdzenia musi to mówić.

## Outcome

Wypełnia agent po pracy.
