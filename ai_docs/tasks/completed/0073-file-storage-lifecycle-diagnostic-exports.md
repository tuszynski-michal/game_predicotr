---
title: File storage lifecycle and diagnostic exports
status: done
last_updated: 2026-07-29
---

# TASK-0073 — File storage lifecycle and diagnostic exports

## Status

`done`

## Goal

Udostępnić administratorowi bezpieczny inwentarz wersjonowanego storage M7
oraz niezmienny eksport diagnostyczny błędów image joba bez automatycznego
usuwania danych i bez ujawniania ścieżek absolutnych.

## Context

TASK-0072 udostępnia statystyki i selektywny retry pliku, ale nie definiuje
jeszcze jednego zarządzanego układu `originals/working/crops/training/models/
exports`, jawnej polityki retencji ani checksumowanego artefaktu błędów.
Wymagania zabraniają dużych binariów w PostgreSQL oraz destrukcji oryginałów
i zaakceptowanych wersji bez jawnej operacji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_07_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- jeden zarządzany root `<artifact-root>/data` i sześć dozwolonych przestrzeni:
  `originals`, `working`, `crops`, `training`, `models`, `exports`,
- read-only inwentarz plików/bajtów z jawną polityką każdej przestrzeni oraz
  `automaticDeletion = false`,
- brak endpointu kasowania w TASK-0073; kontrola retencji oznacza widoczność,
  klasyfikację i jawny zakaz automatycznej destrukcji,
- deterministyczny manifest `image-job-diagnostics-v1` z aggregate joba
  i bounded, uporządkowaną próbką failed files,
- eksport wyłącznie stabilnych kodów, bezpiecznych opisów, względnych ścieżek
  POSIX, etapów i retry count; bez obrazów, sekretów, stack trace i ścieżek
  absolutnych,
- content-addressed zapis pod
  `data/exports/image-jobs/<jobId>/<sha256>/diagnostics.json`,
- idempotentne tworzenie, lista historycznych wersji oraz checksum-verified
  pobranie,
- rozszerzenie szczegółów image joba w panelu o storage policy, utworzenie,
  listę i pobranie eksportów,
- OpenAPI, wygenerowany klient i testy backend/UI.

## Out of scope

- fizyczne usuwanie plików i garbage collection,
- przenoszenie historycznych artefaktów M5–M6 do nowego rootu,
- dołączanie binarnych obrazów lub modeli do eksportu,
- ZIP, wysyłka sieciowa albo cloud/object storage,
- benchmark rozmiaru i przepustowości — TASK-0074,
- publikacja datasetu i APK — TASK-0076–TASK-0077.

## Acceptance criteria

- [x] inwentarz nie wychodzi poza zarządzany root i nie podąża za symlinkiem,
- [x] wszystkie przestrzenie mają jawny policy i wyłączone auto-delete,
- [x] originals i models są jawnie chronione,
- [x] eksport ma deterministyczne bajty, SHA-256 i wersjonowaną ścieżkę,
- [x] exact retry tego samego stanu nie tworzy odmiennych bajtów,
- [x] eksport zawiera dokładne aggregate i jawną informację o obcięciu próbki,
- [x] eksport nie zawiera ścieżek absolutnych, binariów ani danych technicznych
  spoza publicznego kontraktu błędu,
- [x] pobranie ponownie weryfikuje ścieżkę i checksumę,
- [x] UI ma loading/empty/error, blokuje podwójny submit i używa klienta
  generowanego z OpenAPI,
- [x] żadna operacja TASK-0073 nie usuwa pliku.

## Expected files

- nowy application/file-storage moduł API,
- rozszerzenie repozytorium image joba o snapshot diagnostyczny,
- router/schema image storage i image diagnostic exports,
- wiring `main.py` i OpenAPI,
- `packages/admin-api-client`,
- `apps/admin/src/features/jobs/*`,
- focused API/admin/client tests,
- dokumentacja architektury, Decision Log i Current State.

## Verification

Każda komenda ma jawny timeout. Testy plikowe używają wyłącznie katalogów
tymczasowych. Fizyczny PostgreSQL pozostaje testem opt-in; logika serializacji,
bezpiecznych ścieżek, checksum i UI musi przejść bez sieci.

## Assumptions

- zarządzany M7 root jest podkatalogiem `data` istniejącego
  `GAME_PREDICTOR_ARTIFACT_ROOT`,
- brak usuwania jest bezpieczniejszą realizacją pierwszej kontroli retencji;
  przyszła jawna destrukcja wymaga osobnego zadania i decyzji.

## Outcome

Utworzono `ImageArtifactStore` ograniczony do `<artifact-root>/data`, który
raportuje sześć jawnych przestrzeni i pomija symlinki bez oferowania delete/GC.
`ImageStorageService` buduje z trwałego stanu joba kanoniczny, ograniczony
manifest `image-job-diagnostics-v1`, publikuje go bez nadpisania pod ścieżką
content-addressed i weryfikuje pełny SHA-256 podczas listowania oraz pobierania.
Nie dodano migracji ani tabeli eksportów.

Admin API ma endpoint inwentarza oraz create/list/download eksportów. OpenAPI,
wygenerowany klient TypeScript i ekran Jobs są zsynchronizowane. Panel pokazuje
politykę bez automatycznego usuwania, zajętość przestrzeni, historyczne eksporty,
znacznik obcięcia i pobiera dokładne bajty jako `Blob`.

Weryfikacja:

- Ruff format/check: passed,
- focused mypy: passed,
- focused API: 22 passed, 1 skipped; pełne API: 182 passed, 16 skipped,
- skipy pełnego API obejmują wyłączone testy PostgreSQL oraz dwa testy
  symlinków niemożliwe bez uprawnienia bieżącego konta Windows,
- admin UI: 77 passed i typecheck passed,
- admin API client: 14 passed, build/typecheck passed,
- OpenAPI export/generation oraz ESLint panelu: passed.

Fizyczny test PostgreSQL pozostał opt-in i nie był wymagany do zmiany schematu,
ponieważ TASK-0073 nie dodaje migracji. Wydajność pełnego inwentarza oraz dużego
eksportu jest świadomie zakresem TASK-0074.
