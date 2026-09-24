---
title: TASK-0636 — korekta TASK-0635, martwy test admina dla adjacentManualNavigationStep
status: done
last_updated: 2026-09-24
---

# TASK-0636 — korekta TASK-0635: martwy test admina dla `adjacentManualNavigationStep`

## Status

`done`

## Goal

Usunąć nieużywany import `MANUAL_IMAGE_NAVIGATION_STEPS` w
`apps/admin/test/manual-local-image-selection.test.mjs` (prośba
użytkownika) i, po odkryciu przy tym powiązanej regresji, naprawić czerwony
test w tym samym pliku pozostawiony przez TASK-0635.

## Context

Użytkownik poprosił o naprawę drobnego lint warninga (nieużywany import).
Przy naprawie okazało się, że ten sam import blok zawierał też
`adjacentManualNavigationStep`, a plik miał test z asercjami zgodnymi ze
**starym** zachowaniem tej funkcji (`v0.10.387`, free-form) —
bezpośrednio sprzecznymi z naprawą z `TASK-0635`/D-441 (przywrócenie
zachowania opartego na `MANUAL_IMAGE_NAVIGATION_STEPS`). Weryfikacja
`TASK-0635` uruchomiła testy `manual-image-selection-core` i `reviewer`,
ale pominęła `admin` — commit `v0.10.407` przez to po cichu zepsuł 1/564
test w `@game-predictor/admin`, niezauważony do tego tasku.

## Dependencies / entry conditions

- `TASK-0635` (D-441) ukończony — ten task go koryguje.

## Recommended execution

`claude-sonnet-5`, reasoning `medium`. Diagnoza konfliktu dwóch testów o
sprzecznych oczekiwaniach względem tej samej funkcji; naprawa jest
usunięciem martwych asercji i zastąpieniem ich testem rzeczywistego,
lokalnego zachowania Admina.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-441)

## Scope

- `apps/admin/test/manual-local-image-selection.test.mjs`: usunięcie
  nieużywanych importów (`adjacentManualNavigationStep`,
  `MANUAL_IMAGE_NAVIGATION_STEPS`), zamiana martwych asercji na
  `workspaceSource`-owe sprawdzenie rzeczywistej logiki Admina.
- `ai_docs/process/DECISION_LOG.md`: korekta punktu „Compatibility” w D-441
  (był niepełny — obejmował tylko kod produkcyjny, nie testy).

## Out of scope

- Zmiana `adjacentManualNavigationStep` w pakiecie (D-441 zostaje bez
  zmian — poprawne dla Reviewera).
- Zmiana produkcyjnego kodu Admina (`changeNavigationStepByDirection`,
  `normalizeNavigationStep`) — działa poprawnie, tylko test go źle
  weryfikował.

## Acceptance criteria

- [x] `MANUAL_IMAGE_NAVIGATION_STEPS` i `adjacentManualNavigationStep`
      usunięte z importów testu, gdy faktycznie nieużywane.
- [x] Test `'up and down arrows move by one configured navigation step'`
      weryfikuje rzeczywiste zachowanie Admina (bez górnego ograniczenia),
      nie zachowanie współdzielonej funkcji pakietu.
- [x] `npm run test --workspace @game-predictor/admin` w pełni zielony.
- [x] `npm run lint --workspace @game-predictor/admin`: 0 błędów, o jeden
      warning mniej niż przed tym taskiem.

## Technical notes

Pełna diagnoza (dlaczego dwa testy miały sprzeczne oczekiwania, dlaczego
Admin nie używa już `adjacentManualNavigationStep` w produkcji) jest w
`DECISION_LOG.md` D-441, punkt „Korekta (TASK-0636)” — nieduplikowana tutaj.

Nowe asercje w miejsce usuniętych:

```js
assert.match(
  workspaceSource,
  /const navigationStep = Math\.max\(1, currentStep \+ direction\);/,
);
assert.match(
  workspaceSource,
  /function normalizeNavigationStep[\s\S]*?Math\.max\(1, Math\.floor\(value\)\)/,
);
```

Zachowany kontrakt-testowy styl pliku (regex na surowym tekście źródła, nie
import prywatnych funkcji modułu) — spójne z resztą pliku.

## Expected files

- Istniejące: `apps/admin/test/manual-local-image-selection.test.mjs`,
  `ai_docs/process/DECISION_LOG.md`, `ai_docs/process/CURRENT_STATE.md`.
- Nowe: `ai_docs/tasks/completed/0636-manual-navigation-step-admin-test-fix.md`
  (ten plik).

## Test cases

- `apps/admin/test/manual-local-image-selection.test.mjs` pełny plik →
  32/32 (wcześniej 31/32, jeden czerwony).
- `npm run test --workspace @game-predictor/admin` → 564/564.

## Verification

```powershell
node --experimental-strip-types --test apps/admin/test/manual-local-image-selection.test.mjs
npm run test --workspace @game-predictor/admin        # timeout 120 s
npm run typecheck --workspace @game-predictor/admin    # timeout 120 s
npm run lint --workspace @game-predictor/admin         # timeout 120 s
npx prettier --check apps/admin/test/manual-local-image-selection.test.mjs
```

## Risks / open questions

- Brak. Proces uczy się na tym: naprawa funkcji współdzielonego pakietu
  wymaga uruchomienia testów każdego konsumenta, nie tylko pakietu i
  najbardziej oczywistego z nich — zapisane w D-441 jako wniosek na
  przyszłość.

## Outcome

### Changed

- `apps/admin/test/manual-local-image-selection.test.mjs`: usunięte
  nieużywane importy, zamienione martwe asercje.
- `ai_docs/process/DECISION_LOG.md`: D-441 skorygowane (punkt
  „Compatibility” doprecyzowany, nowy punkt „Korekta”).
- `ai_docs/process/CURRENT_STATE.md`: nowa sekcja TASK-0636.

### Verification results

- `node --experimental-strip-types --test apps/admin/test/manual-local-image-selection.test.mjs`
  → 32/32 passed (wcześniej 31/32).
- `npm run test --workspace @game-predictor/admin` → 564/564 passed.
- `npm run typecheck --workspace @game-predictor/admin` → czysto.
- `npm run lint --workspace @game-predictor/admin` → 0 błędów, 4 warningi
  (było 5).
- `npx prettier --check` → zielone bez zmian formatowania.

### Not completed

- Nic w zakresie tego taska.

### Documentation updates

- `ai_docs/process/DECISION_LOG.md`: D-441 skorygowane.
- `ai_docs/process/CURRENT_STATE.md`: nowa sekcja TASK-0636.

### Recommended next task

- Brak pilnego. Proceduralnie: przy przyszłych naprawach funkcji
  współdzielonych pakietów uruchamiać testy wszystkich znanych
  konsumentów, nie tylko oczywistego.
