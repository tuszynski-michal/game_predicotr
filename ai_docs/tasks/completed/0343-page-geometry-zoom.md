---
title: TASK-0343 — Zoom korekty geometrii strony
status: done
last_updated: 2026-08-30
---

# TASK-0343 — Zoom korekty geometrii strony

## Goal

Ułatwić precyzyjne ustawianie narożników i krzywizny dziewięciu ramek bez
zmiany współrzędnych zapisywanej geometrii.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`

## Scope

- dopasowanie zdjęcia do wymiarów viewportu;
- zoom 100–3000% co 25%;
- szybki powrót do 100%;
- przewijanie obrazu w obu osiach;
- mapowanie kursora do źródłowych współrzędnych niezależne od skali;
- zachowanie zoomu podczas przechodzenia między zdjęciami w bieżącej partii.

## Out of scope

- zmiana zapisanych quadów podczas samego zoomowania;
- utrwalanie zoomu w bazie lub API;
- zmiana progów geometrii i preflightu;
- fullscreen i gesty wielodotykowe.

## Outcome

- Edytor używa `fitManualImageToViewport`, tej samej czystej funkcji co lokalna
  ręczna selekcja.
- Kontrolki `−`, procent i `+` zmieniają wyłącznie rozmiar wspólnego canvasu
  obrazu i SVG. Obie warstwy pozostają idealnie nałożone.
- Viewport ma ograniczoną wysokość i własny scroll poziomy oraz pionowy.
- Test regresyjny potwierdza identyczne współrzędne źródłowe punktu przy 100%
  i 200% zoomu.
