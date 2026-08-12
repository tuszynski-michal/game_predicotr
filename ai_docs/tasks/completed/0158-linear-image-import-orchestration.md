---
title: TASK-0158 — Linear image import orchestration
status: done
last_updated: 2026-08-04
---

# TASK-0158 — Linear image import orchestration

## Status

`done`

## Goal

Usunąć koszty pełnego pipeline'u `Import layoutów`, które rosną szybciej niż
liniowo wraz z liczbą zdjęć, bez zmiany geometrii, OCR, klasyfikacji symboli ani
wyników zapisanych dla pojedynczego pliku.

## Context

Audyt implementacji wykazał, że po każdym etapie każdego zdjęcia worker wykonuje
pełną agregację wszystkich plików joba. Dla `n` plików i stałych ośmiu etapów
daje to koszt zbliżony do `O(n²)`. Nowe pliki po `symbol_inference` są ponadto
rehydratowane w drugim przebiegu `waiting_for_review`, mimo że ich projekcja jest
już dostępna w pamięci bieżącego wykonania.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/tasks/0142-v02-owner-acceptance-regressions.md`

## Scope

- odczytać dokładne statystyki batcha raz na wejściu i raz na granicy końcowej,
- utrzymywać liczniki postępu przyrostowo z trwałych przejść statusów plików,
- nie wykonywać pełnej agregacji po każdym etapie,
- wykonać `manual_review` świeżego pliku bez ponownej rehydratacji projekcji,
- rehydratować wyłącznie pliki, które były w `waiting_for_review` przed bieżącym
  przebiegiem,
- zachować trwały checkpoint każdego zakończonego etapu, fencing, anulowanie,
  retry i izolację błędu pojedynczego pliku,
- dodać test ograniczający liczbę pełnych agregacji niezależnie od liczby etapów
  i plików.

## Out of scope

- zmiana adapterów obrazu, confidence, OCR lub modelu symboli,
- równoległe wykonywanie etapów i dodatkowy system kolejkowy,
- mikrobatching inferencji wielu zdjęć,
- zbiorczy zapis plansz i komórek; pozostaje kolejnym pionem po pomiarze tego
  usprawnienia,
- uruchomienie ciężkiego benchmarku podczas pracującego joba selekcji zdjęć.

## Acceptance criteria

- [x] Liczba wywołań pełnego `batch_stats` jest stała dla jednego wykonania
      handlera i nie zależy od liczby etapów ani zdjęć.
- [x] Postęp, liczba sukcesów, błędów i przypadków review wynikają z dokładnych
      przejść statusów pliku.
- [x] Każdy etap nadal jest zapisany przed publikacją postępu joba.
- [x] Świeży plik nie wykonuje ponownie `project_recognition` przed pierwszą
      granicą review.
- [x] Wznowienie istniejącego `waiting_for_review` nadal rehydratuje projekcję i
      przechodzi do walidacji po decyzji użytkownika.
- [x] Anulowanie i awaria po checkpointcie nie cofają trwałego postępu pliku.
- [x] Skupione testy workera, Ruff i kontrola typów zmienionego modułu przechodzą.

## Likely files

- `services/worker/src/game_predictor_worker/images/orchestration.py`
- `services/worker/tests/test_image_batch_orchestration.py`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/CURRENT_STATE.md`

## Assumptions

- statystyki odczytane na wejściu są stabilną bazą, ponieważ jeden job ma jeden
  aktywny lease workera,
- decyzje Reviewera mogą zmieniać projekcję, ale przejście pliku jest nadal
  serializowane przez lease i checkpoint stanu,
- fingerprint pipeline'u opisuje wyniki adapterów, więc optymalizacja samej
  orkiestracji nie wymaga zmiany fingerprintu.

## Outcome

- Pełna agregacja statystyk została ograniczona do dwóch wywołań na wykonanie
  handlera niezależnie od liczby plików i etapów.
- Liczniki pośrednie są aktualizowane z różnicy trwałych statusów poprzedniego i
  zapisanego wykonania pliku.
- Pre-existing review jest rehydratowane przed plikami processing; świeży plik
  kontynuuje do pierwszej kontroli manualnej bez powtórnej projekcji.
- `pytest` dla orkiestracji przeszedł 7/7, a skupiony zestaw pipeline'u,
  kontraktu i source ingestion 38/38.
- Ruff check i format check przeszły. Skupiony mypy z pominięciem znanych
  importów monorepo przeszedł; pełne śledzenie importów przekroczyło twardy limit
  60 sekund i zostało zakończone bez pozostawienia procesu.
- Nie uruchomiono ciężkiego benchmarku obrazów, aby nie konkurować z pracującym
  jobem selekcji 32 079 zdjęć.
