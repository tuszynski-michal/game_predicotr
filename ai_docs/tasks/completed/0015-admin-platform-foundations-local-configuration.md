---
title: TASK-0015 Admin platform foundations and local configuration
status: done
last_updated: 2026-07-26
---

# TASK-0015 — Admin platform foundations and local configuration

## Goal

Utworzyć uruchamialne lokalnie szkielety `services/api` w FastAPI i
`apps/admin` w Next.js z jawną, bezpieczną konfiguracją loopback oraz wspólnymi
komendami jakości monorepo.

## Context

M1 i G6 są zaakceptowane. Jest to pierwszy pion M2.1 i fundament pod PostgreSQL,
Alembic oraz generowany klient OpenAPI, które powstaną w TASK-0016 i TASK-0017.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_02_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- D-003, D-004, D-013, D-014 i D-020 w
  `ai_docs/process/DECISION_LOG.md`

## Scope

- szkielet Next.js App Router z TypeScript strict w `apps/admin`,
- lokalna strona startowa pokazująca stan fundamentu bez pozornego CRUD,
- walidowana konfiguracja adresu lokalnego Admin API,
- szkielet FastAPI w `services/api` z podziałem
  `api/application/domain/storage/schemas`,
- endpoint `GET /api/v1/health` zgodny z zaakceptowanym kontraktem,
- ograniczona do loopback konfiguracja hosta API i dozwolonego origin panelu,
- testy konfiguracji i health,
- root-level komendy uruchomienia i jakości dla obu aplikacji,
- instrukcja uruchomienia na Windows PowerShell.

## Out of scope

- Docker Compose i PostgreSQL,
- SQLAlchemy i migracje Alembic,
- tabele, repozytoria i CRUD domenowy,
- generowanie klienta TypeScript z OpenAPI,
- biblioteka formularzy i edytor payline,
- uwierzytelnianie,
- połączenie aplikacji mobilnej z API.

## Acceptance criteria

- [x] `apps/admin` buduje się jako Next.js App Router z `strict: true`.
- [x] `services/api` uruchamia aplikację FastAPI bez zależności od bazy danych.
- [x] `GET /api/v1/health` zwraca `{"status":"ok","version":"0.1.0"}`.
- [x] nieprawidłowy albo nielokalny host/origin jest odrzucany kontrolowanym
  błędem konfiguracji.
- [x] panel ma jawny stan fundamentu i nie sugeruje gotowego CRUD.
- [x] istnieją komendy PowerShell/npm dla uruchomienia API i panelu.
- [x] Python lint, typecheck i testy obejmują `services/api`.
- [x] root format, lint, typecheck i testy przechodzą.
- [x] mobile nie otrzymuje zależności od FastAPI ani Admin API.

## Technical notes

- API domyślnie nasłuchuje na `127.0.0.1:8000`.
- Panel domyślnie działa na `127.0.0.1:3000`.
- Dozwolone są wyłącznie adresy loopback `localhost`, `127.0.0.1` i `::1`.
- Używamy minimalnych zależności; PostgreSQL i Alembic są celowo odłożone.
- Next.js, FastAPI i Uvicorn są przypięte do wersji zweryfikowanych w tym
  zadaniu, bez automatycznych major upgrade’ów.

## Expected files

- `apps/admin/**`
- `services/api/**`
- `package.json`
- `package-lock.json`
- `pyproject.toml`
- `.env.example`
- `README.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm run format:check
npm run lint
npm run typecheck
npm test
npm run admin:build
.venv\Scripts\python.exe -m pytest services/api/tests
```

## Risks / open questions

- Brak pytań blokujących.
- Integracja z PostgreSQL i OpenAPI client jest poza tym taskiem; fundament nie
  może utrwalać ręcznie skopiowanych typów przyszłego Admin API.

## Outcome

### Changed

- dodano Next.js App Router `apps/admin` z responsywnym ekranem fundamentu,
  konfiguracją adresu Admin API i testami odrzucania hostów innych niż loopback,
- dodano warstwowy pakiet FastAPI `game_predictor_api` z fabryką aplikacji,
  konfiguracją loopback, CORS i kontraktem `GET /api/v1/health`,
- dodano root commands `admin:dev`, `admin:start`, `admin:build`, `api:dev` i
  `api:test`,
- rozszerzono `pyproject.toml` i centralny runner Python o `services/api`,
- przypięto Next.js `16.2.11`, React `19.2.3`, FastAPI `0.139.2`, Uvicorn
  `0.51.0` i HTTPX2 `2.7.0`,
- dodano `.env.example`, instrukcję Windows i ignorowanie `.next`.

### Verification results

- `npm run quality`: zaliczone; 4 testy admin, 63 mobile, 23 shared i 61
  Python po rozszerzeniu centralnego runnera,
- `npm run admin:build`: zaliczone, statyczna trasa `/` z Next.js `16.2.11`,
- Ruff i mypy dla `services/api`: zaliczone, 12 plików źródłowych bez błędów,
- smoke test procesów: `GET /api/v1/health` zwrócił `ok / 0.1.0`, a panel
  odpowiedział HTTP 200 na `127.0.0.1:3000`,
- pierwszy pełny przebieg miał pojedynczy przejściowy timeout istniejącego testu
  Target mobile; test przeszedł osobno w `895 ms`, a powtórzona pełna bramka
  zaliczyła wszystkie 63 testy mobile.

### Not completed

- PostgreSQL, Docker Compose, SQLAlchemy i Alembic — TASK-0016,
- generowany klient OpenAPI — TASK-0017,
- CRUD oraz formularze domenowe — kolejne podetapy M2.

### Documentation updates

- zaktualizowano `README.md`, `TECH_STACK.md`, `DECISION_LOG.md`,
  `MILESTONE_02_EXECUTION_PLAN.md` i `CURRENT_STATE.md`,
- dodano D-021 dla wersji baseline i granicy loopback.

### Recommended next task

- `TASK-0016 — PostgreSQL Compose and Alembic baseline`.
