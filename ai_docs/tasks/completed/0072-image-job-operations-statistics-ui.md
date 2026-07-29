---
title: Image job operations and statistics UI
status: done
last_updated: 2026-07-29
---

# TASK-0072 — Image job operations and statistics UI

## Status

`done`

## Goal

Udostępnić operatorowi trwały, bezpieczny podgląd image import joba oraz
selektywny retry uszkodzonego pliku bez czytania logów i bez duplikowania
wyników M7.2.

## Context

Ogólny ekran Jobs obsługuje polling, filtry, cancel i retry całego joba.
TASK-0071 dodał job-local workflow pliku i atomowy retry dokładnego
`nextStage`, ale brakuje publicznego kontraktu odczytu statystyk/plików oraz
operacji w panelu. Obecny `JobResponse` nie serializuje jeszcze payloadu
`image_directory`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_07_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- jawny response payload dla joba `import_kind = image_directory`,
- endpoint szczegółów image joba z aggregate correct/error/review/waiting,
  licznikami per etap, czasem i throughput,
- bounded lista plików z kolejnością, stanem, `nextStage`, błędem i retry count,
- endpoint retry jednego failed file z wymaganym `expectedStage`,
- atomowe wyczyszczenie błędu pliku i wznowienie tego samego joba, gdy jest
  zatrzymany,
- rozszerzenie istniejącej karty Jobs o szczegóły image importu i akcję retry
  pliku,
- loading/empty/error, ręczne odświeżenie oraz brak podwójnego submitu,
- OpenAPI i wygenerowany klient TypeScript,
- testy serwisu/API, logiki UI i kontraktu.

## Out of scope

- retencja, usuwanie i eksport diagnostyczny — TASK-0073,
- uruchamianie benchmarku lub kolejka — TASK-0074–TASK-0075,
- edycja review planszy,
- publikacja datasetu i APK,
- automatyczny retry bez decyzji operatora.

## Acceptance criteria

- [x] image-directory job jest poprawnie zwracany przez list/detail Jobs,
- [x] panel pokazuje trwałe liczniki i etap bez czytania logów,
- [x] czas i throughput mają jawny, testowalny sposób obliczania,
- [x] lista plików jest bounded i deterministyczna,
- [x] retry wymaga dokładnego failed `nextStage`,
- [x] retry zachowuje file key, stage results i wcześniejszy checkpoint,
- [x] retry nie tworzy nowego joba i bezpiecznie wznawia zatrzymany rekord,
- [x] UI obsługuje loading/empty/error oraz blokuje podwójny submit,
- [x] cancel nadal używa istniejącego wspólnego automatu jobs,
- [x] OpenAPI i klient nie utrzymują ręcznie rozbieżnych typów.

## Expected files

- `services/api/src/game_predictor_api/schemas/jobs.py`
- `services/api/src/game_predictor_api/application/image_jobs.py`
- `services/api/src/game_predictor_api/storage/image_job_repository.py`
- `services/api/src/game_predictor_api/api/image_jobs.py`
- wiring FastAPI/router
- `packages/admin-api-client/src/generated/*`
- `apps/admin/src/features/jobs/*`
- focused API/admin tests
- dokumentacja i Current State

## Verification

Wszystkie komendy otrzymują jawny timeout. PostgreSQL pozostaje testem opt-in;
logika agregacji i retry musi mieć testy bez sieci, a migracja nie jest
potrzebna, jeżeli model z TASK-0071 jest wystarczający.

## Risks / open questions

- rejestracja i konfiguracja produkcyjnych adapterów workera nie są częścią
  panelu operacyjnego,
- przy wielu failed files operator może ponowić je kolejno; jeden retry nie
  ukrywa pozostałych błędów.

## Outcome

- Dodano jawny `ImageImportJobPayload`, endpoint operations i retry dokładnego
  pliku oraz repozytorium agregujące trwałe statystyki i etapy.
- Retry blokuje job/powiązanie, wymaga zgodnego failed `nextStage`, zachowuje
  wcześniejsze checkpointy i wznawia ten sam rekord joba.
- Istniejąca karta Jobs otrzymała rozwijane szczegóły image importu,
  czas/throughput, stage counts, bounded tabelę plików i selektywny retry.
- OpenAPI i generowany klient TypeScript zostały zsynchronizowane.
- Przeszły: 19 focused testów API, 76 testów panelu, 13 testów klienta,
  TypeScript obu pakietów, ESLint zmienionego UI, Ruff, focused mypy i check
  wygenerowanego klienta.
- Dwa testy integracyjne PostgreSQL są gotowe, ale pozostały jawnym skipem,
  ponieważ wymagają `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1` oraz lokalnej bazy.
