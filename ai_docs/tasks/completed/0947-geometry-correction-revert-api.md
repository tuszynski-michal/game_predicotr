# TASK-0947 — API listy, podglądu i cofnięcia korekt geometrii

## Status

`done`

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

Wykonawca: claude-sonnet-5-5 (medium), 2026-10-09. Bez commita (commit i audyt należą do leada).

### Changed

- Router `api/geometry_correction_reverts.py` (`create_geometry_correction_reverts_router`) i schematy `schemas/geometry_correction_reverts.py`: `listGeometryCorrections` (GET, `limit` 1-50, domyślnie 20, odpowiedź `{items}`), `previewGeometryCorrectionRevert` (GET `.../{boardGeometryRevisionId}/revert-preview`, bez zapisu, zwraca też tokeny CAS), `revertGeometryCorrection` (POST `.../revert`, body `{idempotencyKey, expectedGeometryRevision, expectedResolutionRevision}`). Każdy handler wykonuje się w `game_storage_scope(game_id)` (D-442; middleware binduje scope także z ścieżki, jawny scope to dodatkowe zabezpieczenie).
- Mapowanie błędów: serwis i repozytorium rzucają już `ImageReviewNotFoundError`/`ImageReviewConflictError`/`ImageReviewError` z kodem blokady i polskim komunikatem, a istniejący handler w `main.py` zwraca 404/409/422 w kopercie `ErrorResponse`; nie dodano nowego handlera ani zmian w logice serwisu.
- Aktor: konwencja trasy odroczonej geometrii (`board_cell_geometry_pending`): `reviewer-session:{id}` z autoryzacją scope'u `gameId + importJobId` dla bearer sesji Reviewera, inaczej `local-admin`.
- Okablowanie: `main.py` (`geometry_correction_revert_service_dependency`, domyślna zależność z `SqlAlchemyGeometryCorrectionRevertRepository` i `VirtualRestoredRenderVerifier(resolved_settings.artifact_root)`; dodana do `custom_service_dependency_supplied`), `api/router.py` (parametr keyword-only i rejestracja).
- Allowlisty: `security/local_admin.py` (wzorzec `_REVIEWER_MUTATION_PATTERNS` dla `POST .../geometry-corrections/*/revert`), `apps/reviewer/src/security/reviewer-proxy-policy.ts` (GET lista, GET revert-preview, POST revert) + test polityki (inne metody i ścieżki odrzucone).
- OpenAPI i klient: `packages/admin-api-client/openapi/openapi.json`, `src/generated/*` (tylko index/sdk/types zmienione treściowo), wrappery `listGeometryCorrections`, `previewGeometryCorrectionRevert`, `revertGeometryCorrection` i eksport typów w `src/index.ts`, test żądań w `test/client.test.mjs`.
- Testy: `services/api/tests/test_geometry_correction_revert_api.py` (nowy), `test_openapi_contract.py` (nowy test mapowania), `test_local_admin_security.py` (Origin Reviewera dla revert).
- Dokumentacja: `API_CONTRACT.md`, `CODE_MAP.md`, `CODE_MAP_SYMBOLS.md` (regeneracja).

### Verification results

- `..\..\.venv\Scripts\python.exe -m pytest services/api/tests/test_geometry_correction_revert_api.py services/api/tests/test_local_admin_security.py -q` -> 27 passed.
- `... -m pytest services/api/tests/test_openapi_contract.py -q` -> 18 passed.
- `... scripts/export_admin_openapi.py --check` -> current; `npm run check:generated --workspace @game-predictor/admin-api-client` -> current. Diff OpenAPI zawiera wyłącznie 3 nowe ścieżki i 7 nowych schematów (porównanie JSON ze stanem HEAD).
- `npm run test --workspace @game-predictor/admin-api-client` -> 106 pass, 0 fail; `npm run typecheck --workspace @game-predictor/admin-api-client` -> bez błędów.
- `npm run test --workspace @game-predictor/reviewer` -> 241 pass, 0 fail.
- `... -m ruff check services/api services/worker services/test_support scripts` -> All checks passed; `ruff format --check` nowych plików -> czysto.
- `... -m mypy services/api/src services/worker/src scripts` -> Success: no issues found in 864 source files.
- `npx prettier --check` zmienionych plików TS/MJS -> czysto.
- `python scripts/generate_code_map.py` wykonane.

### Not completed

- Brak testów PostgreSQL dla warstwy HTTP (testy API używają repozytorium w pamięci i prawdziwego serwisu; reguły i SQL pokrywają testy TASK-0945/0946). `npm run vision-lab:openapi:check` i `npm run quality` nie były uruchamiane.
- Lista zwraca obiekt `{items}` (nie goły tablicowy JSON) dla spójności z sąsiednimi trasami; przypadek testowy „pusty import -> `[]`” odpowiada `items == []`.

### Documentation updates

- `ai_docs/architecture/API_CONTRACT.md`: opis trzech tras, pól, kodów błędów, aktora i allowlisty. `CURRENT_STATE.md` i `DECISION_LOG.md` zostawione leadowi (zadanie nadal `in_progress`).

### Recommended next task

TASK-0948: sekcja „Ostatnie korekty” w Reviewerze z podglądem i potwierdzeniem na wygenerowanym kliencie.

### Zamknięcie (lead)

- Audyt Codex `gpt-6-astra`/`medium`: REVISE, jedno P1 (brak przypadku `GEOMETRY_REVERT_RENDER_FAILED` w teście mapowania 409). Lead dopisał przypadek z kontrolą `code` i `message` (`test_stale_cas_history_incomplete_and_renderer_errors_map_to_409`); `pytest services/api/tests/test_geometry_correction_revert_api.py` → 21 passed, ruff czysty. Ponowny audyt pominięty (zmiana wyłącznie testu).
- Commit: v1.7.293 / cbf0d588803f20ccfc2a732b7350b2c5c4ff3ff0.
