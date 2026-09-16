---
title: TASK-0565 — Usunięcie starego startu importu zdjęć
status: done
last_updated: 2026-09-16
---

# TASK-0565 — Usunięcie starego startu importu zdjęć

## Goal

Panel i publiczne API nie mogą utworzyć nowego joba importu przez stary token folderu bez preflightu; import przez browser staging v1.0/v1.1 działa dalej.

## Context

Po TASK-0562 pozostawiono stary `POST /api/v1/admin/image-imports`, choć użytkownik korzysta wyłącznie z nowego workflow i polecił usunięcie starej ścieżki.

## Recommended execution

`gpt-6-astra high`; dodatkowa kontrola kontraktu OpenAPI oraz zachowania historycznych jobów przed commitem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Usunięcie legacy folder picker, startu i tokenowego preflightu z publicznego API oraz niewykorzystywanej ścieżki aplikacyjnej.
- Usunięcie fallbacku startu w panelu i jego ręcznego wrappera klienta.
- Aktualizacja OpenAPI, wygenerowanego klienta, testów i dokumentacji.

## Out of scope

- Kasowanie historycznych jobów, manifestów albo stagingów.
- Zmiana osobnych workflowów selekcji zdjęć, ich handoffu oraz odczytu/retry zapisanych importów.

## Acceptance criteria

- [x] Publiczne legacy operacje nie istnieją w OpenAPI ani panelu i nie tworzą joba.
- [x] Import nowego stagingu v1.0/v1.1 i odczyt starych jobów pozostają dostępne.
- [x] Skoncentrowane testy API, klienta i panelu, lint, typy, OpenAPI i build przechodzą.

## Outcome

Usunięto trzy stare trasy API i niewykorzystywaną metodę tworzącą job z tokenu
folderu. Panel uruchamia nowy import wyłącznie z gotowego stagingu. OpenAPI i
klient TypeScript zostały ponownie wygenerowane. Zachowano osobny wybór folderu
dla selekcji zdjęć, historię jobów i ponowne przetwarzanie z oryginałów.

Weryfikacja: 37 testów API importu, 26 testów API selekcji, 51 testów klienta
oraz 41 testów panelu przeszły. Przeszły także Ruff, mypy dla 429 plików
źródłowych API/workera, lint i typecheck panelu, kontrola OpenAPI oraz
produkcyjny build panelu. W dodatkowym teście historycznego reprocessingu
`test_old_preflight_requires_explicit_preparation_not_upload` pozostał
niezwiązany błąd istniejącego kontraktu: test oczekuje
`IMAGE_LATERAL_PARTIAL_PREFLIGHT_REQUIRED`, a niezmieniony `JobService` zwraca
`IMAGE_LATERAL_PARTIAL_SNAPSHOT_INVALID`. Pozostałe 39 testów z tego
dodatkowego przebiegu przeszły.

Nie usuwano danych ani nie uruchamiano nowych jobów. Istniejące procesy usług
mogą wymagać kontrolowanego restartu do załadowania nowego kodu.
