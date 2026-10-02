---
title: Opcja „Nie wiem” przy wyborze symbolu w korekcie siatki
status: done
last_updated: 2026-10-02
---

# TASK-0825 — Opcja „Nie wiem” przy wyborze symbolu w korekcie siatki

## Status

`done`

## Goal

Operator, który nie widzi symbolu (pole zasłonięte lub widoczne we fragmencie),
może to jawnie zaznaczyć w korekcie siatki zamiast wybierać symbol z palety
„na siłę”.

## Context

Paleta z TASK-0822 zawierała tylko aktywne symbole gry. Pozostawienie pola bez
wyboru zostawia podpowiedź modelu, więc nie było sposobu na zapisanie
„nie wiem”. Rozszerza D-488.

## Dependencies / entry conditions

TASK-0820, TASK-0822.

## Scope

- `GridCorrectionCellSymbolPayload.symbolId` jest nullowalne; `null` = „nie wiem”.
- Zapis: dla `null` komórka dostaje akcję `mark_unreadable` (oczekująca,
  `quality_issue = unreadable`, bez etykiety), dla symbolu — `reassign`.
- Reviewer: przycisk „? Nie wiem” w palecie; kafelek pokazuje „?”.
- OpenAPI i klient wygenerowane ponownie.

## Out of scope

- Zmiana przepływu weryfikacji symboli dla komórek nieczytelnych.

## Acceptance criteria

- [x] „? Nie wiem” wysyła `{cellIndex, symbolId: null}` w `cellSymbols`.
- [x] Backend oznacza taką komórkę jako nieczytelną i nie zatwierdza etykiety.
- [x] „Usuń wybór” nadal cofa wybór i przywraca podpowiedź.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_correction_symbol_payload.py services/api/tests/test_virtual_grid_geometry.py services/api/tests/test_board_cell_geometry_pending.py
npm run test:geometry --workspace @game-predictor/reviewer
```

## Outcome

### Changed

- `schemas/geometry_qualification.py`, `application/virtual_grid_geometry.py`,
  `storage/image_symbol_review_repository.py` (`assign`).
- `deferred-board-cell-geometry-editor.tsx`, testy interakcji Reviewera,
  OpenAPI i wygenerowany klient.

### Verification results

- Testy API (payload, serwis, pending, PostgreSQL `assign` z „nie wiem”): 42/42.
- Reviewer: interakcje 12/12, jednostkowe, typecheck, lint, `check:generated` czyste.

### Not completed

- Brak odbioru na żywym Reviewerze; wymagany restart API i `npm run reviewer:build`.
