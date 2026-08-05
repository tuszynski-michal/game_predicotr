---
title: TASK-0172 dedicated image selection worker lane
status: done
release: "0.4"
last_updated: 2026-08-05
---

# TASK-0172 — Dedicated image-selection worker lane

## Status

`done`

## Goal

Odseparować długie joby `image_selection` od właściwego `Importu layoutów` i
pozostałych jobów tak, aby oba procesy mogły działać równolegle bez wzajemnego
blokowania kolejki, zachowując jeden panel Admin, jedno API, jeden PostgreSQL i
ten sam kod workera.

## Context

Właściciel chce uruchamiać selekcję dużego folderu w jednym oknie, a równolegle
przetwarzać wcześniej wybrane zdjęcia w `Imporcie layoutów`. Obecny globalny
`execution_slot = 1` oraz jeden proces workera serializują wszystkie typy jobów.
Osobny mikroserwis, URL, Redis/Celery i druga baza nie są potrzebne do
rozdzielenia obciążenia.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`

## Scope

- wprowadzić dwa trwałe execution lanes w tabeli `jobs`:
  `general = 1` i `image_selection = 2`,
- zachować najwyżej jeden aktywny job w każdym lane,
- filtrować atomowy claim po dozwolonych typach jobów i lane,
- uruchamiać ogólny worker bez handlera `image_selection`,
- uruchamiać dedykowany worker wyłącznie z handlerem `image_selection`,
- dodać osobne komendy PowerShell/npm dla obu procesów,
- zachować wspólne lease, fencing token, heartbeat, checkpoint, cancel i retry,
- udowodnić testem, że import i selekcja mogą być `processing` jednocześnie,
  ale dwa joby w tym samym lane nie mogą być wykonywane równolegle.

## Out of scope

- osobna aplikacja webowa albo drugi URL,
- drugi PostgreSQL lub kopiowanie jobów między bazami,
- Redis, Celery, broker wiadomości albo mikroserwis,
- równoległe wykonywanie dwóch selekcji zdjęć,
- zmiana uploadu, selektora v9 lub pipeline'u Importu layoutów,
- automatyczne dobieranie limitu CPU między dwoma ciężkimi procesami.

## Acceptance criteria

- [x] Migracja Alembic dopuszcza sloty 1 i 2 oraz zachowuje pojedynczy aktywny
      job na slot.
- [x] General worker nie może przejąć joba `image_selection`.
- [x] Image-selection worker nie może przejąć żadnego innego typu joba.
- [x] Oba workery mogą atomowo przejąć po jednym jobie i działać jednocześnie.
- [x] Retry po restarcie odzyskuje wyłącznie wygasły job właściwego lane.
- [x] Dotychczasowe joby i API pozostają zgodne; nie powstaje nowa publiczna
      usługa ani nowy kontrakt OpenAPI.
- [x] Instrukcja operatorska opisuje dwa terminale i sposób kontrolowanego
      zatrzymania procesów.
- [x] Testy domeny, store, CLI, migracji, Ruff i MyPy przechodzą.

## Expected files

- `services/api/alembic/versions/0031_job_execution_lanes.py`
- `services/api/src/game_predictor_api/domain/jobs.py`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/worker/src/game_predictor_worker/jobs/runtime.py`
- `services/worker/src/game_predictor_worker/jobs/store.py`
- `services/worker/src/game_predictor_worker/cli.py`
- `services/worker/tests/test_job_runtime.py`
- `services/worker/tests/test_worker_cli.py`
- `services/api/tests/integration/test_worker_job_store.py`
- `services/api/tests/test_migration_baseline.py`
- `package.json`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_job_runtime.py services/worker/tests/test_worker_cli.py services/api/tests/test_jobs_domain.py services/api/tests/test_migration_baseline.py
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_worker_job_store.py
.\.venv\Scripts\python.exe -m ruff check services/api services/worker
.\.venv\Scripts\python.exe -m mypy services/api/src services/worker/src
```

## Risks / assumptions

- Dwa ciężkie procesy będą konkurować o CPU, RAM i dysk. Rozdzielenie kolejki
  usuwa blokowanie funkcjonalne, ale nie gwarantuje dwukrotnie większej
  przepustowości; operator może uruchomić tylko potrzebny lane.
- Sloty pozostają częścią wewnętrznego kontraktu PostgreSQL. Nie są wybierane
  przez frontend ani payload joba.
- Domyślna komenda ogólnego workera nie może konsumować selekcji, ponieważ po
  restarcie ponownie odtworzyłaby globalne blokowanie.

## Outcome

Dodano migrację `0031_job_execution_lanes`, która dopuszcza dwa unikalne sloty
aktywnych jobów. `LocalJobWorker` przekazuje do atomowego claimu własny slot i
zbiór zarejestrowanych typów. CLI `worker-v10` ma lane `general` oraz
`image-selection`; każdy konstruuje wyłącznie swoje handlery. Komendy npm i
instrukcja operatorska uruchamiają je w dwóch terminalach bez zmiany Admina,
API ani PostgreSQL.

Regresja domeny, CLI, handlera selekcji i SQL migracji przeszła `58 passed`, a
ochrona lokalnego API i OpenAPI `15 passed`. Izolowany test PostgreSQL przeszedł
`4 passed` i potwierdził dwa równoległe lease oraz blokadę drugiego joba w tym
samym lane. Oba procesy uruchomione jednorazowo na świeżej bazie zwróciły
`no_job`, Ruff i MyPy zmienionych źródeł przeszły. Migrację zastosowano lokalnie;
bieżący head to `0031_job_execution_lanes`.
