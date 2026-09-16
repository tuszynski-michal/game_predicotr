---
title: TASK-0574 — Edytor podmienionego zdjęcia przed preflightem
status: done
last_updated: 2026-09-16
---

# TASK-0574 — Edytor podmienionego zdjęcia przed preflightem

## Goal

Po podmianie zdjęcia zachować operatora w korekcie geometrii nowego stagingu i
uruchamiać preflight dopiero po jego jawnym działaniu.

## Context

Dotychczasowy panel po podmianie automatycznie uruchamiał preflight i zastępował
edytor statycznym podglądem „geometria w przygotowaniu”. Po utracie odpowiedzi
panel mógł pozostać przy tym ekranie mimo ukończonego joba. Automatycznie
zarejestrowane podmienione zdjęcie nie pojawiało się ponadto w kolejce review.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Scope

- Edytor nowego zdjęcia przed preflightem i jawny start po zapisaniu korekty.
- Odtworzenie statusu joba i szkicu po odświeżeniu.
- Opcjonalna inspekcja automatycznie zarejestrowanego podmienionego zdjęcia do
  momentu rozpoczęcia importu.
- Zachowanie istniejącego zakazu podmiany po starcie importu.

## Out of scope

- Podmiana zdjęcia i zmiana geometrii w istniejącym stagingu użytkownika.
- Zmiana algorytmu v1.0/v1.1 lub wyników wykonanych jobów.

## Acceptance criteria

- [x] Nowa rewizja stagingu pokazuje edytor bez oczekiwania na preflight.
- [x] Zapis override jest związany z nową checksumą i poprzedza jawny start joba.
- [x] Po ukończeniu joba podmienione zdjęcie można otworzyć także po autoakceptacji.
- [x] Po rozpoczęciu importu API nie dołącza go do opcjonalnej inspekcji.
- [x] Podmiana, podgląd i szkic przetrwają odświeżenie panelu.

## Outcome

### Changed

- Panel edycji obsługuje szkic nowej rewizji bez manifestu preflightu; przycisk
  preflightu pozostaje oddzielny. Odtwarza też status istniejącego joba.
- Endpoint istniejącej kolejki korekty może dołączyć jedno wskazane źródło
  zarejestrowane automatycznie przed importem, bez zmiany licznika review.
- Frontend przypina podgląd do checksumy nowego stagingu i otwiera edytor po
  zakończeniu preflightu.

### Verification results

- API: 49 testów importu i ręcznych override'ów zaliczonych; endpoint z
  opcjonalną inspekcją sprawdzono dla źródła zarejestrowanego i po rozpoczęciu
  importu. Test istniejącego zapisu override przed preflightem ponownie działa
  po poprawieniu przestarzałego wywołania fabryki routera w fixture.
- Admin: 28 skoncentrowanych testów kontraktu paneli, kontrola typów, lint
  (bez błędów; jedno istniejące ostrzeżenie `<img>`) oraz build zaliczone.
- OpenAPI i wygenerowany klient: kontrola zgodności zaliczona.
- Nie wykonano podmiany ani zapisu geometrii w istniejącym stagingu użytkownika.

### Not completed

- Nie zmieniano danych żadnego istniejącego stagingu.

### Documentation updates

- Wymagania importu, architektura i `CURRENT_STATE.md`.

### Recommended next task

- Brak.
