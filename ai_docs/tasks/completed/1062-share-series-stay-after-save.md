# TASK-1062 — Modal serii odbiorcy zostaje na zapisanej serii

## Status

`done`

## Goal

Po zapisie super symbolu w modalu udostępnionej wyszukiwarki widok zostaje na
zapisanej serii; „Następna bez symbolu (N)” działa tylko ręcznie. Admin bez
zmian (po zapisie nadal otwiera następną serię, TASK-1053).

## Context

Odbiór D-564 (operator, 2026-10-19): po zapisie z linku modal od razu otworzył
następną serię bez symbolu (#214537 po zapisie #214352), co wyglądało jak brak
zapisu. Decyzja operatora: w modalu bez automatycznego skoku.

## Dependencies / entry conditions

- `main` v1.7.431 (plan `SHARE_SUPER_GAME_SERIES_EXECUTION_PLAN_20261018.md`
  scalony). Fakt: skok wykonuje `findNextUndefinedSeries` w
  `SuperGameSeriesPanel` po udanym zapisie z symbolem.

## Recommended execution

`claude-fable-5-1` / `high` (warunkowo); poprawka UX po odbiorze, bez audytu
(decyzja operatora w czacie).

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`, „Widok serii supergry odbiorcy”
- D-564

## Scope

- `SuperGameSeriesPanel`: prop `advanceAfterSave?` (domyślnie `true`, jak
  Admin); `false` zostawia zapisaną serię z komunikatem o zapisie.
- `SuperGameSeriesModal` przekazuje `advanceAfterSave={false}`.
- Testy modalu i panelu; `ADMIN_APP.md`.

## Out of scope

- Zachowanie Admina; komunikaty toastu.

## Acceptance criteria

- [ ] Po zapisie w modalu seria zostaje otwarta z komunikatem „Zapisano super
      symbol …”, select pokazuje zapisany symbol, `N` otwiera następną serię.
- [ ] Admin po zapisie nadal otwiera następną serię (test interakcji Admina).
- [ ] `ADMIN_APP.md` opisuje różnicę.

## Expected files

- `packages/board-search-ui/src/super-game-series/super-game-series-panel.tsx`,
  `super-game-series-modal.tsx`,
  `packages/board-search-ui/test-interactions/super-game-series-modal.test.mjs`,
  `super-game-series-panel.test.mjs`, `ai_docs/requirements/ADMIN_APP.md`.

## Test cases

- Modal: zapis → ta sama seria, komunikat sukcesu, `N` → następna.
- Panel z domyślnym `advanceAfterSave` → skok (istniejący test).

## Verification

```powershell
npm run test:interactions --workspace @game-predictor/board-search-ui
npm run test:geometry --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/board-search-ui
```

## Risks / open questions

- Brak.

## Outcome

Commit: v1.7.432 / `82d88208aa4db0241f4ca897b623c5256374bd0c` (numer wersji zdublowany z równoległą naprawą linku wielu gier; task przenumerowany z TASK-1061 na TASK-1062 po scaleniu, kolizja z `1061-multi-game-share-storage-routing.md`).

### Changed

- `super-game-series-panel.tsx`: prop `advanceAfterSave` (domyślnie `true`);
  po zapisie z `false` seria zostaje otwarta z komunikatem
  `applySuperSymbolSaved`.
- `super-game-series-modal.tsx`: `advanceAfterSave={false}`.
- Testy modalu: zapis zostaje na serii (komunikat, select z symbolem, brak
  odczytu następnej serii), `N` otwiera następną; test wiersza zakresu
  dopasowany. `ADMIN_APP.md`: akapit o modalu odbiorcy.

### Verification results

- `npm run test:interactions --workspace @game-predictor/board-search-ui`:
  83 passed; typecheck i lint pakietu OK; prettier OK.
- Admin `super-game-series-workspace.test.mjs`: 22/32 (te same 10 porażek
  sprzed TASK-1053; skok po zapisie bez zmian).
- `npm run docs:check`: OK po zamknięciu.

### Not completed

- Nic.

### Documentation updates

- `ai_docs/requirements/ADMIN_APP.md`.

### Recommended next task

- Odbiór w linku i scalenie do `main`.
