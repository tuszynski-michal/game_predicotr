---
title: Stabilize full Python test collection
status: done
last_updated: 2026-09-02
---

# TASK-0380 — Stabilizacja pełnego zestawu testów Python

## Goal

Usunąć dwa niezależne problemy widoczne dopiero podczas uruchomienia całego
zestawu testów.

## Scope

- unikalna nazwa modułu integracyjnego testu migracji półautomatu;
- jawny historyczny `legacy_file` w fixture projekcji wyszukiwania plansz;
- brak zmian kodu produkcyjnego i kontraktów.

## Outcome

Pytest nie myli już dwóch plików o tej samej nazwie. Fixture projekcji
deklaruje tryb assetu, który wcześniej był niejawnie zakładany przed
wprowadzeniem wirtualnej geometrii.

## Verification

- skoncentrowane testy obu modułów: pass;
- pełny zestaw Python: do ponowienia po zmianie.
