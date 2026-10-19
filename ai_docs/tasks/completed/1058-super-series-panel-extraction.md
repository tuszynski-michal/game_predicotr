# TASK-1058 — Wyniesienie widoku serii supergry do `@game-predictor/board-search-ui`

## Status

`done`

## Goal

`SuperGameSeriesPanel` we wspólnym pakiecie z wąskim interfejsem klienta;
Admin konsumuje panel, a istniejące testy Admina przechodzą bez zmiany
semantyki.

## Context

Plan `ai_docs/delivery/SHARE_SUPER_GAME_SERIES_EXECUTION_PLAN_20261018.md`,
decyzje E–F. Reviewer nie może importować z `apps/admin`; widok serii ma być
współdzielony, nie kopiowany.

## Dependencies / entry conditions

- Niezależny od TASK-1056/1057 (czysta refaktoryzacja Admina).
- Fakt: `apps/admin/test/super-game-series-workspace-contract.test.mjs`
  sprawdza regexami tekst pliku workspace; test interakcji
  `apps/admin/test-interactions/super-game-series-workspace.test.mjs` odpytuje
  DOM po aria/tekście/`data-testid`/`data-badge`/`polygon[data-cell]`.
- Fakt: `packages/board-search-ui` używa globalnych CSS importowanych w
  `apps/admin/src/app/layout.tsx` i stronach Reviewera; pakietowe
  `keyboard-shortcuts.ts` nie ma `extendedDigitShortcut*`.

## Recommended execution

`claude-fable-5-1` / `high` (warunkowo). Review tylko, gdy testy Admina
wymagają zmian poza testem kontraktu.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- plan jak wyżej
- `ai_docs/requirements/ADMIN_APP.md`, „Sekcja „Supergry””

## Scope

Nowe pliki (proponowane) w `packages/board-search-ui/src/super-game-series/`:

- `super-game-series-client.ts` — `SuperGameSeriesViewClient = BoardLinesClient
  & { listSuperGameSeriesBoards; setSuperGameSeriesSuperSymbol;
  listNextUndefinedSuperGameSeries }`.
- `super-game-series-state.ts` — przeniesione z Admina: filtry serii i
  zakres, `pickNextUndefinedSeries`, komunikaty, blok „Series view”, „Super
  symbol choice”, „Retrigger review”, badges, błędy,
  `isSeriesGenerationStale`. W Adminie zostają funkcje listy, zapytań,
  banera stanu, derive i wersji reguł; Admin re-eksportuje przeniesione
  symbole.
- `super-game-series-keyboard.ts` — przeniesiony; pakietowe
  `keyboard-shortcuts.ts` zyskuje `EXTENDED_DIGIT_SHORTCUT_LIMIT`,
  `extendedDigitShortcutIndex`, `extendedDigitShortcutLabel`.
- `super-game-series-panel.tsx` — `SuperGameSeriesPanel` (cykl otwartej
  serii) + `SeriesView` („← Lista serii” tylko z `onBack`), `SeriesBoardView`,
  `SeriesBadges`. Props: `client`, `gameId`, `seriesId`, `symbols`,
  `filters?`, `rulesVersionId?`, `rulesVersions?`, `refreshToken?`,
  `onSeriesChange`, `onBack?`, `onSeriesLoaded?`, `onSeriesSaved?`,
  `onSuperGameStateChange?`, `onBoardEdited?`, `formatAmount?`.
- `super-game-series.css` — globalne klasy `superGameSeries*`; eksport w
  `package.json`; import w `apps/admin/src/app/layout.tsx`.
- Eksporty w `packages/board-search-ui/src/index.ts`.

Admin `super-game-series-workspace.tsx` renderuje panel z adapterem
`listNextUndefinedSuperGameSeries` na `listSuperGameSeries` +
`nextUndefinedSeriesQuery`; poll `state` zostaje w Adminie.

## Out of scope

- Modal i adapter Reviewera (TASK-1059), zmiany zachowania Admina.

## Acceptance criteria

- [ ] Admin: `npm run test` i `npm run test:geometry` zielone; testy
      interakcji bez zmian treści; liczba wywołań `getSuperGameSeriesState`
      bez zmian.
- [ ] Panel bez `onBack` nie renderuje „← Lista serii”; bez `rulesVersions`
      okno linii dostaje `rulesVersions={null}`.
- [ ] Nowy test interakcji pakietu `super-game-series-panel.test.mjs`.
- [ ] `npm run code-map:check` po regeneracji mapy.

## Technical notes

Chronione zachowanie: atrybuty DOM z testów Admina (`aria-label="Karuzela
pozycji serii"`, `aria-label="Pozycje serii"`, `data-testid="missing-card"`,
`data-badge`, `svg polygon[data-cell]`, teksty przycisków). Jedyna zmiana
istniejącego testu Admina: test kontraktu czyta dodatkowo plik panelu
pakietu; `styles\.triggerCell` → `superGameSeriesTriggerCell`.

## Expected files

- Istniejące: `apps/admin/src/features/super-games/super-game-series-workspace.tsx`
  (+ `.module.css`), `super-game-series-state.ts`,
  `super-game-series-keyboard.ts`, `apps/admin/src/app/layout.tsx`,
  `apps/admin/test/super-game-series-workspace-contract.test.mjs`,
  `packages/board-search-ui/src/index.ts`, `keyboard-shortcuts.ts`,
  `package.json`, `ai_docs/architecture/CODE_MAP*.md`.
- Nowe: jak w Scope oraz
  `packages/board-search-ui/test-interactions/super-game-series-panel.test.mjs`.

## Test cases

