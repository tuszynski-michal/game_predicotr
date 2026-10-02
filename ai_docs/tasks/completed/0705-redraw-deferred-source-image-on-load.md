---
title: TASK-0705 — Rysowanie źródła po załadowaniu edytora odroczonej siatki
status: done
---

# TASK-0705 — Rysowanie źródła po załadowaniu edytora odroczonej siatki

## Status

`in_progress`

## Goal

Po pierwszym wejściu do „Niepełnych siatek do ręcznej korekty” canvas pokazuje obraz źródłowy bez wymagania kliknięcia „Wycentruj widok na siatce”.

## Context

`drawSource` czyta obraz z refa, lecz jego zakończenie ładowania nie zmienia żadnej zależności efektu rysującego. Pierwsze rysowanie kończy się więc przed ustawieniem refa i pozostawia czarne canvas; późniejsza akcja użytkownika przypadkowo wymusza redraw.

## Dependencies / entry conditions

- TASK-0704 jest zakończony; zakres nadal ogranicza się do `DeferredBoardCellGeometryEditor`.

## Recommended execution

`gpt-6-sol`, reasoning `high`. To ograniczona naprawa asynchronicznego cyklu React/canvas, wymagająca ochrony przed pokazaniem starego obrazu po zmianie pozycji. Eskalacja tylko przy wykryciu wpływu na inny edytor.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Powiązać zakończenie sukcesu ładowania źródła z ponownym rysowaniem canvasa.
- Przy rozpoczęciu nowego ładowania wyczyścić poprzedni obraz z refa, aby nie narysować starego zdjęcia dla nowej pozycji.
- Dodać regresję kontraktu oraz zachować wszystkie gesty i viewport z TASK-0704.

## Out of scope

- Zmiany API, assetów, preview, zapisu geometrii i innych ekranów.

## Acceptance criteria

- [ ] Pierwsze `onload` obrazu źródłowego wyzwala redraw na bieżącym viewportcie.
- [ ] Przed sukcesem nowego ładowania canvas nie wykorzystuje poprzedniego obrazu.
- [ ] Nie jest potrzebna żadna akcja operatora do pokazania źródła.
- [ ] Testy Reviewera i formatowanie są zielone.

## Technical notes

Dedykowany stan-wersja obrazu jest sygnałem renderu: jest zwiększany tylko po
skutecznym `image.onload` i jest zależnością callbacku `drawSource`. Ref nadal
przechowuje obiekt `Image`, lecz React otrzymuje jawny sygnał, że można go już
rysować. `onerror` nie inkrementuje wersji i zachowuje istniejący komunikat
błędu. Nie wolno centrować viewportu ani modyfikować rogów w reakcji na load.

## Expected files

- Istniejące: `apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx`.
- Istniejące: `apps/reviewer/test/operational-review-workspace-contract.test.mjs`.

## Test cases

- Start ładowania → ref jest pusty, więc stary obraz nie może zostać narysowany.
- Sukces ładowania → zmiana wersji obrazu jest zależnością redraw, bez zmiany viewportu.

## Verification

```powershell
pnpm --filter @game-predictor/reviewer test
pnpm dlx prettier@3.5.3 --check apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx apps/reviewer/test/operational-review-workspace-contract.test.mjs
git diff --check
```

## Risks / open questions

- Ręczny odbiór zależy od dostępności pozycji w lokalnej kolejce; nie tworzyć danych testowych.

## Outcome

### Changed

- Dodano `sourceImageVersion`, który sygnalizuje Reactowi zakończenie
  `Image.onload` i uruchamia redraw bieżącego canvasa.
- Przy nowym ładowaniu ref obrazu jest czyszczony, a canvas odświeżany, więc
  nie może pokazać poprzedniej planszy dla nowej pozycji.
- Nie zmieniono viewportu, rogów, API ani zapisu geometrii.

### Verification results

- `pnpm --filter @game-predictor/reviewer test` — 203/203 zaliczone.
- `pnpm dlx prettier@3.5.3 --check ...` — zielone dla zmienionych plików.
- `git diff --check` — zielone.

### Not completed

- Nie wykonano ręcznego odbioru wskazanej kolejki, ponieważ nie miała już
  pozycji; nie tworzono ani nie modyfikowano danych użytkownika do testu.

### Documentation updates

- `ai_docs/process/CURRENT_STATE.md`

### Recommended next task

- Brak w tym zakresie.
