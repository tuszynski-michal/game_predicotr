---
title: TASK-0764 — Modal planszy z liniami wypłat i kolumna akcji w tabeli
status: done
last_updated: 2026-09-30
---

# TASK-0764 — Modal planszy z liniami wypłat i kolumna akcji w tabeli

## Status

`done`

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

- [x] Przycisk w każdym wierszu ma `aria-label` z numerem planszy; fokus wraca po zamknięciu.
- [x] Esc i kliknięcie tła zamykają modal.
- [x] Wyłączenie jednej linii nie zmienia pozostałych; nowe otwarcie zaczyna od wszystkich widocznych.
- [x] Kolory stabilne według `paylineDisplayOrder`; legenda podaje nazwę (kolor nie jest jedynym nośnikiem).
- [x] Rozjazd sumy linii i wiersza albo inny `rulesVersionId` pokazuje komunikat bez rysunku linii; „Przelicz ponownie” zamyka modal i uruchamia kalkulację zakresu dla bieżącego klucza.
- [x] Ładowanie pokazuje stan „Wczytywanie planszy…”; 404/409/błąd sieci pokazuje komunikat i „Spróbuj ponownie”.
- [x] Szybkie przełączenie planszy nie pokazuje odpowiedzi dla poprzedniej planszy.
- [x] Błąd wczytania obrazu przełącza na schemat 3 × 5.
- [x] Brak widoku → schemat 3 × 5 z tymi samymi liniami.
- [x] Filtr progu i przewijanie tabeli działają jak wcześniej; brak mutacji.

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

### Changed

- Nowy `board-search-board-lines-state.ts`: paleta o wysokim kontraście z
  wzorem kreskowania po jej wyczerpaniu, kolor według `paylineDisplayOrder`
  (stały między planszami), środki pól, widoczność linii, kontrola
  spójności (wypłata, wersja reguł, suma linii), przesunięcia linii,
  komórki schematu 3 × 5.
- Nowy `board-search-board-lines-modal.tsx`: `<dialog>` z przyciętym widokiem
  (URL z `viewRevision`), obrysami pól, łamanymi przez środki pól,
  znacznikami jokerów i nakładką `?`; schemat 3 × 5 przy braku widoku,
  siatki albo błędzie obrazu; legenda z przełącznikami i „Pokaż/Ukryj
  wszystkie”; stany ładowania i błędu z „Spróbuj ponownie”; „Przelicz
  ponownie” przy niespójności; ochrona przed spóźnioną odpowiedzią;
  zamknięcie zwraca fokus na przycisk wiersza.
- `board-search-approximate-win.tsx`: piąta kolumna z ukrytym nagłówkiem
  „Akcje” i przyciskiem „Pokaż planszę”; `board-search-workspace.tsx`:
  metody klienta i symbole gry; `globals.css`: style modala.
- Testy: 6 testów stanu, test interakcji modala (linie, legenda, nakładki,
  schemat, Esc, fokus, błąd i ponowienie, niespójność i przeliczenie).

### Verification results

- `npm run test --workspace @game-predictor/admin`: 648/648 PASS.
- Testy interakcji `board-search-*`: 26/26 PASS.
- Typecheck i lint Admina: 0 błędów.
- Statyczny zrzut modala w przeglądarce: dwie linie w kolorach, joker,
  `?`, legenda.
- Audyt niezależnego agenta `claude-opus-5-5` (poziom rozumowania agenta
  nieustawialny z sesji): cykl 1 FAIL — P2 fokus nie wracał w prawdziwej
  przeglądarce (fokus przed zamknięciem natywnego modala), P2 kolor linii
  zależny od zestawu wygranych linii; 5 × P3. Cykl 2 PASS.

### Not completed

- Po „Przelicz ponownie” fokus trafia na `body`, bo wynik przelicza się od
  nowa (P3, zgodne z planem: operator otwiera modal ponownie).
- Testy interakcji dla kliknięcia tła i tekstu ładowania (P3).

### Documentation updates

- Brak dodatkowych; wymagania zapisane w TASK-0760.

### Recommended next task

- Odbiór etapu A przez operatora; etap B (TASK-0765) po osobnym poleceniu.
