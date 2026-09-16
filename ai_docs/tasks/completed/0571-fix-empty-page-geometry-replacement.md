---
title: TASK-0571 — otwarcie korekty geometrii bez wczytanego źródła
status: done
last_updated: 2026-09-16
---

# TASK-0571 — otwarcie korekty geometrii bez wczytanego źródła

## Goal

Panel korekty geometrii otwiera się bez błędu, gdy lista źródeł jest pusta lub
jeszcze się ładuje.

## Context

W TASK-0570 porównanie oczekującej podmiany korzysta z opcjonalnego odczytu
checksumy źródła, po czym bez osłony odczytuje jego ścieżkę. Początkowo
`source === null`, więc render przerywa się przed pokazaniem stanu ładowania.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Scope

- Bezpieczne porównanie zapisanej podmiany z aktualnym źródłem.
- Test regresyjny dla pustego źródła i dopasowanego źródła.
- Bez zmian API, danych i workflow jobów.

## Acceptance criteria

- [x] Render bez źródła nie odczytuje jego pól i nie rzuca wyjątku.
- [x] Dopasowana podmiana pozostaje dostępna do odzyskania.
- [x] Testy panelu, lint, typecheck i build przechodzą.

## Outcome

Warunek porównania przeniesiono do sprawdzanej funkcji, która odrzuca
`null`, dane niepasujące do zdjęcia i niepoprawną checksumę. Panel stosuje ją
zarówno do stanu bieżącego, jak i danych z pamięci przeglądarki.

Weryfikacja: 4 testy skoncentrowane, pełny zestaw testów Admina, lint,
typecheck i produkcyjny build. Nie zmieniono danych użytkownika ani nie
przerywano działającego joba.
