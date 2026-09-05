---
title: Direct grid pointer drag
status: done
last_updated: 2026-09-06
---

# TASK-0475 — Bezpośrednie przeciąganie narożnika gotowej siatki

## Status

`done`

## Goal

Pierwszy gest na siatce w lokalnej „Walidacji gotowych siatek” ma jednocześnie
wybrać planszę i rozpocząć przeciąganie narożnika albo całego quada. Overlay
pozostaje stale widoczny jako niezbędne narzędzie edycji, bez nieużywanego
przełącznika widoczności.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/tasks/completed/0474-direct-ready-grid-editing.md`

## Scope

- Nie kończyć pierwszego `pointerdown` po samym wyborze planszy.
- Rozpoznawać uchwyt narożnika także tuż poza wnętrzem quada.
- Wiązać aktywny drag z konkretnym szkicem i planszą, aby zmiana zaznaczenia
  podczas gestu nie zapisała ruchu do poprzedniego slotu.
- Usunąć przycisk „Ukryj/Pokaż overlay”; overlay pozostaje stale włączony.
- Zachować atomowy zapis całego źródła i osobny tryb wyznaczania 36 narożników.

## Out of scope

- Zmiana API, croppera, silnika geometrii lub danych importów.
- Scalanie kolejki gotowych plansz z kolejką brakujących plansz.

## Acceptance criteria

- [x] Naciśnięcie i przeciągnięcie narożnika niezaznaczonej planszy działa w
  jednym geście.
- [x] Przeciągnięcie wnętrza planszy przesuwa właściwy quad.
- [x] Uchwyt lekko poza wielokątem nadal wybiera właściwą planszę.
- [x] Zmiana zaznaczenia podczas gestu nie modyfikuje poprzedniego slotu.
- [x] UI nie zawiera przełącznika widoczności overlayu.
- [x] Tryb 36 narożników oraz wspólny zapis źródła zachowują działanie.

## Expected files

- `apps/reviewer/src/features/grid-reviews/grid-review-editor.tsx`
- `apps/reviewer/src/features/grid-reviews/grid-review-state.ts`
- `apps/reviewer/test/grid-review-state.test.mjs`
- `apps/reviewer/test/grid-review-workspace-contract.test.mjs`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm run test --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
npm run reviewer:build
```

## Outcome

### Changed

- Pierwszy `pointerdown` na gotowej planszy wybiera ją i zachowuje aktywny cel
  drag, więc nie trzeba wykonywać drugiego kliknięcia przed przesunięciem.
- Drag przechowuje identyfikator planszy, snapshot szkicu, wymiary źródła i
  geometrię bazową; asynchroniczna zmiana zaznaczenia nie kieruje ruchu do
  poprzedniego slotu.
- Hit-test obejmuje bounded otoczenie narożnika, nie tylko wnętrze wielokąta.
- Usunięto przełącznik widoczności overlayu; warstwa edycji jest stale widoczna.

### Verification results

- `npm run test --workspace @game-predictor/reviewer`: 178/178.
- `npm run typecheck --workspace @game-predictor/reviewer`: OK.
- `npm run lint --workspace @game-predictor/reviewer`: OK.
- `npm run reviewer:build`: OK.
- `git diff --check`: OK; wyłącznie ostrzeżenia Windows LF/CRLF.

### Not completed

- Live QA nie było możliwe, ponieważ w bieżącej sesji nie działała żadna karta
  Reviewera. Produkcyjny build został wygenerowany od nowa.

### Recommended next task

- Osobno kontynuować TASK-0473 dotyczący przekazania brakujących slotów do
  kolejki ręcznej korekty; nie jest to regresja gestu gotowych siatek.
