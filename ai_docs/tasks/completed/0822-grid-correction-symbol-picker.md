---
title: Klikalne kafelki i wybór symbolu w korekcie siatki
status: done
last_updated: 2026-10-02
---

# TASK-0822 — Klikalne kafelki i wybór symbolu w korekcie siatki

## Status

`done`

## Goal

Operator klika kafelek podglądu, wybiera symbol z palety pod podglądem, a zapis
siatki wysyła narzucone symbole.

## Context

Ostatni element przepływu D-488.

## Dependencies / entry conditions

TASK-0820 i TASK-0821 wykonane.

## Recommended execution

`claude-fable-5-1`, poziom bieżącej sesji (nazwy poziomu nie da się odczytać ze środowiska — rekomendacja warunkowa). Eskalacja: rozbieżność kodu z planem
`ai_docs/delivery/GRID_CORRECTION_SYMBOLS_EXECUTION_PLAN.md`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GRID_CORRECTION_SYMBOLS_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-462, D-488)

## Scope

- Edytor `BoardGeometryCorrectionEditor`: kafelki jako przyciski, paleta
  aktywnych symboli, etykieta podpowiedzi/narzuconego symbolu, „Usuń wybór”.
- Workspace pobiera katalog symboli (`listSymbols`).
- Wymagania `ADMIN_APP.md` i `API_CONTRACT.md`, `CURRENT_STATE.md`.

## Out of scope

- Dialog korekty w przeglądzie operacyjnym; skróty klawiszowe; obrazy symboli.

## Acceptance criteria

- [x] Kafelek z pikselami jest klikalny; pole poza zdjęciem nie.
- [x] Wybrany symbol jest widoczny na kafelku i trafia do komendy zapisu.
- [x] Cel bez obsługi symboli (operacyjny) nie pokazuje palety.

## Technical notes

Stan wyboru: mapa indeks pola → identyfikator symbolu, czyszczona po zapisie
i przy zmianie planszy. Podpowiedzi pobierane po każdym aktualnym podglądzie;
błąd podpowiedzi nie blokuje zapisu.

## Expected files

- `apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx`
- `…/board-geometry-correction-workspace.tsx`, `…/board-geometry-correction-target.ts`
- style Reviewera; `apps/reviewer/test-interactions/*`

## Test cases

- klik kafelka + symbol → `cellSymbols` w komendzie zapisu; brak wyboru → brak pola.

## Verification

```powershell
npm run test:geometry --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer; npm run lint --workspace @game-predictor/reviewer
```

## Risks / open questions

- Brak odbioru na żywych danych bez restartu usług.

## Outcome

### Changed

- `BoardGeometryCorrectionEditor`: kafelki-przyciski, paleta symboli, stan
  wyboru i podpowiedzi; `gridCellsWithoutPixels` wyznacza pola nieklikalne.
- `BoardGeometryCorrectionTarget.symbols` dla celu odroczonego i zgłoszonego;
  workspace pobiera katalog (`listSymbols`) i przekazuje go edytorowi.
- Style w `apps/admin/src/app/globals.css` (importowane przez Reviewer).

### Verification results

- `npm run test:geometry --workspace @game-predictor/reviewer`: 11/11.
- `npm run test --workspace @game-predictor/reviewer`: 200/200.
- `typecheck` i `lint` Reviewera czyste; Prettier czysty dla zmienionych plików.

### Not completed

- Brak odbioru na żywym Reviewerze (usługi operatora działają z głównego
  checkoutu; wymagany restart API i przebudowa Reviewera).
- Etykiety pozostają przy indeksach pól po przesunięciu siatki — operator
  widzi je na kafelkach przed zapisem.

### Documentation updates

- `ADMIN_APP.md` („Korekta cięcia siatki”), `CURRENT_STATE.md`, plan.

### Recommended next task

- Odbiór na żywo; ewentualnie skróty 1–9 i obrazy symboli w palecie.
