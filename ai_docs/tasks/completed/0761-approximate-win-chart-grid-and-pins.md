---
title: TASK-0761 — Siatka wykresu i przypinane punkty w „Przybliżonej wygranej”
status: done
last_updated: 2026-09-30
---

# TASK-0761 — Siatka wykresu i przypinane punkty w „Przybliżonej wygranej”

## Status

`done`

## Goal

Wykres bilansu ma opisaną siatkę, a kliknięcie przypina punkt z etykietą w pasie nad wykresem, połączoną z punktem kropkowaną pionową linią.

## Context

Punkty 2 i 3 zgłoszenia operatora z 2026-09-30: bez siatki trudno odczytać położenie punktów, a tooltip przy najechaniu znika i zasłania wykres. Plan: §5 T2.

## Dependencies / entry conditions

- TASK-0760 done (plan i wymagania zapisane).
- Fakt: wykres to ręczny SVG w `ApproximateWinBalanceChart`, bez biblioteki.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (wiersz taska w tabeli planu). Jeden komponent i czyste funkcje; ryzyko w układzie etykiet i dostępności. Audyt: niezależny agent `claude-opus-5-5` (`high` warunkowo — poziomu agenta nie da się ustawić jawnie). Dwa nieudane cykle poprawek P0–P2 zatrzymują etap.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/BOARD_SEARCH_SHARE_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`

## Scope

- Siatka pozioma i pionowa z „okrągłymi” podziałkami (1/2/5 × 10ⁿ), opisy wartości na osiach.
- Pas etykiet nad obszarem danych (do 3 wierszy); etykieta najechania i przypięte etykiety leżą w pasie.
- Kropkowana pionowa linia od etykiety do punktu i znacznik punktu.
- Przypinanie kliknięciem, odpinanie kliknięciem punktu albo „×”, „Wyczyść punkty”, limit 8 z komunikatem.
- Tekstowa lista przypiętych punktów pod wykresem.

## Out of scope

- Stawka i złotówki (TASK-0762).
- Zmiana danych, API i kalkulatora.
- Nowa biblioteka wykresów.

## Acceptance criteria

- [x] Podziałki mają okrągłe wartości; oś Y sięga do skrajnych podziałek obejmujących minimum i maksimum bilansu, a opisy podziałek zastępują etykiety min/max.
- [x] Linia zera pozostaje wyróżniona, gdy bilans ją przecina.
- [x] Przypięcie, odpięcie, limit 8 i czyszczenie działają; dziewiąte kliknięcie nie usuwa starszego punktu.
- [x] Do 9 etykiet (8 przypiętych + najechanie) w 3 wierszach pasa nie nakłada się i nie wychodzi poza wykres; przy braku miejsca etykieta przesuwa się w bok z łamaną linią prowadzącą.
- [x] Klawiatura: strzałki przesuwają podświetlony punkt, Enter/spacja przypina lub odpina, Escape czyści podświetlenie.
- [x] Przypięcia znikają po zmianie planszy albo zakresu (nowy klucz wyniku).
- [x] Istniejące testy stanu przechodzą bez zmiany asercji; pusty wynik zachowuje obecny komunikat.

## Technical notes

Czyste funkcje (proponowane) w `board-search-approximate-win-state.ts`:
`approximateWinAxisTicks(minimum, maximum, targetCount)` zwraca rosnące
podziałki o kroku 1/2/5 × 10ⁿ, obejmujące przedział (dla `min == max`
rozszerza przedział symetrycznie). Dziedzina osi Y = [pierwsza, ostatnia]
podziałka; dotychczasowe etykiety min/max znikają (min, max i bilans końcowy
zostają w `<desc>`). `toggleApproximateWinPinnedPoint(pins,
point, limit)` zwraca `{ pins, limitReached }` bez mutacji;
`layoutApproximateWinPinLabels(labels, width, labelWidth, rows)` przydziela
każdej etykiecie pierwszy z 3 wierszy, w którym nie nachodzi na inne; gdy
żaden nie jest wolny przy docelowym `x`, przesuwa ją poziomo do
najbliższego wolnego miejsca w wierszu o najmniejszym przesunięciu i zwraca
`x` etykiety oraz `x` punktu (łamana linia prowadząca). Szerokość etykiety
≤ 1/6 szerokości wykresu (dwa wiersze tekstu), odstęp mniejszy niż
szerokość etykiety: wiersz blokuje nową etykietę dopiero przy ≥ 3
etykietach, więc przy 3 wierszach dziewiąta etykieta zawsze się mieści. `x`
ograniczony do granic wykresu. Klawiatura: `<svg tabIndex=0>` z obsługą
strzałek, Enter/spacji i Escape; podświetlony punkt ma ten sam znacznik co
najechanie. Tożsamość punktu = `spinNumber` + `kind`.
Klik wybiera najbliższy punkt tą samą regułą co najechanie (bez
`before_payout`). Etykiety przypięte są przyciskami z `aria-label`.
Przypięcia są stanem `ApproximateWinBalanceChart`; komponent jest
montowany z `key` zależnym od klucza wyniku, więc zmiana wyniku je czyści.
Zachować: linię zera, opis `<desc>` (rozszerzony o minimum i maksimum),
komunikat pustego wykresu.

## Expected files

- Istniejące: `apps/admin/src/features/board-search/board-search-approximate-win.tsx` (`ApproximateWinBalanceChart`, `ApproximateWinResultView`), `apps/admin/src/features/board-search/board-search-approximate-win-state.ts`, `apps/admin/src/app/globals.css` (`.boardSearchApproximateWinChart*`), `apps/admin/test/board-search-approximate-win-state.test.mjs`.

## Test cases

- Podziałki: `[-2500, 0]`, `[-120, 9800]`, `[0, 0]`, `[5, 5]`, `[-7, 3]`.
- Przypięcie nowego punktu, odpięcie tego samego, limit 8 (`limitReached = true`, lista bez zmian).
- Układ: dwie etykiety o tym samym `x` trafiają do różnych wierszy; etykieta przy prawej krawędzi jest przesunięta do środka; 9 etykiet o tym samym `x` mieści się bez nakładania (przesunięcia poziome); żadna nie ginie.
- Klawiatura: nawigacja po punktach pomija `before_payout`, zatrzymuje się na krańcach.

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npx prettier --check apps/admin/src/features/board-search apps/admin/test
```

