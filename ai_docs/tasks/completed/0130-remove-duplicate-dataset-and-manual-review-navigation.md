---
title: TASK-0130 Remove duplicate Dataset and Manual Review navigation
status: done
last_updated: 2026-08-01
---

# TASK-0130 — Remove duplicate Dataset and Manual Review navigation

## Status

`done`

## Goal

Usunąć z nawigacji Admina techniczny katalog datasetów i dawne wejście do
Manual Review, pozostawiając jeden przepływ `Import layoutów` oraz jedno wejście
`Zatwierdzanie plansz` do osobnej aplikacji Reviewer.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/VERSION_0_2_EXECUTION_PLAN.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- przestać renderować techniczny `DatasetCatalog` jako część interfejsu gry,
- zachować dataset, staging, walidację i raporty jako wewnętrzne mechanizmy,
- zachować wyłącznie sekcję `Zatwierdzanie plansz` prowadzącą do Reviewera,
- odrzucać stare wartości URL próbujące otworzyć `datasets` lub
  `manual-review`,
- nie usuwać encji domenowych, endpointów, audytu ani historii decyzji.

## Expected files

- `apps/admin/src/features/catalog/catalog-workspace.tsx`
- testy kontraktu workspace'u i stanu nawigacji Admina,
- dokumentacja bieżącego stanu.

## Acceptance criteria

- [x] `Import layoutów` nie renderuje osobnego katalogu Dataset,
- [x] Admin nie udostępnia drugiego ekranu wykonującego decyzje review,
- [x] stare wartości URL nie przywracają usuniętych wejść,
- [x] backendowe encje, endpointy i audyt pozostają bez zmian,
- [x] testy, lint, typecheck i build Admina przechodzą.

## Outcome

Sekcja `Import layoutów` renderuje teraz wyłącznie właściwy workflow importu
zdjęć, postępu i kompletności. Techniczny `DatasetCatalog` nie jest importowany
ani montowany w głównym workspace, ale backendowe wersje datasetu, walidacja,
endpointy i ich użycie przez payout oraz wydania pozostają bez zmian.

Jedynym wejściem użytkownika do decyzji review jest `Zatwierdzanie plansz`,
które otwiera osobną aplikację Reviewer. Parser nawigacji nadal przyjmuje tylko
cztery zatwierdzone sekcje i test regresyjny potwierdza, że stare wartości
`datasets` oraz `manual-review` nie mogą zostać odtworzone z URL.

Weryfikacja: 112 testów Admina, ESLint, TypeScript oraz produkcyjny build Next.js
przeszły. API, schema bazy, dane oraz audyt nie były zmieniane.
