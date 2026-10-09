# TASK-0948 — Sekcja „Ostatnie korekty” w Reviewerze

## Status

`todo`

## Goal

Operator widzi ostatnie korekty bieżącego importu w „Korekta cięcia siatki” i cofa wybraną po podglądzie skutków i potwierdzeniu.

## Context

Plan `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`, sekcja „UI Reviewera (TASK-0948)”.

## Dependencies / entry conditions

- TASK-0947 ukończony (klient z trzema operacjami).

## Recommended execution

`claude-sonnet-5-5`, reasoning `medium`: komponent UI z listą, modalem i testami w istniejącym ekranie. Eskalacja: potrzeba zmiany kontraktu API → zatrzymaj i zgłoś. Review: Codex `gpt-6-astra`, `medium`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md` (sekcja Reviewera, jeśli istnieje; inaczej plan)

## Scope

- Komponent (proponowany) `apps/reviewer/src/features/operational-reviews/geometry-correction-history.tsx` w `BoardGeometryCorrectionWorkspace` (`board-geometry-correction-workspace.tsx`), pod kolejką.
- Wiersz listy: godzina lokalna, sekwencja, pozycja, rodzaj („slot” / „plansza”), autor; „Cofnij” tylko dla `revertable`, inaczej komunikat blokady.
- Modal potwierdzenia z podglądem (`previewGeometryCorrectionRevert`): co zostanie usunięte lub przywrócone; przycisk „Potwierdź cofnięcie” z nowym `idempotencyKey`; blokada podwójnego kliknięcia; obsługa 409 (komunikat i odświeżenie).
- Odświeżenie listy po zapisie korekty (`handleSaved`) i po cofnięciu; odświeżenie kolejki po cofnięciu.
- Wywołania przez klienta z `packages/admin-api-client` (bez ręcznych typów).

## Out of scope

- Panel Admin, zmiany API.

## Acceptance criteria

- [ ] Testy Reviewera: render listy, stan zablokowany, podgląd, potwierdzenie wysyła jedno żądanie z CAS, 409 pokazuje komunikat, sukces odświeża kolejkę i listę.
- [ ] `typecheck`, `lint`, `test` i `build` Reviewera zielone.

## Expected files

- Nowe (proponowane): `apps/reviewer/src/features/operational-reviews/geometry-correction-history.tsx`, test w `apps/reviewer/test/` lub `apps/reviewer/test-interactions/`.
- Zmieniane: `board-geometry-correction-workspace.tsx`, style Reviewera.

## Test cases

- Lista z dwiema korektami (jedna zablokowana) → jeden przycisk „Cofnij”.
- Potwierdzenie → `revertGeometryCorrection` z `expectedGeometryRevision`/`expectedResolutionRevision` z listy.
- Odpowiedź 409 `GEOMETRY_REVERT_CELLS_CHANGED` → komunikat, lista odświeżona.

## Verification

```powershell
npm run test --workspace @game-predictor/reviewer
npm run test:geometry --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
npm run reviewer:build
```

## Risks / open questions

- Brak.

## Outcome

Wypełnia agent po pracy.
