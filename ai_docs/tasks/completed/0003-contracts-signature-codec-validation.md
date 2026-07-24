---
title: TASK-0003 Contracts, signature codec and validation
status: done
last_updated: 2026-07-24
completed_at: 2026-07-24
---

# TASK-0003 — Contracts, signature codec and validation

## Goal

Zdefiniować niezależny od frameworków kontrakt domenowy M1 oraz udowodnić,
że TypeScript i Python identycznie walidują planszę i kodują jej stałoszeroką
sygnaturę `row-major`.

## Context

To pierwsze zadanie M1.2. Kontrakty będą używane przez build-time payout engine
w Pythonie, Target engine w TypeScript oraz późniejsze adaptery SQLite i UI.
Zadanie nie implementuje jeszcze żadnego algorytmu wypłat ani prognozy.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_01_EXECUTION_PLAN.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- kontrakty gry, symbolu, payline, payoutu i forecastu,
- mały pakiet domenowy TypeScript bez importów React Native i Expo,
- odpowiadające kontrakty build-time w Pythonie,
- tekstowy codec stałoszerokiej sygnatury dziesiętnej,
- kodowanie pełnego layoutu oraz ciągłego prefiksu,
- dekodowanie sygnatury,
- walidacja wymiarów planszy, symboli, pełnego layoutu i prefiksu,
- walidacja `row_path`, duplikatów paylines i payout rules,
- wspólne fixture JSON wykonywane przez testy TypeScript i Python,
- stabilne, maszynowo rozpoznawalne kody błędów walidacji.

## Out of scope

- matching w SQLite,
- payout engine i interpretacja jokera,
- Target engine i lokalne maksima,
- finalny generator 3 × 1000 layoutów,
- React Native UI,
- FastAPI, ORM i PostgreSQL,
- wybór reprezentacji BLOB lub indeksu po benchmarku.

## Acceptance criteria

- [x] TypeScript i Python mają zgodne kontrakty niezbędne dla kolejnych zadań M1.2.
- [x] Codec rozróżnia kolizyjne zmiennoszerokie wejścia, np. `[1, 23]` i `[12, 3]`.
- [x] Pełna sygnatura i prefiks są kodowane `row-major` w obu językach identycznie.
- [x] Decoder odrzuca uszkodzoną długość, znaki niedziesiętne i złą liczbę komórek.
- [x] Walidacja odrzuca złe wymiary, długość planszy, obcy symbol i nieciągły prefiks.
- [x] `row_path` ma dokładnie jedną pozycję 0-based na kolumnę i poprawny zakres.
- [x] Identyczne paylines i payout rules są odrzucane.
- [x] Joker nie może mieć własnej payout rule.
- [x] Testy obu języków korzystają z tych samych jawnych fixture JSON.
- [x] Kod domenowy nie importuje Expo, React, SQLite, FastAPI ani ORM.
- [x] Format, lint, typecheck i testy przechodzą.
- [x] `CURRENT_STATE.md` i Outcome są zaktualizowane.

## Technical notes

- Pierwszy codec używa zerowanego od lewej tekstu dziesiętnego.
- `cell_width` / `cellWidth` jest jawną konfiguracją wydania. Nie należy
  wyprowadzać szerokości z aktualnego layoutu.
- Kody symboli są dodatnimi liczbami całkowitymi, muszą mieścić się w
  skonfigurowanej szerokości oraz zakresie `smallint` z modelu danych.
- Kontrakty wyniku payout/forecast są definiowane teraz, lecz ich obliczanie
  należy odpowiednio do TASK-0004 i TASK-0005.

## Expected files

- `packages/shared-ts/`
- `packages/domain-fixtures/`
- `services/worker/src/game_predictor_worker/domain/`
- `services/worker/tests/`
- dokumentacja procesu

## Verification

```powershell
npm run quality
```

## Risks / open questions

- Reprezentacja tekstowa może zostać zastąpiona BLOB-em dopiero po benchmarku;
  adaptery mają traktować sygnaturę jako wartość nieprzezroczystą.
- Niniejsze zadanie nie rozstrzyga semantyki kilku rozłącznych zwycięskich
  ciągów na planszach szerszych niż pięć kolumn.

## Outcome

Zadanie zakończone. Powstał niezależny od frameworków kontrakt M1.2 w
TypeScript i Pythonie, a obie implementacje codeca i walidacji przechodzą te
same jawne przypadki JSON.

### Changed

- dodano pakiet `@game-predictor/shared-ts` z typami gry, symboli, paylines,
  payoutu i forecastu,
- dodano odpowiadające niemutowalne dataclasses po stronie build-time Python,
- zaimplementowano w obu językach kodowanie pełnej sygnatury, prefiksu i
  dekodowanie,
- dodano stabilne kody błędów i walidację gry, planszy, prefiksu, `row_path`,
  duplikatów paylines, payout rules oraz zakazu reguły jokera,
- dodano współdzielone fixture pokrywające jednoznaczność codeca i przypadki
  odrzuceń,
- zapisano D-015 i uzupełniono model danych o `signature_cell_width`.

### Verification results

- `npm run quality` — passed:
  - Prettier i Expo ESLint,
  - Ruff,
  - TypeScript strict dla mobile i `shared-ts`,
  - mypy strict dla 9 plików źródłowych Python,
  - testy kontraktu TypeScript: 9/9,
  - testy kontraktu Python: 9/9,
  - istniejące testy mobile: 4/4,
  - istniejące testy snapshotu: 3/3,
  - walidacja diagnostycznego snapshotu.
- `git diff --check` — passed.

### Not completed

- nie implementowano payout engine ani semantyki jokera; to TASK-0004,
- nie implementowano Target engine; to TASK-0005,
- nie zmieniano diagnostycznego schematu SQLite M1.1; finalny snapshot powstaje
  w M1.3.

### Recommended next task

Po osobnym poleceniu właściciela:

```text
TASK-0004 — Payout engine and golden tests
```
