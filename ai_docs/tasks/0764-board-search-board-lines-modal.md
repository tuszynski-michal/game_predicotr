---
title: TASK-0764 — Modal planszy z liniami wypłat i kolumna akcji w tabeli
status: todo
last_updated: 2026-09-30
---

# TASK-0764 — Modal planszy z liniami wypłat i kolumna akcji w tabeli

## Status

`todo`

## Goal

Każdy wiersz tabeli „Przybliżonej wygranej” ma przycisk otwierający modal z planszą, narysowanymi liniami wypłat i legendą z przełącznikiem każdej linii.

## Context

Punkt 1 zgłoszenia operatora z 2026-09-30. Plan: §3 R2, §5 T5.

## Dependencies / entry conditions

- TASK-0762 done (formatowanie kwot w stawce), TASK-0763 done (kontrakt i klient).

## Recommended execution

`claude-opus-5-5`, reasoning `high` (wiersz taska w tabeli planu). UI na gotowym kontrakcie; geometria nakładki i stan legendy. Audyt: niezależny agent `claude-opus-5-5` (`high` warunkowo — poziomu agenta nie da się ustawić jawnie). Dwa nieudane cykle poprawek P0–P2 zatrzymują etap.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/BOARD_SEARCH_SHARE_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`

## Scope

- Piąta kolumna bez widocznego nagłówka z przyciskiem „Pokaż planszę”.
- Modal `<dialog>` z SVG: widok planszy, łamane przez środki `matchedCells`, obrysy pól, znaczniki jokerów, nakładka `?` na nieznanych polach.
- Legenda: przełącznik, kolor, nazwa linii, symbol, długość, wypłata w stawce; „Pokaż wszystkie”, „Ukryj wszystkie”.
- Kontrola spójności (suma linii i `rulesVersionId`) i „Przelicz ponownie”.
- Stany ładowania i błędów, ochrona przed spóźnioną odpowiedzią, zapasowy schemat przy błędzie obrazu.
- Schemat 3 × 5 z ikon symboli, gdy brak widoku albo wielokątów.

## Out of scope

- Zmiany API.
- Udostępnianie online.

## Acceptance criteria

- [ ] Przycisk w każdym wierszu ma `aria-label` z numerem planszy; fokus wraca po zamknięciu.
- [ ] Esc i kliknięcie tła zamykają modal.
- [ ] Wyłączenie jednej linii nie zmienia pozostałych; nowe otwarcie zaczyna od wszystkich widocznych.
- [ ] Kolory stabilne według `paylineDisplayOrder`; legenda podaje nazwę (kolor nie jest jedynym nośnikiem).
- [ ] Rozjazd sumy linii i wiersza albo inny `rulesVersionId` pokazuje komunikat bez rysunku linii; „Przelicz ponownie” zamyka modal i uruchamia kalkulację zakresu dla bieżącego klucza.
- [ ] Ładowanie pokazuje stan „Wczytywanie planszy…”; 404/409/błąd sieci pokazuje komunikat i „Spróbuj ponownie”.
- [ ] Szybkie przełączenie planszy nie pokazuje odpowiedzi dla poprzedniej planszy.
- [ ] Błąd wczytania obrazu przełącza na schemat 3 × 5.
- [ ] Brak widoku → schemat 3 × 5 z tymi samymi liniami.
- [ ] Filtr progu i przewijanie tabeli działają jak wcześniej; brak mutacji.

## Technical notes

Stan modala w czystym module (proponowany) `board-search-board-lines-state.ts`:
`boardLinesPolygonCentroid(points)`, `boardLinesColor(displayOrder)` z palety
o wysokim kontraście (po wyczerpaniu kolorów — wzór kreskowania),
`toggleBoardLineVisibility(state, matchKey)`, `setAllBoardLinesVisibility`,
`boardLinesConsistency(detail, rowPayoutCredits, rulesVersionId)`.
„Przelicz ponownie” wywołuje przekazany z `BoardSearchApproximateWin`
callback ponownego obliczenia zakresu (istniejące `runCalculation`) i
zamyka modal. Pobieranie szczegółów z licznikiem żądań jak w
`BoardSearchApproximateWin` (odrzucenie spóźnionych odpowiedzi). `onError`
obrazu przełącza na schemat 3 × 5. Klucz dopasowania =
`paylineId + symbolCode`. Obraz widoku ładowany przez URL wrappera klienta
(cache HTTP `immutable`). Wzorzec dialogu: `SymbolReviewSourceModal`.
Klient w `BoardSearchClient` i `ApproximateWinClient` rozszerzony o nowe
metody. Linie z `vector-effect: non-scaling-stroke`.

## Expected files

- Istniejące: `apps/admin/src/features/board-search/board-search-approximate-win.tsx`, `board-search-workspace.tsx` (`BoardSearchClient`), `apps/admin/src/app/globals.css`.
- Nowe (proponowane): `apps/admin/src/features/board-search/board-search-board-lines-modal.tsx`, `board-search-board-lines-state.ts`, `apps/admin/test/board-search-board-lines-state.test.mjs`.

## Test cases

- Środek wielokąta prostokąta i trapezu.
- Stabilność kolorów dla tej samej kolejności.
- Przełączanie jednej linii i wszystkich.
- Spójność: suma równa i ta sama wersja reguł → OK; różna suma → `inconsistent`; inna wersja reguł → `inconsistent`.

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npx prettier --check apps/admin/src/features/board-search apps/admin/test
```

Wszystkie komendy z katalogu worktree, timeout 120 s każda.

## Risks / open questions

- Wiele nakładających się linii na tych samych polach: łamane z niewielkim przesunięciem per linia, aby pozostały rozróżnialne.

## Outcome

Wypełnia agent po pracy.
