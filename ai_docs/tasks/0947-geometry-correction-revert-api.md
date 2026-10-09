# TASK-0947 — API listy, podglądu i cofnięcia korekt geometrii

## Status

`todo`

## Goal

Reviewer i Admin mogą pobrać ostatnie korekty importu, podgląd skutków cofnięcia i wykonać cofnięcie przez trzy trasy z wygenerowanym klientem.

## Context

Plan `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`, sekcja „API (TASK-0947)”.

## Dependencies / entry conditions

- TASK-0945 i TASK-0946 ukończone (serwis z `list_recent`, `preview`, `revert`).

## Recommended execution

`claude-sonnet-5-5`, reasoning `medium`: pion API według istniejącego wzorca. Eskalacja: konieczność zmiany serwisu poza mapowaniem błędów → wróć do wykonawcy TASK-0945/0946 (`claude-opus-5-5`, `high`). Review: Codex `gpt-6-astra`, `medium`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md` — D-442

## Scope

- Router (proponowany) `api/geometry_correction_reverts.py`, schematy Pydantic (proponowane) `schemas/geometry_correction_reverts.py`, rejestracja w aplikacji, `game_storage_scope(game_id)`.
- Trasy i operationId z planu: `listGeometryCorrections`, `previewGeometryCorrectionRevert`, `revertGeometryCorrection`. Mapowanie kodów blokady na 409 z `code` i polskim `message`; 404 dla nieznanej korekty; 422 dla walidacji.
- Allowlisty: `security/local_admin.py` (~249) i `apps/reviewer/src/security/reviewer-proxy-policy.ts` (~131–150); test polityki proxy.
- `npm run openapi:generate`, wrapper w `packages/admin-api-client/src/index.ts`, test żądań klienta, wpis w `services/api/tests/test_openapi_contract.py`.

## Out of scope

- UI (TASK-0948), zmiany logiki cofania.

## Acceptance criteria

- [ ] Trzy trasy w OpenAPI i kliencie; `npm run openapi:check` zielone.
- [ ] Testy API: lista (kolejność, limit ≤ 50, `revertable`/powód), podgląd bez zapisu, cofnięcie, powtórzenie z kluczem, każdy 409 mapowany na kod.
- [ ] Proxy Reviewera przepuszcza wyłącznie te trzy trasy z właściwymi metodami.

## Expected files

- Nowe (proponowane): `services/api/src/game_predictor_api/api/geometry_correction_reverts.py`, `services/api/src/game_predictor_api/schemas/geometry_correction_reverts.py`, `services/api/tests/test_geometry_correction_revert_api.py`.
- Zmieniane: rejestracja routerów, `security/local_admin.py`, `apps/reviewer/src/security/reviewer-proxy-policy.ts`, `packages/admin-api-client/openapi/openapi.json`, wygenerowany klient, `packages/admin-api-client/src/index.ts`, testy klienta i OpenAPI.

## Test cases

- Lista pustego importu → `[]`; lista z korektą zablokowaną → `revertable = false` i kod.
- `POST revert` z nieaktualnym CAS → 409 `GEOMETRY_REVERT_STALE`.
- Proxy: `DELETE` lub inna ścieżka → odrzucone.

## Verification

```powershell
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/test_geometry_correction_revert_api.py services/api/tests/test_openapi_contract.py -q
npm run openapi:check
npm run test --workspace @game-predictor/admin-api-client
npm run test --workspace @game-predictor/reviewer
npm run python:lint
npm run python:typecheck
```

## Risks / open questions

- Brak.

## Outcome

Wypełnia agent po pracy.
