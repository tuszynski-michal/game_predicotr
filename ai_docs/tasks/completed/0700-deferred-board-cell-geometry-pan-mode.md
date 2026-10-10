# TASK-0700 — jawny tryb przesuwania kadru odroczonej siatki

## Status

`done`

## Goal

Widok odroczonej siatki pozostaje statyczny, dopóki operator jawnie nie włączy
panoramowania kadru.

## Context

TASK-0699 dodał przesuwanie viewportu, lecz gest poza uchwytem uruchamia je bez
wyraźnego zamiaru operatora i utrudnia ręczną korektę siatki.

## Dependencies / entry conditions

- Commit `v0.10.453` dostarcza viewport, jego translację i centrowanie.
- Lokalny ekran Reviewera dla wskazanego importu ładuje edytor i obraz źródłowy.

## Recommended execution

`gpt-6-sol` z reasoning `high`: zmiana dotyczy rozróżnienia gestów canvasu i
regresji UI. Niezależny review `gpt-6-astra` z reasoning `medium` jest zalecany,
jeśli pojawi się konflikt między panoramowaniem a uchwytem narożnika.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/DEFERRED_BOARD_CELL_GEOMETRY_PAN_MODE_EXECUTION_PLAN.md`

## Scope

- Dodać domyślnie wyłączony checkbox `Aktywne przesuwanie` w edytorze.
- Zezwolić na start panoramowania tylko po jego zaznaczeniu.
- Zachować priorytet czterech uchwytów narożników oraz lokalność viewportu.
- Dodać regresję kontraktową i zaktualizować wymaganie oraz stan projektu.

## Out of scope

- Zmiana endpointów, OpenAPI, backendu, zapisu geometrii lub danych importu.
- Zapamiętywanie trybu przesuwania między planszami.

## Acceptance criteria

- [ ] Checkbox jest widoczny, dostępny i domyślnie odznaczony po otwarciu planszy.
- [ ] Przeciąganie poza uchwytem przy wyłączonym checkboxie nie zmienia viewportu.
- [ ] Po włączeniu checkboxa tło przesuwa wyłącznie lokalny viewport, a uchwyt nadal zmienia narożnik.
- [ ] Preview, kwalifikacja, idempotencja i zapis nie przyjmują stanu checkboxa.
- [ ] Zmienione testy, lint, typecheck i build są zielone.

## Technical notes

Stan checkboxa pozostaje lokalnym `useState(false)` i jest resetowany podczas
pobierania następnego contextu. `startCanvasGesture` najpierw wykrywa uchwyt;
gdy go nie ma, zakłada `panViewportRef` wyłącznie przy aktywnym trybie. Bez
gestu nie przechwytuje pointera. Zmiana nie wywołuje `replaceCorners`,
`updateFlags`, preview ani resolve.

## Expected files

- Istniejące: `apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx` — stan i bramka gestu.
- Istniejące: `apps/reviewer/test/operational-review-workspace-contract.test.mjs` — regresja kontraktowa UI.
- Istniejące: `ai_docs/requirements/ADMIN_APP.md` — opis zachowania operatora.
- Istniejące: `ai_docs/process/CURRENT_STATE.md` — wynik taska.
- Nowe: `ai_docs/delivery/DEFERRED_BOARD_CELL_GEOMETRY_PAN_MODE_EXECUTION_PLAN.md` — zaakceptowany plan.

## Test cases

- Tryb domyślny: tło canvasu nie inicjuje panoramowania.
- Tryb aktywny: tło inicjuje istniejącą translację viewportu.
- Uchwyt narożnika: działa niezależnie od trybu przesuwania.

## Verification

```powershell
# apps/reviewer, timeout <= 120 s
node --experimental-strip-types --test test/operational-review-state.test.mjs test/operational-review-workspace-contract.test.mjs
node ../../node_modules/eslint/bin/eslint.js .
node ../../node_modules/typescript/bin/tsc --noEmit
node ../../node_modules/next/dist/bin/next build
```

## Risks / open questions

- Checkbox nie może przejąć logiki czterech uchwytów ani być serializowany do API.

## Outcome

### Changed

- Dodano lokalny checkbox `Aktywne przesuwanie`, domyślnie wyłączony dla
  wczytywanej planszy.
- Canvas inicjuje przesuwanie tła wyłącznie po jego zaznaczeniu; cztery
  narożniki zachowują pierwszeństwo w obu trybach.
- Checkbox nie zmienia geometrii, kwalifikacji, preview, idempotencji ani
  payloadu zapisu.

### Verification results

- Skoncentrowane testy Reviewera: 20/20 passed; pełny zestaw Reviewera: 201/201 passed.
- ESLint, TypeScript `--noEmit` i production build Reviewera: passed.
- Artefakt production build zawiera etykietę `Aktywne przesuwanie`.

### Not completed

- Ręczny odbiór po zmianie nie był dostępny: po odświeżeniu lokalny backend
  zwrócił `IMAGE_GRID_REVIEW_PROJECTION_INCOMPLETE` i nie udostępnił kolejki.
  Nie wykonano żadnej mutacji danych.

### Documentation updates

- Uściślono domyślnie statyczny obraz i jawną aktywację panoramowania w
  `ai_docs/requirements/ADMIN_APP.md`.
- Zaktualizowano `ai_docs/process/CURRENT_STATE.md`.

### Recommended next task

- Osobno przywrócić projekcję kolejki lokalnego API i wykonać ręczny odbiór na
  prawdziwej niepełnej planszy; nie jest to zmiana logiki panoramowania.
