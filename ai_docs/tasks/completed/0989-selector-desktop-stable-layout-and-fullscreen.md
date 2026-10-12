---
title: Stabilny układ, minimalny fullscreen i centrowanie zdjęcia
status: done
last_updated: 2026-10-13
---

# TASK-0989 — Stabilny układ, minimalny fullscreen i centrowanie zdjęcia

## Status

`done`

## Goal

Wyłączono rutynowe komunikaty nawigacji/zapisu, pozostałe informacje są dolnym overlayem. Minimalny natywny fullscreen, zsynchronizowane wyjście F11/Escape/przycisk i centrowanie zdjęcia w obu osiach zachowują przewijanie przy dużym zoomie.

## Context

Jawne zgłoszenie użytkownika dotyczące aplikacji desktopowej. Kod wykonano i zatwierdzono wcześniej; zapis taska/dokumentacji został odroczony na polecenie operatora. Ten dokument odtwarza ukończony zakres, nie jest planem niezaimplementowanego taska.

## Dependencies / entry conditions

TASK-0988 i jawna zgoda użytkownika na zmianę UI.

## Recommended execution

gpt-6.1-sol / medium. Mała zmiana renderera i regresje rzeczywistego EXE. Audyt operatora na końcu zgodnie z D-545/D-546; nie deklarujemy nowego niezależnego audytu.

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/DECISION_LOG.md — D-547
- ai_docs/delivery/OFFLINE_PHOTO_SELECTOR_EXECUTION_PLAN.md
- ai_docs/requirements/MANUAL_IMAGE_SELECTION.md
- ai_docs/architecture/MANUAL_IMAGE_SELECTION.md
- ai_docs/quality/OFFLINE_PHOTO_SELECTOR_RELEASE_1_0_0_20261013.md

## Scope

Wyłączono rutynowe komunikaty nawigacji/zapisu, pozostałe informacje są dolnym overlayem. Minimalny natywny fullscreen, zsynchronizowane wyjście F11/Escape/przycisk i centrowanie zdjęcia w obu osiach zachowują przewijanie przy dużym zoomie.

## Out of scope

Zmiany API/Admin/Reviewera/bazy, numeracji domenowej i formatu projektu, upload, dane operatora, nowa instrukcja Word.

## Acceptance criteria

- [x] Zgłoszony układ jest stabilny przy zmianie zdjęcia.
- [x] Windowed i natywny fullscreen zachowują wymagane położenie oraz sterowanie.
- [x] Zoom/przewijanie i wznowienie zachowują zapisany widok.
- [x] Rzeczywisty finalZIP i celowane kontrole PASS.

## Technical notes

Wyłączono rutynowe komunikaty nawigacji/zapisu, pozostałe informacje są dolnym overlayem. Minimalny natywny fullscreen, zsynchronizowane wyjście F11/Escape/przycisk i centrowanie zdjęcia w obu osiach zachowują przewijanie przy dużym zoomie. Nie osłabiono kontroli plików ani serializacji decyzji.

## Expected files

Istniejące zmienione moduły: apps/selector-desktop/src/renderer/App.tsx, style.css, src/contracts.ts, preload.ts, main.ts, scripts/smoke-ux.mjs. Dokumenty stanu i rejestr wydania.

## Test cases

Nawigacja bez przemieszczenia podglądu, zdjęcia pionowe/poziome, fullscreen enter/exit, zoom/scroll, close/reopen, utrata locka, zakres nad zdjęciem.

## Verification

Z katalogu głównego repo w PowerShell; każda komenda ograniczona:

```powershell
node apps/selector-desktop/scripts/run-bounded.mjs 90 npm run test:ui --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 90 npm run lint --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 90 npm run typecheck --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release:ux --workspace @game-predictor/selector-desktop
```

## Risks / open questions

Nie wykonano nowego niezależnego audytu Claude ostatnich zmian ani fizycznych kontroli odbiorcy. Odbiór1.0.0 zaakceptowany decyzją operatora D-547.

## Outcome

### Changed

Wyłączono rutynowe komunikaty nawigacji/zapisu, pozostałe informacje są dolnym overlayem. Minimalny natywny fullscreen, zsynchronizowane wyjście F11/Escape/przycisk i centrowanie zdjęcia w obu osiach zachowują przewijanie przy dużym zoomie.
Commity: v1.7.341 / a9cb2fed291077419c1b67fab546deafaf98771b.

### Verification results

UI6/6, lint/typecheck/format, packaged UX i finalZIP0.1.5 full/UX PASS. Świeży finalZIP1.0.0 full/UX/start PASS.

### Not completed

Nowa instrukcja Word i niezależny końcowy audyt nowych zmian. Brak testów fizycznych nie jest raportowany jako PASS.

### Documentation updates

Zapis dokumentacji odroczony przez operatora; uzupełniony przy scalaniu wydania1.0.0. D-547, wymagania, architektura, instrukcja operatora, Outcome i CURRENT_STATE.

### Recommended next task

Osobna aktualizacja instrukcji Word do finalnego wydania.
