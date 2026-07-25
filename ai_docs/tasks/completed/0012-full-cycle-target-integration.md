---
title: TASK-0012 Full-cycle Target integration
status: done
last_updated: 2026-07-24
---

# TASK-0012 — Full-cycle Target integration

## Goal

Po jednoznacznym exact match uruchomić całkowicie lokalny Target dla pełnego
cyklu `N - 1`, połączyć repozytorium payoutów z czystym engine’em oraz pokazać
kontrolowane podsumowanie obliczenia bez implementowania jeszcze tabeli
lokalnych maksimów.

## Context

TASK-0011 kończy matching wynikiem `unique`, `duplicate` albo `not_found`.
`LocalLayoutRepository` ma gotowy cykliczny odczyt, a `shared-ts` zawiera
`calculateTargetForecast`. To zadanie łączy istniejące kontrakty i rozpoczyna
M1.5. Prezentacja wirtualizowanej tabeli pozostaje w TASK-0013.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_01_EXECUTION_PLAN.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0005-target-engine-golden-tests.md`
- `ai_docs/tasks/completed/0008-matching-repository-cyclic-stream.md`
- `ai_docs/tasks/completed/0011-exact-matching-result-states.md`

## Scope

- port odczytu cyklicznych payoutów niezależny od SQLite w komponentach,
- uruchomienie Target wyłącznie dla wyniku exact `unique`,
- jeden odczyt dokładnie `layout_count - 1` payoutów od następcy spin 0,
- przekazanie wersji wydania, logicznej checksumy, wersji gry, kosztu i numeru
  spin 0 do `calculateTargetForecast`,
- stany `idle`, `loading`, `ready` i `error`,
- możliwość ponowienia po kontrolowanym błędzie,
- bezpieczne ignorowanie wyniku starej planszy, próby albo gry,
- podsumowanie liczby spinów, kosztu, payoutu, końcowego wyniku netto i liczby
  dodatnich lokalnych maksimów,
- jawna informacja, że szczegółowa tabela będzie dołączona w następnym zadaniu,
- testy integracji repozytorium z engine’em i zarządzania stanem.

## Out of scope

- renderowanie wierszy `positiveLocalPeaks`,
- wirtualizacja listy i przebudowa ekranu ze `ScrollView` na jedną listę,
- pomiar płynności tabeli,
- worker lub przenoszenie obliczenia poza wątek JS bez pomiarów,
- zmiana algorytmu Target, schematu SQLite lub precomputed payoutów,
- APK i testy na urządzeniach.

## Acceptance criteria

- [x] Niepełna plansza, `not_found` i `duplicate` nie odczytują payoutów.
- [x] Tylko exact `unique` uruchamia jeden cykliczny odczyt od `sequence_number`.
- [x] Engine otrzymuje dokładnie metadane zweryfikowanego snapshotu i gry.
- [x] Spin 0 nie znajduje się w strumieniu ani liczbie ocenionych spinów.
- [x] Wynik obejmuje dokładnie `layout_count - 1` pozycji.
- [x] Wszystkie payouty i koszty są liczone przez współdzielony engine.
- [x] UI pokazuje loading, podsumowanie albo czytelny `local_data_error`.
- [x] Błąd można ponowić bez zmiany planszy.
- [x] Undo, Reset i zmiana gry usuwają wynik Target.
- [x] Późna odpowiedź starej planszy lub próby nie nadpisuje aktualnego stanu.
- [x] Duplicate nigdy nie uruchamia Target.
- [x] Komponenty i hook nie importują `expo-sqlite` ani SQL.
- [x] Szczegółowa tabela nie jest implementowana w tym zadaniu.
- [x] Format, lint, typecheck i wszystkie testy przechodzą.
- [x] Dokumentacja M1.5 i `CURRENT_STATE.md` są aktualne.

## Technical notes

- `readCyclicPayouts(game, startSequenceNumber)` jest jedynym portem danych
  potrzebnym hookowi.
- `logicalContentSha256` jest logiczną checksumą snapshotu przekazywaną do
  forecastu; `snapshotFileSha256` pozostaje checksumą artefaktu.
- `datasetVersion` i `rulesVersion` pochodzą z wybranej konfiguracji gry,
  natomiast wersja wydania i algorytmu pochodzą ze zweryfikowanych diagnostics.
- Cleanup efektu nie przerywa zapytania SQLite, lecz gwarantuje bezpieczne
  odrzucenie jego wyniku po zmianie kontekstu.

## Expected files

- `apps/mobile/src/features/target/use-target-forecast.ts`
- `apps/mobile/src/features/target/target-summary-card.tsx`
- `apps/mobile/src/features/board/game-workspace-screen.tsx`
- testy przepływu Target i aktualizacja atrap repozytorium
- dokumentacja procesu

## Verification

```powershell
npm run quality
git diff --check
```

## Risks / open questions

- TASK-0012 materializuje tablicę `N - 1`, ponieważ taki jest istniejący
  kontrakt repozytorium i engine’u. Płynność oraz pamięć dla 500 000 rekordów
  wymagają pomiaru na Androidzie przed ewentualną zmianą granicy.
- Loading nie jest procentowym postępem zapytania SQLite. Dalszy UX długiego
  skanu zależy od pomiarów i TASK-0013.

## Outcome

Ukończono 2026-07-24.

- Dodano port `TargetForecastRepository` i hook, który uruchamia jeden
  cykliczny odczyt wyłącznie po exact `unique`.
- Hook przekazuje do `calculateTargetForecast` logiczną checksumę snapshotu,
  wersję wydania i algorytmu oraz wersje, koszt i liczbę layoutów wybranej gry.
- Loading, wynik, kontrolowany `local_data_error` i Retry są obsługiwane bez
  zależności komponentów od SQLite.
- Cleanup odrzuca wynik starej planszy, próby albo gry; Undo, Reset i zmiana
  gry usuwają kontekst Target.
- Podsumowanie pokazuje liczbę ocenionych spinów, koszt spinu, końcowy payout,
  koszt, wynik netto i liczbę dodatnich lokalnych maksimów.
- Test kształtu fixture potwierdza dokładnie `999` spinów dla `1000` layoutów,
  kolejność od `201` do `199` przy spin 0 równym `200`, koszt `9990`, brak
  ponownego odwiedzenia spin 0 i brak nieistniejących dodatnich szczytów.
- Dodano 10 testów integracji Target, w tym duplicate/not found, Retry, błąd
  integralności, Reset, zmianę gry i wyścig odpowiedzi.
- `npm run quality` przeszedł: format, lint, PowerShell syntax, TypeScript,
  mypy, `56` testów mobile, `22` shared TypeScript, `52` Python oraz walidacje
  snapshotu i fixture.
- Szczegółowe wiersze `positiveLocalPeaks`, wirtualizacja i przebudowa ekranu
  pozostają wyłącznie w TASK-0013.
