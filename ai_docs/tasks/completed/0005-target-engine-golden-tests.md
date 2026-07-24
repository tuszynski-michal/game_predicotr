---
title: TASK-0005 Target engine and golden tests
status: done
last_updated: 2026-07-24
completed_at: 2026-07-24
---

# TASK-0005 — Target engine and golden tests

## Goal

Zaimplementować czysty Target engine w TypeScript i udowodnić golden fixtures,
że dla jednoznacznego spinu 0 poprawnie ocenia pełny cykl `N - 1`, kumuluje
koszt oraz payouty i zwraca dodatnie lokalne maksima.

## Context

TASK-0003 dostarczył kontrakty TypeScript, a TASK-0004 gotowe payouty
build-time. TASK-0005 zamyka algorytmiczną część M1.2 bez zależności od SQLite,
React Native i UI. Repozytorium cyklicznego strumienia powstanie dopiero w
M1.3.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_01_EXECUTION_PLAN.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0004-payout-engine-golden-tests.md`

## Scope

- jawny kontrakt `ForecastInput` z wersjami wydania i uporządkowanymi
  payoutami,
- czysta funkcja Target bez SQLite, React i Expo,
- spin 0 bez kosztu i payoutu,
- weryfikacja dokładnie `layout_count - 1` wejściowych spinów,
- kontrola następcy i cyklicznego zawinięcia numerów sekwencji,
- kumulacja każdego payoutu oraz kosztu każdego ocenianego spinu,
- `net = cumulative_payout - cumulative_cost`,
- wykrywanie dodatnich lokalnych maksimów,
- późniejszy niższy szczyt,
- plateau zapisujące pierwszy spin,
- szczyt kończący się na granicy pełnego cyklu,
- wynik bez dodatnich szczytów,
- stabilne błędy integralności i błędnych wartości,
- ręcznie opisane golden fixtures JSON,
- test deterministyczności i braku mutacji wejścia.

## Out of scope

- odczyt payoutów z SQLite,
- exact/duplicate matching i warunek uruchomienia tylko dla `unique`,
- postęp obliczenia, anulowanie oraz obsługa nieaktualnego wyniku,
- React Native, tabela i wirtualizacja,
- benchmark 500 000 rekordów,
- zapis lub cache wyniku.

## Acceptance criteria

- [x] Spin 0 nie jest oceniany i nie zwiększa kosztu.
- [x] Pierwszy oceniany rekord jest następnikiem spinu 0.
- [x] Numeracja zawija się z `layout_count` do 1.
- [x] Ocenianych jest dokładnie `layout_count - 1` spinów.
- [x] Każdy payout po drodze jest dodawany do `cumulative_payout`.
- [x] Każdy oceniany spin zwiększa `cumulative_cost` o `spin_cost`.
- [x] Zero i ujemne lokalne szczyty nie trafiają do wyniku.
- [x] Rosnący odcinek zwraca tylko końcowy szczyt.
- [x] Plateau zwraca pierwszy spin swojej najwyższej wartości.
- [x] Późniejszy niższy szczyt jest zachowany.
- [x] Dodatni szczyt na końcu pełnego cyklu jest zachowany.
- [x] Brak, nadmiar, powtórzenie albo zła kolejność numeru sekwencji daje
  stabilny błąd integralności.
- [x] Wynik zawiera wersje, checksumę i końcowe wartości kumulacyjne.
- [x] Funkcja jest deterministyczna, nie mutuje wejścia i działa w jednym
  przebiegu.
- [x] Golden fixtures opisują ręczne obliczenia niezależnie od implementacji.
- [x] Kod domenowy nie importuje React, Expo ani SQLite.
- [x] Format, lint, typecheck i wszystkie testy przechodzą.
- [x] `CURRENT_STATE.md` i Outcome są zaktualizowane.

## Technical notes

- Wejście zawiera payouty już uporządkowane przez przyszły adapter SQLite;
  engine weryfikuje oczekiwany `sequence_number` każdego spinu.
- Stan lokalnego maksimum jest utrzymywany w jednym przebiegu bez tablicy
  wszystkich wartości `net`.
- Wewnętrzny punkt plateau przechowuje dane pierwszego spinu tej wartości.
- Wszystkie wartości kredytowe i numery muszą być bezpiecznymi liczbami
  całkowitymi JavaScript.

## Expected files

- `packages/shared-ts/src/contracts.ts`
- `packages/shared-ts/src/errors.ts`
- `packages/shared-ts/src/forecast.ts`
- `packages/shared-ts/src/index.ts`
- `packages/shared-ts/test/forecast.test.mjs`
- `packages/domain-fixtures/target-golden-cases.json`
- odpowiadające kontrakty Python
- dokumentacja procesu

## Verification

```powershell
npm run quality
```

## Risks / open questions

- Wydajność adaptera SQLite i skan 500 000 rekordów wymagają osobnego
  benchmarku w M1.3/M1.5.
- Ostateczna etykieta sekcji `Result`/`Target` nie wpływa na kontrakt domenowy.

## Outcome

Zadanie zakończone. Pakiet `shared-ts` zawiera czysty, jednoprzebiegowy Target
engine z pełną walidacją cyklu i ręcznie opisanymi golden przebiegami.

### Changed

- dodano `ForecastInput` i rozszerzono `ForecastResult` o wersje, checksumę
  oraz końcowe wartości kumulacyjne,
- dodano `calculateTargetForecast` bez zależności od React Native i SQLite,
- zaimplementowano spin 0, dokładnie `N - 1` pozycji, zawinięcie, kumulację
  wszystkich payoutów i kosztów oraz `net_credits`,
- zaimplementowano dodatnie lokalne maksima, plateau, późniejszy niższy szczyt
  i szczyt na granicy cyklu,
- dodano walidację długości, ciągłości, payoutów, wersji oraz zakresu safe
  integer,
- dodano dziewięć golden przebiegów z ręcznymi obliczeniami,
- zsynchronizowano odpowiadające kontrakty Python,
- zapisano D-017 określającą granicę strumienia Target.

### Verification results

- `npm run quality` — passed:
  - Prettier, Expo ESLint i Ruff,
  - TypeScript strict dla mobile i `shared-ts`,
  - mypy strict dla 10 plików źródłowych Python,
  - testy Target: 13/13,
  - wszystkie testy `shared-ts`: 22/22,
  - wszystkie testy Python: 27/27,
  - testy mobile: 4/4,
  - walidacja diagnostycznego snapshotu.
- `git diff --check` — passed.

### Not completed

- nie implementowano adaptera SQLite ani cyklicznego zapytania,
- nie implementowano warunku uruchomienia wyłącznie po wyniku `unique`,
- nie implementowano postępu, anulowania, tabeli ani wirtualizacji,
- nie wykonywano benchmarku 500 000 rekordów.

### Documentation updates

- `ALGORITHMS.md` opisuje wejście strumienia, pełny wynik i jeden przebieg,
- `SYSTEM_ARCHITECTURE.md` rozdziela odpowiedzialność adaptera i engine’u,
- `API_CONTRACT.md` jest zgodny z właściwym `ForecastResult`,
- `DECISION_LOG.md` zawiera D-017.

### Recommended next task

Po osobnym poleceniu właściciela:

```text
TASK-0006 — Deterministic fixture generator and sequence validator
```
