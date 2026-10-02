---
title: TASK-0692 — Symbol image from a Symbol Verification cell
status: done
last_updated: 2026-09-25
---

# TASK-0692 — Grafika symbolu z pojedynczego cropa w Weryfikacji symboli

## Status

`done`

## Goal

W `Weryfikacji symboli` jeden zaznaczony crop można jednym przyciskiem
zatwierdzić (opcjonalnie jako wybrany symbol) i ustawić jako grafikę symbolu,
widoczną w `Symbole` i `Wyszukaj plansze`.

## Context

Zgłoszenie użytkownika 2026-09-25. Picker grafiki istniał tylko w sekcji
`Symbole` i wymagał wcześniej zatwierdzonego cropa. Decyzje użytkownika:
akcja wybiera symbol i od razu zatwierdza crop; Admin teraz, wydanie mobilne
później.

## Recommended execution

Wykonane bezpośrednio na prośbę użytkownika w bieżącej sesji
(`claude-opus-5-5`), bez osobnego planu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md` (Weryfikacja symboli)
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Endpoint `POST /api/v1/admin/games/{gameId}/symbol-cell-reviews/{cellReviewId}/symbol-reference`
  reużywający istniejącego wyboru grafiki (te same warunki kwalifikacji, plik i
  zapis co picker `Symbole`).
- OpenAPI, wygenerowany klient, wrapper `selectSymbolReferenceFromCellReview`,
  test żądania.
- Przycisk `Ustaw jako grafikę symbolu` w toolbarze weryfikacji.

## Out of scope

- Użycie wybranej grafiki w aplikacji mobilnej: aplikacja rozwiązuje dziś
  tylko wbudowane klucze `symbols/v01/*.png`
  (`apps/mobile/src/features/board/symbol-assets.ts`), więc wymaga osobnego
  zadania dołączającego grafiki do wydania.

## Acceptance criteria

- [x] Jeden zaznaczony crop → `approve` albo `reassign` (gdy wybrano symbol),
  następnie ustawienie grafiki symbolu.
- [x] Crop niekwalifikowany → 409 `SYMBOL_REFERENCE_CELL_NOT_ELIGIBLE`, bez zapisu.
- [x] Błąd grafiki po udanym zatwierdzeniu jest komunikowany wprost.
- [x] Kontrakt: backend, OpenAPI, klient, wrapper, test żądania.

## Outcome

### Changed

- `services/api/.../storage/symbol_references_repository.py::get_cell_review_candidate`,
  `application/symbol_references.py::ApprovedSymbolReferenceService.select_from_cell_review`,
  `api/symbol_references.py` (nowa trasa `selectSymbolReferenceFromCellReview`).
- `packages/admin-api-client`: wygenerowany klient i wrapper.
- `apps/admin/.../symbol-reviews/symbol-review-mutation-actions.ts::setSymbolImageFromReviewCell`,
  `symbol-review-workspace.tsx` (przycisk i obsługa wyniku).

### Verification results

- `pytest services/api/tests/test_symbol_references_repository.py
  services/api/tests/test_symbol_references_domain.py`: 9/9 (2 nowe).
- Ruff i `ruff format --check` czyste; mypy bez błędów w zmienionych plikach
  (wcześniejsze błędy w innych modułach bez zmian).
- Admin: 606/606 (4 nowe), `typecheck` czysty, `lint` tylko 4 wcześniejsze
  ostrzeżenia. Klient: 63/63 (1 nowy). `openapi:check`: aktualny.
- Prettier: w zmienionych plikach tylko wcześniejsze różnice
  (`index.ts`, `client.test.mjs`, jedna linia `symbol-review-workspace.tsx`).

### Not completed

- Brak odbioru na żywym Adminie: uruchomione API nie przeładowało nowej trasy
  (wymaga restartu API).
- Wydanie mobilne (poza zakresem).

### Documentation updates

- `ADMIN_APP.md` (Weryfikacja symboli), `API_CONTRACT.md`, `CURRENT_STATE.md`.

### Recommended next task

- Dołączanie wybranych grafik symboli do wydania mobilnego (APK offline).
