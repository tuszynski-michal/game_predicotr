---
title: TASK-0419 Align loopback CORS with geometry security
status: active
last_updated: 2026-09-03
---

# TASK-0419 — CORS lokalnych aliasów dla zapisu geometrii

## Problem

TASK-0418 odblokował lokalny origin `localhost:3001` w middleware
bezpieczeństwa, ale konfiguracja CORS FastAPI nadal zawierała tylko literalny
`127.0.0.1:3001`. Przeglądarka blokowała preflight POST z własnym nagłówkiem
`X-Admin-Intent` zanim mógł dojść do poprawionej autoryzacji.

## Scope

- Użyć tego samego, ograniczonego zbioru aliasów loopback dla CORS i
  middleware lokalnego API.
- Potwierdzić, że `localhost:3001` jest dozwolony, a `localhost:3002` nie.

## Out of scope

- Bez originów LAN/publicznych, nowych endpointów, mutacji danych lub zmian
  semantyki geometrii.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_health.py services/api/tests/test_local_admin_security.py -q
.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/main.py services/api/src/game_predictor_api/security/local_admin.py services/api/tests/test_health.py services/api/tests/test_local_admin_security.py
npm run python:typecheck
```

## Outcome

### Changed

- CORS i `LocalAdminSecurityMiddleware` używają jednego predykatu aliasów
  loopback. `localhost:3001` może wykonać preflight i tylko uprzednio
  dozwoloną mutację Reviewera; `localhost:3002` nie otrzymuje nagłówka CORS.

### Verification results

- `pytest services/api/tests/test_health.py services/api/tests/test_local_admin_security.py -q` — 8 passed.
- `ruff check` dla API, middleware i obu regresji — passed.
- Żywy preflight `POST source-geometry-revisions` z `localhost:3001` — 200 i
  wymagane `X-Admin-Intent` w `Access-Control-Allow-Headers`.
- Żywy, celowo niekompletny zapis jednej z dziewięciu plansz —
  `IMAGE_GRID_REVIEW_SOURCE_SLOT_CONFLICT` (422), co potwierdza przejście
  przez CORS oraz autoryzację bez zapisania danych.

### Recommended next step

- Ponowić zapis istniejącego kompletu dziewięciu narożników. W razie błędu
  odpowiedź jest teraz source-scoped, a nie transportowym 403.
