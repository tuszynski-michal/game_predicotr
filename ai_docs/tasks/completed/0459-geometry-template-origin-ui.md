---
title: TASK-0459 Geometry template origin UI
status: done
---

# TASK-0459 — Czytelny ekran nieudanej geometrii

## Goal

Rozróżnić automatyczną geometrię, ręczny zapis i roboczy szablon edytora oraz
pokazać zapisaną diagnostykę bez uruchamiania nowych obliczeń.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- kompatybilne rozszerzenie istniejącego endpointu review sources;
- OpenAPI, klient generowany i wrapper;
- banner pochodzenia, krótki powód i rozwijane szczegóły w Adminie;
- regresje historycznego manifestu i zapisu ręcznych quadów.

## Definition of Done

- szablon nie jest przedstawiany ani zapisywany jako geometria automatyczna;
- historyczny manifest bez diagnostyki nadal działa;
- odczyt szczegółów nie uruchamia workera;
- testy API/Admin, lint, typecheck, OpenAPI i build zmienionego pionu przechodzą.

## Outcome

- Rozszerzono istniejący read model o pochodzenie geometrii, reason code i
  opcjonalną diagnostykę oraz zregenerowano OpenAPI i klienta.
- Admin pokazuje jawny banner szablonu, zwięzły powód i rozwijane metryki.
  Ręczny zapis nadal wygrywa i jest dokładnym celem resetu.
- Weryfikacja: 29 testów API, 5 testów kontraktu UI, Ruff, OpenAPI check,
  typecheck Admina i produkcyjny build przeszły. Pełny lint Admina pozostaje
  czerwony na dwóch wcześniejszych błędach `react-hooks/set-state-in-effect`
  w niezwiązanym `geometry-guard-resolution-panel.tsx`.
