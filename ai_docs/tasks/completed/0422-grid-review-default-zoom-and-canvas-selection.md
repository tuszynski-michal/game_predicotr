---
title: Grid review default zoom and canvas selection
status: done
task_id: TASK-0422
last_updated: 2026-09-03
---

# TASK-0422 — Zoom i wybór planszy na obrazie

## Goal

Ułatwić lokalną korektę geometrii przez start z powiększeniem 150% oraz
bezpośredni wybór widocznej planszy kliknięciem jej siatki na źródle.

## Scope

- ustawić domyślny zoom edytora geometrii na 150%;
- wybierać planszę po aktualnie widocznej geometrii, również po lokalnym
  przesunięciu szkicu;
- w trybie `Wyznacz plansze osobno` pozwolić przełączyć aktywną planszę
  kliknięciem innej siatki bez zmiany jej punktów;
- pokazać czytelną instrukcję i kursor wyboru;
- dodać test czystego hit-testu oraz kontraktu UI.

## Out of scope

- zapis po samym kliknięciu;
- zmiana kolejności slotów lub kontraktu API;
- wybór pojedynczej komórki symbolu na obrazie źródłowym.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Definition of Done

- nowy edytor otwiera źródło przy 150%;
- kliknięcie nieaktywnej, widocznej siatki wybiera ją także w source editing;
- kliknięcie wybierające nie przesuwa ani nie zapisuje geometrii;
- hit-test korzysta z bieżącego szkicu, nie ze starego automatu;
- testy, lint, typecheck i build Reviewera są zielone.

## Outcome

- Domyślny zoom lokalnego edytora wynosi 150%.
- Kliknięcie widocznej siatki wybiera odpowiadający slot poza edycją oraz w
  trybie `Wyznacz plansze osobno`; gest wyboru nie zmienia punktów.
- Wspólny, czysty hit-test używa automatycznej geometrii albo bieżącego szkicu
  dokładnie zgodnego z overlayem.
- Dodano widoczną instrukcję i kursor wyboru planszy.
- Weryfikacja:
  - `npm run test --workspace @game-predictor/reviewer` — 173 passed;
  - `npm run lint --workspace @game-predictor/reviewer` — passed;
  - `npm run typecheck --workspace @game-predictor/reviewer` — passed;
  - skoncentrowany `prettier --check` — passed;
  - `npm run reviewer:build` — passed.
