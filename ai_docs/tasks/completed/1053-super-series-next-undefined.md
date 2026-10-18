# TASK-1053 — Przejście do następnej serii supergry bez super symbolu

## Status

`done`

## Goal

W widoku serii sekcji „Supergry” operator jednym przyciskiem albo klawiszem
`N` otwiera następną (po numerze triggera) serię bez super symbolu, bez
powrotu do listy i przewijania.

## Context

Operator wybiera super symbole serii Mumii. Dziś po każdej serii musi wrócić
do listy, przewinąć do miejsca, w którym skończył, i otworzyć kolejną serię.
Prośba operatora z 2026-10-18.

## Dependencies / entry conditions

- Fakt: `listSuperGameSeries` sortuje po `triggerSequenceNumber`, a `cursor`
  to numer ostatniego triggera poprzedniej strony (`API_CONTRACT.md`, „Serie
  supergry”). Zapytanie `defined=false&cursor=<trigger bieżącej serii>&limit=1`
  zwraca więc następną serię bez symbolu. Zmiana API nie jest potrzebna.
- Fakt: na `main` 10 z 19 testów `test-interactions/super-game-series-workspace.test.mjs`
  pada przed zmianą (fixture'y listy bez `counts`; te same porażki co
  `quality/TASK-1003_BASELINE_HEAD380.md`). Poza zakresem.

## Recommended execution

`claude-opus-5-5` / `high` (poza planem; prośba operatora w czacie). Mała
zmiana UI w jednym module Admina.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`, „Sekcja „Supergry””
- `ai_docs/architecture/API_CONTRACT.md`, „Serie supergry”

## Scope

- Przycisk „Następna bez symbolu (N) →” w nagłówku widoku serii i skrót `N`.
- Szukanie zachowuje filtry kompletności i wiarygodności przebiegu z listy,
  filtr super symbolu zawsze „do zdefiniowania”.
- Gdy za bieżącą serią nie ma serii bez symbolu, szukanie zaczyna od początku
  listy (toast o powrocie na początek); gdy nie ma żadnej innej, komunikat w
  widoku serii.
- Niezapisany wybór symbolu blokuje przejście (komunikat: zapisz albo anuluj).
- Rozszerzenie (operator, 2026-10-18): udany zapis symbolu (`Enter` albo
  „Zapisz”) od razu przechodzi do następnej serii bez symbolu; potwierdzenie
  zapisu trafia do toastu. Zapis wyczyszczenia symbolu zostawia serię.
- Rozszerzenie 2 (operator, 2026-10-18): w serii z retriggerami `Enter`
  najpierw pokazuje kolejno plansze retriggerów do potwierdzenia; symbol
  zapisuje się (i seria przechodzi dalej) dopiero po potwierdzeniu ostatniego
  retriggera. Potwierdzenia są tylko stanem ekranu.

## Out of scope

- Zmiana API, „poprzednia seria”, przywracanie pozycji przewinięcia listy.
- Naprawa 10 wcześniejszych porażek testów interakcyjnych.

## Acceptance criteria

- [x] Przycisk i `N` otwierają następną serię bez symbolu po triggerze bieżącej.
- [x] Brak następnej: zapytanie od początku; inna seria otwiera się z toastem,
      brak innej daje komunikat bez zmiany serii.
- [x] Niezapisany wybór i zapis w toku blokują przejście.
- [x] Spóźniona odpowiedź (seria zmieniona w międzyczasie) niczego nie otwiera.
- [x] Zapis symbolu przechodzi do następnej serii bez symbolu; wyczyszczenie
      zostawia serię; bez innej serii potwierdzenie i komunikat zostają w widoku.
- [x] Retriggery: `Enter` przechodzi przez każdy niepotwierdzony retrigger,
      zapis dopiero po ostatnim; etykieta przycisku i ✓ w pasku pokazują stan.
- [x] Testy stanu, klawiatury i interakcji; lint i typecheck Admina zielone.

## Technical notes

Czysta funkcja `nextUndefinedSeriesQuery(filters, afterTrigger)` w
`super-game-series-state.ts`; komenda klawiatury `next_undefined_series` dla
`n`/`N` bez modyfikatorów. Workspace wywołuje `listSuperGameSeries` (limit 1)
i `onSeriesChange` jak „Otwórz” na liście.

## Expected files

- `apps/admin/src/features/super-games/super-game-series-state.ts`
- `apps/admin/src/features/super-games/super-game-series-keyboard.ts`
- `apps/admin/src/features/super-games/super-game-series-workspace.tsx`
- `apps/admin/test/super-game-series-state.test.mjs`
- `apps/admin/test/super-game-series-keyboard.test.mjs`
- `apps/admin/test-interactions/super-game-series-workspace.test.mjs`
- `ai_docs/requirements/ADMIN_APP.md`

## Test cases

- Zapytanie: filtry listy + `defined=false`, `cursor` = trigger, `limit` 1.
- `n` i `N` dają komendę; z Ctrl/Alt/Meta/Shift nie.
- Interakcja: przejście, powrót na początek, brak serii, blokada niezapisanego
  wyboru.

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run test:geometry --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
```

