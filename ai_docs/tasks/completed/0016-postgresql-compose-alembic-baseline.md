---
title: TASK-0016 PostgreSQL Compose and Alembic baseline
status: done
last_updated: 2026-07-26
---

# TASK-0016 — PostgreSQL Compose and Alembic baseline

## Goal

Dostarczyć lokalny PostgreSQL uruchamiany przez Docker Compose oraz pusty,
odwracalny baseline Alembic dla przyszłych tabel domenowych M2.

## Context

TASK-0015 dostarczył lokalne FastAPI i Next.js. Następny krok M2.1 ustanawia
kanoniczną bazę PostgreSQL i jedyny dozwolony mechanizm zmian jej schematu,
bez przedwczesnego tworzenia tabel gier, symboli albo datasetów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_02_EXECUTION_PLAN.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- D-005, D-014 i D-021 w `ai_docs/process/DECISION_LOG.md`
- `ai_docs/tasks/completed/0015-admin-platform-foundations-local-configuration.md`

## Scope

- przypięty oficjalny obraz PostgreSQL w `infra/docker/compose.yaml`,
- port PostgreSQL udostępniony wyłącznie na loopback,
- trwały nazwany volume i healthcheck,
- walidowana konfiguracja `GAME_PREDICTOR_DATABASE_URL`,
- SQLAlchemy 2.x i Psycopg 3 jako synchroniczny adapter lokalnego API,
- konfiguracja Alembic korzystająca z metadata warstwy storage,
- pierwsza pusta migracja baseline bez tabel domenowych,
- statyczny test grafu migracji i generowania SQL PostgreSQL,
- integracyjny test `upgrade → downgrade → upgrade` na osobnej testowej bazie,
- komendy Windows dla Compose i Alembic,
- instrukcja instalacji Docker Desktop oraz uruchomienia.

## Out of scope

- tabele domenowe i constraints,
- CRUD, repozytoria i transakcje aplikacyjne,
- seedy,
- endpoint sprawdzający gotowość PostgreSQL,
- generowanie klienta OpenAPI,
- automatyczne instalowanie Docker Desktop.

## Acceptance criteria

- [x] Compose używa przypiętego obrazu PostgreSQL i trwałego volume.
- [x] port bazy domyślnie wiąże się wyłącznie z `127.0.0.1`.
- [x] konfiguracja odrzuca nielokalny albo niezgodny URL bazy.
- [x] `alembic upgrade head` działa od pustej bazy.
- [x] baseline nie tworzy żadnej tabeli domenowej.
- [x] `alembic downgrade base` cofa baseline, a ponowny upgrade działa.
- [x] test integracyjny nie dotyka deweloperskiej bazy `game_predictor`.
- [x] root lint, typecheck i testy przechodzą.
- [x] instrukcje Windows nie wymagają globalnego PostgreSQL ani `psql`.

## Technical notes

- obraz: `postgres:18.4-alpine3.24`,
- volume PostgreSQL 18 jest montowany pod `/var/lib/postgresql`,
- domyślny port hosta: `127.0.0.1:5432`,
- sterownik SQLAlchemy: `postgresql+psycopg`,
- test integracyjny używa wyłącznie bazy `game_predictor_baseline_test`,
- środowisko testowe: Docker Desktop `4.83.0`, Engine `29.6.2`, Compose `5.3.1`
  oraz WSL `2.7.11.0`.

## Expected files

- `infra/docker/compose.yaml`
- `alembic.ini`
- `services/api/alembic/**`
- `services/api/src/game_predictor_api/storage/**`
- `services/api/tests/**`
- `scripts/verify_postgres_baseline.ps1`
- `.env.example`
- `package.json`
- `pyproject.toml`
- `README.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm run db:up
npm run db:migrate
npm run db:baseline:verify
npm run quality
```

## Risks / open questions

- Brak pytania produktowego.
- Brak Docker Desktop blokuje wyłącznie fizyczny test Compose/PostgreSQL, nie
  implementację ani statyczne testy migracji.

## Outcome

Implementacja jest kompletna, a zadanie pozostaje aktywne wyłącznie do
fizycznej weryfikacji PostgreSQL:

- dodano przypięty PostgreSQL 18.4 z healthcheckiem, loopback bind i trwałym
  volume,
- skonfigurowano walidowany URL, SQLAlchemy 2.0.51 i Psycopg 3.3.4,
- dodano pusty, odwracalny baseline Alembic `0001_empty_baseline`,
- statycznie potwierdzono jeden head, PostgreSQL SQL upgrade/downgrade i brak
  tabel domenowych,
- test integracyjny zarządza tylko bazą `game_predictor_baseline_test` i
  wykonuje `upgrade → downgrade → upgrade`,
- pełne `npm run quality` przeszło: 4 testy admin, 63 mobile, 23 shared oraz
  71 testów Python; 1 test PostgreSQL został jawnie pominięty z powodu braku
  Docker CLI,
- parser YAML poprawnie odczytał `infra/docker/compose.yaml`,
- po instalacji Docker Desktop i WSL 2 `npm run db:baseline:verify` uruchomił
  przypięty obraz, osiągnął stan `Healthy` i zaliczył fizyczny cykl
  `upgrade → downgrade → upgrade` (`1 passed`),
- skrypt wykrywa zarówno instalację Docker Desktop per-user, jak i all-users.

Wszystkie kryteria akceptacji zostały spełnione. Trwały volume i deweloperska
baza `game_predictor` nie zostały usunięte.
