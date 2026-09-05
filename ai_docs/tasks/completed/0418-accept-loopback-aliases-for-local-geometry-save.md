---
title: TASK-0418 Accept loopback aliases for local geometry save
status: active
last_updated: 2026-09-03
---

# TASK-0418 — Alias loopback dla lokalnego zapisu geometrii

## Problem

Lokalny Reviewer może być otwarty przez operatora jako `localhost:3001`, choć
domyślna konfiguracja API podaje `127.0.0.1:3001`. Oba adresy prowadzą do tego
samego lokalnego procesu, lecz poprzedni middleware porównywał tekst originu
dosłownie. Wtedy dozwolony endpoint wspólnego zapisu geometrii źródła nadal
kończył się `403 ADMIN_ORIGIN_FORBIDDEN`.

## Scope

- Traktować `127.0.0.1`, `localhost` i `[::1]` jako równoważne wyłącznie dla
  skonfigurowanego schematu HTTP i dokładnie tego samego portu Admina albo
  lokalnego Reviewera.
- Zachować ograniczenie Reviewera do jego istniejącej allowlisty mutacji.
- Dodać regresję dla `localhost:3001` oraz negatywną dla innego portu.

## Out of scope

- Bez nowych originów LAN/publicznych, endpointów, tokenów, migracji oraz
  mutacji danych gry.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_local_admin_security.py -q
.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/security/local_admin.py services/api/tests/test_local_admin_security.py
npm run python:typecheck
```

## Outcome

### Changed

- Middleware porównuje lokalne originy przez ograniczony zestaw aliasów
  `127.0.0.1`/`localhost`/`[::1]` tylko dla tego samego HTTP portu.
- Pozostała allowlista Reviewera nadal ogranicza mutacje do tras geometrii;
  `localhost:3002` pozostaje odrzucone.

### Verification results

- `pytest services/api/tests/test_local_admin_security.py -q` — 6 passed.
- `ruff check services/api/src/game_predictor_api/security/local_admin.py services/api/tests/test_local_admin_security.py` — passed.
- `npm run python:typecheck` — passed.

### Recommended next step

- Jednorazowo uruchomić ponownie rzeczywisty proces API, a następnie ponowić
  zapis istniejących szkiców w lokalnym Reviewerze bez odświeżania jego strony.
