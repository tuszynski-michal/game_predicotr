---
title: TASK-0139 — Consolidated matching and Target result summary
status: done
last_updated: 2026-08-01
---

# TASK-0139 — Consolidated matching and Target result summary

## Status

`done`

## Goal

Zastąpić oddzielne karty dopasowania i Targetu jedną kompaktową, dostępną kartą
wyniku bez powtarzanych informacji.

## Context

Po TASK-0137 i TASK-0138 ekran pokazuje poprawne dane, ale stan `unique` zajmuje
dwie karty i powtarza komunikaty. Wersja 0.3 ma prezentować jeden wynik oraz
ograniczyć szczegóły do wartości potrzebnych użytkownikowi.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/VERSION_0_3_EXECUTION_PLAN.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- połączyć stany exact matchingu i Targetu w jednej karcie,
- dla sukcesu pokazać `Układ znaleziony i obliczony` oraz numer pozycji,
- użyć jawnych tekstowych stanów i semantyki zielony / pomarańczowy / czerwony,
- zachować diagnostykę duplikatu, brak layoutu, błędy danych i retry Targetu,
- dodać kompaktowe rozwinięcie wyłącznie z `Koszt spinu`, `Koszt` i
  `Suma końcowa`,
- usunąć `Target obliczony`, objaśnienie o uruchamianiu cyklu, licznik spinów,
  payout, liczbę szczytów i podpis odsyłający do tabeli.

## Out of scope

- zmiana algorytmu, limitu albo tabeli lokalnych maksimów,
- przycisk powrotu na górę z TASK-0140,
- test urządzeniowy i APK z TASK-0141.

## Acceptance criteria

- [x] Pełna plansza renderuje najwyżej jedną kartę wyniku.
- [x] Sukces ma nagłówek `Układ znaleziony i obliczony`, numer układu i zielony
  status bez zbędnego opisu.
- [x] Rozwinięte szczegóły sukcesu zawierają tylko `Koszt spinu`, `Koszt` i
  `Suma końcowa`.
- [x] Duplikat jest pomarańczowy, a brak layoutu i błędy są czerwone; każdy stan
  ma tekst dostępny bez polegania na kolorze.
- [x] Loading exact/Target oraz retry błędu Targetu pozostają kontrolowane.
- [x] Tabela dodatnich maksimów, `Next`, `Undo`, `Reset` i zmiana limitu nie mają
  regresji.
- [x] Testy Mobile, typecheck, lint i format przechodzą.

## Technical notes

- Komponent prezentacyjny przyjmuje dwa istniejące stany hooków; nie łączy
  logiki exact matchingu z enginem Targetu.
- Target nadal uruchamia się wyłącznie dla jednoznacznego anchora.
- Testowe identyfikatory nowej karty opisują stan skonsolidowany, a nie dawną
  fizyczną kartę exact/Target.

## Expected files

- `apps/mobile/src/features/board/game-workspace-screen.tsx`
- `apps/mobile/src/features/board/result-summary-card.tsx`
- `apps/mobile/src/features/board/match-result-card.tsx`
- `apps/mobile/src/features/target/target-summary-card.tsx`
- `apps/mobile/__tests__/exact-matching-flow-test.tsx`
- `apps/mobile/__tests__/target-forecast-flow-test.tsx`
- `apps/mobile/__tests__/target-results-table-test.tsx`
- `apps/mobile/__tests__/next-layout-navigation-test.tsx`
- `ai_docs/delivery/VERSION_0_3_EXECUTION_PLAN.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm.cmd test --workspace @game-predictor/mobile -- --runInBand
npm.cmd run typecheck --workspace @game-predictor/mobile
npm.cmd run lint --workspace @game-predictor/mobile
npm.cmd exec prettier -- --check "apps/mobile/**/*.{ts,tsx}" "ai_docs/tasks/completed/0139-consolidated-matching-and-target-result-summary.md"
```

## Risks / open questions

- Brak pytań blokujących. `Koszt` oznacza skumulowany koszt ocenionego okna, a
  `Suma końcowa` oznacza końcowy wynik netto zgodnie z zaakceptowanym opisem
  wersji 0.3.

## Outcome

TASK-0139 ukończono 2026-08-01.

### Changed

- Dodano `ResultSummaryCard`, który mapuje oba istniejące stany na jedną kartę
  loading/success/warning/error.
- Sukces pokazuje numer i opcjonalne szczegóły: `Koszt spinu`, `Koszt`,
  `Suma końcowa`; disclosure ma jawny stan dostępności.
- Zachowano diagnostykę duplikatu, czerwone stany braku layoutu i błędów oraz
  retry Targetu.
- Usunięto dawne `MatchResultCard` i `TargetSummaryCard` wraz z powtarzanymi
  wartościami i opisami.

### Verification results

- `npm.cmd test --workspace @game-predictor/mobile -- --runInBand` — 11 suites,
  81/81 testów.
- `npm.cmd run typecheck --workspace @game-predictor/mobile` — passed.
- `npm.cmd run lint --workspace @game-predictor/mobile` — passed; odczyt profilu
  Windows wymagał uruchomienia poza ograniczeniem sandboxa.
- Prettier check dla Mobile i dokumentacji zadania — passed.

### Not completed

- Odbiór wizualny i test APK na Google Pixel 10 Pro XL pozostają w TASK-0141.

### Documentation updates

- Zaktualizowano architekturę, plan 0.3 i `CURRENT_STATE.md`; wymagania Mobile
  już zawierały wdrożoną semantykę.

### Recommended next task

- TASK-0140 — Results-aware scroll-to-top control.