- Panel: odczyt i karuzela; zapis z `expectedRevision`; 409 →
  `applySuperSymbolConflict` + ponowny odczyt; `afterTrigger` i zawinięcie;
  skróty zablokowane przy `linesOpen` i w `select`; `refreshToken` wymusza
  odczyt; brak „← Lista serii” bez `onBack`.
- Regresja: wszystkie testy Admina.

## Verification

```powershell
# D:\game_predicotr, timeout 120 s każda
npm run test --workspace @game-predictor/board-search-ui
npm run test:interactions --workspace @game-predictor/board-search-ui
npm run test --workspace @game-predictor/admin
npm run test:geometry --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/board-search-ui
npm run lint --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/board-search-ui
.\.venv\Scripts\python.exe scripts/generate_code_map.py
npm run code-map:check
```

## Risks / open questions

- Stub `showModal` w jsdom (jak w teście Admina) potrzebny w nowym teście
  pakietu.
- Przed TASK-1053 10 testów interakcji Admina padało środowiskowo
  (`tasks/completed/1055-…`, „22/32”); porównać wynik z `main` przed zmianą.

## Outcome

Commit: v1.7.427 / `8d682a44bc3942ff822c41bab1d34f8c9973e7c5`.

### Changed

- `packages/board-search-ui/src/super-game-series/` (nowe):
  `super-game-series-panel.tsx` (`SuperGameSeriesPanel`, `SeriesBadges`;
  cykl otwartej serii: odczyt, karuzela, szczegóły plansz, zapis CAS z
  przeglądem retriggerów, „Następna bez symbolu”, skróty, okno linii, toast;
  propsy `client`, `gameId`, `seriesId`, `symbols`, `filters?`,
  `rulesVersionId?` (`undefined` = host jeszcze nie wybrał), `rulesVersions?`,
  `refreshToken?`, `initialSequenceNumber?`, `formatAmount?`, `onSeriesChange`,
  `onBack?`, `onSeriesLoaded?`, `onSeriesSaved?`, `onSuperGameStateChange?`,
  `onBoardEdited?`; spóźnione odpowiedzi po odmontowaniu są ignorowane),
  `super-game-series-state.ts` (filtry, zakres, `pickNextUndefinedSeries`,
  komunikaty, widok serii, wybór symbolu, przegląd retriggerów, odznaki,
  błędy; nowe `seriesCardIndexOf`), `super-game-series-keyboard.ts`,
  `super-game-series-client.ts` (`SuperGameSeriesViewClient`,
  `SuperGameSeriesModalClient`), `super-game-series.css` (klasy
  `superGameSeries*`, także style modala dla TASK-1059).
- `packages/board-search-ui/src/keyboard-shortcuts.ts`:
  `EXTENDED_DIGIT_SHORTCUT_LIMIT`, `extendedDigitShortcutIndex`,
  `extendedDigitShortcutLabel`; `package.json` eksportuje
  `./super-game-series/*` i `./super-game-series.css`; `src/index.ts`
  eksportuje panel, odznaki i typy klienta.
- Admin: `super-game-series-workspace.tsx` zachowuje listę, filtry, zakres,
  derive, odpytywanie stanu i toast; otwartą serię renderuje
  `SuperGameSeriesPanel` z adapterem `seriesViewClient` (następna seria =
  `listSuperGameSeries` + `nextUndefinedSeriesQuery`); `onBoardEdited` i
  `onSeriesSaved` odświeżają listę, `refreshToken` po przeliczeniu serii.
  `super-game-series-state.ts` re-eksportuje moduł pakietu i zachowuje część
  listy; `super-game-series-keyboard.ts` to re-eksport; CSS module bez reguł
  widoku; `app/layout.tsx` importuje `super-game-series.css`.
- Testy: nowy `packages/board-search-ui/test-interactions/super-game-series-panel.test.mjs`
  (8 testów); `apps/admin/test/super-game-series-workspace-contract.test.mjs`
  czyta także plik panelu (`superGameSeriesTriggerCell`,
  `onSeriesSaved={reloadList}`);
  `apps/admin/test-interactions/super-game-series-workspace.test.mjs` dostał
  hook `resolve` przypinający jedną kopię React (wzór z
  `board-search-sharing-workspace.test.mjs`), bo panel z pakietu rozwiązuje
  React z głównego `node_modules`, a Admin ma własną kopię 19.2.3; asercje
  bez zmian.
- Mapa kodu zregenerowana.

### Verification results

- `npm run test --workspace @game-predictor/board-search-ui`: 102 passed;
  `npm run test:interactions`: 76 passed (68 + 8 nowych).
- `npm run test --workspace @game-predictor/admin`: 804 passed, 0 failed.
- `npm run test:geometry --workspace @game-predictor/admin`,
  `super-game-series-workspace.test.mjs`: 22 passed / 10 failed, dokładnie te
  same 10 co na bazowym commicie (sprawdzone przez `git stash`; lista w
  `tasks/completed/1055-…`, „10 porażek sprzed TASK-1053”). Bez hooka React
  padało 30 (dwie kopie React: `apps/admin/node_modules/react` 19.2.3 i
  główne 19.2.8).
- Typecheck admin i board-search-ui: OK; lint board-search-ui: 0 problemów;
  lint admin: 5 ostrzeżeń wyłącznie w `page-geometry-correction-panel.tsx`
  (sprzed taska); prettier: OK; `npm run code-map:check`: OK.

### Not completed

- 10 porażek testu interakcji Admina sprzed TASK-1053 pozostają poza
  zakresem (nie dotyczą panelu: lista, „Wczytaj kolejne”, katalog symboli).

### Documentation updates

- `ai_docs/architecture/CODE_MAP*.md`; `ADMIN_APP.md` w TASK-1060.

### Recommended next task

- TASK-1060, potem TASK-1057 i TASK-1059 (modal używa panelu).
