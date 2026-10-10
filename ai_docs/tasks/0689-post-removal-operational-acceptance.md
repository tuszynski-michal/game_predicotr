---
title: TASK-0689 — T10 — odbiór operacyjny po usunięciu legacy public
status: todo
last_updated: 2026-09-25
---

# TASK-0689 — T10 — odbiór operacyjny po usunięciu legacy `public`

## Status

`todo`

## Goal

Niezależnie potwierdzić, że aktywne gry, API, worker i trwały routing działają po 0125 wyłącznie na V2.

## Context

Zielony Alembic nie dowodzi braku ukrytego odczytu legacy; wymagany jest nowy proces i stan aktywnej bazy.

## Dependencies / entry conditions

T09 succeeded z pełnym postflightem. Błąd T09 lub brak dokładnego raportu blokuje ten task i etap D.

## Recommended execution

`gpt-6-astra`, reasoning `high`; niezależny review `gpt-6-sol`, reasoning `high`. Każdy P0–P2 lub odczyt `public` zatrzymuje plan bez tworzenia tabel powrotnych.

## Relevant docs

- `AGENTS.md`, plan D-448, T09 report
- `storage/game_storage_routing.py`, testy V2 lifecycle/routing i runbook

## Scope

- Read-only kontrola locations trzech aktywnych gier, manifestu/partycji V2 i braku 65 relacji public.
- Kontrolowany API/worker smoke z nowego procesu, obejmujący routing, katalog i reprezentatywny odczyt game-owned.
- Raport regresji, obserwowalności i stanu po restarcie.

## Out of scope

Zmiana danych, import, retry jobów, GC, automatyczny rollback i nowe feature.

## Acceptance criteria

- [ ] Wszystkie aktywne gry pozostają active/V2 generation 2 i ich partycje są dostępne.
- [ ] Żadna ścieżka smoke nie odczytuje/uszkadza public legacy; brak location nadal fail-closed.
- [ ] Odbiór z nowej sesji/procesu jest zapisany wraz z ryzykami.

## Technical notes

Smoke na produkcji pozostaje minimalny i bez zapisu, o ile operator nie udzieli osobnej zgody. Nie interpretować braku danych domenowych jako sukcesu: test weryfikuje routing i znane, bezpieczne metadane.

## Expected files

- Nowe: `ai_docs/quality/LEGACY_PUBLIC_STORE_POST_REMOVAL_ACCEPTANCE.md`.

## Test cases

- Trzy registered V2 games; restart/nowa transakcja; public relation absent; catalog/shared relations remain; missing registry → controlled failure.

## Verification

```powershell
# Zatwierdzone, ograniczone smoke z runbooka; timeout <= 120 s na proces.
```

## Risks / open questions

- Finding po produkcyjnym DDL wymaga nowej decyzji o naprawie, nie downgrade 0125.

## Outcome

Wypełnia agent po pracy.
