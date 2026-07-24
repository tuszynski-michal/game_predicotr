---
title: TASK-0009 Board reducer and basic components
status: completed
last_updated: 2026-07-24
---

# TASK-0009 — Board reducer and basic components

## Goal

Dostarczyć czysty reducer sesji wprowadzania planszy oraz dostępne podstawowe
komponenty wyboru gry, planszy row-major i symboli, podłączone do katalogu gier
z lokalnego snapshotu.

## Context

M1.3 dostarczyło zweryfikowany snapshot i `LocalLayoutRepository`. TASK-0009
rozpoczyna M1.4, ale nie wykonuje jeszcze zapytań matching. Stan planszy ma być
niezależny od SQLite i komponentów, aby TASK-0010 i TASK-0011 mogły dołączyć
prefix/exact bez zmiany semantyki Undo i Reset.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_01_EXECUTION_PLAN.md`
- `ai_docs/delivery/MILESTONE_01_MOCKED_MOBILE.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0008-matching-repository-cyclic-stream.md`

## Scope

- czysty reducer TypeScript niezależny od React, Expo i SQLite,
- stała długość planszy wynikająca z `rows × columns`,
- przechowywanie komórek w kolejności row-major,
- ręczne dodanie symbolu do pierwszej pustej komórki,
- Undo ostatniej operacji,
- przygotowanie automatycznego uzupełnienia jako jednego kroku Undo,
- Reset zachowujący grę, ale czyszczący planszę, historię i odrzucony prefiks,
- zmiana gry czyszcząca cały kontekst poprzedniej planszy,
- jawny stan odrzuconego prefiksu dla przyszłego modala,
- wybór gry na podstawie katalogu ze snapshotu,
- komponent planszy z pustymi i wypełnionymi kafelkami,
- pozioma lista symboli z oznaczeniem jokera,
- przyciski Undo i Reset z poprawnymi stanami disabled,
- dostępne etykiety i stabilne identyfikatory komórek,
- podłączenie katalogu gier do głównego ekranu po walidacji snapshotu,
- testy reduktora i podstawowe testy komponentów.

## Out of scope

- zapytania prefix matching,
- modal pojedynczego kandydata,
- uruchomienie exact matching,
- stany wyniku `unique`, `duplicate` i `not_found`,
- obliczenie oraz renderowanie Target,
- finalny design wizualny i obrazy symboli,
- testy na fizycznych urządzeniach.

## Acceptance criteria

- [x] Reducer nie importuje React, Expo ani SQLite.
- [x] Plansza ma dokładnie `rows × columns` komórek w kolejności row-major.
- [x] Append wypełnia pierwszą pustą komórkę i nie zmienia pełnej planszy.
- [x] Undo cofa ręczne dodanie jednego symbolu.
- [x] Automatyczne uzupełnienie jest cofane jako jedna operacja.
- [x] Reset zachowuje grę i czyści planszę, historię oraz odrzucony prefiks.
- [x] Zmiana gry tworzy planszę o nowych wymiarach bez starego kontekstu.
- [x] Komponenty pokazują gry, komórki i symbole z konfiguracji snapshotu.
- [x] Selection jest nieaktywne dla pełnej planszy.
- [x] Undo jest nieaktywne bez historii.
- [x] Każdy symbol i każda komórka mają czytelną etykietę dostępności.
- [x] Joker ma tekstowe oznaczenie, a nie tylko inny kolor.
- [x] Ekran ładowania i `local_data_error` nadal działają.
- [x] Format, lint, typecheck i wszystkie testy przechodzą.

## Technical notes

- Historia przechowuje snapshot komórek sprzed operacji, dzięki czemu ręczne
  dodanie i automatyczne uzupełnienie mają identyczny mechanizm Undo.
- Reducer przyjmuje wyłącznie dodatnie bezpieczne kody symboli. Sprawdzenie, czy
  kod należy do wybranej gry, pozostaje odpowiedzialnością warstwy
  aplikacyjnej przekazującej `game.symbols`.
- Odrzucony prefiks jest czyszczony po każdej zmianie planszy. Samo otwieranie
  i zamykanie modala należy do TASK-0010.
- UI używa wbudowanych komponentów React Native i własnych tokenów; zadanie nie
  dodaje biblioteki komponentów.

## Expected files

- `apps/mobile/src/features/board/board-reducer.ts`
- `apps/mobile/src/features/board/board-grid.tsx`
- `apps/mobile/src/features/board/game-header.tsx`
- `apps/mobile/src/features/board/symbol-selection.tsx`
- `apps/mobile/src/features/board/game-workspace-screen.tsx`
- `apps/mobile/src/features/local-snapshot/local-snapshot-gate.tsx`
- `apps/mobile/__tests__/board-reducer-test.ts`
- `apps/mobile/__tests__/board-components-test.tsx`
- dokumentacja procesu

## Verification

```powershell
npm run quality
git diff --check
```

## Risks / open questions

Układ jest funkcjonalnym baseline M1 dla telefonu w pionie. Ostateczne odstępy,
rozmiary kafelków i zachowanie na obu urządzeniach zostaną potwierdzone podczas
testów urządzeń w M1.6.

## Outcome

Zadanie zakończone. Główny ekran po walidacji snapshotu pokazuje katalog gier,
planszę i symbole z finalnej lokalnej bazy. Stan wprowadzania pozostaje czystą
logiką niezależną od React i SQLite.

### Changed

- dodano immutable `boardReducer` z akcjami `select_game`, `append_symbol`,
  `undo`, `reset`, `complete_board` i `reject_suggestion`,
- historia przechowuje komórki sprzed operacji, dlatego automatyczne
  uzupełnienie będzie cofane jednym Undo,
- Reset zachowuje wybraną grę, a zmiana gry usuwa komórki, historię i odrzucony
  prefiks,
- dodano `GameHeader` z wyborem gry, Undo i Reset,
- dodano `BoardGrid` renderujący stabilne pozycje row-major,
- dodano poziomy `SymbolSelection` z tekstowym oznaczeniem `JOKER`,
- pełna plansza blokuje Selection, a brak historii blokuje Undo,
- wszystkie interaktywne elementy i komórki mają etykiety dostępności,
- `LocalSnapshotGate` po walidacji odczytuje katalog przez
  `LocalLayoutRepository` i pokazuje nowy ekran roboczy,
- wersja wydania i podstawowe liczniki snapshotu pozostają widoczne,
- dodano bezpośrednie zależności testowe `react-test-renderer` i jego typy oraz
  jednoznaczne mapowanie React w Jest dla workspace’u.

### Verification results

- `npm run quality` — passed:
  - Prettier, Expo ESLint, Ruff i składnia 5 skryptów PowerShell,
  - TypeScript strict dla mobile i `shared-ts`,
  - mypy strict dla 17 plików Python,
  - testy mobile: 31/31, w tym 9 reduktora i 4 komponentów,
  - testy `shared-ts`: 22/22,
  - testy Python: 52/52,
  - walidacja finalnego snapshotu i fixture.
- `git diff --check` — passed.

### Not completed

- matching prefix nie jest jeszcze wywoływany po zmianie planszy,
- nie ma modala unikalnego kandydata,
- exact matching i stany wyniku pozostają poza tym zadaniem,
- nie zbudowano nowego APK i nie wykonano testów na urządzeniach.

### Documentation updates

- `CURRENT_STATE.md` wskazuje ukończone TASK-0009 i następny TASK-0010,
- plan M1 kieruje następny krok na integrację prefix matching,
- README mobile opisuje aktualny ekran planszy.

### Recommended next task

Po osobnym poleceniu właściciela:

```text
TASK-0010 — Prefix matching and unique candidate modal
```
