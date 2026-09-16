---
title: Separate board frame and symbol lattice geometry
status: done
last_updated: 2026-09-04
---

# TASK-0445 — Rozdzielenie ramki planszy i siatki symboli

## Status

`done`

## Goal

Wprowadzić addytywny, wersjonowany kontrakt rozdzielający obszar analizy,
zewnętrzną ramkę i końcową siatkę symboli bez zmiany replayu v0.10 v1/v2.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- role `analysisQuad`, `boardFrameQuad` i `symbolGridQuad` w schema v2 wyniku;
- `finalQuad` jako kompatybilny alias końcowej siatki wyłącznie dla nowego schema;
- addytywne pola kolejki walidacji siatki i OpenAPI;
- test niezmienności payloadu schema v1.

## Out of scope

- uruchomienie estymatora v19;
- produkcyjny rollout v3;
- migracja danych lub automatyczny reprocess.

## Acceptance criteria

- [x] schema v1 serializuje dokładnie dotychczasowy payload;
- [x] schema v2 wymaga jawnego `analysisQuad` i końcowego `symbolGridQuad` dla automatu;
- [x] `finalQuad` i `symbolGridQuad` nie mogą się różnić;
- [x] API zwraca jawne, opcjonalne role geometrii.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_structured_geometry_engine.py services/api/tests/test_image_grid_reviews.py
npm run openapi:check
```

## Risks / open questions

- Brak. Pola są addytywne i przechowywane w istniejących payloadach JSONB.

## Outcome

### Changed

- Dodano jawne role do schema v2 wyniku structured i addytywne pola kolejki.
- Zachowano serializację i checksumę schema v1 nawet dla obiektu z adnotacjami ról.
- Zregenerowano OpenAPI i klienta TypeScript.

### Verification results

- `13 passed` dla testów structured geometry i API kolejki.
- Ruff lint i format: passed.
- `npm run openapi:check`: passed.

### Not completed

- Estimator i rollout v3 należą do TASK-0446–0448.

### Documentation updates

- Wymagania, architektura, API contract, Decision Log i Current State.

### Recommended next task

- TASK-0446.
