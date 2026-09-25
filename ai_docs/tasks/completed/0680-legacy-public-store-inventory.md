---
title: TASK-0680 — T01 — read-only inventory legacy public
status: done
last_updated: 2026-09-25
---

# TASK-0680 — T01 — read-only inventory legacy `public`

## Status

`done`

## Goal

Wytworzyć checksummowany, read-only raport dowodzący dokładnego zakresu legacy i warunków wejściowych dalszego planu.

## Context

Odczyt z 2026-09-25 wskazał 65 pustych kopii, ale nie może być podstawą późniejszego DDL.

## Dependencies / entry conditions

P00 done; dostęp do PostgreSQL wyłącznie read-only. Aktywna migracja, utracony dostęp, location nie-V2 lub jakakolwiek niepusta tabela kończy task jako `blocked`.

## Recommended execution

`gpt-6-sol`, reasoning `high`; niezależny review `gpt-6-astra`, reasoning `high`. Niepewny wynik katalogu lub manifestu wymaga eskalacji przed T02.

## Relevant docs

- `AGENTS.md`, `CURRENT_STATE.md`, plan D-448
- `architecture/DATA_MODEL.md`, `DECISION_LOG.md` (D-377, D-440)
- `storage/game_data_v2_manifest_v1.py::GAME_TABLES`

## Scope

- Porównać manifest v1 z relacjami `public`; dla każdej kandydatki zapisać OID, typ, właściciela, rozmiar, `count(*)`, FK/triggery/polityki i zależności.
- Odczytać wszystkie `game_storage_locations`, `game_storage_migrations`, Alembic head, aktywne jobs/maintenance i blokady istotne dla DDL.
- Wygenerować lokalny raport z czasem, połączeniem/DB fingerprintem, kanonicznym manifestem i SHA-256 bez sekretów.

## Out of scope

Jakikolwiek zapis, DDL, naprawa danych, migracja 0125 lub uruchamianie workera.

## Acceptance criteria

- [x] Raport rozróżnia dokładnie game-owned, catalog oraz shared/control i potwierdza pustość każdej z 65 relacji.
- [x] Zawiera stan location/migracji/jobs/locków i jest powtarzalny z nowej read-only sesji.
- [x] Wynik jest `ready`; mechanizm fail-closed raportuje blocker bez próby dalszej naprawy.

## Technical notes

Zapytania mają `default_transaction_read_only=on`, bounded statement/lock timeout i nie używają szacowania `reltuples` jako dowodu pustości. Raport nie zapisuje URI, haseł ani pełnych ścieżek assetów. Zależność z relacji spoza manifestu jest blockerem niezależnie od pustości tabeli.

## Expected files

- Nowe (proponowane): `scripts/audit_legacy_public_game_store.py`, `ai_docs/quality/LEGACY_PUBLIC_STORE_INVENTORY.md`.
- Istniejące: `.../game_data_v2_manifest_v1.py::GAME_TABLES`.

## Test cases

- Pusta relacja manifestu → `ready`; jedna niepusta → `blocked`; brak/nadmiar relacji albo FK spoza listy → `blocked`; location inna niż V2, migracja aktywna lub lock → `blocked`.

## Verification

```powershell
# Dokładna komenda powstaje w tasku; uruchomiona tylko na połączeniu read-only, timeout <= 120 s.
```

## Risks / open questions

- `count(*)` każdej relacji musi pozostać ograniczony timeoutem; timeout jest błędem, nie dowodem zera.

## Outcome

### Changed

- Dodano `scripts/audit_legacy_public_game_store.py`: bounded
  `REPEATABLE READ READ ONLY`, manifest-bound inventory, kontroli location,
  migracji, aktywnych jobów, FK/zależności i locków oraz atomowy raport JSON.
- Dodano 9 testów audytora i raport jakości z dowodem z lokalnej bazy.

### Verification results

- Raport `ready`, SHA-256
  `081212ac08ce63e132d689e7c23984e16338395e424695326579166fb4a6e95e`:
  65/65 pustych tabel, 3 active V2 locations, zero migracji, aktywnych jobs,
  zewnętrznych FK/zależności i locków. Druga świeża sesja dała identyczny wynik
  merytoryczny.
- `pytest services/api/tests/test_legacy_public_store_inventory.py` — 9/9;
  Ruff check/format — czyste.
- Mypy pełnego API wykrywa wcześniejsze, niezwiązane błędy importów API → worker;
  nie zmieniono ich w tym tasku.

### Not completed

- Nie wykonano DDL, DML, migracji 0125, zmian routingu ani operacji na danych.

### Documentation updates

- Dodano `ai_docs/quality/LEGACY_PUBLIC_STORE_INVENTORY.md` oraz raport JSON;
  zaktualizowano Current State.

### Recommended next task

- T02 / TASK-0681 — wyłącznie po jawnym poleceniu rozpoczęcia kolejnego taska.
