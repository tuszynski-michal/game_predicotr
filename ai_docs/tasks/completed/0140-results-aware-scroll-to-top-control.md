---
title: TASK-0140 — Results-aware scroll-to-top control
status: done
last_updated: 2026-08-01
---

# TASK-0140 — Results-aware scroll-to-top control

## Status

`done`

## Goal

Dodać do głównej listy Mobile dostępny przycisk powrotu na górę, widoczny
dopiero po dotarciu użytkownika do sekcji wyników Targetu.

## Context

Długa, wirtualizowana tabela wyników utrudnia ręczny powrót do planszy i
Selection. Przycisk ma skrócić tę nawigację bez dokładania drugiego pionowego
scrollera ani zmiany algorytmu Targetu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/VERSION_0_3_EXECUTION_PLAN.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- zmierzyć rzeczywistą pozycję początku sekcji wyników Targetu,
- pokazać pływający przycisk dopiero po osiągnięciu tej pozycji,
- przewijać istniejący `FlatList` do początku,
- respektować safe area, minimalny obszar dotykowy i dostępność,
- pozostawić na końcu listy odstęp, dzięki któremu przycisk nie zasłoni
  ostatnich wierszy tabeli,
- dodać regresję widoczności i działania przycisku.

## Out of scope

- zmiana algorytmu Targetu lub danych tabeli,
- zmiana progu na podstawie stałej wysokości ekranu,
- drugi pionowy `ScrollView`,
- odbiór APK na Google Pixel 10 Pro XL — należy do TASK-0141.

## Acceptance criteria

- [x] Przycisk nie jest widoczny przed uzyskaniem wyniku Targetu ani przed
  dotarciem do sekcji wyników.
- [x] Przycisk pojawia się po osiągnięciu zmierzonego początku sekcji wyników.
- [x] Użycie przycisku wywołuje animowane przewinięcie głównego `FlatList` do
  offsetu `0`.
- [x] Przycisk ma rolę, nazwę i co najmniej 44 × 44 punkty obszaru dotykowego.
- [x] Przycisk pozostaje wewnątrz safe area, a końcowy odstęp listy zapobiega
  zasłanianiu ostatniego wiersza.
- [x] Mobile zachowuje jeden pionowy `FlatList`, a regresja automatyczna
  przechodzi.

## Technical notes

Pozycja sekcji jest pobierana z `onLayout` jej kotwicy w nagłówku tego samego
`FlatList`. Widoczność zależy od porównania tego pomiaru z bieżącym offsetem
`onScroll`; nie używamy wysokości zakodowanej dla jednego urządzenia.

## Expected files

- `apps/mobile/src/features/board/game-workspace-screen.tsx`
- `apps/mobile/__tests__/target-results-table-test.tsx`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/VERSION_0_3_EXECUTION_PLAN.md`

## Verification

```powershell
npm.cmd test --workspace @game-predictor/mobile -- --runInBand
npm.cmd run typecheck --workspace @game-predictor/mobile
npm.cmd run lint --workspace @game-predictor/mobile
npm.cmd run format:check
```

## Risks / open questions

- Brak pytań blokujących. Wizualny odbiór na docelowym Pixelu pozostaje częścią
  TASK-0141.

## Outcome

### Changed

- Główna lista mierzy pozycję kotwicy wyników i porównuje ją z bieżącym
  offsetem przewijania.
- Dostępny przycisk 52 × 52 pojawia się dopiero w sekcji wyników i animowanie
  przewija istniejący `FlatList` do początku.
- Footer listy został zwiększony do 88 punktów, aby ostatni wiersz można było
  przewinąć ponad pływający przycisk.
- Dodano regresję granicy widoczności, dostępności i komendy przewijania.

### Verification results

- `npm.cmd test --workspace @game-predictor/mobile -- --runInBand` — 82/82.
- `npm.cmd run typecheck --workspace @game-predictor/mobile` — passed.
- `npm.cmd run lint --workspace @game-predictor/mobile` — passed.
- Prettier dla zmienionych plików — passed.
- Pełny `npm.cmd run format:check` nadal zgłasza sześć niezwiązanych,
  wcześniejszych plików oraz `pnpm-lock.yaml`; zmieniony plik Mobile został
  sformatowany osobno.

### Not completed

- Odbiór wizualny i offline na Google Pixel 10 Pro XL pozostaje w TASK-0141.

### Documentation updates

- Zaktualizowano architekturę Mobile, plan 0.3 i `CURRENT_STATE.md`.

### Recommended next task

- TASK-0141 — Version 0.3 mobile regression and Pixel acceptance.
