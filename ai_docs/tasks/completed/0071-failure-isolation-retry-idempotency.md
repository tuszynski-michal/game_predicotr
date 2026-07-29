---
title: Failure isolation, retry and idempotency
status: done
last_updated: 2026-07-29
---

# TASK-0071 — Failure isolation, retry and idempotency

## Status

`done`

## Goal

Domknąć M7.2 przez trwałą izolację błędu pojedynczego źródła, bezpieczny retry
od ostatniego checkpointu, rehydratację współdzielonych wyników i skierowanie
konfliktów numeracji do review bez cichej zmiany sekwencji.

## Context

TASK-0070 zapisuje niezmienne wyniki etapów i projekcje source/board/cell/review
oraz materializuje staging dopiero po decyzji planszy. Obecny
`ImageBatchHandler` nadal pozwala wyjątkowi adaptera zakończyć cały job, a
completed execution współdzielone z innym jobem nie odtwarza jeszcze jego
job-local projekcji. Walidacja ciągłości zwraca błąd zamiast ponownie otworzyć
konkretne plansze do review.

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

- trwały `failed_stage`, stabilny kod, bezpieczny opis, licznik retry i czas
  ostatniego błędu per `image_file_execution`,
- przechwycenie kontrolowanego i nieoczekiwanego wyjątku jednego etapu bez
  zatrzymania diagnostyki pozostałych plików,
- job przechodzi do `waiting_for_review` po pełnym przebiegu, jeżeli zawiera
  failed files albo nierozwiązane review,
- jawny retry pojedynczego pliku od nieukończonego etapu, bez usuwania
  wcześniejszych niezmiennych wyników,
- retry konkretnego etapu wyłącznie wtedy, gdy jest dokładnie `nextStage`,
- rehydratacja source/board/cell/review dla joba korzystającego z globalnego
  completed lub waiting execution,
- append-only decyzje operacyjnego review i idempotency key,
- konflikt OCR/zaakceptowanych numerów usuwa wyłącznie nieopublikowany staging
  konfliktujących plansz i ponownie kieruje je do review,
- testy izolacji, kontynuacji, retry, reuse, model drift i braku duplikatów.

## Out of scope

- panel operacyjny i publiczne endpointy retry — TASK-0072,
- eksport diagnostyczny i lifecycle storage — TASK-0073,
- masowy benchmark i decyzja o kolejce — TASK-0074–TASK-0075,
- publikacja datasetu, payout, SQLite i APK,
- auto-accept, auto-reject oraz retraining.

## Acceptance criteria

- [x] wyjątek jednego adaptera zapisuje stabilny błąd oraz dokładny failed stage,
- [x] pozostałe pliki kończą swój przebieg mimo pojedynczego błędu,
- [x] retry wznawia ten sam file execution od nieukończonego etapu,
- [x] retry etapu wcześniejszego lub późniejszego jest odrzucany,
- [x] istniejące stage results, boards, cells, review i staging nie są
  duplikowane,
- [x] completed execution użyte w nowym jobie odtwarza job-local provenance bez
  ponownej inferencji,
- [x] konflikt numeru otwiera właściwe plansze do review i nie przesuwa
  pozostałych sekwencji,
- [x] decyzje review są append-only i exact retry jest idempotentny,
- [x] G7.2 przechodzi bez Redis/Celery i bez publikacji danych.

## Technical notes

- checkpoint pozostaje ostatnim poprawnym uporządkowanym prefiksem; status
  `failed` jest przechowywany w rekordzie execution, nie w kontrakcie
  checkpointu,
- nieoczekiwany wyjątek otrzymuje ogólny kod bez wycieku ścieżki absolutnej,
  stack trace ani treści modelu,
- retry czyści tylko pola błędu/status wykonania i nie usuwa niezmiennych
  stage results,
- ponowne review zwiększa revision i zachowuje wcześniejszą decyzję jako event.

## Expected files

- `services/api/alembic/versions/0018_image_failure_retry.py`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/worker/src/game_predictor_worker/images/orchestration.py`
- `services/worker/src/game_predictor_worker/images/orchestration_store.py`
- `services/worker/src/game_predictor_worker/images/pipeline_execution.py`
- `services/worker/src/game_predictor_worker/images/pipeline_store.py`
- focused worker/API/migration tests
- dokumentacja architektury, danych, testów i Current State

## Verification

Każda komenda otrzyma jawny timeout. Fizyczny PostgreSQL pozostaje testem
opt-in, a offline migration test jest obowiązkowy.

## Risks / open questions

- publiczne API retry jest celowo późniejsze; TASK-0071 dostarcza atomowe
  metody application/store, które UI wywoła w TASK-0072,
- globalny execution może być współdzielony tylko dla identycznego
  `pipelineFingerprint`; model drift zawsze pozostaje osobnym wynikiem.

## Outcome

- migracja `0018_image_failure_retry` dodaje trwałe błędy, retry metadata,
  job-local workflow checkpoint/status i append-only
  `image_review_resolution_events`,
- `ImageBatchHandler` izoluje kontrolowany i nieoczekiwany wyjątek jednego
  pliku, kontynuuje batch i przechodzi do review po pełnej diagnostyce,
- `retry_file` zachowuje ostatni poprawny checkpoint i immutable stage results,
  a inny etap niż `nextStage` kończy stabilnym błędem,
- globalne stage results rehydratują source/board/cell/review nowego joba bez
  ponownego wywołania adapterów; decyzja pozostaje job-local,
- continuity otwiera plansze konfliktujące do review, dopisuje event i usuwa
  tylko ich nieopublikowany staging,
- przeszło 34 focused testów M7.2, 176 testów API i 411 testów workera; Ruff
  oraz focused mypy przeszły,
- fizyczny test PostgreSQL nie został wykonany, ponieważ lokalny
  `127.0.0.1:5432` zakończył próbę kontrolowanym timeoutem,
- pełny mypy ujawnił dwa istniejące błędy poza zakresem TASK-0071:
  `jobs/runtime.py:130` i `images/symbol_vertical_slice.py:134`.
