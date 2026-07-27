---
title: Local worker execution, lease and resume
status: done
last_updated: 2026-07-27
---

# TASK-0030 — Local worker execution, lease and resume

## Status

`done`

## Goal

Dodać lokalny proces workera, który atomowo przejmuje trwały job, wykonuje
zarejestrowany handler poza requestem HTTP, zapisuje heartbeat i checkpoint,
bezpiecznie obsługuje anulowanie oraz odzyskuje pracę po wygaśnięciu lease.

## Context

TASK-0029 dostarczył trwały rekord joba, wspólny lifecycle i Admin API.
TASK-0030 dodaje granicę wykonawczą bez implementowania jeszcze konkretnych
workflow payout/snapshot/build ani ekranu panelu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_03_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- lease z nieprzenośnym tokenem, ownerem, expiry i heartbeat,
- atomowe przejęcie najstarszego `created` joba,
- bazowe ograniczenie jednego `processing` joba,
- wersjonowany JSONB checkpoint zapisany razem z postępem,
- odzyskanie wygasłego lease i wznowienie tego samego rekordu,
- ochrona przed zapisem workera ze starym tokenem,
- anulowanie przy bezpiecznym checkpointcie,
- jawne retry `failed → created` bez tworzenia nowego joba,
- rejestr handlerów, wykonanie poza transakcją DB i lokalny polling CLI,
- migracja Alembic, testy domenowe, runtime i współbieżności PostgreSQL.

## Out of scope

- implementacja import/validate/payout/snapshot/android_build workflow,
- ekran jobs w panelu,
- artefakty wydania i precomputing,
- proces działający jako usługa systemowa,
- Redis, Celery, mikroserwisy i chmura.

## Acceptance criteria

- [x] Dwa workery nie mogą jednocześnie uzyskać aktywnego lease.
- [x] Claim wybiera deterministycznie najstarszy gotowy job.
- [x] Każda mutacja wykonawcza wymaga aktualnego tokenu lease.
- [x] Heartbeat wydłuża lease, a wygasły token nie może zapisywać.
- [x] Checkpoint i progress zapisują się atomowo i nie cofają liczników.
- [x] Cancel request zatrzymuje handler przy następnym bezpiecznym checkpointcie.
- [x] Wygasły job wraca do `created` z checkpointem albo kończy jako cancelled.
- [x] Ponowne przejęcie zwiększa attempt i wznawia ten sam rekord.
- [x] Wyjątek handlera daje stabilny błąd bez pozostawienia aktywnego slotu.
- [x] CLI potrafi wykonać jeden przebieg albo polling bez blokowania API.
- [x] Migracja, testy jednostkowe i fizyczny PostgreSQL przechodzą.

## Technical notes

- Obowiązuje D-033.
- Domyślny lease trwa 60 sekund; handler powinien heartbeatować częściej niż
  expiry i checkpointować po małej bezpiecznej partii.
- Konkretny handler jest rejestrowany przez przyszły pion funkcjonalny. Brak
  handlera kończy przejęty job stabilnym `JOB_HANDLER_NOT_REGISTERED`.

## Expected files

- `services/api/alembic/versions/0008_job_leases.py`
- `services/api/src/game_predictor_api/domain/jobs.py`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/worker/src/game_predictor_worker/jobs/`
- `services/worker/src/game_predictor_worker/__main__.py`
- testy domenowe, runtime i PostgreSQL
- dokumentacja architektury, uruchomienia oraz stanu

## Verification

```powershell
npm run quality
npm run db:baseline:verify
npm run worker:once
```

## Risks / open questions

- Brak pytań blokujących. Dobór wielkości partii należy do konkretnego handlera
  z następnych zadań.

## Outcome

- Dodano migrację `0008_job_leases`, constraint singletonowego slotu i indeks
  odzyskiwania wygasłego lease.
- Domena i PostgreSQL store obsługują claim, heartbeat, atomowy checkpoint,
  fencing tokenu, anulowanie, failure, review, recovery i retry tego samego
  rekordu.
- Lokalny runtime uruchamia typowane handlery poza transakcją; CLI obsługuje
  pojedynczą próbę i ciągły polling. Brak handlera kończy job stabilnym błędem.
- Admin API udostępnia retry oraz bezpieczne pola obserwowalności; OpenAPI i
  klient TypeScript są zsynchronizowane.
- `npm run quality` zakończyło się powodzeniem: 150 testów Python (4 testy
  PostgreSQL pominięte w standardowym przebiegu), 63 mobile, 44 panelu, 23
  wspólnej domeny i 8 klienta API.
- `npm run db:baseline:verify` uruchomiło 4/4 testy na fizycznym PostgreSQL,
  łącznie z konkurencyjnym claim, recovery i fencing.
- `npm run admin:build` zakończył się powodzeniem.
- Nie uruchomiono `npm run worker:once` na deweloperskiej bazie użytkownika,
  ponieważ pozostaje ona na rewizji `0002_games_symbols`. Tryby CLI zostały
  zweryfikowane izolowanymi testami bez migracji ani przejęcia danych
  użytkownika.
