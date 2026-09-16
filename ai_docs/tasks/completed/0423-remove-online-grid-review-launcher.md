---
title: Remove online grid review launcher
status: done
task_id: TASK-0423
last_updated: 2026-09-03
---

# TASK-0423 — Usunięcie zdalnych zaszłości z walidacji siatki

## Goal

Zapewnić jeden stabilny, lokalny sposób otwierania `Zatwierdzania cięcia
siatki`, bez migających kontrolek starego lifecycle'u udostępniania.

## Scope

- usunąć z launchera online link, kod, status ingressu i listę aktywnych prac;
- usunąć lokalne assignmenty, heartbeat i akcję kończenia pracy;
- otwierać docelowy loopback URL bezpośrednio;
- usunąć nieużywany adapter, pomocniczą nawigację, testy i style;
- zaktualizować wymagania oraz instrukcję operatorską.

## Out of scope

- zmiana purpose-scoped zdalnej ręcznej selekcji zdjęć;
- destrukcyjne usuwanie historycznych tabel i endpointów backendu;
- zmiana API geometrii albo danych plansz.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Definition of Done

- przy pierwszym renderze ani po załadowaniu danych nie istnieje przycisk
  online lub kończenia pracy;
- otwarcie lokalne nie wykonuje reviewer-work API;
- popup otrzymuje od razu finalny scope gry i importu;
- testy Admina, lint, typecheck i build przechodzą.

## Outcome

- Launcher renderuje jeden stabilny przycisk `Otwórz lokalnie`; usunięto link
  online, kody, ingress, listę assignmentów i akcje ich zamykania.
- Lokalny Reviewer otrzymuje od razu docelowy URL loopback z grą i importem,
  bez wywołania reviewer-work API oraz bez pustej karty pośredniej.
- Usunięto frontendowy adapter assignmentów, nieużywane pomocniki nawigacji,
  stare testy akcji oraz style wyłącznie dla udostępniania.
- Purpose-scoped zdalna ręczna selekcja zdjęć pozostała bez zmian.
- Weryfikacja:
  - `npm run test --workspace @game-predictor/admin` — 372 passed;
  - `npm run lint --workspace @game-predictor/admin` — passed;
  - `npm run typecheck --workspace @game-predictor/admin` — passed;
  - `npm run admin:build` — passed;
  - skoncentrowany Prettier — passed;
  - globalny `npm run format:check` nadal wskazuje siedem wcześniejszych,
    niezwiązanych plików, natomiast wszystkie pliki kodu TASK-0423 są zgodne.
