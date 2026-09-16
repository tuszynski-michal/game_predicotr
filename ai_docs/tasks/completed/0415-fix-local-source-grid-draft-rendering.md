---
title: TASK-0415 Fix local source grid draft rendering
status: done
last_updated: 2026-09-03
---

# TASK-0415 — Naprawa lokalnego renderowania pustego szkicu geometrii źródła

## Goal

Lokalny tryb `Wyznacz plansze osobno` musi otwierać pierwszy pusty slot bez
awarii Reviewera i bez przejścia do ekranu zdalnego kodu dostępu.

## Context

Tryb source geometry celowo rozpoczyna wybraną planszę od zera punktów. Canvas
overlay próbował jednak odczytać pierwszy punkt niezależnie od długości szkicu,
co kończyło klienta błędem `Cannot read properties of undefined (reading 'x')`.
Po reloadzie nieprawidłowy ekran zdalnej sesji maskował przyczynę.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Bezpiecznie renderować pusty i częściowy szkic narożników w lokalnym canvasie.
- Zachować kolejność LT → PT → PD → LD i pozostałe aktywne sloty źródła.
- Dodać regresyjny test stanu zeropunktowego oraz kontrolę użycia go przez
  renderer.
- Zaktualizować bieżący stan i wynik zadania.

## Out of scope

- Bez zmiany zdalnego Reviewera, dostępu kodem i jego kontraktów.
- Bez mutacji geometrii, importów lub danych użytkownika.

## Acceptance criteria

- [ ] Kliknięcie `Wyznacz plansze osobno` nie kończy się błędem strony.
- [ ] Pusty szkic nie ma kotwicy overlayu, a szkic częściowy pozostaje
  renderowalny.
- [ ] Poprzedni lokalny URL zachowuje `mode=local`, `gameId` i `importJobId`.
- [ ] Testy, lint i typecheck Reviewera są zielone.

## Expected files

- `apps/reviewer/src/features/grid-reviews/grid-review-state.ts`
- `apps/reviewer/src/features/grid-reviews/grid-review-editor.tsx`
- `apps/reviewer/test/grid-review-state.test.mjs`
- `apps/reviewer/test/grid-review-workspace-contract.test.mjs`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm run test --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run reviewer:build
```

## Outcome

### Changed

- Canvas lokalnego Reviewera rozpoznaje zeropunktowy szkic jako poprawny stan
  przed pierwszym kliknięciem LT i nie próbuje odczytać nieistniejącej
  współrzędnej.
- Szkic zwykłej edycji oraz wskazany crop są wiązane z `reviewItemId`, zamiast
  być synchronicznie resetowane w efekcie Reacta. Usuwa to ostrzeżenie lintu i
  nie miesza stanu po przełączeniu slotu.
- Dodano regresję dla braku kotwicy pustego szkicu oraz kontrakt ochrony
  renderera.

### Verification results

- `npm run test --workspace @game-predictor/reviewer` — passed (172 testy).
- `npm run lint --workspace @game-predictor/reviewer` — passed.
- `npm run typecheck --workspace @game-predictor/reviewer` — passed.
- `npm run reviewer:build` — passed.
- Rzeczywisty lokalny URL importu `3264a85b-ad19-49db-aa4a-a1d0893f2f6c`:
  kliknięcie `Wyznacz plansze osobno` utrzymało `mode=local`, otworzyło
  `Plansza 1/9 · kliknij narożnik LT (1/4)` i nie zapisało błędu konsoli.

### Not completed

- Nie zmieniano ograniczonego, zdalnego Reviewera ani jego dostępu kodem;
  pozostaje on celowo odseparowany od lokalnego API geometrii v0.10.

### Documentation updates

- `CURRENT_STATE.md` opisuje prawidłowy pusty szkic lokalnej geometrii.

### Recommended next task

- Kontynuować wyłącznie osobno wskazany przez operatora task.
