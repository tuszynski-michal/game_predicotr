# TASK-0720 — Filtr i tooltip „Przybliżonej wygranej”

## Status

done

## Goal

Tabela „Przybliżonej wygranej” pokazuje cztery istotne kolumny i do 10 wierszy,
ma lokalny filtr minimalnej wypłaty, a wykres pokazuje narastający bilans z
tooltipem punktu; zakres wygranej przyjmuje do 100 000 spinów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/tasks/completed/0719-approximate-win-scroll-table-and-chart.md`

## Scope

- Kolumny: Spin, Plansza, Wypłata, Bilans narastająco.
- Przewijalna tabela o wysokości około 10 rekordów.
- Suwak minimalnej wypłaty filtrujący wyłącznie widoczną tabelę, bez żądania API.
- Tooltip wykresu po najechaniu: liczba spinów i narastający bilans.
- Rozszerzenie zakresu podczas realizacji (polecenie operatora): wykres
  pokazuje narastający bilans (wypłaty minus koszt) zamiast samych wypłat, a
  maksymalny „Zakres wygranej” rośnie z 10 000 do 100 000 spinów
  (`APPROXIMATE_WIN_SPIN_COUNT_MAX`, walidacja API, OpenAPI, stała Admina).
- Testy, wymaganie i CURRENT_STATE.

## Out of scope

- Zmiana algorytmu payoutu i kształtu odpowiedzi API (poza górną granicą
  `spinCount`).

## Acceptance criteria

- [x] Tabela ma dokładnie cztery wskazane kolumny i widocznych około 10 wierszy.
- [x] Zmiana suwaka filtruje tabelę lokalnie i nie powoduje obliczenia ponownego.
- [x] Najechanie na wykres pokazuje tooltip ze spinami i wygraną.
- [x] Testy, lint i typecheck Admina przechodzą.

## Technical notes

Suwak ma zakres od zera do najwyższej wypłaty aktualnej odpowiedzi i pokazuje
wartość liczbową. Wykres pozostaje pełnym przebiegiem odpowiedzi; filtr ma
zgodnie z poleceniem użytkownika wpływ tylko na tabelę.

## Expected files

- `apps/admin/src/features/board-search/board-search-approximate-win.tsx`
- `apps/admin/src/features/board-search/board-search-approximate-win-state.ts`
- `apps/admin/src/app/globals.css`
- `apps/admin/test/board-search-approximate-win-state.test.mjs`
- `apps/admin/test-interactions/board-search-approximate-win.test.mjs`
- `ai_docs/requirements/ADMIN_APP.md`, `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run test:geometry --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
```

## Outcome

### Changed

- Admin `board-search-approximate-win.tsx`: tabela z kolumnami Spin, Plansza,
  Wypłata, Bilans narastająco (plansza częściowa oznaczona jako potwierdzone
  minimum), obszar przewijania ~10 wierszy (`max-block-size: 360px`), suwak
  „Minimalna wypłata w tabeli” filtrujący lokalnie tylko tabelę
  (`filterApproximateWinRows`), wykres narastającego bilansu z tooltipem
  najbliższego punktu wypłaty lub końca zakresu (liczba spinów, bilans);
  seria bilansu ma punkt tuż przed każdą wypłatą (spadek o koszt spinów) i
  kończy się na ostatnim spinie zakresu bilansem z podsumowania, z etykietą
  minimum i linią zera. Minimum i maksimum liczone pętlą
  (`approximateWinExtremes`), bez rozwijania dużych tablic w argumenty.
- Zakres wygranej do 100 000 spinów: `APPROXIMATE_WIN_SPIN_COUNT_MAX`
  (API i walidacja zapytania), OpenAPI, `APPROXIMATE_WIN_RANGE_MAX` Admina,
  `API_CONTRACT.md`, `ADMIN_APP.md`.
- Testy: stan (seria bilansu z punktami przed wypłatą i końcem zakresu,
  ekstrema dla 200 001 wartości, filtr), interakcje (kolumny, filtr bez
  nowego żądania i bez zmiany podsumowania oraz wykresu, linia zera, tooltip
  końca zakresu, odrzucenie spóźnionej odpowiedzi po zwinięciu), test API
  górnej granicy `spinCount` wyliczany ze stałej.

### Verification results

- Admin: typecheck, lint PASS; `npm run test` 616/616; `test:geometry`
  wszystkie testy „Przybliżonej wygranej” PASS, jedyna porażka
  `bulk unreadable reconciles…` występuje też na HEAD.
- API: `test_board_search_approximate_win_api.py` +
  `test_board_search_approximate_win_domain.py` 42 passed;
  `openapi:check` PASS.
- Pomiar na żywej grze `777` (odczyt, start 1): 10 000 spinów — 2,1 s,
  100 000 spinów — 17,5 s i 10 110 wierszy odpowiedzi; Admin nie ma limitu
  czasu żądania, więc wynik pojawia się po stanie ładowania.
- Audyt claude-opus-5-5 (subagent, poziom rozumowania dziedziczony): brak
  P0–P1, 1× P2 — wykres bilansu łączył tylko punkty po wypłatach (ukrywał
  spadki, kończył się na ostatniej wypłacie); poprawione jak opisano wyżej
  wraz z P3: asercje filtra lokalnego, pętla zamiast `Math.max(...)`, filtr
  liczony raz na render. Pozostałe P3: brak przerywania starszych żądań
  (`AbortController`), pozycja tooltipu przy krawędziach wąskiego wykresu.

### Not completed

- Tabela nie jest wirtualizowana: przy 100 000 spinów renderuje ~10 tys.
  wierszy (filtr minimalnej wypłaty ogranicza widok).

### Documentation updates

- `ADMIN_APP.md` (tabela, filtr, wykres bilansu, zakres), `API_CONTRACT.md`,
  `CURRENT_STATE.md`.

### Recommended next task

- Brak; ewentualnie wirtualizacja tabeli, jeśli 100 000 spinów okaże się
  wolne w przeglądarce.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0720 | gpt-6-sol | medium | Lokalna, deterministyczna zmiana jednego komponentu Admina. | Niewymagany; lint, typecheck i testy interakcji. Domknięcie (testy, dokumentacja, commit) wykonał claude-opus-5-5. |
