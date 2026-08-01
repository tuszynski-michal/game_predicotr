---
title: TASK-0135 compact mobile header and board shell
status: done
last_updated: 2026-08-01
---

# TASK-0135 — Compact mobile header and board shell

## Status

`done`

## Goal

Zmniejszyć wysokość głównego wejścia aplikacji mobilnej przez wdrożenie
docelowego układu nagłówka 0.3 oraz usunięcie zbędnych tytułów, liczników i
statusu gotowości danych bez zmiany zachowania dopasowania i Targetu.

## Context

Właściciel rozpoczął niezależny tor Mobile 0.3 na branchu
`ft/change-mobile-app`. Trwający odbiór Admina 0.2 nie blokuje tego pionu i nie
jest częścią jego zakresu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/VERSION_0_3_EXECUTION_PLAN.md`

## Scope

- zastąpić dotychczasowy branding kompaktową etykietą
  `ver {releaseVersion}`,
- umieścić wybór gry bezpośrednio pod wersją,
- umieścić rząd `Next`, `Undo`, `Reset` na dole nagłówka,
- udostępnić `Next` jako jawną nieaktywną kontrolkę przygotowaną do TASK-0138,
- usunąć z planszy tytuł `Layout` i licznik `selected/total`,
- usunąć komunikat `Dane lokalne gotowe`,
- usunąć tytuł i opis sekcji Selection,
- zmniejszyć odstępy pomiędzy nagłówkiem, planszą i Selection bez zmniejszania
  obszarów dotykowych istniejących akcji.

## Out of scope

- nawigacja po sekwencji i zachowanie `Next` — TASK-0138,
- zawijana siatka, nazwy PL/EN i kompaktowe kafelki symboli — TASK-0136,
- konfigurowalny limit Targetu — TASK-0137,
- konsolidacja prezentacji wyniku i powrót na górę — TASK-0139–0140,
- zmiany panelu Admin i zamknięcie TASK-0142.

## Acceptance criteria

- [x] Nagłówek pokazuje `ver {releaseVersion}` bez `Sequence Target` i
      `OFFLINE`.
- [x] Wybór gry znajduje się przed rzędem akcji.
- [x] Rząd akcji ma kolejność `Next`, `Undo`, `Reset`; `Next` pozostaje
      nieaktywny i dostępnie opisany do czasu TASK-0138.
- [x] Plansza nie renderuje tytułu `Layout` ani licznika `selected/total`.
- [x] Nie jest renderowany komunikat `Dane lokalne gotowe`.
- [x] Selection nie renderuje osobnego tytułu ani opisu.
- [x] Zmiana gry, ręczne wprowadzanie symboli, `Undo` i `Reset` zachowują
      dotychczasowe działanie.
- [x] Testy komponentów, pełne testy Mobile, typecheck i lint przechodzą.

## Technical notes

- TASK-0135 przygotowuje tylko kontrakt UI `Next`. Przycisk nie może uruchamiać
  Targetu ani wybierać pozycji przed wdrożeniem jednoznacznego anchora w
  TASK-0138.
- Główna lista wyników pozostaje jedynym pionowym kontenerem przewijanym.

## Expected files

- `apps/mobile/src/features/board/game-header.tsx`
- `apps/mobile/src/features/board/game-workspace-screen.tsx`
- `apps/mobile/src/features/board/symbol-selection.tsx`
- `apps/mobile/__tests__/board-components-test.tsx`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/tasks/0135-compact-mobile-header-and-board-shell.md`

## Verification

```powershell
npm.cmd test --workspace @game-predictor/mobile
npm.cmd run typecheck --workspace @game-predictor/mobile
npm.cmd run lint --workspace @game-predictor/mobile
```

## Risks / open questions

- Brak pytań blokujących. Funkcjonalne `Next` pozostaje świadomie odłożone do
  TASK-0138.

## Outcome

### Changed

- Nagłówek pokazuje wyłącznie kompaktową etykietę `ver {releaseVersion}`, wybór
  gry i dolny rząd akcji `Next`, `Undo`, `Reset`.
- `Next` ma dostępny opis i pozostaje wyłączony do implementacji anchora
  sekwencji w TASK-0138.
- Usunięto tytuł i licznik planszy, status gotowości danych oraz nagłówek i opis
  Selection.
- Zmniejszono marginesy i padding nagłówka, planszy oraz wejścia Selection bez
  zmniejszania minimalnej wysokości przycisków poniżej 44 punktów.
- Dodano regresje kontraktu renderowania i zachowano dotychczasowe testy zmiany
  gry, wyboru symbolu, `Undo` i `Reset`.

### Verification results

- `npm.cmd test --workspace @game-predictor/mobile` — passed, 67/67.
- `npm.cmd run typecheck --workspace @game-predictor/mobile` — passed.
- `npm.cmd run lint --workspace @game-predictor/mobile` — passed poza sandboxem;
  pierwsza próba została zatrzymana przez systemowy `EPERM` podczas kontroli
  wielkości liter ścieżki Windows, nie przez błąd kodu.

### Not completed

- Funkcjonalna nawigacja `Next` pozostaje w TASK-0138.
- Zawijana, kompaktowa siatka i etykiety PL/EN pozostają w TASK-0136.
- Ręczny odbiór całego ekranu na Pixelu pozostaje w TASK-0141.

### Documentation updates

- Utworzono i zamknięto TASK-0135.
- `CURRENT_STATE.md` wskazuje niezależny tor Mobile 0.3 i następny TASK-0136.

### Recommended next task

- TASK-0136 — Responsive compact Selection grid and labels.
