# TASK-1054 — Filtr zakresu plansz na liście serii supergry

## Status

`done`

## Goal

Lista serii sekcji „Supergry” ma filtr zakresu plansz (od–do numeru
sekwencji triggera), a przejście do następnej serii bez symbolu nie wychodzi
poza ten zakres.

## Context

Operator weryfikuje super symbole serii Mumii zakresami (np. plansze 1–1000).
Dziś musi przewijać całą listę. Prośba operatora z 2026-10-18, po TASK-1053.

## Dependencies / entry conditions

- TASK-1053 (gałąź `claude/super-series-next-undefined`, v1.7.419–420).
- Fakt: lista API jest posortowana po `triggerSequenceNumber`, a `cursor` to
  numer triggera, po którym zaczyna się strona (`API_CONTRACT.md`, „Serie
  supergry”). Początek zakresu to `cursor = od − 1`; koniec zakresu Admin
  ucina po stronie klienta i kończy stronicowanie. Zmiana API nie jest
  potrzebna.

## Recommended execution

`claude-opus-5-5` / `high` (poza planem; prośba operatora w czacie).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`, „Sekcja „Supergry””
- `ai_docs/architecture/API_CONTRACT.md`, „Serie supergry”

## Scope

- Pola „Plansze od” i „do” (liczby całkowite ≥ 1, od ≤ do; każde opcjonalne)
  z przyciskiem „Zastosuj zakres” (także `Enter`) i „Wyczyść zakres”.
- Seria należy do zakresu, gdy jej trigger leży w zakresie.
- Lista, „Wczytaj kolejne”, usunięcie wiersza po zapisie symbolu oraz
  „Następna bez symbolu” (`N`, po zapisie) respektują zakres.

## Out of scope

- Licznik serii bez symbolu w zakresie (licznik zostaje globalny; wymaga API).
- Zakres w adresie URL.

## Acceptance criteria

- [x] Zakres zmienia zapytanie pierwszej strony (`cursor = od − 1`) i ucina
      wiersze za końcem zakresu, bez „Wczytaj kolejne” za końcem.
- [x] Błędny zakres (nie liczba, < 1, od > do) pokazuje błąd i nie zmienia listy.
- [x] „Następna bez symbolu” szuka tylko w zakresie, także przy powrocie na
      początek.
- [x] Testy stanu i interakcji; lint, typecheck, prettier zielone.

## Technical notes

`SeriesFilters` dostaje `fromSequence` i `toSequence` (`null` = bez granicy).
Czyste funkcje w `super-game-series-state.ts`: zapytanie, ucinanie strony,
dopasowanie serii, parsowanie pól zakresu.

## Expected files

- `apps/admin/src/features/super-games/super-game-series-state.ts`
- `apps/admin/src/features/super-games/super-game-series-workspace.tsx` (+ CSS)
- `apps/admin/test/super-game-series-state.test.mjs`
- `apps/admin/test-interactions/super-game-series-workspace.test.mjs`
- `ai_docs/requirements/ADMIN_APP.md`

## Test cases

- Zapytanie z zakresem i bez; strona z wierszami za końcem zakresu.
- Parsowanie: puste, liczby, błędy.
- Interakcja: zastosowanie i wyczyszczenie zakresu, następna seria w zakresie.

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run test:geometry --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
```

## Risks / open questions

- Założenie: zakres dotyczy numeru planszy wyzwalającej serii (triggera).

## Outcome

Commit: v1.7.421 (hash dopisuje kolejny commit).

### Changed

- `super-game-series-state.ts`: `SeriesFilters.fromSequence`/`toSequence`
  (opcjonalne, `null` = otwarty koniec), `seriesBoardRange`,
  `seriesInBoardRange`, `parseSeriesBoardRange`, `seriesBoardRangeLabel`,
  `clipSeriesPageToRange`; `seriesListQuery` zaczyna od `cursor = od − 1`,
  `applySeriesListPage` ucina stronę za końcem zakresu i kończy
  stronicowanie, `seriesMatchesFilters` i `pickNextUndefinedSeries` sprawdzają
  zakres, komunikat braku serii podaje zakres.
- `super-game-series-workspace.tsx` (+ CSS): formularz „Plansze od / do” z
  „Zastosuj zakres” (`Enter`) i „Wyczyść zakres”, etykieta aktywnego zakresu,
  komunikat błędu; „Następna bez symbolu” szuka w zakresie.
- `ADMIN_APP.md`, sekcja „Supergry”; mapa kodu zregenerowana.

### Verification results

- `node --test test/super-game-series-*.test.mjs`: 58/58 (4 nowe testy
  zakresu).
- `tsx --test test-interactions/super-game-series-workspace.test.mjs`: 22/32;
  2 nowe testy zakresu przechodzą, 10 porażek sprzed TASK-1053 bez zmian.
- `npm run typecheck` (admin) OK; `eslint` zmienionych plików 0 problemów;
  `prettier --check` OK.
- Ręcznie w Adminie (Mumie a1): zakres 1–1000 pokazuje 10 serii (#119–#997),
  bez „Wczytaj kolejne”; tylko odczyt.

### Not completed

- Licznik serii bez symbolu w zakresie (wymaga rozszerzenia API) i zakres w
  adresie URL: poza zakresem.

### Documentation updates

- `ai_docs/requirements/ADMIN_APP.md`, `ai_docs/architecture/CODE_MAP*.md`.

### Recommended next task

- Opcjonalnie: licznik serii bez symbolu w zakresie (parametry zakresu w API).
