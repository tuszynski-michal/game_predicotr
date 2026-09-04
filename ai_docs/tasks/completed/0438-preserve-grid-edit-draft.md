---
title: Preserve an unfinished grid edit draft
status: done
task_id: TASK-0438
last_updated: 2026-09-04
---

# TASK-0438 — Zachowanie szkicu po zakończeniu edycji siatki

## Goal

Nie przywracać automatycznej geometrii po kliknięciu `Zakończ edycję` dla
pojedynczej planszy.

## Scope

- zachować kompletny albo częściowy szkic po wyjściu z trybu przesuwania;
- pozostawić panel A/B i zapis dostępne dla zachowanego szkicu;
- pozwolić wznowić edycję bez resetu;
- blokować zwykłe zatwierdzenie, nawigację i zmianę planszy do czasu zapisania
  szkicu albo jawnego `Resetuj do automatu`;
- dodać testy regresyjne stanu i kontraktu UI.

## Out of scope

- automatyczny zapis przy zakończeniu edycji;
- zmiana API, geometrii lub semantyki zatwierdzenia;
- utrwalanie niezapisanego szkicu po zamknięciu lub odświeżeniu strony;
- zmiana trybu `Wyznacz plansze osobno`.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Definition of Done

- `Zakończ edycję` nie modyfikuje bieżących narożników;
- zachowany szkic nadal można porównać A/B, zapisać albo wznowić;
- nie można przypadkowo zatwierdzić automatu ani przejść do innej planszy przy
  niezapisanym szkicu;
- tylko jawny reset przywraca automat;
- testy Reviewera, lint, typecheck, format i build są zielone.

## Outcome

- `Zakończ edycję` wyłącza manipulowanie narożnikami bez przypisania
  `automaticCorners`; zmieniony albo częściowy szkic pozostaje aktywny.
- Panel A/B i zapis pozostają widoczne, a `Kontynuuj edycję` wraca do tego
  samego szkicu. Jawny `Resetuj do automatu` jest jedyną akcją odrzucającą
  zmianę.
- Niezapisany szkic utrzymuje blokadę skrótów zatwierdzenia i nawigacji,
  blokuje inne sloty oraz tryb całego źródła.
- Nie zmieniono API, geometrii, trwałych danych ani trybu
  `Wyznacz plansze osobno`.
- Weryfikacja:
  - `npm run test --workspace @game-predictor/reviewer` — 174 passed;
  - `npm run lint --workspace @game-predictor/reviewer` — passed;
  - `npm run typecheck --workspace @game-predictor/reviewer` — passed;
  - `npm run reviewer:build` — passed;
  - skoncentrowany Prettier — passed;
  - `git diff --check` — passed.
