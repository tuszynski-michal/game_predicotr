# TASK-0782 — Zmiana kolejności symboli gry w katalogu

## Status

`done`

## Goal

Operator zmienia kolejność symboli gry przyciskami „w górę / w dół” w katalogu
symboli, a skróty cyfrowe 1–9 (weryfikacja symboli, wyszukiwarka plansz)
podążają za nową kolejnością.

## Context

W grze 777 symbol „7” został dodany jako ósmy, więc wszędzie ma skrót `8`, a
„gwiazda” ma `7`. Skróty wynikają z `display_order` symbolu
(`apps/admin/src/features/symbol-reviews/symbol-review-keyboard.ts`,
`apps/admin/src/features/board-search/board-search-keyboard.ts`). API nadaje
`display_order` przy utworzeniu, a `PATCH` symbolu go nie przyjmuje, mimo że
`CatalogService.update_symbol` już obsługuje parametr `display_order`.
Operator wybrał trwałą zmianę w API i panelu zamiast wyjątku per gra lub
ręcznego `UPDATE` w bazie.

## Dependencies / entry conditions

- Fakt: `SymbolModel.display_order` nie ma ograniczenia unikalności, tylko
  `>= 0`; remisy rozstrzyga `mobile_code`.
- Fakt: `display_order` nie zmienia sumy wypłat; worker używa go wyłącznie do
  kolejności iteracji i kolejności listy dopasowań
  (`domain/payout.py::_ordinary_symbols_by_display_order`).
- Fakt: snapshot mobilny kopiuje `display_order`; nowa kolejność pojawi się w
  aplikacji po kolejnym `snapshot:generate`.

## Recommended execution

