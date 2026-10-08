# TASK-0936 — Rozwinięcie super symbolu i koszt per pozycja w prognozie Adminu

## Status

`todo`

## Goal

Plansze w serii supergry są liczone według rodzaju `wild_super_spins`
(rozwinięcie super symbolu na kolumny, koszt spinu 0), a przybliżona wygrana
i stawki panelu sumują koszt per pozycja; gry bez supergry dają wyniki
identyczne jak dotąd.

## Context

Plan: etap S-C, sekcja „Wypłata planszy w serii”. Reguły operatora:
rozwinięcie przykrywa symbole, liczy kolumny (niesąsiednie), próg =
minimum symbolu, wypłata × liczba linii, koszt 0, brakująca plansza = pusta.

## Dependencies / entry conditions

- TASK-0932 (ewaluator v4) i TASK-0933 (serie) zacommitowane.
- Założenie Z-1: wypłaty za sztuki w kredytach bezwzględnych.

## Recommended execution

gpt-6-astra / high. Logika rozwinięcia, koszt per pozycja, trzech
konsumentów, regresja 777, dokumenty domenowe. Eskalacja do claude-fable-5-1
/ high przy niezgodności z obserwowanymi wygranymi na pierwszej serii.
Audyt: claude-opus-5-5 / high.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`
- `ai_docs/requirements/ALGORITHMS.md` (§B, §D)
- `ai_docs/requirements/MANAGEMENT_PANEL.md` (stawki)
- `ai_docs/process/DECISION_LOG.md` (wpis dla tego planu)

## Scope

- `super_games/wild_super_spins.py`: `evaluate_series_board(board,
  super_symbol, rules)` według kroków 1–4 planu (przekształcenie planszy
  tylko przy `k ≥ minimum(X)`); wynik z osobnymi składowymi: linie, sztuki,
  rozwinięcie, oraz `payout_kind` według reguły: `provisional`, gdy
  `super_symbol` jest `null`, gdy stan serii jest `stale`, albo gdy plansza
  ma nieznaną komórkę **poza** kolumnami już przykrytymi przez X (nieznana
  komórka może dodać kolumnę X, przekroczyć próg i przykryć wcześniejszą
  wygraną, więc `confirmed_minimum` nie jest bezpieczne); nieznane komórki
  wyłącznie wewnątrz kolumn już przykrytych nie zmieniają wyniku i
  dopuszczają `exact`.
- Projekcja per pozycja (`mode`, `super_symbol_id`, `remaining_spins`,
  `spin_cost_credits`, `payout_credits`, `payout_kind`) budowana z serii
  i kanonicznych plansz; przybliżona wygrana §D i kalkulator stawek panelu
  sumują koszt per pozycja; podsumowanie pokazuje osobno sumę wyników
  prowizorycznych i liczbę takich pozycji.
- Modal linii: dla planszy w serii pokazuje planszę rozwiniętą i wiersz
  „Rozwinięcie K ×3 kolumny → 10 × 5 linii = 50”.
- Golden cases (Python + TS): K w kolumnach 2,4,5; K w 2,4 (brak); przykrycie
  usuwa wygraną symbolu pod spodem; zastąpienie wygranych liniowych X;
  retrigger w serii; `k < minimum(X)` bez przekształcenia planszy; seria bez
  symbolu = wynik prowizoryczny; nieznana komórka poza kolumnami X przy
  `k = minimum − 1` → `provisional`, a po uzupełnieniu jej jako X wynik
  zmienia się przez przykrycie (test przekroczenia progu); nieznana komórka
  w kolumnie już przykrytej → `exact`; stan `stale` → `provisional`.
- `ALGORITHMS.md` §B/§D i `MANAGEMENT_PANEL.md`: opis trybu; wpis
  `DECISION_LOG.md` (następny wolny numer).

## Out of scope

- Aplikacja mobilna i snapshot. Inne rodzaje supergry.

## Acceptance criteria

- [ ] Golden cases z zakresu przechodzą w Pythonie i TS z identycznymi wynikami.
- [ ] Dla 777 wyniki przybliżonej wygranej i stawek panelu są bajt w bajt
      identyczne z wynikami przed zmianą (test porównawczy na fixture).
- [ ] Seria bez super symbolu: wynik `provisional` liczony osobno w
      podsumowaniu; test pokazuje, że po definicji wynik może wzrosnąć i może
      zmaleć (przykrycie), więc nie jest prezentowany jako minimum.
- [ ] Koszt serii = 0 w podsumowaniu; pozycja wyzwalająca ma koszt normalny.

## Technical notes

- `k` liczone na planszy oryginalnej; przekształcenie tylko przy
  `k ≥ minimum(X)`; linie na planszy rozwiniętej, sztuki Mumii na
  oryginalnej.
- Wygrane liniowe X są zastępowane rozwinięciem, gdy `k ≥ minimum(X)`.

## Expected files

- Nowe: `services/worker/src/game_predictor_worker/domain/super_games/wild_super_spins.py`
  (rozszerzenie z TASK-0931), `domain/sequence_mode_projection.py` (proponowany).
- Istniejące: `services/api/src/game_predictor_api/domain/board_search_approximate_win.py`,
  `application/board_search_approximate_win.py`, `domain/management_stakes.py`,
  `packages/shared-ts/src/validation.ts`, `packages/domain-fixtures/payout-golden-cases.json`,
  `packages/board-search-ui/src/board-search-board-lines-modal.tsx`,
  `ai_docs/requirements/ALGORITHMS.md`, `ai_docs/process/DECISION_LOG.md`.

## Test cases

- Jak w kryteriach; dodatkowo: X = symbol z minimum 2 (Sarkofag) w jednej
  kolumnie → brak rozwinięcia; w dwóch → rozwinięcie × 5.

## Verification

```powershell
# katalog worktree, timeout 120 s każda
.\.venv\Scripts\python.exe -m pytest services/worker/tests -k "payout or super_game" -q
.\.venv\Scripts\python.exe -m pytest services/api/tests -k "approximate_win or management_stakes" -q
npm run test --workspace @game-predictor/shared-ts
npm run test --workspace @game-predictor/board-search-ui
npm run quality
```

## Risks / open questions

- Reguła „× liczba linii” jest deklaracją operatora; pierwsza seria z pełnymi
  zdjęciami i znanymi wygranymi ją zweryfikuje. Rozbieżność → korekta
  rodzaju w kodzie, nie w danych.

## Outcome

Wypełnia agent po pracy.

### Changed

### Verification results

### Not completed

### Documentation updates

### Recommended next task
