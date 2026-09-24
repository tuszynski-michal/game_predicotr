---
title: TASK-0643 — zapis niepełnych siatek (cold start) i zatwierdzanie całego zdjęcia (virtual_source)
status: done
last_updated: 2026-09-24
---

# TASK-0643 — zapis niepełnych siatek (cold start) i zatwierdzanie całego zdjęcia (`virtual_source`)

## Status

`done`

## Goal

W Reviewerze („Weryfikacja plansz”, gra 777
`bfc4f949-5c14-4850-b02a-db99610bcfa5`, import
`1a1cff95-436e-4054-ae1f-8ef4565cd7b0`) działają oba zapisy zgłoszone przez
użytkownika:

1. „Niepełne siatki do ręcznej korekty” — zapis kończył się
   `IMAGE_SYMBOL_ONNX_ARTIFACT_MISSING`.
2. „Walidacja gotowych siatek” — „Zatwierdź całe zdjęcie” nic nie zapisywał.

## Context

Zgłoszenie użytkownika po zamknięciu planu D-442.

## Dependencies / entry conditions

- Fakt (read-only, DB): import ma przypięty snapshot
  `inferenceMode: "unclassified"` (`cold-start-unclassified-v1`,
  `onnxRelativePath: unclassified/cold-start-unclassified-v1.no-onnx`) —
  plik ONNX celowo nie istnieje.
- Fakt (read-only, DB): wszystkie 470 197 wierszy `recognized_boards` w
  `game_data_v2` mają `board_checksum_sha256 IS NULL` i ustawione
  `geometry_checksum_sha256` (`asset_mode = 'virtual_source'`,
  `ck_recognized_boards_asset_provenance`).

## Recommended execution

claude-opus-5-5, reasoning: medium. Dwie punktowe poprawki backendu z
reprodukcją na żywych danych w transakcji wycofywanej. Dodatkowy review: nie.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/DECISION_LOG.md` (D-442)

## Scope

- `ManualBoardCellSymbolPredictor.predict` dla snapshotu `unclassified`
  zwraca 15 komórek `?` bez ładowania ONNX — identycznie jak
  `ProductionImageStageAdapterSuite._unclassified_symbol_boards` w imporcie.
- `SymbolCellReviewWriteThroughCoordinator.approve_current_geometry` zapisuje
  w `image_board_geometry_review_events.board_checksum_sha256` checksum
  geometrii dla planszy `virtual_source` (helper
  `_geometry_review_event_board_checksum`), tak jak robią to już zdarzenia
  `geometry_saved` w `virtual_grid_geometry_repository.py`.

## Out of scope

- Zmiany schematu/migracji (kolumna zdarzeń pozostaje NOT NULL + CHECK sha256).
- Frontend Reviewera (komunikaty błędów działały poprawnie).

## Acceptance criteria

- [x] Zapis ręcznej korekty dla importu cold start nie woła ONNX.
- [x] Zatwierdzenie całego zdjęcia z planszami `virtual_source` przechodzi
      (reprodukcja na żywej bazie w transakcji wycofanej: przed poprawką
      `NotNullViolation`, po — 9/9 zatwierdzonych, rollback).
- [x] Testy regresyjne dla obu przypadków.

## Technical notes

Przyczyna #2: `approve_current_geometry` wstawiał
`board_checksum_sha256=board.board_checksum_sha256`, czyli `NULL` dla
każdej planszy wirtualnej → `IntegrityError` → cała transakcja
zatwierdzania wycofana, Reviewer pokazywał błąd zapisu. Dotyczyło to każdej
gry na `game_data_v2` (oraz ścieżki pojedynczego `geometry-approval`).

## Expected files

- `services/worker/src/game_predictor_worker/images/manual_board_cell_symbol_prediction.py`
- `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`
- `services/worker/tests/test_manual_board_cell_symbol_prediction.py`
- `services/api/tests/test_image_symbol_review_virtual_source.py`

## Test cases

- `test_manual_prediction_for_cold_start_import_returns_unknown_cells_without_onnx`
- `test_geometry_approval_event_identifies_virtual_board_by_geometry_checksum`

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_symbol_review_virtual_source.py services/worker/tests/test_manual_board_cell_symbol_prediction.py services/api/tests/test_board_cell_geometry_pending.py services/api/tests/test_image_grid_review_api.py services/api/tests/test_image_symbol_reviews_api.py -q
```

## Risks / open questions

- Brak zmian kontraktu API, OpenAPI bez zmian.

## Outcome

### Changed

- Predyktor ręcznej korekty obsługuje tryb `unclassified` (komórki `?`).
- Zdarzenie audytu zatwierdzenia geometrii planszy `virtual_source`
  używa `geometry_checksum_sha256`.

### Verification results

- Reprodukcja #2 na żywej bazie (skrypt w scratchpadzie, `session.rollback()`
  na końcu, zero trwałych zapisów): przed poprawką `NotNullViolation`, po
  poprawce `approved_review_item_ids` = 9 plansz.
- Wyniki testów, lint i typecheck — patrz `CURRENT_STATE.md`.

### Not completed

- Odbiór w UI Reviewera wykonany osobno (patrz `CURRENT_STATE.md`).

### Documentation updates

- `ai_docs/process/CURRENT_STATE.md`, `ai_docs/process/DECISION_LOG.md` (D-444).

### Recommended next task

- Brak.
