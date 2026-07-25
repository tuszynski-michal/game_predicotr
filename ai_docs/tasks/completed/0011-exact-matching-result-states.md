---
title: TASK-0011 Exact matching and result states
status: done
last_updated: 2026-07-24
---

# TASK-0011 — Exact matching and result states

## Goal

Dla pełnej planszy wykonać lokalne exact matching i pokazać jednoznaczne,
dostępne stany `unique`, `duplicate`, `not_found` albo `local_data_error`,
domykając bramkę G4 bez uruchamiania Target.

## Context

TASK-0010 obsługuje prefiks i modal, a `LocalLayoutRepository` z TASK-0008 ma
gotowy kontrakt exact. TASK-0011 kończy M1.4. Jednoznaczny numer sekwencji ma
być widoczny, ale pełny cykl Target pozostaje zadaniem M1.5.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_01_EXECUTION_PLAN.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0010-prefix-matching-unique-candidate-modal.md`

## Scope

- mały port exact matching bez zależności komponentów od SQLite,
- exact lookup wyłącznie dla kompletnej planszy,
- brak równoległego prefix lookup dla pełnej planszy,
- stany `idle`, `loading`, `ready` i `error`,
- ochrona przed zastosowaniem wyniku starszej planszy albo gry,
- `unique` z jednym `sequence_number`,
- `duplicate` z pełnym licznikiem i opcjonalnymi numerami diagnostycznymi,
- brak arbitralnego wyboru numeru dla duplikatu,
- `not_found` pozostawiający planszę do poprawy przez Undo,
- `local_data_error` z możliwością Undo albo Reset,
- czyszczenie wyniku po Undo, Reset i zmianie gry,
- jawna informacja, że Target nie został jeszcze uruchomiony,
- testy komponentowe wszystkich wyników i wyścigu odpowiedzi,
- domknięcie M1.4 i bramki G4.

## Out of scope

- odczyt cyklicznych payoutów,
- uruchomienie Target engine,
- tabela lokalnych maksimów,
- postęp długiego skanu,
- budowa APK i testy urządzeń,
- zmiana kontraktu repozytorium lub schematu SQLite.

## Acceptance criteria

- [x] Komponenty exact nie importują `expo-sqlite` ani SQL.
- [x] Niepełna plansza nie uruchamia `findExact`.
- [x] Pełna plansza uruchamia dokładnie exact, bez dodatkowego prefix lookup.
- [x] UI pokazuje loading przed wynikiem exact.
- [x] `unique` pokazuje dokładnie jeden `sequence_number`.
- [x] `duplicate` pokazuje licznik i nie wybiera numeru jako unique.
- [x] Mała lista duplikatów może pokazać numery diagnostyczne.
- [x] `not_found` pozostawia komórki oraz aktywne Undo.
- [x] `local_data_error` jest czytelny i nie usuwa planszy.
- [x] Późna odpowiedź starszej planszy albo gry jest ignorowana.
- [x] Undo usuwa exact result i ponownie uruchamia prefix matching.
- [x] Reset i zmiana gry usuwają exact result oraz kontekst duplikatu.
- [x] Żaden wynik exact nie uruchamia Target w tym zadaniu.
- [x] Informacja o stanie nie jest przekazywana wyłącznie kolorem.
- [x] Pełny przepływ matching przechodzi bez Internetu i backendu.
- [x] Format, lint, typecheck i wszystkie testy przechodzą.
- [x] Bramka G4 i dokumentacja są zaktualizowane.

## Technical notes

- Hook exact używa tego samego wzorca co prefix: wynik jest przypisany do
  instancji gry, referencji tablicy komórek i pełnej sygnatury.
- Po osiągnięciu pełnej planszy hook prefix jest wyłączony, dzięki czemu jedna
  zmiana nie uruchamia dwóch zapytań matching.
- `duplicate.sequenceNumbers === null` oznacza przekroczenie limitu
  diagnostycznego; UI nadal pokazuje pełny `occurrenceCount`.
- Sekcja wyniku jest przygotowana jako wejście do TASK-0012, ale nie wykonuje
  żadnego odczytu payoutów.

## Expected files

- `apps/mobile/src/features/board/use-exact-matching.ts`
- `apps/mobile/src/features/board/match-result-card.tsx`
- `apps/mobile/src/features/board/game-workspace-screen.tsx`
- `apps/mobile/__tests__/exact-matching-flow-test.tsx`
- aktualizacja testów prefix i podstawowych komponentów
- dokumentacja procesu

## Verification

```powershell
npm run quality
git diff --check
```

## Risks / open questions

Testy komponentowe nie zastępują odbioru na Pixel 10 Pro XL i Galaxy S21
Ultra. Ten odbiór pozostaje w M1.6.

## Outcome

Ukończono 2026-07-24.

- Dodano osobny hook exact matching, który uruchamia się wyłącznie dla pełnej
  planszy i ignoruje odpowiedzi dotyczące nieaktualnej planszy albo gry.
- Po wypełnieniu planszy prefix matching jest wyłączany, więc UI wykonuje tylko
  jedno zapytanie matching.
- Dodano jawne, dostępne tekstowo stany `unique`, `duplicate`, `not_found`,
  `loading` i `local_data_error`.
- Duplikat pokazuje pełny licznik i numery diagnostyczne, jeśli mieszczą się w
  limicie, ale nigdy nie jest zamieniany na arbitralnie wybrany wynik unique.
- Undo, Reset i zmiana gry usuwają wynik exact; brak dopasowania i błąd danych
  nie czyszczą automatycznie planszy.
- Target nie jest uruchamiany. Integracja pełnego cyklu pozostaje w TASK-0012.
- Dodano osiem testów przepływu exact; cały pakiet mobile ma `46/46` testów.
- `npm run quality` przeszedł: format, lint, PowerShell syntax, TypeScript,
  mypy, `46` testów mobile, `22` shared TypeScript, `52` Python oraz walidacje
  snapshotu i fixture.
- `git diff --check` przeszedł bez błędów.
