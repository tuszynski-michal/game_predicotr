---
title: TASK-0456 Page geometry preflight phase progress
status: done
last_updated: 2026-09-05
---

# TASK-0456 — Rzeczywisty progres preflightu geometrii stron

## Goal

Usunąć fałszywy stan `100%`, gdy preflight po pierwszym przebiegu nadal wykonuje
dodatkowe dopasowanie auto-anchorów, oraz pokazać operatorowi świeżość pracy
workera bez naruszania uruchomionych jobów.

## Scope

- trwały, cząstkowy checkpoint pierwszego przebiegu, każdego przebiegu
  auto-anchor oraz zapisu manifestu;
- osobny licznik fazy, niezależny od monotonicznych liczników całego joba;
- addytywne pola progresu w API i wygenerowanym kliencie;
- pasek fazy i polskie komunikaty w monitorze jobów;
- jawny komunikat `worker aktywny` albo ostrzeżenie o nieświeżym heartbeat;
- kompatybilny stan indeterminowany dla już uruchomionych i historycznych jobów
  bez nowych pól checkpointu.

## Out of scope

- restart, retry lub zmiana danych joba
  `abf57847-478f-4469-8e06-6f3ad0ab0d5b`;
- zmiana algorytmu rejestracji, progów, liczby auto-anchorów lub wyników
  geometrii;
- migracja Alembic i zmiana ogólnego kontraktu monotoniczności jobów.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Definition of Done

- dojście pierwszego przebiegu do `N/N` nie pokazuje zakończenia całego joba;
- dodatkowy przebieg zapisuje checkpoint co najwyżej co 25 ocenionych źródeł;
- UI pokazuje numer przebiegu oraz jego dokładny licznik i pasek;
- zapis manifestu ma osobny etap;
- historyczny checkpoint bez nowych pól pokazuje pasek indeterminowany i stan
  heartbeat zamiast fałszywego `100%`;
- zmiana nie restartuje ani nie modyfikuje bieżącego joba;
- testy workera, API, klienta i Admina są zielone.

## Outcome

- Worker zapisuje jawny `source_registration`, każdy przebieg
  `auto_anchor_retry`, `manifest_write` i `complete`. Ponowienie checkpointuje
  start, każdą partię 25 źródeł i koniec bez cofania wspólnych liczników.
- API udostępnia addytywne pola fazy, jej licznik, numer przebiegu oraz
  provisional review count. OpenAPI i klient TypeScript zostały zregenerowane.
- Monitor Admina preferuje dokładny pasek fazy i pokazuje świeżość heartbeat.
  Już uruchomiony lub historyczny checkpoint bez pól fazy otrzymuje pasek
  indeterminowany zamiast fałszywego `100%`.
- Nie restartowano usług i nie modyfikowano joba
  `abf57847-478f-4469-8e06-6f3ad0ab0d5b`. Zakończył się sam statusem
  `completed`: 2751 zarejestrowanych oraz 50 do review.

### Verification

- skoncentrowane testy workera i API: 38/38 passed;
- testy stanu i kontraktu monitora Admina: 19/19 passed;
- Ruff zmienionych modułów: passed;
- typecheck Admina: passed;
- OpenAPI i wygenerowany klient: current;
- produkcyjny build Admina: passed;
- lint zmienionych plików Admina: passed;
- pełny lint Admina nadal zatrzymują dwa wcześniejsze błędy
  `react-hooks/set-state-in-effect` w
  `geometry-guard-resolution-panel.tsx`;
- pełny mypy przekroczył limit 120 sekund; skoncentrowany przebieg nie wskazał
  błędu nowej serializacji, ale ujawnił wcześniejsze błędy w
  `image_reviews.py`, `virtual_grid_geometry_repository.py` oraz wcześniejszy
  błąd `Literal` w `schemas/jobs.py` poza zmienianym kontraktem.
