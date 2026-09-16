---
title: TASK-0460 Board area masked registration
status: done
---

# TASK-0460 — Wariant dopasowania ograniczający wpływ tła

## Goal

Dodać nieaktywny domyślnie wariant rejestracji, który wyznacza cechy kotwicy
wyłącznie w otoczce dziewięciu ręcznie zweryfikowanych quadów.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- polityka `verified-page-registration-v2-board-area-mask-v1`;
- maska convex hull w przestrzeni obrazu 50% z paddingiem 10% mediany
  wysokości planszy;
- cache cech kotwic per budżet istniejącej instancji;
- testy maski, pochylenia, replay v1 oraz liczby przebiegów.

Poza zakresem są API wyboru i zmiana domyślnej polityki.

## Definition of Done

- cechy wzorca poza maską nie uczestniczą w dopasowaniu;
- target pozostaje analizowany w całości;
- budżety i liczba fallbacków nie rosną;
- v1 zachowuje dotychczasowy fingerprint i wynik;
- testy workera, Ruff i kontrola typów zmienionego modułu przechodzą.

## Outcome

- Dodano osobną politykę maskowanych cech kotwicy z convex hull pełnych 36
  narożników i paddingiem 10% mediany wysokości planszy.
- Target pozostaje bez maski; cache kotwic, trzy budżety i bramki końcowe są
  wspólne z v1. Payload v1 nie otrzymał nowych pól.
- Weryfikacja: 26 skoncentrowanych testów rejestracji i preflightu przeszło;
  obejmują maskę kotwicy, pełny target, metadane profilu i replay v1.
