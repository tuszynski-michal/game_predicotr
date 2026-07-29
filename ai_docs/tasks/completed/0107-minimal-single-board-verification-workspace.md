---
title: Minimal single-board verification workspace
status: done
last_updated: 2026-07-29
completed_at: 2026-07-29
---

# TASK-0107 — Minimal single-board verification workspace

## Status

`done`

## Goal

Zbudować w lokalnym panelu admina minimalistyczny ekran operacyjnego review,
który pokazuje jedną planszę 5 × 3 nad foldem, zachowuje kontekst gry i import
joba oraz korzysta wyłącznie z kontraktu TASK-0106.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_06_5_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- dodać osobną sekcję nawigacji dla operacyjnego zatwierdzania plansz,
- pobrać aktywne gry i ich joby importu `image_directory`,
- wymagać wybranego kontekstu gry oraz import joba,
- przełączać widok `pending` / `completed`,
- pokazywać dokładne liczniki statusów,
- obsłużyć bounded poprzedni/następny oraz skok do `sequenceNumber`,
- pokazać kompaktowy header z grą, sequence, pozycją, statusem i małym
  przyciskiem `Zatwierdź`,
- pokazać dokładnie 15 cropów row-major z aktualną etykietą i confidence,
- pokazać bieżącą etykietę domyślnie wybranej komórki,
- umieścić pełne oryginalne zdjęcie poniżej siatki,
- pokazać miejsce na legendę skrótów bez uruchamiania sterowania z TASK-0108,
- obsłużyć loading, empty, error, brak obrazu i konflikt kursora,
- dodać testy czystego stanu, akcji API i kontraktu komponentu.

## Out of scope

- zmiana symbolu i tooltip sugestii — TASK-0108,
- skróty klawiaturowe oraz dwustopniowe potwierdzenie — TASK-0108,
- zapis decyzji accepted/corrected/rejected — TASK-0108,
- edycja siatki i nowe cropy — TASK-0109,
- ręczne testy ekranu — odbiór po TASK-0111,
- hosting i dostęp zdalny — M8.7.

## Acceptance criteria

- [x] ekran nie pobiera całej kolejki i używa cursorów TASK-0106,
- [x] każdy request zawiera `gameId` oraz `importJobId`,
- [x] pending i completed mają jawny wybór i liczniki,
- [x] header, akcja, etykiety i siatka 5 × 3 mieszczą się nad foldem przy
  1366 × 768,
- [x] plansza pokazuje dokładnie 15 komórek oraz stan wybranej komórki,
- [x] oryginalne zdjęcie jest poniżej głównej planszy,
- [x] completed nie jest przedstawione jako tylko do odczytu,
- [x] loading, empty, error i brak obrazu są jawne tekstowo,
- [x] nowe zachowanie ma testy automatyczne oraz przechodzi lint, typecheck i
  build.

## Expected files

- `apps/admin/src/features/operational-reviews/operational-review-actions.ts`
- `apps/admin/src/features/operational-reviews/operational-review-state.ts`
- `apps/admin/src/features/operational-reviews/operational-review-workspace.tsx`
- `apps/admin/src/features/catalog/catalog-workspace.tsx`
- `apps/admin/src/components/admin-shell.tsx`
- `apps/admin/src/app/globals.css`
- `apps/admin/test/operational-review-*.test.mjs`
- dokumentacja procesu.

## Assumptions

- pierwsza wersja wybiera pierwszy aktywny image import job aktualnej gry,
- domyślny widok to `pending`, a pierwsza komórka jest wybrana informacyjnie,
- przycisk zatwierdzenia jest widoczny, ale jego bezpieczna akcja powstaje w
  TASK-0108,
- TASK-0107 nie uruchamia ani nie publikuje strony; panel pozostaje lokalny,
- każda potencjalnie ciężka komenda ma timeout nie większy niż 120 sekund.

## Outcome

Dodano osobną sekcję `Zatwierdzanie` w lokalnym panelu. Ekran wybiera aktywną
grę oraz najnowszy dostępny import `image_directory`, ładuje jedną planszę
przez bounded cursor TASK-0106 i przełącza widoki pending/completed. Kompaktowy
header pokazuje sequence, pozycję źródła/planszy, status, rewizję, liczniki,
nawigację i skok do numeru układu.

Główna siatka renderuje dokładnie 15 cropów row-major z nazwą symbolu i
confidence. Pierwsza komórka jest wybrana informacyjnie, pełny oryginał znajduje
się poniżej, a brak pliku ma kontrolowany placeholder. Completed jest jawnie
opisane jako edytowalne przez następną rewizję. Przycisk zatwierdzenia jest
widoczny, lecz bezpiecznie nieaktywny do TASK-0108; ekran nie zapisuje niczego
po samym odczycie.

Walidacja:

- nowe testy actions/state/contract — `6 passed`,
- pełne testy panelu — `83 passed`,
- TypeScript strict — passed,
- ESLint zmienionego obszaru — passed,
- Prettier — passed,
- produkcyjny `next build` — passed.

Nie wykonano ręcznych testów ani wizualnego odbioru 1366 × 768. Zgodnie z
decyzją właściciela odbędą się zbiorczo po TASK-0111.
