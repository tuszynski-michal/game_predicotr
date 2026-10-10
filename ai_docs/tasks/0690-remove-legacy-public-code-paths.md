---
title: TASK-0690 — T11 — usunięcie nieosiągalnych ścieżek legacy public
status: todo
last_updated: 2026-09-25
---

# TASK-0690 — T11 — usunięcie nieosiągalnych ścieżek legacy `public`

## Status

`todo`

## Goal

Usunąć lub jednoznacznie odseparować pozostałe nieprodukcyjne symbole legacy po udowodnieniu operacyjnego V2-only.

## Context

Zmiany wcześniej byłyby ryzykowne; dopiero T10 dowodzi, że legacy public store jest fizycznie i operacyjnie nieosiągalny.

## Dependencies / entry conditions

T10 done i bez nierozwiązanych P0–P2. Należy ponownie przeprowadzić symbol/usage audit; wyłącznie martwy kod może być usunięty.

## Recommended execution

`gpt-6-sol`, reasoning `high`; niezależny review `gpt-6-astra`, reasoning `high`. Niejasny konsument blokuje usunięcie danego symbolu.

## Relevant docs

- `AGENTS.md`, plan D-448, T02/T03 audit, T10 acceptance
- `storage/game_storage_routing.py`, modele/fixtures, OpenAPI i testy

## Scope

- Usunąć nieosiągalne legacy identyfikatory, komentarze, test fixtures i dokumentację albo nadać adapterowi non-PostgreSQL precyzyjną nazwę/izolację.
- Zaktualizować testy i generated contract, jeśli ścieżka była eksponowana publicznie.

## Out of scope

Usuwanie historycznych migracji, manifestu v1, catalog/shared tables, testowego adaptera koniecznego do szybkich unitów oraz zmiana danych.

## Acceptance criteria

- [ ] Runtime PostgreSQL nie zawiera nieosiągalnego fallbacku legacy ani misleading API description.
- [ ] Adapter testowy nie może przypadkiem uruchomić się jako production PostgreSQL path.
- [ ] Pełne testy konsumentów zmienionego kontraktu przechodzą.

## Technical notes

Nie usuwać artefaktu tylko dlatego, że nazwa zawiera `legacy`. Historyczne migracje i audit reports pozostają historią. Każda usuwana ścieżka ma przed zmianą wynik usage audit.

## Expected files

- Istniejące: symbole ustalone przez audit w T02/T03/T10, ich testy i dokumentacja.

## Test cases

- Production PostgreSQL path bez legacy symbolu; unit adapter funkcjonuje tylko poza PostgreSQL; API/client nie ujawnia obsolete storage version.

## Verification

```powershell
# Focused tests konsumentów, lint/typecheck, potem wymagany szerszy suite; timeout <= 120 s na krok.
```

## Risks / open questions

- Usunięcie publicznego typu wymaga kompatybilnej, wygenerowanej aktualizacji klienta.

## Outcome

Wypełnia agent po pracy.
