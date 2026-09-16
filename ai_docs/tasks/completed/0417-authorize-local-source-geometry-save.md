---
title: TASK-0417 Authorize local source geometry save
status: done
last_updated: 2026-09-03
---

# TASK-0417 — Autoryzacja lokalnego wspólnego zapisu geometrii źródła

## Problem

Nawet po usunięciu niepotrzebnej bramki globalnego backfillu lokalny Reviewer
na porcie `3001` nie może wywołać endpointu wspólnego zapisu geometrii źródła.
Middleware lokalnego Admin API nie ma jego dwóch, dokładnie ograniczonych ścieżek
w allowliście originu Reviewera, przez co zwraca `403 ADMIN_ORIGIN_FORBIDDEN`.
UI upraszcza ten transportowy błąd do komunikatu „Nie udało się zapisać
geometrii wszystkich plansz zdjęcia.”.

## Scope

- Dopuścić dla lokalnego originu Reviewera wyłącznie istniejące mutacje:
  - `POST /api/v1/admin/games/{game_id}/grid-reviews/source-geometry-approval`,
  - `POST /api/v1/admin/games/{game_id}/grid-reviews/source-geometry-revisions`.
- Zachować blokadę wszystkich pozostałych endpointów Admina dla originu
  Reviewera.
- Dodać regresję pozytywną dla obu tras oraz negatywną dla niepowiązanej
  mutacji administracyjnej.

## Out of scope

- Bez poszerzania dostępu zdalnego, bearer tokenów, OpenAPI, jobów i danych gry.
- Bez zmiany semantyki zapisu geometrii.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_local_admin_security.py services/api/tests/test_image_grid_review_api.py -q
.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/security/local_admin.py services/api/tests/test_local_admin_security.py
npm run python:typecheck
```

## Outcome

### Changed

- Lokalny origin Reviewera może wywołać tylko istniejące, source-scoped
  endpointy wspólnego zatwierdzenia i zapisu geometrii v0.10.
- Pozostałe mutacje Admina nadal zwracają `ADMIN_ORIGIN_FORBIDDEN` dla originu
  Reviewera.

### Verification results

- `pytest services/api/tests/test_local_admin_security.py services/api/tests/test_image_grid_review_api.py -q` — 14 passed.
- `ruff check` dla middleware i regresji — passed.

### Recommended next step

- Uruchomić lokalne API z tym commitem, otworzyć ponownie lokalny Reviewer i
  zapisać istniejący komplet dziewięciu szkiców bez ponownego ich wyznaczania.