## Risks / open questions

- Założenie: „następna” oznacza kolejną po numerze triggera w filtrach
  kompletności i przebiegu wybranych na liście.

## Outcome

Commit: v1.7.419 / `f0bc558cede260129722396b90ffd5e444734d3c`.

### Changed

- `super-game-series-state.ts`: `nextUndefinedSeriesQuery` (filtry listy,
  `defined=false`, `cursor` = trigger, `limit` 2), `pickNextUndefinedSeries`,
  komunikaty (`noUndefinedSeriesLeftMessage`, `undefinedSeriesWrappedMessage`,
  `UNSAVED_SUPER_SYMBOL_NOTICE`, `superSymbolSavedMessage` wydzielony z
  `applySuperSymbolSaved`); przegląd retriggerów: pole
  `confirmedRetriggers` stanu widoku (zerowane przy odczycie serii),
  `nextRetriggerReviewStep`, `advanceRetriggerReview`, `superSymbolSaveLabel`.
- `super-game-series-keyboard.ts`: komenda `next_undefined_series` dla `n`/`N`.
- `super-game-series-workspace.tsx` (+ CSS): przycisk „Następna bez symbolu
  (N) →” w nagłówku widoku serii, szukanie po triggerze i od początku listy,
  blokada niezapisanego wyboru i zapisu w toku, odrzucenie spóźnionej
  odpowiedzi; podpowiedź skrótów wymienia `N`. Udany zapis symbolu wywołuje
  to samo szukanie (`findNextUndefinedSeries`) z potwierdzeniem zapisu w
  toaście; wyczyszczenie symbolu nie przechodzi dalej. `save()` przed
  zapisem przechodzi przez niepotwierdzone retriggery; przycisk zapisu ma
  etykietę następnego kroku, potwierdzone retriggery mają ✓ w pasku.
- Testy zmienione świadomie (zmiana kontraktu `Enter`): w 4 testach
  interakcyjnych na serii z retriggerem #105 dodano jeden `Enter`
  potwierdzający retrigger, test konfliktu rewizji oczekuje zachowanej
  pozycji #105, test kontraktu sprawdza `superSymbolSaveLabel(view)` zamiast
  literału „Zapisz (Enter)”.
- `ADMIN_APP.md`, sekcja „Supergry”: nowy punkt widoku serii.
- Mapa kodu zregenerowana.

### Verification results

- `node --test test/super-game-series-*.test.mjs`: 54/54 (7 nowych testów stanu,
  1 nowy test klawiatury, `n` w teście modyfikatorów).
- `tsx --test test-interactions/super-game-series-workspace.test.mjs`: 20/30;
  11 nowych testów przechodzi, 10 porażek to te same testy co przed zmianą
  (fixture'y listy bez `counts`).
- `npm run typecheck` (admin): OK. `eslint` zmienionych plików: 0 problemów
  (cały workspace: 5 ostrzeżeń w innych plikach, bez błędów). `prettier
  --check`: OK.
- Ręcznie w działającym Adminie (Mumie a1): z serii #119 (symbol K) przycisk
  otworzył #10828, klawisz `N` otworzył #11054; zapytanie API ok. 20 ms.
  Żaden symbol nie został zapisany.

### Not completed

- Naprawa 10 wcześniejszych porażek testów interakcyjnych (poza zakresem).

### Documentation updates

- `ai_docs/requirements/ADMIN_APP.md`, `ai_docs/architecture/CODE_MAP*.md`.

### Recommended next task

- Opcjonalnie: naprawa fixture'ów `counts` w testach interakcyjnych Supergier.
