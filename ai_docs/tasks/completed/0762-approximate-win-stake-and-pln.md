---
title: TASK-0762 — Stawka i złotówki w „Przybliżonej wygranej”
status: done
last_updated: 2026-09-30
---

# TASK-0762 — Stawka i złotówki w „Przybliżonej wygranej”

## Status

`done`

## Goal

Operator wybiera stawkę (1,20–20 zł) i jednostkę (kredyty/złote), a wszystkie kwoty sekcji przeliczają się według D-470.

## Context

Punkt 4 zgłoszenia operatora z 2026-09-30. Liniowość potwierdzona: 4 winogrona = 1 000 kredytów przy 10 zł i 600 kredytów przy 6 zł. Plan: §3 R1, §5 T3.

## Dependencies / entry conditions

- TASK-0761 done (etykiety wykresu korzystają z formatowania kwot).

## Recommended execution

`claude-opus-5-5`, reasoning `high` (wiersz taska w tabeli planu). Arytmetyka pieniężna z zaokrągleniami, wiele miejsc prezentacji. Audyt: niezależny agent `claude-opus-5-5` (`high` warunkowo — poziomu agenta nie da się ustawić jawnie). Dwa nieudane cykle poprawek P0–P2 zatrzymują etap.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/BOARD_SEARCH_SHARE_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- Kontrolki „Stawka” i „Jednostka” w nagłówku wyniku, poza `<summary>` (kliknięcie nie zwija sekcji).
- Przeliczenie: kafelki podsumowania, koszt spinu w nagłówku, kolumny Wypłata i Bilans narastająco, próg suwaka, osie, etykiety i opis wykresu.
- Mnożnik widoczny w nagłówku.
- Zapamiętanie wyboru w `localStorage` (preferencja widoku).

## Out of scope

- Zmiana API i kalkulatora (przeliczenie tylko po stronie klienta).
- Legenda modala (TASK-0764 użyje tej samej funkcji).

## Acceptance criteria

- [x] Tabela przykładów z R1 planu przechodzi w testach, w tym 1 000 kredytów przy 6 zł = 600 kredytów = 60,00 zł.
- [x] Jedno zaokrąglenie do grosza (połówki od zera) na wartości końcowej; bilans narastający przeliczany z kredytów bazowych.
- [x] Przy stawce bazowej i jednostce „kredyty” ekran jest identyczny z dotychczasowym.
- [x] Suwak progu przechowuje wartość w kredytach bazowych (krok 1 kredyt bazowy), wyświetla ją przeliczoną; zmiana stawki lub jednostki nie resetuje progu.
- [x] `spinCost = 0` wyłącza wybór stawki z komunikatem; jednostka „złote” działa w kursie `kredyty / 10` bez dzielenia przez koszt spinu.
- [x] Błąd `localStorage` nie psuje ekranu.

## Technical notes

Nowy moduł (proponowany) `board-search-stake.ts`:
`APPROXIMATE_WIN_STAKES_GROSZE = [120, 200, 400, 600, 1000, 2000]`;
stawka bazowa w groszach = `spinCost * 10`;
`scaleApproximateWinAmount(baseCredits, stakeGrosze, spinCost)` zwraca
wartość w groszach jako liczbę całkowitą:
`roundHalfAwayFromZero(baseCredits * stakeGrosze, spinCost)` liczone z
ilorazu i reszty: `reszta = a % d`, `iloraz = (a - reszta) / d` (dzielenie
dokładne, bo `a - reszta` jest wielokrotnością `d`), połówki od zera przy
`2 × |reszta| ≥ d`. Kredyty to
grosze / 10 przy formatowaniu (1 kredyt = 10 gr), więc mogą mieć jedno
miejsce po przecinku (np. 0,6). Zaokrąglenie połówek od zera, aby bilans
ujemny i dodatni zaokrąglały się symetrycznie. Iloczyn
`baseCredits * stakeGrosze` musi być `Number.isSafeInteger`; przekroczenie
jest błędem programistycznym. `formatApproximateWinAmount(grosze, unit)`
formatuje `pl-PL`: złote z 2 miejscami i „zł”, kredyty z 0–1 miejscem.
Stawka domyślna = bazowa; jeżeli bazowa nie jest na liście dozwolonych,
dodać ją jako pierwszą opcję „bazowa”. Zapis preferencji pod kluczem
`game-predictor-approximate-win-display-v1` z walidacją przy odczycie.

