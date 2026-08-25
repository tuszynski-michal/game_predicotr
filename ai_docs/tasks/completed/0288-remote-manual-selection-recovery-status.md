---
title: TASK-0288 — Recovery, status i obserwowalność zdalnej selekcji
status: done
last_updated: 2026-08-24
---

# TASK-0288 — Recovery, status i obserwowalność zdalnej selekcji

## Status

`done`

## Goal

Zapewnić idempotentne wznowienie zdalnej ręcznej selekcji po restarcie oraz
jednoznaczną, zredagowaną diagnostykę stanu bez automatycznego usuwania danych.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- klasyfikacja crash-windowów i idempotentna bounded reconciliation,
- odzyskanie zweryfikowanego transferu oraz wygasłych kolejek po restarcie,
- status delta z licznikami kolejek/bajtów i heartbeat writer lease,
- zredagowane findings/audyt bez sekretów i ścieżek hosta,
- raport osieroconych artefaktów oraz host-only preview GC,
- polling z ograniczonym backoffem i diagnostyka Admina,
- fault-injection oraz testy skali i bezpieczeństwa.

## Out of scope

- automatyczne lub ręczne wykonanie destrukcyjnego GC,
- WebSocket/SSE i telemetryka chmurowa,
- rozszerzenia bramki bezpieczeństwa należące do TASK 17.

## Acceptance criteria

- [x] Restart nigdy nie potwierdza niezweryfikowanych bajtów.
- [x] Każdy znany półstan ma deterministyczny finding i ścieżkę recovery.
- [x] Powtórzony reconciler nie dubluje transferu, akcji ani wyniku.
- [x] Status rozróżnia pending/uploading/materializing/synced/conflict.
- [x] Publiczne DTO i logi nie ujawniają ścieżek, tokenów, kodów ani lease tokenu.
- [x] GC pozostaje wyłącznie bezpiecznym preview bez operacji delete.
- [x] Recovery działa po starcie nowego procesu API/workera.

## Outcome

Zaimplementowano bounded startup/worker reconciliation transferów i brakujących
akcji materializacji, status delta z kolejkami/bajtami/heartbeat, bezpieczny
polling z backoffem, diagnostykę Admina, redaction i agregatowy preview GC bez
delete. Fault-injection obejmuje exact verified, partial, conflicting verified,
brak pliku/akcji oraz powtórzony reconciler. Kontrakt OpenAPI i klient Admina są
zregenerowane. Nie dodano migracji ani TASK 17.
