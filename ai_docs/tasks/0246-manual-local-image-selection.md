---
title: TASK-0246 local manual image selection workspace
status: in_progress
release: '0.6'
last_updated: 2026-08-18
---

# TASK-0246 — Lokalna ręczna selekcja zdjęć

## Goal

Udostępnić prosty, niezależny fallback do ręcznego przypisywania zdjęć do
ciągłych zakresów 9 layoutów bez zależności od automatycznego selektora.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/requirements/ADMIN_APP.md`

## Acceptance

- osobna zakładka w Adminie z wyborem pierwszego layoutu, kierunku oraz dwóch
  lokalnych folderów,
- naturalne, rekurencyjne listowanie JPEG-ów i zachowanie oryginalnych bajtów,
- Enter zapisuje `seq_start-end.jpg`, zwiększa zakres o 9 i przechodzi do kolejnego
  zdjęcia; Tab pomija zakres i pozostawia zdjęcie; strzałki tylko nawigują,
- sesja jest odtwarzana po zamknięciu i ponownym wejściu; Ctrl+Z bezpiecznie cofa
  ostatni zapis,
- checksum blokuje nadpisanie lub usunięcie obcego pliku,
- testy jednostkowe, typecheck i lint Admina przechodzą.

## Outcome

Implementacja UI, logiki plików, magazynu IndexedDB i testów jest gotowa.
W `v0.6.28` magazyn został podniesiony do wersji 2 i zapisuje trwały ślad
widoczności oraz decyzji. Wynik i ślad treningowy są eksportowane jako
`manual-image-selection-output-v1.json` i `manual-image-selection-trace-v1.json`.
Pozostało wykonać końcowy przegląd integracyjny oraz oznaczyć zadanie jako done
po akceptacji manualnego przepływu w przeglądarce.