## Expected files

- Istniejące: `apps/admin/src/features/board-search/board-search-approximate-win.tsx`, `board-search-approximate-win-state.ts` (`formatApproximateWinCredits`, `filterApproximateWinRows`), `apps/admin/src/app/globals.css`.
- Nowe (proponowane): `apps/admin/src/features/board-search/board-search-stake.ts`, `apps/admin/test/board-search-stake.test.mjs`.

## Test cases

- 10 000 kredytów: 10 zł → 1 000,00 zł; 6 zł → 600,00 zł / 6 000 kredytów; 20 zł → 2 000,00 zł.
- 1 000 kredytów (4 winogrona) przy 6 zł → 60,00 zł / 600 kredytów.
- 5 kredytów przy 1,20 zł → 0,06 zł / 0,6 kredytu.
- Koszt spinu 100 przy 1,20 zł → 1,20 zł / 12 kredytów.
- Połówka grosza: +0,5 gr → 1 gr; −0,5 gr → −1 gr.
- Ujemny bilans −2 500 kredytów przy 6 zł → −150,00 zł.
- Nieprawidłowa preferencja w magazynie → wartości domyślne.

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npx prettier --check apps/admin/src/features/board-search apps/admin/test
```

Wszystkie komendy z katalogu worktree, timeout 120 s każda.

## Risks / open questions

- Ułamkowe kredyty (np. 0,6) mogą zaskoczyć; format pokazuje miejsce po przecinku tylko gdy potrzebne.

## Outcome

### Changed

- Nowy `board-search-stake.ts`: lista stawek, opcja „bazowa” spoza listy,
  `effectiveApproximateWinStakeGrosze`, `roundDivideHalfAwayFromZero`
  (iloraz i reszta), `scaleApproximateWinAmount` i
  `scaleApproximateWinAmountAtStake`, formatowanie kredytów i złotych,
  mnożnik, zapis preferencji w `localStorage` z walidacją.
- `board-search-approximate-win.tsx`: kontrolki „Stawka” i „Jednostka” w
  nagłówku wyniku (poza `<summary>`), przeliczenie nagłówka, kafelków,
  tabeli, progu suwaka (przechowywanego w kredytach bazowych), osi, etykiet,
  opisu i listy przypiętych punktów; wykres rysowany w jednostce widoku,
  podpis „zł” przy osi w trybie złotych.
- `globals.css`: styl kontrolek.
- Testy: `test/board-search-stake.test.mjs` (11 testów, w tym przykład
  operatora 1 000 → 600 kredytów / 60 zł i test wydajności), dwa testy
  interakcji (zmiana stawki i jednostki bez żądania, zachowanie progu,
  opcja bazowa jako `null`, koszt spinu 0).

### Verification results

- `npm run test --workspace @game-predictor/admin`: 642/642 PASS.
- Testy interakcji `board-search-*`: 25/25 PASS.
- Typecheck i lint Admina: 0 błędów (znane ostrzeżenia w `imports/`).
- Statyczny zrzut w przeglądarce: kafelki, tabela i osie w złotych przy
  stawce 6 zł (mnożnik 3 dla kosztu spinu 20).
- Audyt niezależnego agenta `claude-opus-5-5` (poziom rozumowania agenta
  nieustawialny z sesji): cykl 1 FAIL — P1 spowolnienie przy stawce innej
  niż bazowa (budowanie etykiet opcji przy każdej kwocie) i 7 × P3; cykl 2
  PASS; dwa pozostałe P3 (odnośnik `aria-describedby`, dwa miejsca po
  przecinku w etykietach) poprawione przed commitem.

### Not completed

- Nic w zakresie taska. Odmiana „kredytów” dla wartości ułamkowych
  pozostaje uproszczona (P3).

### Documentation updates

- Brak dodatkowych; wymagania zapisane w TASK-0760.

### Recommended next task

- TASK-0763 (API szczegółów planszy i przyciętego widoku).
