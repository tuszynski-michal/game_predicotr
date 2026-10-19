# TASK-1059 — Modal serii supergry w udostępnionej wyszukiwarce (Reviewer)

## Status

`todo`

## Goal

Kliknięcie znacznika supergry (trigger lub spin) w wynikach i w tabeli
przybliżonej wygranej otwiera modal `<dialog>` z `SuperGameSeriesPanel`; po
zamknięciu z edycją odświeżane są wyniki i zakres; działa w linku jednej gry
i w panelu wielu gier.

## Context

Plan `ai_docs/delivery/SHARE_SUPER_GAME_SERIES_EXECUTION_PLAN_20261018.md`,
decyzje G–H.

## Dependencies / entry conditions

- TASK-1056 (typy klienta), TASK-1057 (proxy), TASK-1058 (panel).
- Fakt: edytor wzoru ma globalny listener `keydown`
  (`board-search-workspace.tsx`, `handleKeyboardShortcut`); listener panelu
  serii też jest globalny; potrzebna jawna blokada.
- Fakt: po edycji w oknie linii wyniki odświeża `onBoardEdited →
  runSearch({preserveSelection: true})`, zakres `onRecalculate →
  setSearchKey(key + ':refresh')`.

## Recommended execution

`claude-fable-5-1` / `high` (warunkowo). Audyt Codex przed commitem.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- plan jak wyżej
- `ai_docs/requirements/ADMIN_APP.md`, „Udostępnianie wyszukiwania online”

## Scope

- `board-search-super-game-marker.tsx`: prop `onOpenSeries?(seriesId)`;
  z nim `<button type="button" className="boardSearchSuperGameLink">`;
  `seriesHref` bez zmian; brak obu → sam label.
- `board-search-results.tsx`, `board-search-approximate-win.tsx`: prop
  `onOpenSuperGameSeries?` przekazany do znacznika.
- `board-search-workspace.tsx`: prop `superGameSeries?: { client }`, stan
  `openSeries`, modal, `onClose(edited)` → `runSearch({ preserveSelection:
  true })` + `setSearchKey(key + ':refresh')`; `handleKeyboardShortcut`
  przerywa przy otwartym modalu.
- Nowy `packages/board-search-ui/src/super-game-series/super-game-series-modal.tsx`
  — `SuperGameSeriesModal`: natywny `<dialog>` + `showModal`, `onCancel` z
  `preventDefault`, „Zamknij”, powrót fokusu, nagłówek „Seria od #N”,
  `SuperGameStateBanner`, poll `getSuperGameSeriesState` gdy `fresh=false`
  i `refreshToken++` po powrocie `fresh=true`; `edited` z
  `onSeriesSaved`/`onBoardEdited`.
- `board-search-share-data-source.ts`: `getSuperGameSeriesState`,
  `listSuperGameSeriesBoards` (mapowanie publiczne → typy Admina: `gameId` =
  stała udostępnienia, `definedBy: null`, ids `null`),
  `setSuperGameSeriesSuperSymbol` (`PUT`, `credentials: 'same-origin'`,
  `clearData()` po odpowiedzi, 401 → `onUnauthorized`),
  `listNextUndefinedSuperGameSeries`; `toAdminSymbol` z
  `superGameTriggerCount`; `toAdminSearch` przekazuje `seriesId`.
- Bramki `board-search-share-gate.tsx` i `board-search-panel-gate.tsx`:
  `superGameSeries={{ client: dataSource }}`; strony importują
  `super-game-series.css`.

## Out of scope

- Lista serii, filtry, „Przelicz serie”, `refreshBoardSearchBoardDocument`
  w udostępnieniu, dziennik linku.

## Acceptance criteria

- [ ] Klik znacznika na karcie wyniku i w wierszu zakresu otwiera modal; bez
      `superGameSeries` znacznik jest samym labelem.
- [ ] Cyfry/Enter/Esc/N w modalu nie zmieniają wzoru ani nie uruchamiają
      wyszukiwania; Esc nie zamyka modala; Esc przy otwartym oknie linii
      zamyka tylko okno linii.
- [ ] Po zapisie super symbolu i zamknięciu wyniki i tabela zakresu pokazują
      nowy `superSymbolCode`; poprawka komórki z modala → to samo odświeżenie.
- [ ] Modal bez „← Lista serii” i „Przelicz serie”; z `SuperGameStateBanner`.
- [ ] Panel wielu gier: zmiana gry odmontowuje modal; klient serii używa
      prefiksu per gra.

## Technical notes

Błędy: 404 serii → komunikat panelu, modal zostaje z „Zamknij”; 409 →
`applySuperSymbolConflict` + ponowny odczyt; 422 → komunikat; 401 w trakcie →
`onUnauthorized` bramki; 429 → komunikat API; `fresh=false` → baner, zapis
dozwolony jak w Adminie. Nie używać literału `superGameSeriesHref:` w
Reviewerze (test Admina `board-search-super-game-link.test.mjs`).

## Expected files

- Istniejące: `packages/board-search-ui/src/board-search-super-game-marker.tsx`,
  `board-search-results.tsx`, `board-search-approximate-win.tsx`,
  `board-search-workspace.tsx`, `src/index.ts`,
  `apps/reviewer/src/features/board-search-share/board-search-share-data-source.ts`,
  `board-search-share-gate.tsx`,
  `apps/reviewer/src/features/board-search-panel/board-search-panel-gate.tsx`,
  `apps/reviewer/src/app/board-search/page.tsx`, `board-search-panel/page.tsx`,
  `packages/board-search-ui/test-interactions/board-search-super-game.test.mjs`,
  `apps/reviewer/test/board-search-share-data-source.test.mjs`.
- Nowe: `packages/board-search-ui/src/super-game-series/super-game-series-modal.tsx`,
  `packages/board-search-ui/test-interactions/super-game-series-modal.test.mjs`.

## Test cases

- Znacznik z `onOpenSeries` renderuje przycisk i wywołuje callback z
  `seriesId`; bez obu propsów brak akcji.
- Modal: otwarcie z wyniku, zapis → `onClose(true)` → ponowne
  `searchGameBoards`; `keydown '1'` nie wywołuje `placeSymbol`; Esc nie
  zamyka; „Zamknij” zwraca fokus.
- Źródło danych: mapowanie serii bez kluczy wewnętrznych, PUT z JSON i
  `credentials`, `clearData` po zapisie, `next-undefined` z/bez
  `afterTrigger`, `superGameTriggerCount`, marker z `seriesId`.

## Verification

```powershell
# D:\game_predicotr, timeout 120 s każda (build do 300 s)
npm run test --workspace @game-predictor/board-search-ui
npm run test:interactions --workspace @game-predictor/board-search-ui
npm run test --workspace @game-predictor/reviewer
npm run test:geometry --workspace @game-predictor/reviewer
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
npm run reviewer:build
```

## Risks / open questions

- Dwa `<dialog>` w top layer (okno linii nad modalem serii): w jsdom
  `showModal` stubowany.

## Outcome

Wypełnia agent po pracy.
