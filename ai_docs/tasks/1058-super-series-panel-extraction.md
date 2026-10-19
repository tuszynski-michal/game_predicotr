# TASK-1058 — Wyniesienie widoku serii supergry do `@game-predictor/board-search-ui`

## Status

`todo`

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

Wypełnia agent po pracy.
