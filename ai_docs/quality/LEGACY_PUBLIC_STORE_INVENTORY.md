---
title: Legacy public game-store inventory
status: accepted
last_updated: 2026-09-25
---

# Read-only inventory legacy `public` — TASK-0680

## Wynik

**Ready.** Dwa niezależne odczyty w nowych transakcjach `REPEATABLE READ READ ONLY`
dały identyczny wynik merytoryczny (z pominięciem czasu odczytu). Raport końcowy
ma SHA-256 `081212ac08ce63e132d689e7c23984e16338395e424695326579166fb4a6e95e`.
Jest zapisany w `LEGACY_PUBLIC_STORE_INVENTORY_2026-09-25.json`; nie zawiera
URI, haseł ani ścieżek assetów.

## Stan zaobserwowany

| Kontrola | Wynik |
|---|---:|
| Alembic | `0124_game_data_v2_partial_visibility_constraints` |
| Transakcja audytu | `transaction_read_only = on` |
| Relacje manifestu v1 | 65 istnieje, 65 ma `rowCount = 0` |
| Zewnętrzne FK / relacje zależne | 0 / 0 |
| Location | 3, wszystkie `game_data_v2` / gen. 2 / `active` / manifest v1 |
| `game_storage_migrations` | 0 |
| Aktywne joby (`created`, `processing`) | 0 |
| Zewnętrzne locki na 65 relacjach | 0 |

W katalogu pozostaje 202 triggerów należących do 65 historycznych tabel; są
raportowane, ale nie są zewnętrzną zależnością: PostgreSQL usuwa je razem z
właścicielem tabeli. Audyt ignoruje także własne indeksy i TOAST; sprawdza
osobno zewnętrzne FK oraz tabele, widoki, widoki zmaterializowane, foreign i
partitioned relations zależne od relacji legacy.

## Granice dowodu

Raport jest dowodem dla STOP A z chwili odczytu, nie zgodą na DDL. T09 ponowi
ten sam preflight bezpośrednio przed 0125 i nadal wymaga osobnego potwierdzenia
użytkownika. Nie wykonano DDL, DML, migracji, importu, GC ani zmian danych.

## Weryfikacja implementacji

- `pytest services/api/tests/test_legacy_public_store_inventory.py` — 9/9.
- Ruff check i format nowych plików — czyste.
- Mypy pełnego API pozostaje zablokowany przez wcześniejsze, niezwiązane błędy
  importów API → worker; nowy skrypt nie dodał findingu po uruchomieniu obu
  źródłowych katalogów na ścieżce mypy.
