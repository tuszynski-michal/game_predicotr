---
title: Queue and pipeline architecture decision
status: done
last_updated: 2026-07-29
---

# TASK-0077 — Queue and pipeline architecture decision

## Status

`done`

## Goal

Zamknąć pomiarową decyzję, czy obecny lokalny pipeline wymaga Redis/Celery,
osobnej kolejki lub wielu workerów, bez omijania blokady jakości TASK-0076.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_07_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/quality/m7-storage-database-load-report.json`
- `ai_docs/quality/m7-import-operations-benchmark-report.json`

## Scope

- checksum-bound ocena raportów TASK-0074 i TASK-0075,
- jawna decyzja retain/change dla jednego workera i globalnego slotu,
- oddzielna ocena Redis, Celery, brokerów i mikroserwisów,
- zapis obecnych wąskich gardeł,
- mierzalne warunki ponownego otwarcia decyzji,
- kanoniczny raport i walidator decyzji,
- synchronizacja architektury, planu, strategii testów i Decision Log.

## Out of scope

- implementacja kolejki lub nowego procesu,
- publikacja datasetu i APK — zablokowany TASK-0076,
- obniżenie progów jakości albo retraining,
- zmiana schematu PostgreSQL lub API,
- decyzje M8 dotyczące prywatnej dystrybucji.

## Acceptance criteria

- [x] oba raporty wejściowe są weryfikowane przez SHA-256 i walidatory,
- [x] decyzja wynika z zapisanych pomiarów, a nie z preferencji technologicznej,
- [x] jakość/manual review jest oddzielona od przepustowości infrastruktury,
- [x] raport jawnie rozstrzyga single worker, Redis, Celery i mikroserwisy,
- [x] warunki ponownego otwarcia są mierzalne i nie uruchamiają migracji
  automatycznie,
- [x] decyzja nie odblokowuje TASK-0076 ani `massImportAllowed`,
- [x] raport jest kanoniczny, bez sekretów i ścieżek absolutnych,
- [x] testy, lint i typecheck przechodzą,
- [x] dokumentacja i Decision Log są aktualne.

## Expected files

- `services/worker/src/game_predictor_worker/images/queue_decision.py`
- `scripts/build_m7_queue_decision.py`
- `services/worker/tests/test_m7_queue_decision.py`
- `ai_docs/quality/m7-queue-architecture-decision.json`
- `package.json`
- dokumentacja procesu, architektury i testów

## Risks / open questions

- TASK-0075 mierzy synthetic persistence/recovery fixture, nie czas człowieka ani
  accuracy nieoznaczonych zdjęć.
- Finalny G7 nadal wymaga TASK-0076; ta decyzja zamyka wyłącznie architekturę
  kolejki na podstawie obecnych danych.

## Outcome

- Kanoniczny raport `m7-queue-architecture-decision-v1` weryfikuje raporty
  TASK-0074/0075 przez ich walidatory i SHA-256.
- Decyzja: `retain_current_architecture`, jeden lokalny worker,
  `execution_slot = 1`, scheduling przez istniejące PostgreSQL jobs z fenced
  lease. Redis, Celery i mikroserwisy nie są przyjmowane.
- Dowody: rejestracja `184.32 plików/s`, storage `431.19 plików/s`, recovery
  wszystkich sześciu etapów przeszedł, persistence review osiągnęło
  `26.16 decyzji/s`.
- Główne ograniczenie jest jakościowe: `massImportAllowed = false` i 100%
  manual review. Broker nie poprawi accuracy ani nie odblokuje TASK-0076.
- Zapisano pięć mierzalnych warunków ponownej oceny: trwały backlog ciężkich
  jobów, dwukrotne przekroczenie zaakceptowanego SLA, wielu administratorów,
  regresja recovery/fencingu albo zmiana lokalnej topologii.
- Raport zapisano w
  `ai_docs/quality/m7-queue-architecture-decision.json`; SHA-256:
  `c511da766e7276666cbd62413a1128540aa00b930357fe77736d9a1dfce8cf09`.
- Focused testy: `3 passed`; Ruff, mypy, builder i `--check` przeszły.
