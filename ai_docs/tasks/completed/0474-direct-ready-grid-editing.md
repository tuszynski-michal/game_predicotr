---
title: Direct ready-grid editing
status: done
last_updated: 2026-09-06
---

# TASK-0474 — Bezpośrednia edycja gotowych siatek

## Status

`done`

## Goal

Kliknięcie planszy w lokalnej „Walidacji gotowych siatek” od razu otwiera jej
edycję, a `Enter`, `F` i główny przycisk zapisują oraz zatwierdzają cały komplet
jednego zdjęcia.

## Context

Dotychczas operator musiał po wskazaniu planszy osobno kliknąć „Zmień siatkę”.
Ponadto pojedynczy szkic blokował przejście do kolejnej planszy, chociaż backend
ma już atomowy kontrakt zapisu całego źródła.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`

## Scope

- Bezpośrednio rozpocząć edycję po kliknięciu siatki lub jej pozycji na liście.
- Przechować szkice wszystkich aktywnych plansz bieżącego zdjęcia.
- Usunąć przycisk „Zmień siatkę”.
- Skierować `Enter`, `F` i „Zatwierdź całe zdjęcie” do atomowego zapisu szkiców,
  jeśli trwa edycja, albo do zwykłego zatwierdzenia, jeśli nie ma zmian.
- Zachować jawny tryb wyznaczania 36 narożników od początku.

## Out of scope

- Zmiana API, geometrii, croppera albo danych istniejących importów.
- Zdalny Reviewer i niepełne sloty TASK-0473.

## Acceptance criteria

- [x] Kliknięcie dowolnej widocznej siatki od razu uruchamia jej edycję.
- [x] Poprawki nie znikają przy przełączaniu między planszami zdjęcia.
- [x] UI nie zawiera przycisku „Zmień siatkę”.
- [x] `Enter`, `F` i główny przycisk wykonują tę samą atomową operację kompletu.
- [x] Niekompletny szkic 36 narożników nie jest zapisywany.
- [x] Nawigacja nie porzuca niezapisanych zmian.

## Technical notes

Istniejący endpoint `source-geometry-revisions` pozostaje jedyną mutacją dla
kompletu `virtual_source`; nie powstaje nowy kontrakt HTTP.

## Expected files

- `apps/reviewer/src/features/grid-reviews/grid-review-editor.tsx`
- `apps/reviewer/src/features/grid-reviews/grid-review-workspace.tsx`
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

## Risks / open questions

- Historyczne `legacy_file` zachowuje zapis pojedynczej geometrii; bezpośredni
  atomowy zapis kompletu dotyczy aktualnego `virtual_source`.

## Outcome

### Changed

- Kliknięcie canvasa albo przycisku slotu bezpośrednio uruchamia edycję.
- Source-wide szkic jest inicjalizowany bieżącą geometrią wszystkich plansz i
  zachowuje kolejne korekty.
- Usunięto osobny przycisk „Zmień siatkę” i wewnętrzny przycisk zapisu.
- Główna akcja oraz `Enter`/`F` zapisują zmieniony komplet jednym istniejącym
  requestem; bez zmian używają szybkiego zatwierdzenia.
- Nawigacja i odrzucenie są zablokowane przy niezapisanym szkicu.

### Verification results

- `npm run test --workspace @game-predictor/reviewer`: 177/177.
- `npm run typecheck --workspace @game-predictor/reviewer`: OK.
- `npm run lint --workspace @game-predictor/reviewer`: OK.
- `npm run reviewer:build`: OK.

### Not completed

- Nie wykonywano live QA w przeglądarce ani zmian API/bazy; nie były wymagane.

### Documentation updates

- Zaktualizowano `ADMIN_APP.md`, `ITERATIVE_IMAGE_IMPORT.md` i
  `CURRENT_STATE.md`.

### Recommended next task

- Osobno domknąć przekazanie brakujących slotów TASK-0473 do edytora; nie jest
  częścią walidacji kompletnych źródeł.