Claude Opus 5.5, reasoning high (sesja bieżąca). Mała zmiana pionowa API +
klient + UI na istniejącym kontrakcie. Eskalacja: brak. Review: niezależny
audyt Opus 5.5 zgodnie z regułą operatora.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/API_CONTRACT.md` (operacje symboli)
- `ai_docs/requirements/ADMIN_APP.md`

## Scope

- `SymbolUpdate` przyjmuje opcjonalne `displayOrder` (liczba całkowita
  `0..2147483647`, jawne `null` odrzucane jak dla innych pól).
- Router `PATCH /api/v1/admin/games/{gameId}/symbols/{symbolId}` przekazuje
  `display_order` do `CatalogService.update_symbol`.
- OpenAPI i wygenerowany klient; test żądania klienta.
- Admin: czysta funkcja planująca zmianę kolejności (przesunięcie o jedną
  pozycję i przenumerowanie całej listy `0..n-1`), akcja wysyłająca `PATCH`
  tylko dla zmienionych symboli, przyciski „↑/↓” w wierszu listy symboli.
- Dokumentacja API i wymagań Admina.

## Out of scope

- Atomowy endpoint zmiany kolejności całej listy.
- Zmiana kolejności w wersjach reguł (osobne `displayOrder` linii).
- Ręczna zmiana danych 777 — operator wykona ją w panelu.
- Ponowne generowanie snapshotu mobilnego.

## Acceptance criteria

- [x] `PATCH` z `displayOrder` zmienia kolejność; lista symboli zwraca nowy
  porządek; wartość ujemna i `null` dają `422 VALIDATION_ERROR`.
- [x] Pominięte `displayOrder` zachowuje wartość (regresja edycji nazwy).
- [x] Klient wysyła `displayOrder` w ciele `updateSymbol`.
- [x] Przycisk „↑” przy symbolu na pozycji 8 przenosi go na pozycję 7, a
  poprzedni symbol z pozycji 7 na pozycję 8; skróty biorą nową kolejność.
- [x] Przyciski są nieaktywne na krańcach listy i w czasie trwającej mutacji.
- [x] Błąd częściowego zapisu pokazuje komunikat i odświeża listę z API.

## Technical notes

- Plan zmiany: lista posortowana jak w UI (`displayOrder`, `mobileCode`,
  `id`); zamień element z sąsiadem; nadaj indeksy `0..n-1`; wyślij `PATCH`
  tylko tam, gdzie `displayOrder` się zmienia. Przenumerowanie usuwa też
  istniejące remisy i luki.
- Przykład: `[A:0, B:1, C:1]`, „↑” dla C → `[A:0, C:1, B:2]`; `PATCH` C→1
  nie jest potrzebny, wysyłany jest tylko B→2.
- Zapisy są sekwencyjne i nieatomowe. Po sukcesie panel nakłada zapisane
  wartości lokalnie i sortuje listę; po błędzie wczytuje listę ponownie z API,
  aby pokazać rzeczywisty stan. Wybór gry jest zablokowany w trakcie zapisu.
  Remis po częściowym błędzie jest bezpieczny i znika przy kolejnym
  przesunięciu (przenumerowanie całej listy).

## Expected files

- `services/api/src/game_predictor_api/schemas/catalog.py::SymbolUpdate`
- `services/api/src/game_predictor_api/api/catalog.py::update_symbol`
- `services/api/tests/test_catalog_api.py`
- `packages/admin-api-client/openapi/openapi.json`, `src/generated/*`
- `packages/admin-api-client/test/client.test.mjs`
- `apps/admin/src/features/symbols/symbol-catalog-state.ts` (nowe
  `planSymbolReorder`)
- `apps/admin/src/features/symbols/symbol-catalog-actions.ts` (nowe
  `reorderSymbols`)
- `apps/admin/src/features/symbols/symbol-catalog.tsx`
- `apps/admin/test/symbol-catalog-*.test.mjs`
- `ai_docs/architecture/API_CONTRACT.md`, `ai_docs/requirements/ADMIN_APP.md`

## Test cases

- API: `PATCH displayOrder` → 200 i nowy porządek listy; `-1` → 422;
  `null` → 422; `PATCH name` bez `displayOrder` nie zmienia kolejności.
- Klient: ciało żądania zawiera `displayOrder`.
- Stan: przesunięcie w górę/w dół, krańce listy (brak zmian), remisy.
- Akcja: wysyła tylko zmienione symbole; zatrzymuje się na pierwszym błędzie.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_catalog_api.py services/api/tests/test_openapi_contract.py
npm run openapi:check
npm run test --workspace @game-predictor/admin-api-client
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run python:lint
```

## Risks / open questions

- Kolejność listy dopasowań wypłat w nowo liczonych wynikach może się zmienić
  (suma bez zmian).

## Outcome

Commit `v1.7.57` na gałęzi `feat/symbol-display-order` (worktree
`worktrees/symbol-display-order`, baza `v1.7.56` / `7fd01d92`).

### Changed

- `SymbolUpdate.display_order` (`0..2147483647`, `null` odrzucane) i
  przekazanie w `update_symbol`; OpenAPI i `types.gen.ts` zregenerowane.
- Admin: `planSymbolReorder`, `applySymbolDisplayOrderChanges`,
  `reorderSymbols`; przyciski „↑/↓” w wierszu katalogu, blokada przycisków i
  wyboru gry w trakcie zapisu, przeładowanie listy po błędzie.
- `API_CONTRACT.md` (pola `PATCH` symbolu), `ADMIN_APP.md` (reguła kolejności).

### Verification results

- `pytest services/api/tests/test_catalog_api.py`: 5 passed.
- `test_openapi_contract.py`: 2 failed / 15 passed — te same 2 porażki
  (`test_grid_review_openapi_is_topology_aware_and_checksum_bound`,
  `test_operational_image_reviews_openapi_exposes_bounded_cursor_queue`)
  występują na czystym `7fd01d92`; niezwiązane z taskiem (po TASK-0727).
- `export_admin_openapi.py --check`, `check:generated`: aktualne.
- `@game-predictor/admin-api-client` test: 67 pass. Admin `test`: 619 pass;
  nowy `test-interactions/symbol-catalog-reorder.test.mjs`: 3 pass.
- Admin `typecheck` PASS, `lint` 0 błędów (4 wcześniejsze ostrzeżenia w innych
  plikach); ruff + ruff format + mypy dla zmienionych plików Pythona PASS.
- Audyt Opus 5.5: cykl 1 — brak P0/P1, P2 (brak testu UI) naprawione wraz z
  P3 (blokada wyboru gry, notatka taska, pliki tylko z EOL); cykl 2 — brak
  P0–P2.

### Not completed

- Zamiana „7”/„gwiazda” w grze 777 — operator wykona w panelu.
- Świadomie poza zakresem (P3 audytu): remis w weryfikacji symboli
  rozstrzygany po `code` zamiast `mobileCode` (widoczny tylko po częściowym
  błędzie zapisu), luźna walidacja `int` (akceptuje `true`), zarchiwizowane
  symbole w liście katalogu, nieaktualne zdanie o `DELETE` w
  `API_CONTRACT.md`.

### Documentation updates

- `API_CONTRACT.md`, `ADMIN_APP.md`, `CURRENT_STATE.md`.

### Recommended next task

- Scalić `feat/symbol-display-order` do `v1.1-vision-lab-hybrid-geometry`.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0782 | Claude Opus 5.5 | high | Mały pion API+klient+UI na istniejącym kontrakcie; wymaga spójnej regeneracji OpenAPI. | Tak — niezależny audyt Claude Opus 5.5 (poziom rozumowania dziedziczony, nie da się ustawić jawnie). |
