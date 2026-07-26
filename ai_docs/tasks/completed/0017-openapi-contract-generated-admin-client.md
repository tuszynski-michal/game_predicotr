---
title: TASK-0017 OpenAPI contract and generated admin client
status: done
last_updated: 2026-07-26
---

# TASK-0017 — OpenAPI contract and generated admin client

## Goal

Ustanowić deterministyczny kontrakt OpenAPI FastAPI oraz generowany, typowany
klient TypeScript używany przez lokalny panel administracyjny.

## Context

TASK-0015 dostarczył FastAPI i Next.js, a TASK-0016 PostgreSQL oraz Alembic.
Ostatni krok M2.1 usuwa możliwość ręcznego rozchodzenia się typów HTTP między
backendem i panelem przed rozpoczęciem CRUD gier i symboli.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_02_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- stabilny `operationId` i test kontraktu istniejącego health endpointu,
- deterministyczny eksport OpenAPI 3.1 bez uruchamiania serwera HTTP,
- workspace `@game-predictor/admin-api-client`,
- typy i klient Fetch generowane przez `@hey-api/openapi-ts`,
- automatyczna kontrola driftu specyfikacji i wygenerowanego kodu,
- komendy Windows do generowania i sprawdzania kontraktu,
- włączenie kontroli OpenAPI do root quality gate.

## Out of scope

- CRUD gier, symboli lub innych zasobów,
- nowe tabele PostgreSQL,
- ręcznie utrzymywane typy odpowiedzi HTTP,
- klient lub połączenie HTTP w aplikacji mobilnej,
- React Query i warstwa cache,
- uruchamianie API podczas generowania klienta.

## Acceptance criteria

- [x] OpenAPI zawiera stabilny kontrakt `GET /api/v1/health`.
- [x] eksport tej samej aplikacji daje identyczny plik JSON.
- [x] typ `HealthResponse` pochodzi z wygenerowanego schematu.
- [x] wygenerowany klient Fetch wykonuje typowane wywołanie health.
- [x] zmiana backendowego OpenAPI bez regeneracji powoduje błąd kontroli driftu.
- [x] panel może importować workspace klienta bez ręcznego typu odpowiedzi.
- [x] mobile nie otrzymuje zależności od klienta Admin API.
- [x] format, lint, typecheck, testy i produkcyjny build panelu przechodzą.

## Technical notes

- generator i klient Fetch: `@hey-api/openapi-ts 0.99.0`,
- generator ma jawne wsparcie peer dependency dla TypeScript 6,
- kanonicznym źródłem jest `create_app(...).openapi()` w backendzie,
- zapisany JSON i kod TypeScript są artefaktami generowanymi oraz sprawdzanymi
  w quality gate,
- obecny kontrakt zawiera tylko health; zasoby admin będą dodawane przez
  odpowiadające im piony M2.
- początkowo rozważone `openapi-typescript 7.13.0` zostało odrzucone po
  kontrolowanym błędzie instalacji, ponieważ deklaruje peer dependency tylko
  dla TypeScript 5.x.

## Expected files

- `services/api/src/game_predictor_api/api/health.py`
- `services/api/tests/test_openapi_contract.py`
- `scripts/export_admin_openapi.py`
- `packages/admin-api-client/**`
- `apps/admin/package.json`
- `apps/admin/src/**`
- `package.json`
- `package-lock.json`
- `README.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm run openapi:generate
npm run openapi:check
npm run admin:build
npm run quality
```

## Risks / open questions

- Brak pytania produktowego.
- Każdy przyszły endpoint musi jawnie określić modele response/error, zanim
  zostanie użyty przez panel.

## Outcome

### Zmieniono

- FastAPI publikuje stabilne `operationId = getHealth`, jawny model odpowiedzi
  i lokalny adres serwera w OpenAPI 3.1.
- Dodano deterministyczny eksport specyfikacji do
  `packages/admin-api-client/openapi/openapi.json`.
- Dodano workspace `@game-predictor/admin-api-client`, generowany klient Fetch,
  typ `HealthResponse` oraz cienki adapter używany przez panel.
- Dodano kontrolę driftu kontraktu i wygenerowanego kodu do głównej bramki
  `npm run quality`.
- Aplikacja mobilna nie otrzymała zależności od klienta ani transportu HTTP.

### Wyniki weryfikacji

- `npm run openapi:generate` — sukces.
- `npm run openapi:check` — sukces, zapisany kontrakt i klient są aktualne.
- `npm run admin:build` — sukces, produkcyjny build Next.js został wygenerowany.
- `npm run quality` — sukces: format, OpenAPI drift, lint, kontrola składni
  PowerShell, typecheck, 63 testy mobile, 4 testy panelu, 1 test klienta,
  23 testy shared oraz 72 testy Python przeszły.
- Jeden test integracyjny PostgreSQL jest celowo pomijany w zwykłym przebiegu;
  fizyczny cykl PostgreSQL został zaliczony podczas TASK-0016.

### Niewykonane

- Nie dodano CRUD gier ani symboli; jest to zakres TASK-0018.
- Nie dodano klienta API do aplikacji mobilnej, zgodnie z architekturą offline.

### Dokumentacja

- Zaktualizowano kontrakt API, stos technologiczny, instrukcje repozytorium,
  plan M2, rejestr decyzji oraz bieżący stan projektu.
- D-023 utrwala OpenAPI FastAPI jako źródło prawdy i
  `@hey-api/openapi-ts 0.99.0` jako generator zgodny z TypeScript 6.

### Następne zadanie

Po poleceniu właściciela rozpocząć TASK-0018 — domenę, repozytoria i API gier
oraz symboli.
