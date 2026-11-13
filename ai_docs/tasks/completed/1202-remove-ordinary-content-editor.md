---
title: TASK-1202 — Usunięcie ręcznego edytora etykiet zawartości
status: done
last_updated: 2026-11-13
---

# TASK-1202 — Usunięcie ręcznego edytora etykiet zawartości

## Status

`done`

## Goal

Admin nie ma już ręcznego edytora zwykłych etykiet zawartości; obrysy zatwierdza się
wyłącznie w oknie „Obrysy symboli z siatek” (TASK-1201), a ślepy pomiar działa jak dotąd.

## Context

D-608 przeznaczyła ręczny edytor do usunięcia. Operator: „usuń na samym końcu jak
starczy Ci tokenów”, „zrób wszystkie zadania od 1-3”. Ten sam edytor otwierał przycisk
„Oznacz zdjęcia do testu” w panelu uczenia; przycisk otwiera teraz nowe okno.

## Dependencies / entry conditions

- TASK-1201 w `main` (v1.7.628).

## Recommended execution

Claude Opus 5.5, reasoning medium; bez dodatkowego review (polecenie operatora).

## Relevant docs

- `AGENTS.md`
- [D-608](../../process/decisions/DECISION_LOG_2026.md#d-608--obrysy-symboli-z-zatwierdzonych-siatek)
- `ai_docs/requirements/ADMIN_APP.md`

## Scope

- Usunięcie `grid-content-ordinary.tsx`, `grid-content-source-selection.tsx`,
  `grid-content-readiness.tsx` oraz trybu `ordinary` z `GridContentReferenceWorkspace`.
- „Oznacz zdjęcia do testu” → „Zatwierdź obrysy symboli” (nowe okno).
- Testy interakcji starego edytora usunięte lub zawężone do ślepego pomiaru.

## Out of scope

- Endpointy API (zapis i odczyt etykiet, cele po `sourceIds`, gotowość pokrycia):
  zostają, bo zapis używa nowe okno, a pozostałe są kontraktem API.
- Ogólny moduł `grid-content-state.ts` i płótno `grid-content-canvas.tsx` (wspólne ze
  ślepym pomiarem).

## Acceptance criteria

- [x] Brak wejścia do ręcznego edytora w Adminie; ślepy pomiar bez zmian.
- [x] Przycisk próbki testowej otwiera `/symbol-outlines?gameId=` bez wywołań API.
- [x] Typecheck i testy Admina bez nowych porażek.

## Test cases

- Panel uczenia: „Zatwierdź obrysy symboli” otwiera nowe okno w `_blank`, bez wywołań
  API, a starego przycisku nie ma.
- Ślepy pomiar: dotychczasowe testy cohort/targets/session/remount przechodzą.

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run test:geometry --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
```

## Outcome

Commit: v1.7.630 (hash dopisuje kolejny commit).

### Changed

- Usunięte komponenty edytora zwykłych etykiet, wyboru źródeł i gotowości pokrycia;
  `GridContentReferenceWorkspace` obsługuje tylko ślepy pomiar (bez propów `mode`,
  `annotationSourceIds`).
- `GridModelWorkspace` trzyma tylko stan otwarcia ślepego pomiaru.
- Panel uczenia: „Zatwierdź obrysy symboli” otwiera okno obrysów; usunięto
  `annotationClient`.
- Testy: usunięto 9 testów starego edytora, zawężono test remountu i pętle przejść do
  zmiany gry, zastąpiono test „Oznacz zdjęcia do testu”.

### Verification results

- Admin `node --test test/*.test.mjs`: 864/864.
- Testy interakcji etykiet, panelu uczenia i Geometrii V3: 97/97.
- Wszystkie testy interakcji: 11 porażek, identycznych z `main` (serie, picker); zero
  nowych.
- `tsc --noEmit` PASS; eslint zmienionych plików bez błędów.

### Not completed

- Endpointy używane wyłącznie przez stary edytor (`content-targets?sourceIds`, asset
  źródła z pinami, `content-readiness`) zostają w API; ich usunięcie to zmiana kontraktu.

### Documentation updates

- `ADMIN_APP.md`, `CURRENT_STATE.md`.

### Recommended next task

- Ewentualne wycofanie nieużywanych endpointów po decyzji operatora.
