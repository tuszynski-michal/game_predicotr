---
title: Zakres pośrodku nad zdjęciem i końcowy zapis widoku
status: done
last_updated: 2026-10-13
---

# TASK-0990 — Zakres pośrodku nad zdjęciem i końcowy zapis widoku

## Status

`done`

## Goal

Zakres przeniesiono poza toolbar do osobnego wyśrodkowanego wiersza nad zdjęciem w obu trybach. Semantyka dziewięciu plansz pozostaje. closingProject blokuje spóźnione zmiany widoku podczas close; dodano deterministyczną regresję scrolla po kliknięciu zamknięcia.

## Context

Jawne zgłoszenie użytkownika dotyczące aplikacji desktopowej. Kod wykonano i zatwierdzono wcześniej; zapis taska/dokumentacji został odroczony na polecenie operatora. Ten dokument odtwarza ukończony zakres, nie jest planem niezaimplementowanego taska.

## Dependencies / entry conditions

TASK-0989 i jawna zgoda użytkownika na zmianę UI.

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

Zakres przeniesiono poza toolbar do osobnego wyśrodkowanego wiersza nad zdjęciem w obu trybach. Semantyka dziewięciu plansz pozostaje. closingProject blokuje spóźnione zmiany widoku podczas close; dodano deterministyczną regresję scrolla po kliknięciu zamknięcia.

## Out of scope

Zmiany API/Admin/Reviewera/bazy, numeracji domenowej i formatu projektu, upload, dane operatora, nowa instrukcja Word.

## Acceptance criteria

- [x] Zgłoszony układ jest stabilny przy zmianie zdjęcia.
- [x] Windowed i natywny fullscreen zachowują wymagane położenie oraz sterowanie.
- [x] Zoom/przewijanie i wznowienie zachowują zapisany widok.
- [x] Rzeczywisty finalZIP i celowane kontrole PASS.

## Technical notes

Zakres przeniesiono poza toolbar do osobnego wyśrodkowanego wiersza nad zdjęciem w obu trybach. Semantyka dziewięciu plansz pozostaje. closingProject blokuje spóźnione zmiany widoku podczas close; dodano deterministyczną regresję scrolla po kliknięciu zamknięcia. Nie osłabiono kontroli plików ani serializacji decyzji.

## Expected files

Istniejące zmienione moduły: apps/selector-desktop/src/renderer/App.tsx, style.css, scripts/smoke-ux.mjs. Dokumenty stanu i rejestr wydania.

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

Zakres przeniesiono poza toolbar do osobnego wyśrodkowanego wiersza nad zdjęciem w obu trybach. Semantyka dziewięciu plansz pozostaje. closingProject blokuje spóźnione zmiany widoku podczas close; dodano deterministyczną regresję scrolla po kliknięciu zamknięcia.
Commity: v1.7.342 / c9afef29d4839cc17eee727ca8324832f6b9379b; v1.7.343 / 8a3249fdefc49547cb2d8ed001e8841cdd2867eb.

### Verification results

UI6/6, lint/typecheck, packaged UX po poprawce oraz finalZIP0.1.6 UX PASS. Geometria zakresu: mniej niż1CSSpixel od środka zdjęcia. Pierwszy smoke wykrył utratę widoku przy close; nieudane logi zachowane. Świeży1.0.0 full/UX/start PASS.

### Not completed

Nowa instrukcja Word i niezależny końcowy audyt nowych zmian. Brak testów fizycznych nie jest raportowany jako PASS.

### Documentation updates

Zapis dokumentacji odroczony przez operatora; uzupełniony przy scalaniu wydania1.0.0. D-547, wymagania, architektura, instrukcja operatora, Outcome i CURRENT_STATE.

### Recommended next task

Osobna aktualizacja instrukcji Word do finalnego wydania.
