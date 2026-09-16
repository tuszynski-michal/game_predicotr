---
title: TASK-0443 — Odblokowanie zapisu poprawionej siatki
status: done
---

# TASK-0443 — Odblokowanie zapisu poprawionej siatki

## Status

`done`

## Goal

Aktualny podgląd A/B poprawionej pojedynczej siatki ma odblokować jej trwały
zapis w lokalnym Reviewerze.

## Context

Po zmianie geometrii podgląd zapisywał klucz samych narożników, podczas gdy
bramka zapisu porównywała go z kluczem szkicu zawierającym identyfikator
planszy. Niezgodne formaty klucza utrzymywały przycisk zapisu w stanie
nieaktywnym mimo aktualnego podglądu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Ujednolicić klucz wygenerowanego podglądu z kluczem używanym przez bramkę
  zapisu.
- Dodać test regresyjny kontraktu Reviewera.
- Zachować wymaganie aktualnego podglądu A/B przed zapisem.

## Out of scope

- Zmiana API, geometrii, danych gry albo istniejących rewizji.
- Automatyczny zapis po samym kliknięciu `Zakończ edycję`.

## Acceptance criteria

- [x] Podgląd wygenerowany dla bieżącego szkicu odblokowuje zapis.
- [x] Każda kolejna zmiana szkicu ponownie blokuje zapis do odświeżenia A/B.
- [x] Klucz nadal obejmuje identyfikator planszy, a w trybie źródłowym cały
      komplet szkiców.
- [x] Testy, lint, typecheck i build Reviewera przechodzą.

## Technical notes

Żądanie preview nadal porównuje osobno same narożniki z geometrią automatyczną,
aby nie wykonywać drugiego renderu dla identycznego obrazu. Tylko klucz
ważności podglądu korzysta z pełnego `draftKey`.

## Expected files

- `apps/reviewer/src/features/grid-reviews/grid-review-editor.tsx`
- `apps/reviewer/test/grid-review-workspace-contract.test.mjs`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/tasks/0443-grid-review-preview-key.md`

## Verification

```powershell
npm run test --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run build --workspace @game-predictor/reviewer
```

## Risks / open questions

- Brak. Zmiana nie modyfikuje kontraktu zapisu ani danych.

## Outcome

Wypełnia agent po pracy.

### Changed

- Klucz ważności podglądu A/B korzysta z pełnego `draftKey`, identycznego z
  bramką zapisu.
- Porównanie geometrii z automatem nadal korzysta wyłącznie z narożników, więc
  nie wykonuje zbędnego drugiego renderu.
- Dodano test regresyjny wykrywający ponowne pomieszanie obu formatów klucza.

### Verification results

- `npm run test --workspace @game-predictor/reviewer` — 174 testy, 174 passed.
- `npm run lint --workspace @game-predictor/reviewer` — passed.
- `npm run typecheck --workspace @game-predictor/reviewer` — passed.
- `npm run build --workspace @game-predictor/reviewer` — passed.

### Not completed

- Nie zmieniano API, backendu, geometrii ani danych operatorskich.

### Documentation updates

- Zaktualizowano `CURRENT_STATE.md`. Wymagania i D-329 pozostają bez zmian.

### Recommended next task

- Brak. Po odświeżeniu Reviewera wykonać ręczny smoke test jednej siatki.
