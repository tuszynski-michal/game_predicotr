---
title: TASK-0567 — usunięcie starego selektora silników
status: done
last_updated: 2026-09-16
---

# TASK-0567 — usunięcie starego selektora silników

## Goal

Nowy panel importu oferuje tylko v1.0 i v1.1, a stary selektor v20/v2/v3 nie
pozostaje w kodzie ani aktualnie podawanym pakiecie Admina.

## Context

Po restarcie komputera operator nadal widział tekst starego selektora. Komponent
nie był już montowany przez bieżący panel, lecz nadal istniał w źródłach i w
starszym pakiecie developerskim.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Scope

- Usunąć martwy komponent oraz wyłącznie jego style i nieużywaną stałą.
- Poprawić testy Admina, zachowując etykiety historycznych jobów.
- Zweryfikować świeżą odpowiedź lokalnego serwera Admina.

## Out of scope

- Zmiana zapisanych polityk gry, historycznych jobów, API albo bazy danych.

## Acceptance criteria

- [x] Bieżący panel nie zawiera selektora v20/v2/v3.
- [x] Świeżo pobrany pakiet Admina zawiera v1.0/v1.1 i nie zawiera tekstu
  starego selektora.
- [x] Testy panelu, lint i kontrola typów przechodzą.

## Outcome

Usunięto komponent `BoardCellProcessingModePicker`, jego style i nieużywaną
stałą domyślnego v19. Lokalnie usunięto dwa wygenerowane pliki starego pakietu.
Świeże żądanie HTTP pobiera obecny pakiet z v1.0/v1.1 bez starego tekstu.
Testy Admina: 492/492; lint i typecheck: zaliczone. Istniejące dane i procesy
API/workera pozostały bez zmian.