Wszystkie komendy z katalogu worktree, timeout 120 s każda.

## Risks / open questions

- Wąski ekran: pas etykiet ma stałą wysokość w jednostkach viewBox, więc skaluje się z wykresem.

## Outcome

### Changed

- `board-search-approximate-win-state.ts`: `approximateWinAxisTicks` (kroki
  1/2/5 × 10ⁿ, opcja `integerStep`, ochrona przed wartościami nieskończonymi
  i zbyt wieloma podziałkami), `approximateWinPointKey`,
  `toggleApproximateWinPinnedPoint` (limit 8, `limitReached`),
  `moveApproximateWinHighlight`, `layoutApproximateWinPinLabels` (3 wiersze,
  przesunięcie w bok, `reserved`, tolerancja 1e-6).
- `board-search-approximate-win.tsx` (`ApproximateWinBalanceChart`): siatka
  z opisami osi, dziedzina Y do skrajnych podziałek, pas etykiet nad
  wykresem z kropkowaną łamaną linią prowadzącą, przypinanie kliknięciem i
  klawiaturą, „×”, lista przypiętych punktów, „Wyczyść punkty”, komunikat
  limitu, `key` wykresu zależny od wyniku, powrót fokusu na wykres.
- `globals.css`: siatka, oś, linia zera, etykiety, znaczniki; usunięte reguły
  tooltipu HTML.
- Testy: 11 nowych testów stanu, test interakcji zaktualizowany z tooltipu na
  etykiety w pasie oraz rozszerzony o siatkę, przypinanie, klawiaturę, „×” i
  czyszczenie.

### Verification results

- `npm run test --workspace @game-predictor/admin`: 631/631 PASS.
- `npx tsx --test test-interactions/board-search-*.test.mjs`: 23/23 PASS.
- `npm run typecheck` i `npm run lint` (Admin): 0 błędów; 4 ostrzeżenia w
  niezwiązanych plikach `imports/` istniały wcześniej.
- Prettier plików taska: czysty. `prettier --check` całego katalogu
  `board-search` zgłasza 5 plików spoza taska (dwa niesformatowane na HEAD,
  trzy różnią się wyłącznie końcami linii CRLF w checkoucie).
- Statyczny zrzut wykresu w przeglądarce: siatka, pas etykiet, łamana linia
  dla przesuniętej etykiety, lista punktów.
- Audyt niezależnego agenta `claude-opus-5-5` (poziom rozumowania agenta
  nieustawialny z sesji): cykl 1 FAIL — P2 nakładanie etykiet przez błąd
  zmiennoprzecinkowy w `isFree` (sondowanie: ok. 1% przypadków) oraz 9 × P3;
  cykl 2 PASS po poprawkach P2 i P3 1–7, 9.

### Not completed

- Ogłaszanie podświetlonego punktu czytnikom ekranu przy nawigacji
  strzałkami (P3, opcjonalne).

### Documentation updates

- Brak dodatkowych; wymagania zapisane w TASK-0760.

### Recommended next task

- TASK-0762 (stawka i złote).
