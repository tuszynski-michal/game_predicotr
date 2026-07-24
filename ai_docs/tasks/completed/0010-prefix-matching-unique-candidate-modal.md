---
title: TASK-0010 Prefix matching and unique candidate modal
status: completed
last_updated: 2026-07-24
---

# TASK-0010 — Prefix matching and unique candidate modal

## Goal

Po każdej zmianie niepustej planszy wykonać lokalne dopasowanie prefiksu i
bezpiecznie zaproponować jedyny pełny layout w dostępnym modalu z akcjami
Akceptuj oraz Zamknij.

## Context

TASK-0009 dostarczyło reducer i podstawowe komponenty, a TASK-0008 port
repozytorium. TASK-0010 łączy te warstwy bez ujawniania komponentom zapytań
SQLite. Exact matching pełnej planszy i końcowe stany wyniku należą do
TASK-0011.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_01_EXECUTION_PLAN.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0009-board-reducer-basic-components.md`

## Scope

- utrzymanie jednej instancji `LocalLayoutRepository` utworzonej podczas
  inicjalizacji snapshotu,
- mały port prefix matching przekazywany do ekranu zamiast SQLite,
- kodowanie aktualnej planszy do stałoszerokiego prefiksu,
- zapytanie po każdej zmianie niepustego prefiksu,
- jawne stany `idle`, `loading`, `ready` i `error`,
- dokładny `candidate_count` widoczny poza kolorem,
- ignorowanie odpowiedzi dotyczącej nieaktualnej gry lub planszy,
- modal tylko dla jednego pełnego kandydata dłuższego od prefiksu,
- wizualizacja pełnej proponowanej planszy i `sequence_number`,
- Akceptuj uzupełniające planszę jako jeden krok Undo,
- Zamknij bez zmiany komórek,
- brak ponownego otwarcia modala dla odrzuconego, niezmienionego prefiksu,
- ponowne wyszukiwanie po Append, Undo, Reset i zmianie gry,
- kontrolowany `local_data_error` dla awarii prefix matching,
- testy komponentowe przepływu i wyścigu odpowiedzi.

## Out of scope

- exact matching pełnej planszy,
- wynik `unique`, `duplicate` albo `not_found`,
- uruchomienie Target,
- trwałe zapamiętywanie odrzuconej propozycji,
- anulowanie trwającego zapytania SQLite na poziomie natywnym,
- finalny design i testy na fizycznych urządzeniach.

## Acceptance criteria

- [x] Komponenty nie importują `expo-sqlite` ani nie znają SQL.
- [x] Niepusty prefiks uruchamia `findByPrefix` dla wybranej gry.
- [x] Pusty prefiks nie wykonuje zbędnego zapytania.
- [x] UI pokazuje loading, liczbę kandydatów i `local_data_error`.
- [x] Nieaktualna odpowiedź nie otwiera modala ani nie zmienia licznika.
- [x] Zero i wiele kandydatów nie otwierają modala.
- [x] Jeden kandydat o większej liczbie komórek otwiera modal.
- [x] Modal pokazuje pełny layout oraz numer sekwencji.
- [x] Akceptacja uzupełnia planszę i jedno Undo przywraca ręczny prefiks.
- [x] Zamknięcie nie zmienia planszy.
- [x] Zamknięty modal nie otwiera się ponownie dla tego samego prefiksu.
- [x] Zmiana planszy czyści odrzucenie i może zaproponować nowy kandydat.
- [x] Reset i zmiana gry usuwają widoczny kandydat i stary licznik.
- [x] Przyciski modala mają jawne etykiety oraz odpowiedni rozmiar dotykowy.
- [x] Format, lint, typecheck i wszystkie testy przechodzą.

## Technical notes

- Hook integracyjny może ignorować wynik przez flagę cleanup; SQLite może
  dokończyć odczyt, ale wynik nie jest stosowany do nowszego prefiksu.
- Widoczny kandydat musi mieć ten sam prefiks, który jest aktualnie zakodowany
  z planszy. To zabezpiecza również render pomiędzy zmianą stanu a wykonaniem
  efektu.
- Odrzucony prefiks jest częścią `BoardState` z TASK-0009 i jest czyszczony
  przez każdą operację zmieniającą komórki.
- Pełna plansza nadal może wykonać prefix lookup, ale modal się nie otwiera,
  ponieważ kandydat nie jest dłuższy. TASK-0011 zastąpi ten krok exact
  matchingiem.

## Expected files

- `apps/mobile/src/features/board/use-prefix-matching.ts`
- `apps/mobile/src/features/board/candidate-layout-modal.tsx`
- `apps/mobile/src/features/board/game-workspace-screen.tsx`
- `apps/mobile/src/features/local-snapshot/local-snapshot-gate.tsx`
- `apps/mobile/__tests__/prefix-matching-flow-test.tsx`
- dokumentacja procesu

## Verification

```powershell
npm run quality
git diff --check
```

## Risks / open questions

Testy komponentowe udowadniają ochronę przed wyścigiem Promise. Pomiary
expo-sqlite na urządzeniu pozostają w M3/M1.6 zgodnie z istniejącym planem.

## Outcome

Zadanie zakończone. Niepusty stan planszy jest kodowany do prefiksu i
sprawdzany przez jedną instancję lokalnego repozytorium. UI pokazuje stan
wyszukiwania i otwiera modal tylko dla aktualnego, unikalnego kandydata
dłuższego od ręcznego prefiksu.

### Changed

- `LocalSnapshotGate` zachowuje utworzony `LocalLayoutRepository` i przekazuje
  go jako mały port prefix matching,
- dodano hook `usePrefixMatching` z `idle`, `loading`, `ready` i `error`,
- pusty układ nie wykonuje zapytania, a kolejne niepuste wersje używają
  stałoszerokiego codeca sygnatury,
- wynik jest związany z grą, dokładną referencją planszy i prefiksem,
- cleanup efektu ignoruje późną odpowiedź starszego zapytania,
- UI pokazuje dokładny `candidate_count` oraz tekstowy `local_data_error`,
- dodano `CandidateLayoutModal` z pełną planszą, numerem sekwencji i przyciskami
  Akceptuj/Zamknij,
- akceptacja wysyła `complete_board`, dlatego jedno Undo przywraca ręczny
  prefiks,
- zamknięcie zapisuje odrzucony prefiks bez zmiany komórek i nie wykonuje
  ponownego zapytania dla tego samego stanu,
- Append, Undo, Reset i zmiana gry automatycznie unieważniają stary wynik,
- Selection jest blokowane przy `local_data_error`, ale Undo i Reset pozostają
  dostępne.

### Verification results

- `npm run quality` — passed:
  - Prettier, Expo ESLint, Ruff i składnia 5 skryptów PowerShell,
  - TypeScript strict dla mobile i `shared-ts`,
  - mypy strict dla 17 plików Python,
  - testy mobile: 38/38, w tym 7 testów przepływu prefix/modal,
  - testy `shared-ts`: 22/22,
  - testy Python: 52/52,
  - walidacja finalnego snapshotu i fixture.
- `git diff --check` — passed.

### Not completed

- pełna plansza nie uruchamia jeszcze exact matching,
- nie są renderowane stany `unique`, `duplicate` ani `not_found`,
- Target pozostaje wyłączony,
- nie zbudowano nowego APK i nie wykonano testów urządzeń.

### Documentation updates

- `CURRENT_STATE.md` wskazuje ukończone TASK-0010 i następny TASK-0011,
- plan M1 kieruje następny krok na exact matching i kompletne stany wyniku,
- README mobile opisuje lokalną propozycję prefiksu.

### Recommended next task

Po osobnym poleceniu właściciela:

```text
TASK-0011 — Exact matching and result states
```
