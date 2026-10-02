---
title: Fixed viewport while editing deferred grid corners
status: done
last_updated: 2026-09-26
---

# TASK-0703 — stały viewport podczas korekty odroczonej siatki

## Status

`in_progress`

## Goal

Przeciąganie narożnika na ekranie „Niepełne siatki do ręcznej korekty” nie zmienia skali ani położenia obrazu, gdy operator nie włączył „Aktywnego przesuwania”.

## Context

TASK-0700 poprawnie blokuje przesuwanie tła, ale wspólna funkcja aktualizacji narożnika automatycznie buduje nowy viewport z obrysu. Zmiana szerokości lub wysokości siatki zmienia więc rozmiar canvasu i wygląda jak niepożądane powiększanie albo pomniejszanie obrazu.

## Dependencies / entry conditions

- TASK-0700 dostarczył checkbox „Aktywne przesuwanie”.
- Ręczny odbiór wskazanego ekranu potwierdził, że checkbox jest widoczny, ale gest narożnika nadal zmienia widok.

## Recommended execution

`gpt-6-sol`, reasoning `high`: mała poprawka UI wymaga odróżnienia trwałej geometrii od lokalnego viewportu oraz regresji interakcji canvasu. Eskalacja nie jest oczekiwana.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- `DeferredBoardCellGeometryEditor` i testy jego zachowania viewportu.
- Utrzymanie stałego viewportu w czasie dragowania narożnika.

## Out of scope

- Zmiana API, preview, zapisu geometrii, kwalifikacji niepełnej planszy oraz innych edytorów siatek.

## Acceptance criteria

- [ ] Przy domyślnie wyłączonym checkboxie przesunięcie narożnika zmienia tylko narożnik.
- [ ] Podczas tego gestu `viewport` nie zmienia `x`, `y`, `width` ani `height`.
- [ ] „Wycentruj widok na siatce” oraz „Przywróć sugestię” nadal mogą świadomie wycentrować widok.
- [ ] Nie ma regresji ręcznego przesuwania po zaznaczeniu checkboxa.

## Technical notes

Oddziel funkcję zmiany narożników od jawnego resetu viewportu. Gest canvasu nie może wywoływać automatycznego `operationalReviewGeometryViewport`; reset viewportu jest dozwolony wyłącznie dla inicjalizacji, zmiany kwalifikacji, przywrócenia sugestii i jawnego przycisku centrowania. Test ma odtworzyć zmianę rozmiaru obrysu i sprawdzić niezmienność viewportu.

## Expected files

- Istniejące: `apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx`.
- Istniejące: właściwy test Reviewera dla `DeferredBoardCellGeometryEditor`.
- Istniejące: `ai_docs/process/CURRENT_STATE.md`.

## Test cases

- Drag narożnika z wyłączonym checkboxem i obrysem o zmienionej szerokości → viewport bez zmian.
- Przywrócenie sugestii → viewport jest jawnie wycentrowany do sugestii.
- Drag tła z włączonym checkboxem → translacja viewportu bez zmiany narożników.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr; timeout maks. 120 s
pnpm --filter reviewer test -- --runInBand
pnpm --filter reviewer lint
pnpm --filter reviewer typecheck
```

## Risks / open questions

- Brak: zachowanie jest jednoznaczne i lokalne dla wskazanego edytora.

## Outcome

### Changed

- Drag narożnika aktualizuje wyłącznie `corners`; nie wywołuje już automatycznego
  przeliczenia `viewport` z nowego obrysu.
- `replaceCorners` centruje viewport wyłącznie po jawnym przekazaniu
  `recenterViewport: true`; używa go tylko „Przywróć sugestię”. Przycisk
  „Wycentruj widok na siatce” pozostaje osobną świadomą akcją.
- Test kontraktowy chroni domyślne niecentrowanie po zmianie narożnika oraz
  jawne centrowanie przy przywróceniu sugestii.

### Verification results

- `pnpm --filter @game-predictor/reviewer test`: 201 passed.
- Prettier check dla dwóch zmienionych plików: passed.
- `git diff --check`: passed.

### Not completed

- `lint`, `typecheck` i `test:geometry` nie wystartowały: lokalny
  `node_modules` nie zawiera wykonywalnych `eslint`, `tsc` ani `tsx`. Nie
  zmieniano zależności ani konfiguracji poza zakresem zadania.
- Po przeładowaniu wskazanego importu kolejka odroczonych siatek zwróciła `0`,
  więc nie wykonano drugiego ręcznego dragowania na aktywnym pending itemie.

### Documentation updates

- Zaktualizowano `CURRENT_STATE.md`.

### Recommended next task

- Brak; po odświeżeniu Reviewera drag narożnika zachowuje stały viewport.
