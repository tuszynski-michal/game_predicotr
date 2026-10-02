---
title: Podpowiedzi symboli dla cięcia w korekcie siatki
status: done
last_updated: 2026-10-02
---

# TASK-0818 — Podpowiedzi symboli dla cięcia w korekcie siatki

## Status

`done`

## Goal

Reviewer może pobrać symbole ustalone dla planszy zgłoszonej oraz predykcję
modelu dla bieżącego cięcia planszy odroczonej.

## Context

Operator chce widzieć symbole dla cięcia przed zapisem.

## Dependencies / entry conditions

TASK-0817 wykonane.

## Recommended execution

`claude-fable-5-1`, poziom bieżącej sesji (nazwy poziomu nie da się odczytać ze środowiska — rekomendacja warunkowa). Eskalacja: rozbieżność kodu z planem
`ai_docs/delivery/GRID_CORRECTION_SYMBOLS_EXECUTION_PLAN.md`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GRID_CORRECTION_SYMBOLS_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-462, D-486)

## Scope

- `GET /admin/image-reviews/{review_item_id}/correction-symbols` (proponowane,
  `getImageGridReviewCorrectionSymbols`).
- `POST …/board-cell-geometry-pending/{pending_id}/geometry-symbol-preview`
  (proponowane, `previewPendingBoardCellGeometrySymbols`).
- Wspólna odpowiedź `GridCorrectionSymbolsResponse`; OpenAPI, klient, wrapper,
  allowlista proxy Reviewera dla endpointu odroczonego.

## Out of scope

- Zapis czegokolwiek; predykcja modelu dla plansz zgłoszonych.

## Acceptance criteria

- [x] Plansza zgłoszona: symbol przypisany, a przy jego braku predykcja.
- [x] Plansza odroczona: predykcja przypiętego modelu dla podanych narożników;
      brak modelu → pusta lista, nie błąd.
- [x] Żaden endpoint niczego nie zapisuje.

## Technical notes

Kod symbolu → identyfikator przez aktywne symbole gry; `?` i kody nieaktywne
dają `symbolId = null`. Endpoint odroczony używa tej samej walidacji komendy co
`geometry-preview`.

## Expected files

- `application/virtual_grid_geometry.py`, `application/board_cell_geometry_pending.py`
- `storage/virtual_grid_geometry_repository.py`, `storage/image_symbol_review_repository.py`
- `schemas/image_grid_reviews.py`, `api/image_grid_reviews.py`,
  `api/board_cell_geometry_pending.py`
- `packages/admin-api-client`, `apps/reviewer/src/security/reviewer-proxy-policy.ts`

## Test cases

- predykcja z atrapą predyktora → identyfikatory aktywnych symboli;
- brak predyktora → pusta lista; polityka proxy przepuszcza nowy POST.

## Verification

```powershell
npm run openapi:check
npm run test --workspace @game-predictor/reviewer
```

## Risks / open questions

- Podpowiedź planszy zgłoszonej pochodzi sprzed zmiany cięcia.

## Outcome

### Changed

- `VirtualGridCellSymbolSuggestion`, `review_item_symbols`,
  `preview_pending_slot_symbols`, `preview_manual_symbols`.
- `SqlAlchemyGridCorrectionSymbolRepository.current_symbols` /
  `active_symbol_ids_by_code`; dwa endpointy, OpenAPI, klient i wrappery.
- Allowlisty: `reviewer-proxy-policy.ts` oraz `security/local_admin.py`
  (druga nie była w planie — bez niej POST z originu 3001 byłby odrzucany).

### Verification results

- `test_virtual_grid_geometry.py` + `_repository.py`: 56 passed.
- `test_board_cell_geometry_pending.py`, `test_image_grid_review_api.py`,
  `test_local_admin_security.py`: zielone; PostgreSQL 1 passed.
- Klient 76/76; Reviewer 199/199; `export_admin_openapi.py --check` i
  `check:generated` aktualne; Ruff i Prettier czyste dla zmienionych plików.

### Not completed

- Predykcja modelu dla plansz zgłoszonych (poza zakresem planu).

### Documentation updates

- `API_CONTRACT.md`, `CURRENT_STATE.md`.

### Recommended next task

- TASK-0819.
