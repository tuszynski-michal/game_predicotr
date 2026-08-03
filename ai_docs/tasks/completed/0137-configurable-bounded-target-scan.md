---
title: TASK-0137 configurable bounded Target scan
status: done
last_updated: 2026-08-01
completed_at: 2026-08-01
---

# TASK-0137 — Configurable bounded Target scan

## Status

`done`

## Goal

Pozwolić użytkownikowi Mobile wybrać dokładną liczbę przyszłych spinów
ocenianych przez Target, bez zmiany kolejności cyklu, kosztu, payoutu ani
jednoznacznego anchora sekwencji.

## Context

Dotychczas adapter SQLite zawsze odczytuje `N - 1` payoutów. W 0.3 domyślne
okno wynosi 10 000, UI dopuszcza 1 000–500 000, a rzeczywisty odczyt i wynik
obejmują `min(target_scan_limit, N - 1)` pozycji po spinie 0.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/VERSION_0_3_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` — D-116

## Scope

- dodać `targetScanLimit` do kontraktu wejścia i wyniku czystego forecast engine,
- walidować bezpieczny dodatni limit nie większy niż 500 000,
- wymagać dokładnie `min(targetScanLimit, layoutCount - 1)` payoutów,
- ograniczyć jedno cykliczne zapytanie SQLite przez parametr `LIMIT`,
- dodać kompaktowy kontrolowany input Mobile: domyślnie 10 000, zakres
  1 000–500 000 i dowolna liczba całkowita,
- dla niepoprawnego draftu nie uruchamiać ani nie pokazywać starego Targetu,
- przy zmianie poprawnego limitu anulować logicznie poprzednią odpowiedź i
  uruchomić nowy odczyt,
- zachować pełny cykl przez limit co najmniej `N - 1`.

## Out of scope

- funkcjonalny `Next` — TASK-0138,
- konsolidacja kart wyniku — TASK-0139,
- zmiana snapshotu lub precomputed payoutów,
- suwak i zapamiętywanie ustawienia po restarcie aplikacji.

## Acceptance criteria

- [x] Engine zwraca jawny limit i `evaluatedSpinCount` równy mniejszej z wartości
      limit oraz `N - 1`.
- [x] Ograniczony przebieg zachowuje wrap-around, koszt, kumulację i lokalne
      maksima wyłącznie w ocenionym oknie.
- [x] Adapter SQLite pobiera tylko wymagane rekordy jednym uporządkowanym
      zapytaniem i wykrywa brak lub złą kolejność.
- [x] UI akceptuje liczby całkowite 1 000–500 000, pokazuje błąd poza zakresem i
      startuje z wartością 10 000.
- [x] Zmiana limitu przy jednoznacznym layoucie ukrywa stary wynik, ignoruje
      spóźnioną odpowiedź i uruchamia nowy Target.
- [x] Testy shared engine, repository, integracji Mobile, typecheck, lint i
      format zmienionych plików przechodzą.

## Expected files

- `packages/shared-ts/src/contracts.ts`
- `packages/shared-ts/src/forecast.ts`
- `packages/shared-ts/src/errors.ts`
- `packages/shared-ts/test/forecast.test.mjs`
- `packages/domain-fixtures/target-golden-cases.json`
- `apps/mobile/src/data/local-layout-repository.ts`
- `apps/mobile/src/features/target/target-scan-limit-input.tsx`
- `apps/mobile/src/features/target/use-target-forecast.ts`
- `apps/mobile/src/features/board/game-workspace-screen.tsx`
- odpowiadające testy Mobile

## Verification

```powershell
npm.cmd test --workspace @game-predictor/shared-ts
npm.cmd test --workspace @game-predictor/mobile -- --runInBand
npm.cmd run typecheck --workspace @game-predictor/mobile
npm.cmd run lint --workspace @game-predictor/mobile
```

## Risks / open questions

- Brak pytań blokujących. D-116 rozstrzyga input liczbowy zamiast suwaka oraz
  relację limitu do pełnego cyklu.

## Outcome

Dodano jawny `targetScanLimit` do wejścia i wyniku czystego engine’u oraz jeden
współdzielony zestaw stałych limitu. Engine waliduje zakres techniczny i wymaga
dokładnie `min(targetScanLimit, layoutCount - 1)` rekordów. Adapter SQLite używa
parametryzowanego `LIMIT`, zachowuje cykliczną kolejność i nadal wykrywa braki.

Mobile ma kompaktowy input liczbowy z domyślną wartością 10 000 oraz walidacją
1 000–500 000. Niepoprawny draft ukrywa Target. Zmiana poprawnego limitu dla
jednoznacznego layoutu uruchamia nowy odczyt, a cleanup hooka ignoruje odpowiedź
poprzedniego limitu.

Przeszły 24 testy shared engine i 74 testy Mobile, w tym ograniczony wrap-around,
repository `LIMIT`, wartości brzegowe UI oraz spóźniona odpowiedź. Przeszły
również typechecki shared/Mobile, lint Mobile i format zmienionych plików.
Odbiór na Pixelu pozostaje w TASK-0141.
