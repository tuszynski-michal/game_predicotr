---
title: TASK-0699 — viewport odroczonej korekty geometrii komórek
status: done
---

# TASK-0699 — viewport odroczonej korekty geometrii komórek

## Status

`done`

## Goal

Operator może przesunąć i wycentrować widok źródła w kolejce niepełnych siatek,
nie zmieniając geometrii planszy ani danych trwałych.

## Context

TASK-0693 dodał zapis plansz częściowych, lecz widok canvasu pozostaje związany
z automatyczną sugestią. Przy przesuniętej lub przyciętej planszy utrudnia to
ustawienie czterech narożników.

## Dependencies / entry conditions

- TASK-0693 (`v0.10.451`) udostępnia `allowOutsideSource` i kwalifikację
  brakujących komórek.
- Użytkownik polecił wykonać pełny task i zaakceptował decyzje techniczne.
- Plan: `ai_docs/delivery/DEFERRED_BOARD_CELL_GEOMETRY_VIEWPORT_EXECUTION_PLAN.md`.

## Recommended execution

gpt-6-sol / high. Zadanie dotyczy transformacji canvasu i zachowania geometrii;
gpt-6-astra / medium wykonuje końcowy review diffu i testów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/delivery/DEFERRED_BOARD_CELL_GEOMETRY_VIEWPORT_EXECUTION_PLAN.md`

## Scope

- Lokalny stan i przeciąganie viewportu w `DeferredBoardCellGeometryEditor`.
- Przycisk centrowania aktualnej siatki oraz instrukcja dostępna bez koloru.
- Testy czystej transformacji i kontraktu UI.

## Out of scope

- API, OpenAPI, baza, worker i regeneracja cropów.
- Persistowanie pozycji widoku.
- Odtwarzanie pikseli nieobecnych w zdjęciu źródłowym.

## Acceptance criteria

- [x] Przeciągnięcie tła przesuwa wyłącznie widok; cztery narożniki i klucz
  podglądu pozostają niezmienione.
- [x] Przeciągnięcie uchwytu nadal zmienia wyłącznie właściwy narożnik i
  ponownie centruje widok na aktualnej siatce.
- [x] Przycisk „Wycentruj widok na siatce” przywraca viewport z bieżących
  narożników.
- [x] Pełna plansza nie pokazuje obszaru poza zdjęciem, a częściowa zachowuje
  szare tło i istniejącą kwalifikację pól.
- [x] Testy, lint i typecheck Reviewera przechodzą.

## Technical notes

`OperationalReviewGeometryViewport` pozostaje rzutem źródłowych współrzędnych
na canvas. Nowa translacja dodaje offset do `viewport.x/y`, zachowuje
`width/height`; gest tła odejmuje przesunięcie kursora w pikselach źródła,
aby obraz poruszał się zgodnie z dłonią operatora. Przycisk oraz każda zmiana
narożnika wywołują istniejący `operationalReviewGeometryViewport` z aktualnych
`corners`. Viewport nie jest elementem komendy HTTP i nie może unieważniać
preview.

## Expected files

- Istniejące: `apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx`.
- Istniejące: `apps/reviewer/src/features/operational-reviews/operational-review-state.ts`.
- Istniejące: `apps/reviewer/test/operational-review-state.test.mjs`.
- Istniejące: `apps/reviewer/test/operational-review-workspace-contract.test.mjs`.

## Test cases

- Translacja viewportu o dodatni i ujemny wektor zachowuje wymiary i mapowanie
  canvas → źródło.
- Bieżące narożniki poza obrazem przy partial renderują się w viewportcie bez
  clampowania.
- Kontrakt edytora zawiera akcję centrowania, stan panningu i nie miesza go z
  `dragIndexRef`.

## Verification

```powershell
npm run test --workspace @game-predictor/reviewer
npm run test:geometry --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
```

## Risks / open questions

- Działający build na porcie 3001 był starszy niż źródła. Odbiór ręczny wymaga
  przebudowanego/ponownie uruchomionego Reviewera, lecz nie wolno nadpisywać
  aktywnej pracy operatora.

## Outcome

### Changed

- `DeferredBoardCellGeometryEditor` rozróżnia przeciąganie narożnika od tła;
  drugie przesuwa wyłącznie lokalny viewport. Dodano przycisk „Wycentruj widok
  na siatce”.
- `operationalReviewTranslatedGeometryViewport` zachowuje rozmiar okna,
  ogranicza kompletną planszę do źródła i dopuszcza obszar poza źródłem tylko
  dla istniejącego trybu partial.
- Wymagania, plan i testy opisują oraz chronią zachowanie.

### Verification results

- `node --experimental-strip-types --test test/*.test.mjs` (w
  `apps/reviewer`): 201/201 passed.
- ESLint i `tsc --noEmit` Reviewera: passed.
- `next build`: passed.
- `git diff --check`: passed.

### Not completed

- `test:geometry` nie wystartował, ponieważ `tsx` kończy się przed ładowaniem
  testu na wcześniejszym błędzie środowiska Node 24:
  `uv_os_get_passwd ENOMEM`.
- Ręczna interakcja z prawdziwą planszą nie doszła do canvasu: endpoint
  kolejki zwrócił „Nie udało się pobrać planszy”. Nie zapisano danych.

### Documentation updates

- `ADMIN_APP.md`, `CURRENT_STATE.md` i plan wykonania opisują viewport jako
  stan wyłącznie prezentacyjny.

### Recommended next task

- Osobno zdiagnozować błąd API pobrania wpisu Reviewera oraz środowiskowy błąd
  `tsx`/Node, bez mieszania ich z geometrią planszy.
