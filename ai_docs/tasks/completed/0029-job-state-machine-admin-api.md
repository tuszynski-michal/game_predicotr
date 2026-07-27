---
title: Job state machine and Admin API
status: done
last_updated: 2026-07-27
---

# TASK-0029 — Job state machine and Admin API

## Status

`done`

## Goal

Wprowadzić trwały, wspólny model zadań administracyjnych, bezpieczny automat
stanów oraz typowany kontrakt Admin API, bez uruchamiania jeszcze workera.

## Context

M2 zakończyło synchroniczny pion konfiguracji dla bounded danych. M3.1
potrzebuje teraz trwałego rekordu dla operacji długich, które później wykona
osobny lokalny worker. Stan cyklu życia zadania musi być niezależny od etapu
konkretnego pipeline'u.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_03_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- wspólny model domenowy typów i stanów jobs,
- czyste, deterministyczne reguły przejść, postępu, błędów i anulowania,
- wersjonowane, typowane payloady wejściowe dla pięciu typów jobs,
- migracja Alembic tabeli `jobs` z ograniczeniami i indeksami,
- repozytorium SQLAlchemy,
- enqueue, lista, szczegóły i żądanie anulowania w Admin API,
- stabilny klucz wejścia zapobiegający zduplikowanemu enqueue,
- aktualizacja OpenAPI i generowanego klienta TypeScript,
- testy domeny, API, migracji i fizycznego PostgreSQL.

## Out of scope

- polling, lease, heartbeat, checkpoint i uruchamianie workera,
- wykonanie któregokolwiek typu joba,
- ekran postępu w panelu,
- precomputing payoutów, snapshot i build APK,
- Redis, Celery, mikroserwisy i chmura.

## Acceptance criteria

- [x] Każdy job ma typowany payload `schemaVersion = 1`.
- [x] Status i `stage` są rozdzielone, a błędne przejście jest odrzucane.
- [x] Utworzenie tego samego wejścia nie może zapisać dwóch jobs.
- [x] Anulowanie nieuruchomionego joba kończy go od razu.
- [x] Anulowanie joba `processing` tylko ustawia żądanie dla bezpiecznego punktu.
- [x] Terminalnego joba nie można ponownie przełączyć bez jawnego retry.
- [x] API udostępnia enqueue, bounded listę, szczegóły i cancel.
- [x] Migracja ma downgrade, constraints i indeksy.
- [x] OpenAPI oraz klient TypeScript nie mają driftu.
- [x] Testy jednostkowe, API i fizyczny PostgreSQL przechodzą.

## Technical notes

- Obowiązuje D-032.
- `created` jest trwałym stanem gotowym do późniejszego przejęcia przez workera.
- `scanning`, `validating`, `writing_layouts` i podobne wartości są etapami,
  nie osobnymi stanami cyklu życia.
- Jeden ciężki job jednocześnie będzie egzekwowany atomowo podczas lease w
  TASK-0030, a nie przez blokowanie enqueue.

## Expected files

- `services/api/src/game_predictor_api/domain/jobs.py`
- `services/api/src/game_predictor_api/application/jobs.py`
- `services/api/src/game_predictor_api/storage/job_repository.py`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/api/src/game_predictor_api/schemas/jobs.py`
- `services/api/src/game_predictor_api/api/jobs.py`
- `services/api/alembic/versions/0007_jobs.py`
- testy API, domeny, migracji i PostgreSQL
- OpenAPI i generowany klient TypeScript
- dokumentacja architektury oraz stanu

## Verification

```powershell
npm run quality
npm run admin:build
npm run db:baseline:verify
```

## Risks / open questions

- Brak pytań blokujących. Kontrakt lease i polityka odzyskiwania po restarcie
  pozostają jawnie w TASK-0030.

## Outcome

Zadanie ukończone 2026-07-27. Fundament trwałych jobs i publiczny kontrakt
Admin API są gotowe do użycia przez worker z TASK-0030.

### Changed

- Dodano wspólny automat stanów, czyste operacje postępu, review, retry,
  ukończenia, błędu i dwuetapowego anulowania.
- Dodano pięć typowanych payloadów `schemaVersion = 1` oraz deterministyczny,
  unikalny hash wejścia.
- Migracja `0007_jobs` tworzy enumy, JSONB, constraints, indeksy i FK
  `dataset_versions.source_job_id`.
- Dodano repozytorium SQLAlchemy oraz endpointy create/list/get/cancel.
- Zregenerowano OpenAPI i klient TypeScript wraz z wygodnymi metodami jobs.
- Zaktualizowano wymagania, model danych, kontrakt API, architekturę i D-032.

### Verification results

- `npm run quality`: 139 standardowych testów Python przeszło, 3 fizyczne
  scenariusze zostały zgodnie z projektem pominięte; przeszły też 63 testy
  mobile, 44 panelu, 23 wspólnej domeny i 8 klienta API.
- `npm run admin:build`: produkcyjny build Next.js przeszedł.
- `npm run db:baseline:verify`: 3 izolowane testy PostgreSQL przeszły, w tym
  repozytorium jobs i cykl upgrade–downgrade–upgrade do `0007_jobs`.
- `git diff --check`, pojedynczy head Alembic i końcowy format check przeszły.

### Not completed

- Nie dodano lease, heartbeat, checkpointów ani procesu workera.
- Nie dodano ekranu jobs w panelu.
- Nie wykonuje się jeszcze żadnego workflow długiego zadania.

### Recommended next task

- po kolejnym poleceniu właściciela:
  `TASK-0030 — Local worker execution, lease and resume`.
