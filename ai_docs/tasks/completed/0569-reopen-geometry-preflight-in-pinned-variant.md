---
title: TASK-0569 — zachowanie wariantu ukończonego preflightu
status: done
last_updated: 2026-09-16
---

# TASK-0569 — zachowanie wariantu ukończonego preflightu

## Goal

Ponowne otwarcie i odświeżenie stagingu z ukończonym preflightem v1.1 nie
przełącza go na v1.0 ani nie tworzy kolejnego joba.

## Context

Staging `200575 - 222912 cut` ukończył preflight v1.1, ale ponowne otwarcie
raportu użyło domyślnego v1.0 i pozwoliło utworzyć drugi job. Odświeżanie listy
jobów dodatkowo resetowało wariant w panelu.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Scope

- Odtworzyć wariant ukończonego preflightu z listy jobów powiązanych ze stagingiem
  i sumą manifestu źródeł.
- Zachować wybrany wariant podczas odświeżania statusu; istniejący preflight
  odświeżać odczytowo.
- Dodać test regresyjny dla ukończonego v1.1 oraz późniejszego joba v1.0.

## Out of scope

- Zmiany algorytmu geometrii, manifestów i polityki backendu.

## Acceptance criteria

- [x] Ukończony v1.1 pozostaje v1.1 po ponownym otwarciu raportu.
- [x] Odświeżenie istniejącego preflightu nie tworzy joba.
- [x] Nowy staging bez preflightu zachowuje domyślne v1.0.
- [x] Ukończony job v1.1 i jego dane pozostają bez zmian.

## Outcome

Panel dobiera wariant ukończonego joba dla tego samego stagingu i manifestu,
nie resetuje wariantu przy pobieraniu listy i odświeża istniejący preflight
odczytowo. Drugi job v1.0 anulowano przy 0/2482. Testy Admina 493/493,
typecheck i lint przeszły. Nie uruchomiono nowego joba ani builda produkcyjnego.
