---
title: Klikalne kafelki i wybór symbolu w korekcie siatki
status: todo
last_updated: 2026-10-02
---

# TASK-0819 — Klikalne kafelki i wybór symbolu w korekcie siatki

## Status

`todo`

## Goal

Operator klika kafelek podglądu, wybiera symbol z palety pod podglądem, a zapis
siatki wysyła narzucone symbole.

## Context

Ostatni element przepływu D-486.

## Dependencies / entry conditions

TASK-0817 i TASK-0818 wykonane.

## Recommended execution

`claude-fable-5-1`, poziom bieżącej sesji (nazwy poziomu nie da się odczytać ze środowiska — rekomendacja warunkowa). Eskalacja: rozbieżność kodu z planem
`ai_docs/delivery/GRID_CORRECTION_SYMBOLS_EXECUTION_PLAN.md`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GRID_CORRECTION_SYMBOLS_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-462, D-486)

## Scope

- Edytor `BoardGeometryCorrectionEditor`: kafelki jako przyciski, paleta
  aktywnych symboli, etykieta podpowiedzi/narzuconego symbolu, „Usuń wybór”.
- Workspace pobiera katalog symboli (`listSymbols`).
- Wymagania `ADMIN_APP.md` i `API_CONTRACT.md`, `CURRENT_STATE.md`.

## Out of scope

- Dialog korekty w przeglądzie operacyjnym; skróty klawiszowe; obrazy symboli.

## Acceptance criteria

- [ ] Kafelek z pikselami jest klikalny; pole poza zdjęciem nie.
- [ ] Wybrany symbol jest widoczny na kafelku i trafia do komendy zapisu.
- [ ] Cel bez obsługi symboli (operacyjny) nie pokazuje palety.

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

Wypełnia agent po pracy.
