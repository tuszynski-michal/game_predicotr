# TASK-0934 — Sekcja „Supergry” w Adminie

## Status

`todo`

## Goal

W Adminie operator widzi listę serii supergry gry, otwiera serię, przegląda
planszę wyzwalającą i kolejne plansze w karuzeli, wybiera super symbol
klawiszem (`1`–`9`, `0`) lub z listy i zapisuje go z kontrolą rewizji.

## Context

Super symbol jest widoczny tylko na zdjęciach. Plan: etap S-B. Istniejące
komponenty podglądu planszy z liniami (`packages/board-search-ui`) i karuzela
wyników wyszukiwania (← / →) są bazą.

## Dependencies / entry conditions

- TASK-0933 (API serii) zacommitowany i zaudytowany.
- Fakt: `BoardSearchBoardLinesModal` i podgląd planszy przyjmują
  `sequenceNumber` i `symbols`; nawigacja ← / → istnieje w
  `board-search-results.tsx`.

## Recommended execution

gpt-6.1-sol / high. Nowy ekran Adminu na istniejących komponentach, zapis
CAS. Eskalacja do gpt-6-astra / high przy konieczności zmiany kontraktu
komponentów współdzielonych. Audyt: claude-opus-5-5 / medium.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Nowa zakładka gry „Supergry” (tylko dla gier z rodzajem ≠ `none`): lista
  serii z filtrem statusu i weryfikacji, licznik `pending_symbol`, przycisk
  „Przelicz serie” (job).
- Widok serii: plansza wyzwalająca (z oznaczeniem komórek symbolu
  uruchamiającego), karuzela plansz `start…start+length-1` istniejącym
  podglądem (obraz, linie), brakująca plansza jako pusta karta „brak
  planszy”, retriggery oznaczone; wybór super symbolu: select + skróty
  `1`–`9`, `0` (rozszerzona mapa z TASK-0930); `Enter` zapisuje z
  `expectedRevision`; 409 → komunikat i odświeżenie bez nadpisania.
- Stan `incomplete` i `unverified` czytelnie oznaczone; `null` (wyczyść
  symbol) dostępny.
- Testy stanu (node --test) i kontrakt renderu; wrapper klienta.

## Out of scope

- Wyszukiwanie plansz (TASK-0935), wypłaty serii (TASK-0936), Reviewer.

## Acceptance criteria

- [ ] Lista serii stronicowana kursorem, filtry działają.
- [ ] Karuzela pokazuje wszystkie pozycje serii, w tym brakujące.
- [ ] Zapis super symbolu: sukces aktualizuje status na `defined`; konflikt
      rewizji nie nadpisuje i pokazuje aktualny stan.
- [ ] Skróty klawiszowe nie działają w polach tekstowych i z modyfikatorami.
- [ ] Gra `none` nie pokazuje zakładki.

## Technical notes

- Stan ekranu jako czysta maszyna stanów w `super-game-series-state.ts`
  (proponowany), testowana bez DOM, wzorem `board-search-results-state.ts`.

## Expected files

- Nowe: `apps/admin/src/features/super-games/{super-game-series-workspace.tsx,
  super-game-series-state.ts, super-game-series-keyboard.ts}`,
  `apps/admin/test/super-game-series-state.test.mjs`.
- Istniejące: nawigacja gry w Adminie, wrappery klienta, `ADMIN_APP.md`.

## Test cases

- Seria 101–120 z retriggerem 105: karuzela ma 20 kart, karta 105 oznaczona.
- Brak planszy 103: karta „brak planszy”.
- `0` przy 10 symbolach wybiera Mumię jako kandydata, ale zapis blokowany,
  jeśli kandydat jest symbolem uruchamiającym (super symbol musi być zwykły).
- 409 → stan nie zmieniony, komunikat.

## Verification

```powershell
# katalog worktree, timeout 120 s każda
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
```

## Risks / open questions

- Czy super symbolem może być Wild albo symbol uruchamiający? Plan: nie
  (tylko zwykłe symbole); walidacja po stronie API w TASK-0933.

## Outcome

Wypełnia agent po pracy.

### Changed

### Verification results

### Not completed

### Documentation updates

### Recommended next task
