---
title: TASK-0458 Page geometry rejection diagnostics
status: done
---

# TASK-0458 — Dokładna, niedroga diagnostyka odrzucenia

## Goal

Zapisać stabilną i ograniczoną diagnostykę przyczyny, dla której rejestracja
pełnej strony nie dostarczyła dziewięciu bezpiecznych quadów, bez dodatkowego
przebiegu ORB/RANSAC i bez zmiany decyzji algorytmu.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- wynik rejestracji rozróżniający sukces i zamknięte powody odrzucenia;
- ograniczone podsumowanie prób i najlepsza nieudana próba w manifeście;
- test każdej bramki oraz zachowania kompatybilnej metody `register()`;
- dokumentacja kontraktu diagnostycznego.

Poza zakresem są API/UI, nowy wariant dopasowania i zmiana aktywnych jobów.

## Definition of Done

- diagnostyka nie zwiększa liczby wywołań ORB/RANSAC;
- brak pomiaru nie jest serializowany jako zero;
- sukces i quady pozostają identyczne z dotychczasową ścieżką;
- retry może zapisać diagnostykę w istniejącym checkpointowanym manifeście;
- testy workera, lint i kontrola typów zmienionych modułów przechodzą.

## Outcome

- Dodano `PageRegistrationEvaluation` oraz stabilne reason codes dla kolejnych
  bramek dopasowania i finalizacji geometrii.
- Manifest preflightu zapisuje najlepszą nieudaną próbę oraz bounded summary
  bez dodatkowych wywołań ORB/RANSAC.
- Kompatybilna metoda `register()` zachowuje dotychczasowy kontrakt.
- Weryfikacja: 23 skoncentrowane testy oraz Ruff przeszły. Skupiony mypy
  bez pełnej ścieżki monorepo zgłosił brak importu pakietu API, a pełny i
  ponowiony wariant nie zwróciły wyniku w limicie 60 sekund i zostały
  przerwane bez pozostawienia nowego procesu.
